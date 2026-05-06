import time
import logging
from datetime import datetime, timezone
from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from database import get_db
from models import NexusApp, NexusRateLimit
from middleware.auth import verify_api_key
from redis_pool import get_redis

logger = logging.getLogger("nexus.rate_limiter")


async def get_app_rate_limits(app_id: int, endpoint: str, db: AsyncSession) -> tuple[int, int]:
    """
    Get the configured rate limits for an app and endpoint.
    Caches the limits in Redis for 600 seconds to prevent constant DB lookups.
    """
    redis_client = get_redis()
    cache_key = f"rate_limit_config:{app_id}:{endpoint}"
    cached_data = await redis_client.get(cache_key)

    if cached_data:
        parts = cached_data.split(":")
        return int(parts[0]), int(parts[1])

    # Cache miss: load from DB
    stmt = (
        select(NexusRateLimit)
        .where(NexusRateLimit.app_id == app_id, NexusRateLimit.endpoint == endpoint)
    )
    result = await db.execute(stmt)
    limit_obj = result.scalar_one_or_none()

    # Defaults from config.py (overridable via .env)
    rpm = limit_obj.max_requests_per_minute if limit_obj else settings.DEFAULT_RPM
    rpd = limit_obj.max_requests_per_day if limit_obj else settings.DEFAULT_RPD

    # Cache the configuration (sourced from settings)
    await redis_client.setex(cache_key, settings.RATE_LIMIT_CONFIG_CACHE_TTL_SEC, f"{rpm}:{rpd}")
    return rpm, rpd


async def check_rate_limits(
    request: Request,
    app: NexusApp = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db)
) -> NexusApp:
    """
    FastAPI dependency that enforces:
    1. Sliding Window Request Rate Limiting per minute and per day using Redis Sorted Sets.
    2. Hourly Cumulative Token Rate Limiting (Infinite Loop Prevention Guardrail).
    Returns the authenticated NexusApp — inject this once in the router (Fix #12).
    """
    request_id = str(request.state.request_id) if hasattr(request.state, "request_id") else "unknown"
    redis_client = get_redis()

    # Superadmin bypasses rate limiting
    if app.app_name == "SuperAdmin":
        return app

    app_id = app.id
    endpoint = request.url.path
    now = time.time()

    # --- 1. Hourly Cumulative Token Rate Limiting (Infinite Loop Prevention) ---
    # Fix #22: use timezone-aware utc
    current_hour_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
    token_budget_key = f"nexus:token_limit:{app_id}:{current_hour_str}"
    accumulated_tokens_str = await redis_client.get(token_budget_key)
    accumulated_tokens = int(accumulated_tokens_str) if accumulated_tokens_str else 0

    # TOKEN_HOURLY_LIMIT from config.py (overridable via .env, default 10M)
    if accumulated_tokens >= settings.TOKEN_HOURLY_LIMIT:
        logger.warning(f"App {app_id} hit Hourly Cumulative Token Limit (Loop Prevention) on {endpoint}!")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Batas akumulasi token per jam terlampaui (pencegahan infinite loop)",
                "request_id": request_id
            }
        )

    # --- 2. Sliding Window Request Rate Limiting ---
    rpm, rpd = await get_app_rate_limits(app_id, endpoint, db)

    # Minute key and Day key
    minute_key = f"rate_limit:minute:{app_id}:{endpoint}"
    day_key = f"rate_limit:day:{app_id}:{endpoint}"

    # Fix #15: ZADD first, then ZCARD so the count is post-insertion (no off-by-one)
    async with redis_client.pipeline(transaction=True) as pipe:
        # A. Minute Limit (Sliding Window of 60s)
        one_minute_ago = now - 60
        pipe.zremrangebyscore(minute_key, 0, one_minute_ago)
        pipe.zadd(minute_key, {str(now): now})   # add FIRST
        pipe.zcard(minute_key)                   # count AFTER add
        pipe.expire(minute_key, 65)

        # B. Day Limit (Sliding Window of 86400s)
        one_day_ago = now - 86400
        pipe.zremrangebyscore(day_key, 0, one_day_ago)
        pipe.zadd(day_key, {str(now): now})      # add FIRST
        pipe.zcard(day_key)                      # count AFTER add
        pipe.expire(day_key, 86450)

        results = await pipe.execute()

        # Results: [zremrange, zadd, zcard, expire, zremrange, zadd, zcard, expire]
        current_minute_requests = results[2]
        current_day_requests = results[6]

    # C. Validate limits
    if current_minute_requests > rpm:
        logger.warning(f"App {app_id} rate limited: {current_minute_requests}/{rpm} requests/min on {endpoint}")
        retry_after = 60 - (int(now) % 60)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Batas pemanggilan per menit terlampaui ({rpm} req/min)",
                "retry_after_seconds": retry_after,
                "request_id": request_id
            }
        )

    if current_day_requests > rpd:
        logger.warning(f"App {app_id} rate limited: {current_day_requests}/{rpd} requests/day on {endpoint}")
        retry_after = 86400 - (int(now) % 86400)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Batas pemanggilan per hari terlampaui ({rpd} req/day)",
                "retry_after_seconds": retry_after,
                "request_id": request_id
            }
        )

    return app
