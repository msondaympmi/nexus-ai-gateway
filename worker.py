import logging
from datetime import datetime, timezone

from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal
from models import NexusApp, NexusJob, NexusUsageLog
from webhook_dispatcher import dispatch_webhook
from redis_pool import get_arq_redis_settings

# Configure worker logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.worker")


async def process_async_job(ctx, job_id: str) -> str:
    """
    Core arq background task to process asynchronous OCR/Summarization requests.
    Fix #6:  Calls real AI service functions (not stubs).
    Fix #10: Uses job.webhook_url with correct signing via dispatch_webhook.
    Fix #22: Uses timezone-aware datetime.now(timezone.utc).
    """
    logger.info(f"Starting background Job {job_id}")

    async with AsyncSessionLocal() as session:
        # 1. Load Job from DB
        stmt = select(NexusJob).where(NexusJob.id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            logger.error(f"Job {job_id} not found in database!")
            return "failed: job_not_found"

        # 2. Update status to 'processing'
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)  # Fix #22
        await session.commit()

        try:
            result_data = {}
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            cost_usd = 0.0
            model_name = "gemini-1.5-flash"

            payload = job.request_payload or {}

            # Fix #6: Call the actual AI service modules (not fake stubs)
            if job.endpoint == "/v1/ai/ocr":
                from modules.ocr.schemas import OcrRequest
                from modules.ocr.service import execute_ocr

                ocr_request = OcrRequest(**payload)
                # Load the app object for service calls
                stmt_app = select(NexusApp).where(NexusApp.id == job.app_id)
                res_app = await session.execute(stmt_app)
                app_obj = res_app.scalar_one_or_none()

                ocr_response = await execute_ocr(
                    request=ocr_request,
                    app=app_obj,
                    db=session
                )
                result_data = ocr_response.model_dump()
                prompt_tokens = ocr_response.usage.prompt_tokens
                completion_tokens = ocr_response.usage.completion_tokens
                total_tokens = ocr_response.usage.total_tokens
                cost_usd = float(ocr_response.cost_usd)
                model_name = ocr_request.model

            elif job.endpoint == "/v1/ai/summarize":
                from modules.summarize.schemas import SummarizeRequest
                from modules.summarize.service import execute_summarize

                sum_request = SummarizeRequest(**payload)
                stmt_app = select(NexusApp).where(NexusApp.id == job.app_id)
                res_app = await session.execute(stmt_app)
                app_obj = res_app.scalar_one_or_none()

                sum_response = await execute_summarize(
                    request=sum_request,
                    app=app_obj,
                    db=session
                )
                result_data = sum_response.model_dump()
                prompt_tokens = sum_response.usage.prompt_tokens
                completion_tokens = sum_response.usage.completion_tokens
                total_tokens = sum_response.usage.total_tokens
                cost_usd = float(sum_response.cost_usd)
                model_name = sum_request.model

            else:
                raise ValueError(f"Unknown job endpoint: {job.endpoint}")

            # 3. Save successful result
            job.status = "done"
            job.result_payload = result_data
            job.completed_at = datetime.now(timezone.utc)  # Fix #22
            job.cost_usd = cost_usd
            await session.commit()

            # Calculate latency
            end_time = datetime.now(timezone.utc)
            latency_ms = int((end_time - job.started_at).total_seconds() * 1000) if job.started_at else None

            # 4. Dispatch Webhook Callback if registered
            if job.webhook_url:
                stmt_app = select(NexusApp).where(NexusApp.id == job.app_id)
                res_app = await session.execute(stmt_app)
                app_obj = res_app.scalar_one_or_none()

                webhook_secret = getattr(app_obj, "webhook_secret", None) if app_obj else None

                job.webhook_attempts += 1
                webhook_sent = await dispatch_webhook(
                    url=job.webhook_url,
                    app_id=job.app_id,
                    app_name=job.app_name,
                    encrypted_secret=webhook_secret,
                    event_type="job.completed",
                    job_id=job.id,
                    endpoint=job.endpoint,
                    caller_user_id=job.caller_user_id,
                    latency_ms=latency_ms,
                    result_payload=result_data
                )
                job.webhook_status = "sent" if webhook_sent else "failed"
                await session.commit()

            return "done"

        except Exception as e:
            logger.error(f"Job {job_id} failed with exception: {e}", exc_info=True)

            end_time = datetime.now(timezone.utc)
            latency_ms = int((end_time - job.started_at).total_seconds() * 1000) if job.started_at else None

            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = end_time  # Fix #22
            await session.commit()

            # Dispatch Failure Webhook
            if job.webhook_url:
                job.webhook_attempts += 1
                webhook_sent = await dispatch_webhook(
                    url=job.webhook_url,
                    app_id=job.app_id,
                    app_name=job.app_name,
                    encrypted_secret=None,
                    event_type="job.failed",
                    job_id=job.id,
                    endpoint=job.endpoint,
                    caller_user_id=job.caller_user_id,
                    latency_ms=latency_ms,
                    result_payload={"error": "job_failed", "message": str(e)}
                )
                job.webhook_status = "sent" if webhook_sent else "failed"
                await session.commit()

            return f"failed: {e}"


# --- arq Worker Settings Class ---

class WorkerSettings:
    """arq worker configuration settings."""
    # Fix #23: Use arq RedisSettings type (not aioredis client)
    redis_settings = get_arq_redis_settings()
    functions = [process_async_job]

    # Concurrent job limit sourced from config.py (overridable via .env)
    max_jobs = settings.WORKER_MAX_JOBS
    
    # SRS §9.3: job_timeout 300s
    job_timeout = settings.JOB_TIMEOUT_SECONDS

    async def on_startup(self, ctx):
        logger.info("Background arq Worker process started. Running startup checks...")
        # SRS §9.3: Auto re-queue jobs stuck in processing for > 5 minutes
        try:
            from datetime import timedelta
            async with AsyncSessionLocal() as session:
                stuck_time = datetime.now(timezone.utc) - timedelta(minutes=5)
                # Find jobs that have been processing for more than 5 minutes
                stmt = select(NexusJob).where(
                    NexusJob.status == "processing",
                    NexusJob.started_at < stuck_time
                )
                result = await session.execute(stmt)
                stuck_jobs = result.scalars().all()
                
                if stuck_jobs:
                    logger.warning(f"Found {len(stuck_jobs)} stuck jobs. Re-queuing...")
                    for job in stuck_jobs:
                        job.status = "queued"
                        job.started_at = None
                        # Re-enqueue in arq (if we have access to the pool, or just rely on a sweeper)
                        # For now, just reset the DB status so they can be picked up
                    await session.commit()
        except Exception as e:
            logger.error(f"Error during worker startup checks: {e}")

    async def on_shutdown(self, ctx):
        logger.info("Background arq Worker process shutting down.")
