import time
import logging
import litellm
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings, load_module_settings
from models import NexusApp, NexusUsageLog
from modules.chat.service import calculate_llm_cost
from modules.ocr.schemas import OcrRequest, OcrResponse, Usage

logger = logging.getLogger("nexus.ocr_service")

# Configure LiteLLM options
litellm.api_base = settings.LITELLM_API_BASE

# Load module-specific settings
ocr_settings = load_module_settings("ocr")
OCR_TEMPERATURE = ocr_settings.get("temperature", 0.1)
OCR_CONFIDENCE_DEFAULT = ocr_settings.get("confidence_default", 0.99)
OCR_DEFAULT_MODEL = ocr_settings.get("default_model", "gemini-1.5-flash")


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


async def execute_ocr(
    request: OcrRequest,
    app: NexusApp,
    db: AsyncSession,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None
) -> OcrResponse:
    """
    Executes a synchronous OCR extraction request via LiteLLM Proxy.
    Sends the target file_url to the multimodal LLM (Gemini), extracts text, tracks tokens and costs.
    """
    start_time = time.time()

    # 1. Structure the multimodal message payload with image URL (Section 8.5)
    prompt_instruction = "Tolong ekstrak seluruh teks dari gambar atau dokumen berikut secara akurat tanpa menambahkan penjelasan apapun."
    if request.output_format == "json" and request.extraction_schema:
        prompt_instruction = f"Tolong ekstrak informasi dari gambar berikut ke dalam format JSON yang valid sesuai schema berikut:\n{request.extraction_schema}"
    elif request.output_format == "markdown":
        prompt_instruction = "Tolong ekstrak seluruh teks dari gambar berikut ke dalam format Markdown yang rapi."

    if request.language_hint:
        prompt_instruction += f"\nHint bahasa: {request.language_hint}"

    messages_payload = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt_instruction
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": request.file_uri
                    }
                }
            ]
        }
    ]

    # 2. Call LiteLLM Proxy (module-level retry decorator)
    try:
        response = await _call_llm_with_retry(
            model=request.model,
            messages=messages_payload,
            temperature=OCR_TEMPERATURE  # Sourced from ocr/settings.json
        )
    except Exception as e:
        logger.error(f"LiteLLM OCR call failed after retries: {e}", exc_info=True)
        raise RuntimeError(f"Gagal melakukan proses OCR: {str(e)}")

    # 3. Extract text content and usage
    extracted_text = response.choices[0].message.content
    
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens

    # Calculate USD cost
    cost_usd = calculate_llm_cost(request.model, prompt_tokens, completion_tokens)

    # Extract filename from uri
    filename = request.file_uri.split("/")[-1] if "/" in request.file_uri else "document.pdf"

    # 4. Formulate response
    ocr_response = OcrResponse(
        filename=filename,
        output_format=request.output_format,
        page_count=1,  # Default for single image/doc via URI
        result=extracted_text,
        confidence_note=f"High confidence ({OCR_CONFIDENCE_DEFAULT})",
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
            endpoint="/v1/ai/ocr",
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

    return ocr_response
