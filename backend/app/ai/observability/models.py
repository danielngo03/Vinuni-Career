"""ORM model for the ``ai_usage_log`` table.

PII-safe cost/observability tracking per ``docs/AI_PRODUCT_SPEC.md`` §5.4.

Stored: task type, internal model alias, success flag, char-length buckets,
optional user/session UUID, optional cost estimate.

Never stored: provider name, model name, API key, prompt text, response text,
PII, IP address, raw token counts, raw latency.

Cross-database: ``Uuid`` and ``Numeric`` render correctly on PostgreSQL
(runtime) and SQLite (unit tests).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, UniqueConstraint, Uuid, func
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
