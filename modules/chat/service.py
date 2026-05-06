import time
import json
import logging
import uuid
import litellm
from typing import Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings, load_module_settings
from models import NexusApp, NexusUsageLog
from modules.chat.schemas import ChatRequest, ChatResponse, Usage, ChatChoice, ChatChoiceMessage

logger = logging.getLogger("nexus.chat_service")

# Configure LiteLLM options
litellm.api_base = settings.LITELLM_API_BASE

# Load module-specific settings (Section 21.5 of SRS)
chat_settings = load_module_settings("chat")
PRICING_TABLE = chat_settings.get("pricing", {
    "gemini-1.5-pro": {"input_1m": 1.25, "output_1m": 5.00},
    "gemini-1.5-flash": {"input_1m": 0.075, "output_1m": 0.30}
})
DEFAULT_MODEL = chat_settings.get("default_model", "gemini-1.5-pro")
DEFAULT_TEMPERATURE = chat_settings.get("default_temperature", 0.7)
CLAMPED_MAX_TOKENS = chat_settings.get("clamped_max_tokens", 4096)
MAX_MESSAGES_LIMIT = chat_settings.get("max_messages_limit", 50)


# Module-level retry decorator — params sourced from config.py (overridable via .env)
@retry(
    stop=stop_after_attempt(settings.LLM_MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=settings.LLM_RETRY_MULTIPLIER,
        min=settings.LLM_RETRY_WAIT_MIN_SEC,
        max=settings.LLM_RETRY_WAIT_MAX_SEC
    ),
    retry=retry_if_exception_type((litellm.exceptions.RateLimitError, litellm.exceptions.ServiceUnavailableError)),
    reraise=True
)
async def _call_llm_with_retry(**kwargs):
    """Module-level LiteLLM caller with exponential backoff retry (Section 17.3.1)."""
    return await litellm.acompletion(**kwargs)


def calculate_llm_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculates the real cost of a model transaction in USD based on input and output token rates."""
    pricing = PRICING_TABLE.get(model, PRICING_TABLE["gemini-1.5-flash"])
    cost_input = (prompt_tokens / 1_000_000) * pricing["input_1m"]
    cost_output = (completion_tokens / 1_000_000) * pricing["output_1m"]
    return cost_input + cost_output


async def mock_retrieve_rag_context(app_id: int, query: str) -> str:
    """
    Simulates retrieval of context from GCP Firestore Vector Search with strict tenant isolation.
    (Will be replaced by direct Firestore vector queries in modules/knowledge/service.py)
    """
    logger.info(f"Querying Firestore Knowledge Base for App {app_id} with query: '{query}'")
    return (
        f"[DOKUMEN KLAIM PANDUAN MPM - APP {app_id}]\n"
        "1. Klaim kendaraan roda empat wajib menyertakan foto kerusakan bagian depan dan samping.\n"
        "2. Batas waktu pelaporan klaim adalah 3x24 jam sejak waktu kejadian perkara."
    )


async def execute_chat_completion(
    request: ChatRequest,
    app: NexusApp,
    db: AsyncSession,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None
) -> Union[ChatResponse, StreamingResponse]:
    """
    Executes a chat completion request via LiteLLM Proxy.
    Injects RAG context if requested, tracks token counts, and logs costs to MySQL.
    Supports SSE streaming when request.stream=True.
    """
    start_time = time.time()
    chat_id = f"chatcmpl-{uuid.uuid4()}"

    messages_payload = [msg.model_dump(exclude_none=True) for msg in request.messages]

    # §8.4: Inject system_prompt and/or document_context as system messages (simple RAG)
    if request.system_prompt or request.document_context:
        injected_content = ""
        if request.system_prompt:
            injected_content += request.system_prompt + "\n"
        if request.document_context:
            injected_content += f"Gunakan dokumen referensi berikut untuk menjawab pertanyaan pengguna:\n{request.document_context}"
        messages_payload.insert(0, {"role": "system", "content": injected_content.strip()})

    # 1. Inject RAG context from Firestore if use_rag is True
    if request.use_rag:
        user_query = messages_payload[-1]["content"] if messages_payload else ""
        context = await mock_retrieve_rag_context(app.id, user_query)
        system_rag_prompt = {
            "role": "system",
            "content": (
                "Anda adalah asisten asuransi MPM yang cerdas.\n"
                f"Gunakan dokumen referensi berikut untuk menjawab pertanyaan pengguna:\n{context}"
            )
        }
        messages_payload.insert(0, system_rag_prompt)

    # 2a. Handle streaming (SSE) response path
    if request.stream:
        async def event_generator():
            try:
                response_stream = await _call_llm_with_retry(
                    model=request.model,
                    messages=messages_payload,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    tools=request.tools,
                    tool_choice=request.tool_choice,
                    stream=True
                )
                index = 0
                async for chunk in response_stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        yield f'data: {json.dumps({"chunk": content, "index": index})}\n\n'
                        index += 1
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f'data: {json.dumps({"error": str(e)})}\n\n'

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # 2b. Standard synchronous response path
    try:
        response = await _call_llm_with_retry(
            model=request.model,
            messages=messages_payload,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            tools=request.tools,
            tool_choice=request.tool_choice
        )
    except Exception as e:
        logger.error(f"LiteLLM completion call failed after retries: {e}", exc_info=True)
        raise RuntimeError(f"Gagal memanggil layanan AI: {str(e)}")

    # 3. Extract completion choices and tokens
    choice_obj = response.choices[0]
    message_obj = choice_obj.message

    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens

    cost_usd = calculate_llm_cost(request.model, prompt_tokens, completion_tokens)

    # Convert LiteLLM tool_calls if present
    tool_calls = None
    if hasattr(message_obj, "tool_calls") and message_obj.tool_calls:
        tool_calls = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            }
            for tc in message_obj.tool_calls
        ]

    # 4. Formulate the standardized response payload
    chat_response = ChatResponse(
        id=chat_id,
        created=int(start_time),
        model=request.model,
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens
        ),
        choices=[
            ChatChoice(
                index=0,
                message=ChatChoiceMessage(
                    role="assistant",
                    content=message_obj.content,
                    tool_calls=tool_calls
                ),
                finish_reason=choice_obj.finish_reason or "stop"
            )
        ],
        cost_usd=cost_usd
    )

    # 5. Log transaction and costs to database (Audit Trail)
    duration_ms = int((time.time() - start_time) * 1000)
    try:
        usage_log = NexusUsageLog(
            app_id=app.id,
            user_id=user_id,
            user_name=user_name,
            endpoint="/v1/ai/chat",
            model_name=request.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=duration_ms,
            status_code=200
        )
        db.add(usage_log)
        await db.commit()
    except Exception as db_err:
        logger.error(f"Failed to write usage log to database: {db_err}")
        await db.rollback()

    return chat_response
