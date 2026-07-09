"""Data shapes for the workforce (coordinator/worker) pattern.

Pure dataclasses/enums for in-process planning (``SubtaskSpec``,
``SubtaskResult``) plus the ``ai_workforce_runs`` ORM model used to persist run
state so the frontend can poll ``GET /api/v1/ai/workforce/runs/{run_id}`` from
any API process, not just the one that started the run.

Deviation from ``docs/AI_PRODUCT_SPEC.md`` §4.2 (documented, not silent): the
spec describes per-subtask results "stored in Redis with TTL 1 hour". This
codebase has no existing Redis-backed application-state abstraction (Redis is
only used today as the Celery broker/result backend) and the rest of the
platform stores exactly this shape of bounded, queryable run/job state in
Postgres JSONB columns (see ``ai_usage_log``, ``ai_task_model_configs``). A
durable, queryable ``ai_workforce_runs`` row is used instead so status survives
a worker restart and can be read without a Celery result-backend dependency in
the request path. If workforce volume grows enough to need real TTL eviction,
add a scheduled sweep job (``app.modules.automation.scheduler``) rather than
switching to Redis.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class SubtaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"


TERMINAL_SUBTASK_STATUSES = frozenset({SubtaskStatus.SUCCESS, SubtaskStatus.FAILED})
TERMINAL_RUN_STATUSES = frozenset({RunStatus.PARTIAL, RunStatus.COMPLETE, RunStatus.FAILED})


@dataclass(frozen=True, slots=True)
class SubtaskSpec:
    """One planned unit of work the coordinator dispatches to a worker.

    ``key`` is the idempotency/dedup key: stable and deterministic given the
    run's inputs (e.g. ``f"{application_id}"``) so a Celery redelivery of the
    same logical subtask never re-runs (and re-charges) a completed subtask.
    """

    key: str
    subtask_type: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SubtaskResult:
    """The outcome of executing one ``SubtaskSpec``."""

    key: str
    status: SubtaskStatus
    result: dict | None = None
    error_code: str | None = None
    duration_ms: int | None = None

    def to_json(self) -> dict:
        return {
            "status": self.status.value,
            "result": self.result,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
        }


class WorkforceRun(Base):
    """Durable state for one coordinator run (``ai_workforce_runs``).

    Written once at plan time (``PENDING``/``RUNNING`` + the full subtask key
    list), then updated in place — under a row lock — as each worker reports a
    terminal ``SubtaskResult``. Never stores raw prompt text, chunk content, or
    provider/model identity; ``result`` payloads are the same user-safe shapes
    the underlying AI service already returns (e.g. screening-brief bullets).
    """

    __tablename__ = "ai_workforce_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # e.g. "bulk_screening_brief" — extend by adding a new task_type + a new
    # subtask_type executor, never by branching this field in a giant if-chain.
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RunStatus.PENDING.value)

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    # Reconstructs the acting Principal inside the (separate-process) Celery
    # worker, and carries task-specific context (e.g. {"job_id": "..."}).
    # Never contains raw prompt/PII beyond what the requester already owns.
    context_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

    # Planned subtask keys, in dispatch order.
    subtask_keys_json: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    # subtask_key -> SubtaskResult.to_json(); populated as workers report in.
    subtask_results_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    # Aggregated, user-safe summary — set once the run reaches a terminal status.
    summary_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
