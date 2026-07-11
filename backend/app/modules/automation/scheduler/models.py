"""ORM model for scheduler job run history.

Stores one row per completed job execution so the platform admin
health console can surface last-run status, duration, and result
for every registered scheduled job without keeping in-memory state.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class SchedulerJobRun(Base):
    """Append-only record of a single scheduled-job execution."""

    __tablename__ = "scheduler_job_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_name: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "ok" or "error"
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Primary access pattern: latest run per job name.
        Index("ix_scheduler_job_runs_job_name_started_at", "job_name", "started_at"),
    )
