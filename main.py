import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import structlog

from config import settings
from database import engine
from redis_pool import init_redis, close_redis
from modules.chat.router import router as chat_router
from modules.ocr.router import router as ocr_router
from modules.summarize.router import router as summarize_router
from modules.knowledge.router import router as knowledge_router
from modules.jobs.router import router as jobs_router
from modules.admin.router import router as admin_router

# Configure Structured JSON Logging using structlog
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger("nexus.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown event handling."""
    logger.info("Starting Nexus AI Gateway", environment=settings.ENVIRONMENT, debug=settings.DEBUG)
    # Fix #8: Initialize the shared Redis pool once at startup
    await init_redis()
    yield
    # Fix #8: Cleanly close Redis pool on shutdown
    await close_redis()
    logger.info("Shutting down Nexus AI Gateway")
    await engine.dispose()


app = FastAPI(
    title="Nexus AI Gateway",
    description="Central M2M AI Services Platform for MPM Insurance",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

# Fix #21: Restrict CORS to internal service origins only (not wildcard)
# For an M2M gateway, browser CORS should be locked down.
INTERNAL_ORIGINS = [
    "http://localhost",
    "http://localhost:8100",
    "http://localhost:8501",   # Streamlit admin dashboard
    "http://127.0.0.1:8100",
    "http://127.0.0.1:8501",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=INTERNAL_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "X-API-Key", "X-Response-Mode", "X-Callback-Url", "X-User-Id", "X-User-Name", "Content-Type"],
)


@app.middleware("http")
async def add_request_id_and_latency(request: Request, call_next):
    """
    HTTP Middleware to:
    1. Generate and inject a unique Request-ID for centralized tracing.
    2. Track and log execution latency.
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start_time) * 1000)
    
    # Set headers in response for downstream debugging
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    
    logger.info(
        "HTTP Request Processed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        latency_ms=duration_ms,
        request_id=request_id
    )
    return response


# --- Standardized Error Handling (Section 17.2) ---

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom exception handler for standard HTTP Exceptions, formatting as structured JSON."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    error_content = {
        "error": "http_error",
        "message": exc.detail,
        "request_id": request_id
    }
    
    # Handle dict details directly (like from verify_api_key or rate limiters)
    if isinstance(exc.detail, dict):
        error_content = exc.detail
        if "request_id" not in error_content:
            error_content["request_id"] = request_id

    return JSONResponse(
        status_code=exc.status_code,
        content=error_content
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Fallback handler for unhandled internal exceptions, masking sensitive errors."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error("Unhandled server exception", error=str(exc), request_id=request_id, exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "Terjadi kesalahan internal pada server",
            "request_id": request_id
        }
    )


# --- Register All Modular Routers ---
app.include_router(chat_router)
app.include_router(ocr_router)
app.include_router(summarize_router)
app.include_router(knowledge_router)
app.include_router(jobs_router)
app.include_router(admin_router)


@app.get("/health/liveness", tags=["Health"])
async def health_liveness():
    """Liveness probe: Returns 200 OK if the FastAPI process is running."""
    return {"status": "ok"}


@app.get("/health/readiness", tags=["Health"])
async def health_readiness():
    """Readiness probe: Actually pings DB and Redis to verify connectivity."""
    from redis_pool import get_redis
    from database import AsyncSessionLocal
    from sqlalchemy import text

    components = {}

    # Check Redis
    try:
        redis_client = get_redis()
        await redis_client.ping()
        components["redis"] = "ok"
    except Exception:
        components["redis"] = "error"

    # Check Database
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception:
        components["database"] = "error"

    # Check LiteLLM (basic connectivity — not a full model call)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.LITELLM_API_BASE}/health")
            components["litellm"] = "ok" if resp.status_code == 200 else "degraded"
    except Exception:
        components["litellm"] = "unreachable"

    overall = "ok" if all(v == "ok" for v in components.values()) else "degraded"
    status_code = 200 if overall == "ok" else 503

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "version": "1.0.0",
            "components": components
        }
    )
