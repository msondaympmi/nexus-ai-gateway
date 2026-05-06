"""
Shared Redis pool module (Fix #8, #13).
Single connection pool reused across auth, rate_limiter, and job enqueueing.
Created at startup, closed at shutdown via lifespan context in main.py.
"""
import redis.asyncio as aioredis
from arq.connections import RedisSettings

from config import settings

# Single shared async Redis client for the entire app (Fix #8)
redis_pool: aioredis.Redis = None


def get_redis() -> aioredis.Redis:
    """Return the application-wide Redis client."""
    return redis_pool


def get_arq_redis_settings() -> RedisSettings:
    """Return arq-compatible Redis settings."""
    kwargs = {
        "host": settings.REDIS_HOST,
        "port": settings.REDIS_PORT,
        "database": settings.REDIS_DB,
    }
    if settings.REDIS_PASSWORD:
        kwargs["password"] = settings.REDIS_PASSWORD
    return RedisSettings(**kwargs)


async def init_redis() -> None:
    """Create the shared Redis connection pool. Called once at startup."""
    global redis_pool
    redis_pool = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=50
    )


async def close_redis() -> None:
    """Close the Redis connection pool. Called at shutdown."""
    global redis_pool
    if redis_pool:
        await redis_pool.aclose()
        redis_pool = None
