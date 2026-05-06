from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import NexusApp, NexusJob
from middleware.rate_limiter import check_rate_limits

router = APIRouter(prefix="/v1/ai/jobs", tags=["Jobs"])


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    request: Request,
    app: NexusApp = Depends(check_rate_limits),
    db: AsyncSession = Depends(get_db)
):
    """
    GET /v1/ai/jobs/{job_id}
    Retrieves the status and result of an asynchronous background job.
    App-isolation: Client apps can only view their own jobs.
    """
    request_id = getattr(request.state, "request_id", "unknown")

    # 1. Load the job from MySQL
    stmt = select(NexusJob).where(NexusJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": "Job ID tidak ditemukan",
                "request_id": request_id
            }
        )

    # 2. Strict App-Isolation enforcement (Section 8.4 and Section 8.9 context)
    # SuperAdmin bypasses isolation
    if app.app_name != "SuperAdmin" and job.app_id != app.id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "message": "Anda tidak memiliki akses ke Job ID ini",
                "request_id": request_id
            }
        )

    # 3. Format response dynamically based on status (Section 9.2 guidelines)
    response_data = {
        "job_id": job.id,
        "status": job.status,
        "endpoint": job.endpoint,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
    }

    if job.status == "queued":
        # Estimate wait times (mock metrics per queue statistics)
        response_data.update({
            "position_in_queue": 1,
            "estimated_wait_seconds": 15
        })
    elif job.status == "processing":
        response_data.update({
            "started_at": job.started_at.isoformat() if job.started_at else None
        })
    elif job.status == "done":
        latency_ms = int((job.completed_at - job.started_at).total_seconds() * 1000) if job.completed_at and job.started_at else 0
        response_data.update({
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "latency_ms": latency_ms,
            "result": job.result_payload
        })
    elif job.status == "failed":
        response_data.update({
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message or "Unknown processing error"
        })

    return response_data


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    request: Request,
    app: NexusApp = Depends(check_rate_limits),
    db: AsyncSession = Depends(get_db)
):
    """
    POST /v1/ai/jobs/{job_id}/cancel
    Cancels a queued job.
    """
    request_id = getattr(request.state, "request_id", "unknown")

    stmt = select(NexusJob).where(NexusJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Job ID tidak ditemukan", "request_id": request_id}
        )

    if app.app_name != "SuperAdmin" and job.app_id != app.id:
        raise HTTPException(
            status_code=403,
            detail={"error": "forbidden", "message": "Anda tidak memiliki akses ke Job ID ini", "request_id": request_id}
        )

    if job.status != "queued":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "cannot_cancel",
                "message": "Job sedang diproses dan tidak dapat di-cancel",
                "current_status": job.status,
                "request_id": request_id
            }
        )

    job.status = "cancelled"
    await db.commit()

    return {"job_id": job.id, "status": "cancelled", "message": "Job berhasil di-cancel"}


@router.get("")
async def list_jobs(
    request: Request,
    status: str = None,
    endpoint: str = None,
    after: str = None,
    before: str = None,
    limit: int = 20,
    offset: int = 0,
    app: NexusApp = Depends(check_rate_limits),
    db: AsyncSession = Depends(get_db)
):
    """
    GET /v1/ai/jobs
    Lists jobs for the calling app with filters and pagination.
    """
    from datetime import datetime
    
    limit = min(limit, 100)
    
    stmt = select(NexusJob)
    if app.app_name != "SuperAdmin":
        stmt = stmt.where(NexusJob.app_id == app.id)
        
    if status:
        stmt = stmt.where(NexusJob.status == status)
    if endpoint:
        stmt = stmt.where(NexusJob.endpoint == endpoint)
        
    if after:
        try:
            after_dt = datetime.fromisoformat(after.replace('Z', '+00:00'))
            stmt = stmt.where(NexusJob.queued_at >= after_dt)
        except ValueError:
            pass
    if before:
        try:
            before_dt = datetime.fromisoformat(before.replace('Z', '+00:00'))
            stmt = stmt.where(NexusJob.queued_at <= before_dt)
        except ValueError:
            pass
            
    # Count total
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Apply pagination
    stmt = stmt.order_by(NexusJob.queued_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    
    jobs_list = []
    for job in jobs:
        latency_ms = None
        if job.completed_at and job.started_at:
            latency_ms = int((job.completed_at - job.started_at).total_seconds() * 1000)
            
        jobs_list.append({
            "job_id": job.id,
            "status": job.status,
            "endpoint": job.endpoint,
            "caller_user_id": job.caller_user_id,
            "queued_at": job.queued_at.isoformat() if job.queued_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "latency_ms": latency_ms
        })
        
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "jobs": jobs_list
    }
