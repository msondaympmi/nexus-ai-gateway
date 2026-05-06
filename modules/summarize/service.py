import time
import logging
import litellm
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings, load_module_settings
from models import NexusApp, NexusUsageLog
from modules.chat.service import calculate_llm_cost
from modules.summarize.schemas import SummarizeRequest, SummarizeResponse, Usage

logger = logging.getLogger("nexus.summarize_service")

# Configure LiteLLM options
litellm.api_base = settings.LITELLM_API_BASE

# Load module-specific settings
sum_settings = load_module_settings("summarize")
SUM_TEMPERATURE = sum_settings.get("temperature", 0.3)
SUM_DEFAULT_MODEL = sum_settings.get("default_model", "gemini-1.5-flash")
SUM_MAX_CHAR_LENGTH = sum_settings.get("max_character_length", 100000)
SUM_DEFAULT_LENGTH = sum_settings.get("default_length", "medium")


# Retry params sourced from config.py (overridable via .env)
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


async def execute_summarize(
    request: SummarizeRequest,
    app: NexusApp,
    db: AsyncSession,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None
) -> SummarizeResponse:
    """
    Executes a synchronous text summarization request via LiteLLM Proxy.
    Instructs the LLM based on requested length, tracks tokens, and logs costs to MySQL.
    """
    start_time = time.time()
    original_len = len(request.text)

    # 1. Format target instructions based on style
    style_instructions = {
        "bullet": "Gunakan format poin-poin (bullet points).",
        "paragraph": "Gunakan format paragraf naratif.",
        "executive": "Buat ringkasan eksekutif tingkat tinggi (high-level executive summary)."
    }
    instruction = style_instructions.get(request.style, style_instructions["paragraph"])

    sys_prompt = f"Anda adalah asisten perangkum teks ahli. {instruction} Gunakan bahasa {request.language}."
    if request.max_length:
        sys_prompt += f" Usahakan ringkasan tidak lebih dari {request.max_length} kata."
    if request.focus:
        sys_prompt += f" Berikan fokus khusus pada topik berikut: '{request.focus}'."

    messages_payload = [
        {
            "role": "system",
            "content": sys_prompt
        },
        {
            "role": "user",
            "content": f"Tolong rangkum teks berikut:\n\n{request.text}"
        }
    ]

    # 2. Call LiteLLM Proxy (module-level retry decorator)
    try:
        response = await _call_llm_with_retry(
            model=request.model,
            messages=messages_payload,
            temperature=SUM_TEMPERATURE  # Sourced from summarize/settings.json
        )
    except Exception as e:
        logger.error(f"LiteLLM summarize call failed after retries: {e}", exc_info=True)
        raise RuntimeError(f"Gagal melakukan rangkuman: {str(e)}")

    # 3. Extract choices and token counts
    summary_text = response.choices[0].message.content
    
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens

    # Calculate real USD cost
    cost_usd = calculate_llm_cost(request.model, prompt_tokens, completion_tokens)

    # 4. Formulate response payload
    summary_len = len(summary_text)
    ratio = round(summary_len / original_len, 4) if original_len > 0 else 0.0

    summarize_response = SummarizeResponse(
        summary=summary_text,
        language=request.language,
        style=request.style,
        compression_ratio=ratio,
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens
        ),
        cost_usd=cost_usd
    )

    # 5. Log transaction and costs to database asynchronously (Audit Trail)
    duration_ms = int((time.time() - start_time) * 1000)
    try:
        usage_log = NexusUsageLog(
            app_id=app.id,
            user_id=user_id,
            user_name=user_name,
            endpoint="/v1/ai/summarize",
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

    return summarize_response
