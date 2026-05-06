import secrets as secrets_mod
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from passlib.context import CryptContext

from database import get_db
from models import NexusApp, NexusAppPermission, NexusUsageLog, NexusRateLimit
from config import settings

router = APIRouter(prefix="/v1/admin", tags=["Admin"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def verify_admin_access(
    request: Request,
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")
):
    """Simple dependency to protect admin endpoints using the ADMIN_API_KEY environment variable."""
    request_id = getattr(request.state, "request_id", "unknown")
    # S-1: Timing-safe comparison to prevent side-channel attacks
    if not x_admin_key or not secrets_mod.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthorized",
                "message": "Akses admin tidak sah",
                "request_id": request_id
            }
        )


@router.post("/apps", dependencies=[Depends(verify_admin_access)])
async def create_app(
    app_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    POST /v1/admin/apps
    Registers a new client application.
    Generates a secure plaintext API key, calculates prefix and bcrypt hash, and saves to MySQL.
    """
    # 1. Generate secure plaintext API key (nexus-live-{32 random hex})
    hex_chars = secrets_mod.token_hex(16)
    plaintext_key = f"nexus-live-{hex_chars}"
    prefix = hex_chars[:4]
    
    # 2. Hash plaintext key using bcrypt
    hashed_key = pwd_context.hash(plaintext_key)

    # 3. Create database records
    app = NexusApp(
        app_name=app_name,
        api_key_prefix=prefix,
        api_key_hash=hashed_key,
        is_active=True
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    # 4. Populate default permissions (all allowed by default)
    modules = ["chat", "ocr", "summarize", "knowledge"]
    for mod in modules:
        perm = NexusAppPermission(app_id=app.id, module_name=mod, is_allowed=True)
        db.add(perm)
    
    # A-3: Seed default rate limits for ALL module endpoints (not just chat)
    for endpoint in ["/v1/ai/chat", "/v1/ai/ocr", "/v1/ai/summarize", "/v1/ai/knowledge"]:
        limit = NexusRateLimit(
            app_id=app.id,
            endpoint=endpoint,
            max_requests_per_minute=settings.DEFAULT_RPM,
            max_requests_per_day=settings.DEFAULT_RPD
        )
        db.add(limit)
    await db.commit()

    return {
        "status": "created",
        "app_id": app.id,
        "app_name": app.app_name,
        "api_key_prefix": prefix,
        # Display the plaintext API key EXACTLY ONCE (Section 7.1 instruction)
        "plaintext_api_key": plaintext_key,
        "warning": "Simpan API key ini dengan aman. Kunci plaintext tidak akan dapat ditampilkan lagi!"
    }


@router.get("/apps", dependencies=[Depends(verify_admin_access)])
async def list_apps(db: AsyncSession = Depends(get_db)):
    """GET /v1/admin/apps - Lists all registered client applications."""
    stmt = select(NexusApp)
    result = await db.execute(stmt)
    apps = result.scalars().all()
    
    return [
        {
            "id": app.id,
            "app_name": app.app_name,
            "api_key_prefix": app.api_key_prefix,
            "is_active": app.is_active,
            "created_at": app.created_at.isoformat() if app.created_at else None
        }
        for app in apps
    ]


@router.get("/usage", dependencies=[Depends(verify_admin_access)])
async def get_usage_summary(db: AsyncSession = Depends(get_db)):
    """
    GET /v1/admin/usage
    Aggregates usage records per application, computing total tokens and total USD spent.
    Useful for centralized cost tracking and business dashboards.
    """
    stmt = (
        select(
            NexusApp.id,
            NexusApp.app_name,
            func.sum(NexusUsageLog.total_tokens).label("total_tokens"),
            func.sum(NexusUsageLog.cost_usd).label("total_cost_usd"),
            func.count(NexusUsageLog.id).label("total_requests")
        )
        .join(NexusUsageLog, NexusApp.id == NexusUsageLog.app_id)
        .group_by(NexusApp.id, NexusApp.app_name)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "app_id": row.id,
            "app_name": row.app_name,
            "total_tokens": int(row.total_tokens) if row.total_tokens else 0,
            "total_cost_usd": float(row.total_cost_usd) if row.total_cost_usd else 0.0,
            "total_requests": row.total_requests or 0
    ]


@router.post("/apps/{app_id}/rotate-key", dependencies=[Depends(verify_admin_access)])
async def rotate_key(
    app_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    POST /v1/admin/apps/{app_id}/rotate-key
    Rotates the API key for an app.
    Generates a new secure plaintext API key, updates the bcrypt hash in DB, 
    and clears the Redis cache.
    """
    from redis_pool import get_redis
    
    stmt = select(NexusApp).where(NexusApp.id == app_id)
    result = await db.execute(stmt)
    app = result.scalar_one_or_none()
    
    if not app:
        raise HTTPException(status_code=404, detail="App tidak ditemukan")

    # Clear old cache
    redis_client = get_redis()
    old_cache_key = f"auth_cache:{app.api_key_prefix}"
    await redis_client.delete(old_cache_key)

    # Generate new key
    hex_chars = secrets_mod.token_hex(16)
    plaintext_key = f"nexus-live-{hex_chars}"
    new_prefix = hex_chars[:4]
    
    hashed_key = pwd_context.hash(plaintext_key)

    app.api_key_prefix = new_prefix
    app.api_key_hash = hashed_key
    await db.commit()

    return {
        "status": "rotated",
        "app_id": app.id,
        "app_name": app.app_name,
        "new_api_key_prefix": new_prefix,
        "new_plaintext_api_key": plaintext_key,
        "warning": "Simpan API key ini dengan aman. Kunci plaintext tidak akan dapat ditampilkan lagi!"
    }
