from datetime import datetime
import uuid
from typing import List, Optional
from sqlalchemy import (
    String, Integer, BigInteger, Boolean, DateTime, ForeignKey,
    Text, JSON, Numeric, func, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# Core Declarative Base Class using modern SQLAlchemy 2.0 Type Mapping
class Base(DeclarativeBase):
    pass


class NexusApp(Base):
    __tablename__ = "nexus_apps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    app_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_prefix: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    callback_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now(), nullable=True)

    # SQLAlchemy 2.0 Async-compatible relationships with back_populates
    permissions: Mapped[List["NexusAppPermission"]] = relationship(
        "NexusAppPermission", back_populates="app", cascade="all, delete-orphan"
    )
    rate_limits: Mapped[List["NexusRateLimit"]] = relationship(
        "NexusRateLimit", back_populates="app", cascade="all, delete-orphan"
    )
    jobs: Mapped[List["NexusJob"]] = relationship(
        "NexusJob", back_populates="app", cascade="all, delete-orphan"
    )
    usage_logs: Mapped[List["NexusUsageLog"]] = relationship(
        "NexusUsageLog", back_populates="app", cascade="all, delete-orphan"
    )


class NexusAppPermission(Base):
    __tablename__ = "nexus_app_permissions"

    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("nexus_apps.id", ondelete="CASCADE"), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Bidirectional relationship with NexusApp
    app: Mapped["NexusApp"] = relationship("NexusApp", back_populates="permissions")


class NexusJob(Base):
    __tablename__ = "nexus_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("nexus_apps.id", ondelete="CASCADE"), nullable=False)
    app_name: Mapped[str] = mapped_column(String(100), nullable=False)
    caller_user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    caller_user_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)  # 'queued', 'processing', 'done', 'failed', 'cancelled'
    result_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[Numeric] = mapped_column(Numeric(10, 6), default=0.000000, nullable=False)
    
    queued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Webhook Management Columns
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    webhook_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    webhook_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    webhook_last_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    webhook_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    app: Mapped["NexusApp"] = relationship("NexusApp", back_populates="jobs")

    __table_args__ = (
        Index("idx_app_status", "app_id", "status"),
        Index("idx_status_queued", "status", "queued_at"),
        Index("idx_caller", "caller_user_id"),
    )


class NexusUsageLog(Base):
    __tablename__ = "nexus_usage_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("nexus_apps.id", ondelete="CASCADE"), nullable=False)
    app_name: Mapped[str] = mapped_column(String(100), nullable=False)
    caller_user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    caller_user_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    response_mode: Mapped[str] = mapped_column(String(10), nullable=False) # 'sync' or 'async'
    job_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("nexus_jobs.id", ondelete="SET NULL"), nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Token Metrics
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Cost & Diagnostics
    cost_usd: Mapped[Numeric] = mapped_column(Numeric(10, 6), default=0.000000, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    app: Mapped["NexusApp"] = relationship("NexusApp", back_populates="usage_logs")

    __table_args__ = (
        Index("idx_app_date", "app_id", "requested_at"),
        Index("idx_endpoint_date", "endpoint", "requested_at"),
        Index("idx_caller_date", "caller_user_id", "requested_at"),
        Index("idx_requested_at", "requested_at"),
    )


class NexusRateLimit(Base):
    __tablename__ = "nexus_rate_limits"

    app_id: Mapped[str] = mapped_column(String(36), ForeignKey("nexus_apps.id", ondelete="CASCADE"), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(100), primary_key=True)
    requests_per_hour: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    max_tokens_per_day: Mapped[int] = mapped_column(Integer, default=2000000, nullable=False)

    app: Mapped["NexusApp"] = relationship("NexusApp", back_populates="rate_limits")
