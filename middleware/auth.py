import asyncio
import logging
import hashlib
from typing import Optional

from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from passlib.context import CryptContext

from config import settings
from database import get_db
from models import NexusApp, NexusAppPermission
from redis_pool import get_redis

logger = logging.getLogger("nexus.auth")

# Password/API Key hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer security scheme
security_scheme = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    """Helper to generate a SHA256 hash of a token for Redis cache key safety."""
    return hashlib.sha256(token.encode()).hexdigest()


async def verify_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: AsyncSession = Depends(get_db)
) -> NexusApp:
    """
    Dependency to authenticate incoming machine-to-machine requests.
    Extracts the API Key from the Bearer token, checks Redis cache,
    compares bcrypt hashes in a thread pool (Fix #9) if cache miss,
    and loads permissions.
    """
    request_id = str(request.state.request_id) if hasattr(request.state, "request_id") else "unknown"

    token = None
    if credentials:
        token = credentials.credentials
    else:
        # Fallback to direct X-API-Key header if provided
        token = request.headers.get("X-API-Key")

    if not token or not token.startswith("nexus-live-"):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "API key tidak valid atau tidak disertakan",
                "request_id": request_id
            }
        )

    # 1. Check Redis Cache for pre-authenticated key hashes (Fix #8: use shared pool)
    redis_client = get_redis()
    token_hash = hash_token(token)
    cache_key = f"auth_cache:{token_hash}"
    cached_app_id = await redis_client.get(cache_key)

    if cached_app_id:
        # Cache hit! Load app with permissions
        stmt = (
            select(NexusApp)
            .where(NexusApp.id == int(cached_app_id), NexusApp.is_active == True)
            .options(selectinload(NexusApp.permissions))
        )
        result = await db.execute(stmt)
        app = result.scalar_one_or_none()
        if app:
            return app

    # 2. Cache miss: Extract prefix for fast SQL lookup
    # Token structure: nexus-live-{32 hex chars}. Prefix is first 4 chars of the hex part.
    token_hex_part = token.replace("nexus-live-", "")
    if len(token_hex_part) < 4:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "API key format salah",
                "request_id": request_id
            }
        )
    prefix = token_hex_part[:4]

    # Look up active apps with this prefix
    stmt = (
        select(NexusApp)
        .where(NexusApp.api_key_prefix == prefix, NexusApp.is_active == True)
        .options(selectinload(NexusApp.permissions))
    )
    result = await db.execute(stmt)
    apps = result.scalars().all()

    # Fix #9: Run bcrypt verify in a thread pool so it doesn't block the async event loop
    loop = asyncio.get_event_loop()
    authenticated_app = None
    for app in apps:
        is_match = await loop.run_in_executor(None, pwd_context.verify, token, app.api_key_hash)
        if is_match:
            authenticated_app = app
            break

    if not authenticated_app:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "API key tidak valid atau tidak aktif",
                "request_id": request_id
            }
        )

    # Cache the successful authentication (TTL from config.py, default 300s)
    await redis_client.setex(cache_key, settings.AUTH_CACHE_TTL_SEC, str(authenticated_app.id))
    return authenticated_app


def require_permission(module_name: str):
    """
    Dependency factory to check if the authenticated app has permissions for a specific module.
    Usage: Depends(require_permission("chat"))
    """
    async def permission_dependency(app: NexusApp = Depends(verify_api_key), request: Request = None) -> NexusApp:
        request_id = str(request.state.request_id) if request and hasattr(request.state, "request_id") else "unknown"

        # Bypassed if superadmin key
        if app.app_name == "SuperAdmin":
            return app

        # Check if module permission is allowed
        has_permission = any(
            perm.module_name == module_name and perm.is_allowed
            for perm in app.permissions
        )

        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "forbidden",
                    "message": f"Aplikasi tidak memiliki izin untuk modul: {module_name}",
                    "request_id": request_id
                }
            )
        return app
    return permission_dependency
