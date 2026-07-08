"""ORM models for AI observability tables.

Tables:
- ``ai_usage_log``: PII-safe cost/observability tracking per ``docs/AI_PRODUCT_SPEC.md`` §5.4.
- ``ai_model_price``: admin-editable per-(provider, model) token price table.
- ``ai_ops_event``: admin-only per-call operational telemetry (AI_PRODUCT_SPEC §5.6).
- ``ai_usage_daily``: pre-aggregated rollup for fast dashboards.

Stored in ai_usage_log: task type, internal model alias, success flag,
char-length buckets, optional user/session UUID, optional cost estimate.

Never stored: provider name, model name, API key, prompt text, response text,
PII, IP address, raw token counts, raw latency (ai_usage_log).

Cross-database: ``Uuid`` and ``Numeric`` render correctly on PostgreSQL
(runtime) and SQLite (unit tests).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base


class AiUsageLog(Base):
    """Append-only record written once per AI gateway call.

    The table is insert-only: no updates, no soft deletes. Rows are retained
    for analytics and cost reporting; they contain zero user-identifiable
    content beyond an optional ``user_id`` FK and ``session_id`` reference.
    """

    __tablename__ = "ai_usage_log"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # "ai_assistant_chat", "cv_bullets", "cv_rewrite", "job_fit", etc.
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=False)
    # Internal alias only — never a provider or real model name.
    model_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # "xs" / "sm" / "md" / "lg" — see _db_bucket() in usage.py
    prompt_chars_bucket: Mapped[str | None] = mapped_column(String(16), nullable=True)
    completion_chars_bucket: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Nullable: anonymous / system / background calls have no user or session.
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # Not always available — depends on provider cost reporting.
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)


class AiModelPrice(Base):
    """Admin-editable per-(provider, model) token price table.

    Used by ``pricing.estimate_cost_usd_db`` to compute accurate cost
    estimates when the concrete provider/model is known. Stored prices are
    in USD per 1 000 tokens (per-1k) for both input and output.

    The ``active`` flag lets admins soft-disable a row without deleting it
    (useful when swapping models — mark the old row inactive, insert the new
    one). ``updated_by`` tracks the admin UUID responsible for the last change;
    ``updated_at`` is auto-refreshed on every write.

    Never surfaced to end users — internal cost-accounting only.
    Cross-database: ``Uuid`` and ``Numeric`` render on both PostgreSQL and SQLite.
    """

    __tablename__ = "ai_model_price"
    __table_args__ = (
        UniqueConstraint("provider", "model", name="uq_ai_model_price_provider_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_usd_per_1k: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    output_usd_per_1k: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AiOpsEvent(Base):
    """Admin-only per-call operational telemetry (AI_PRODUCT_SPEC §5.6). No prompt text."""

    __tablename__ = "ai_ops_event"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    alias: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="ok"
    )
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    circuit_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    unpriced: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AiUsageDaily(Base):
    """Pre-aggregated rollup for fast dashboards.

    Grain: day × task_type × provider × model × org_id.
    Provider and model default to empty string ``""`` when unknown so the
    unique constraint never contains NULLs (NULL equality is unreliable across
    databases).
    """

    __tablename__ = "ai_usage_daily"
    __table_args__ = (
        UniqueConstraint(
            "day",
            "task_type",
            "provider",
            "model",
            "org_id",
            name="uq_ai_usage_daily_grain",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    day: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=""
    )
    model: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default=""
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    fallbacks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    blocked: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 7), nullable=False, server_default="0"
    )
    latency_ms_sum: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    latency_ms_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )


class AiBillableUsage(Base):
    """Durable billable-usage ledger (PRODUCT_OPERATING_MODEL.md §3.1).

    The append-only source of truth for plan/package credit limits — DISTINCT
    from ``ai_usage_log`` (PII-safe provider call log) and ``ai_ops_event``
    (superadmin ops telemetry). Every billable AI call records exactly one row
    here with the *charge decision* (``result_status`` + ``units_charged``), so a
    model call can be attributed to the correct student/partner-org/university
    budget and feature even when the provider telemetry also fired.

    Idempotent: ``idempotency_key`` (caller-namespaced, e.g.
    ``"cv_fit_explanation:<cv_version>:<job_version>"``) is globally unique when
    present, so a Celery redelivery / client retry / cache reuse never
    double-charges. ``NULL`` keys are allowed to repeat (non-idempotent events).

    Never stores provider name, model id, prompt/response text, token counts, or
    raw cost internals beyond the aggregate ``provider_cost_usd`` estimate — this
    ledger is user/org/budget attribution, not observability.
    Cross-database: ``Uuid`` and ``Numeric`` render on both PostgreSQL and SQLite.
    """

    __tablename__ = "ai_billable_usage"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ai_billable_usage_idempotency"),
        # Composite index backing the per-user 3h rolling soft-warn window
        # (energy_service.soft_warn_state). Added in migration 0084.
        Index(
            "ix_ai_billable_usage_user_created",
            "actor_user_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    # Nullable: system/background calls have no acting user.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    # "student" | "partner" | "university" | "system"
    actor_persona: Mapped[str] = mapped_column(String(24), nullable=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    # "user" | "org" | "department" | "platform"
    billing_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    # Product feature key, e.g. "chatbot" | "cv_fit_explanation" | "jd_extraction".
    feature_key: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # Internal AI task name (matches ai_usage_log.task_type).
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Credits actually charged to the actor/org (0 for free/failed/cached/blocked).
    units_charged: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Estimated internal provider cost (counted even when units_charged == 0).
    provider_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    # "success" | "provider_failed" | "validation_failed" | "cached" | "blocked"
    result_status: Mapped[str] = mapped_column(String(24), nullable=False)
    # Nullable cross-links to the observability rows for the same call.
    ai_usage_log_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    ai_ops_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
