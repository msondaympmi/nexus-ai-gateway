import os
import json
import logging
import functools
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("nexus.config")


class Settings(BaseSettings):
    # ── Database (MySQL) ─────────────────────────────────────────────────
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "nexus_user"
    MYSQL_PASSWORD: str = "nexus_password"
    MYSQL_DB: str = "nexus_db"

    # ── Redis (Job Queue & Rate Limiter) ──────────────────────────────────
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""  # S-3: Optional Redis auth password

    # ── AI Provider (LiteLLM Proxy) ───────────────────────────────────────
    LITELLM_API_BASE: str = "http://localhost:4000"
    VERTEX_PROJECT: str = "big-bliss-302909"
    VERTEX_LOCATION: str = "asia-southeast2"

    # ── Security & Encryption — REQUIRED, no defaults ────────────────────
    ENCRYPTION_KEY: str = Field(...)
    ADMIN_API_KEY: str = Field(...)

    # ── Application ───────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8100
    HOST: str = "127.0.0.1"

    # ── LLM Retry Policy (used by all service modules) ────────────────────
    LLM_MAX_RETRY_ATTEMPTS: int = 3
    LLM_RETRY_WAIT_MIN_SEC: int = 2
    LLM_RETRY_WAIT_MAX_SEC: int = 10
    LLM_RETRY_MULTIPLIER: float = 1.0

    # ── Webhook Dispatch Retry Policy ────────────────────────────────────
    WEBHOOK_MAX_RETRY_ATTEMPTS: int = 4
    WEBHOOK_RETRY_MULTIPLIER: float = 1.5
    WEBHOOK_RETRY_WAIT_MIN_SEC: int = 2
    WEBHOOK_RETRY_WAIT_MAX_SEC: int = 10
    WEBHOOK_TIMEOUT_SEC: float = 10.0

    # ── Authentication Cache ──────────────────────────────────────────────
    AUTH_CACHE_TTL_SEC: int = 300       # 5 minutes

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_CONFIG_CACHE_TTL_SEC: int = 600   # 10 minutes
    DEFAULT_RPM: int = 60                         # Requests per minute
    DEFAULT_RPD: int = 10000                      # Requests per day
    TOKEN_HOURLY_LIMIT: int = 10_000_000          # Infinite loop prevention

    # ── Background Worker ─────────────────────────────────────────────────
    WORKER_MAX_JOBS: int = 4            # Concurrent arq job limit

    # ── Database Connection Pool (Q-1) ────────────────────────────────────
    DB_POOL_SIZE: int = 20              # Steady-state pool connections
    DB_POOL_MAX_OVERFLOW: int = 10      # Extra connections under burst load
    DB_POOL_RECYCLE_SEC: int = 3600     # Recycle connections after 1 hour

    # ── Derived URLs (not set via env) ────────────────────────────────────
    @property
    def database_url(self) -> str:
        return f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}"

    @property
    def redis_url(self) -> str:
        # S-3: Include password in Redis URL if set
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instantiate settings singleton
settings = Settings()


@functools.lru_cache(maxsize=32)
def load_module_settings(module_name: str) -> dict:
    """
    LRU-cached loader for per-module settings.json files (Section 21.5 of SRS).
    Prevents repeated disk reads on each request.
    """
    file_path = os.path.join(os.path.dirname(__file__), "modules", module_name, "settings.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load settings for module '{module_name}': {e}. Using defaults.")
    return {}
