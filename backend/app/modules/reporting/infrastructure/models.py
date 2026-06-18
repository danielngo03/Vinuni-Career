from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.models.base import TimestampMixin, now_utc, uuid_str
from app.platform.database.session import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_resource: Mapped[str] = mapped_column(String(120), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    old_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        index=True,
    )

class UserActivityLog(Base):
    __tablename__ = "user_activity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    activity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        index=True,
    )

class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    feature_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        index=True,
    )

class JobStatistic(Base):
    __tablename__ = "job_statistics"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    bookmark_count: Mapped[int] = mapped_column(Integer, default=0)
    application_count: Mapped[int] = mapped_column(Integer, default=0)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class GeneratedReport(Base, TimestampMixin):
    __tablename__ = "generated_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    generated_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(120), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(60), default="PENDING")
