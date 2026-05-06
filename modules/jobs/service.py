import logging
from datetime import datetime, timezone
from typing import Optional

from arq import create_pool
from sqlalchemy.ext.asyncio import AsyncSession

from models import NexusJob
from redis_pool import get_arq_redis_settings

logger = logging.getLogger("nexus.jobs_service")

# C-2: Module-level arq pool singleton — avoid creating/tearing down a TCP connection per enqueue
_arq_pool = None


async def _get_arq_pool():
    """Lazily create and cache a module-level arq connection pool."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(get_arq_redis_settings())
    return _arq_pool


async def enqueue_async_job(
    app_id: int,
    endpoint: str,
    request_payload: dict,
    webhook_url: Optional[str],
    db: AsyncSession
) -> dict:
    """
    Utility function to create an async job in MySQL and push it to the Redis arq queue.
    Returns the standard 202 JSON response with job_id and poll_url.
    """
    # 1. Create Job object in MySQL (status: queued)
    job = NexusJob(
        app_id=app_id,
        endpoint=endpoint,
        request_payload=request_payload,
        webhook_url=webhook_url,
        status="queued",
        queued_at=datetime.now(timezone.utc)
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    job_id = job.id
    logger.info(f"Created Job {job_id} in MySQL with status 'queued' for App {app_id} on {endpoint}")

    # 2. Push job payload to Redis arq queue (reuses module-level pool)
    try:
        pool = await _get_arq_pool()
        await pool.enqueue_job("process_async_job", job_id)
        logger.info(f"Enqueued Job {job_id} into arq queue.")
    except Exception as redis_err:
        logger.error(f"Failed to enqueue Job {job_id} in Redis: {redis_err}")
        job.status = "failed"
        job.error_message = f"Queue system unreachable: {str(redis_err)}"
        await db.commit()
        raise RuntimeError("Sistem antrean tidak dapat dijangkau")

    poll_url = f"/v1/ai/jobs/{job_id}"
    return {
        "job_id": job_id,
        "status": "queued",
        "poll_url": poll_url
    }
