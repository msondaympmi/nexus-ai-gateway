import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings

logger = logging.getLogger("nexus.database")

# Initialize SQLAlchemy Async Engine with connection pooling (Q-1: params from config.py)
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_POOL_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE_SEC,
    pool_pre_ping=True,
    echo=settings.DEBUG and settings.ENVIRONMENT == "development"
)

# Initialize Sessionmaker factory bound to the async engine
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


# FastAPI dependency injection helper for transactional database sessions
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Asynchronous generator yielding scoped SQLAlchemy DB sessions.
    Automatically closes the session once execution context exits.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session encountered error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
