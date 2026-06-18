"""SQLAlchemy models for AI run tracking."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.models.base import TimestampMixin, now_utc, uuid_str
from app.platform.database.session import Base


class AIRun(Base, TimestampMixin):
    """Tracks a single AI task execution end-to-end."""

    __tablename__ = "ai_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_type: Mapped[str] = mapped_column(String(80), index=True)  # e.g. "cv_extraction", "matching"
    status: Mapped[str] = mapped_column(
        String(40), default="QUEUED", index=True
    )  # QUEUED | RUNNING | DONE | FAILED | CANCELLED
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    input_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)  # e.g. "cv:uuid"
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256 of input
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class AIRunEvent(Base):
    """Structured progress events for an AI run — streamed via SSE."""

    __tablename__ = "ai_run_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    event_type: Mapped[str] = mapped_column(String(80))  # "step_start" | "step_done" | "error" | "result"
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
