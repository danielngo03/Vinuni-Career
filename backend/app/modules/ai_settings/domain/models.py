"""``ai_settings`` ORM model — a single platform-scoped governance row (ADR-0011 §1).

SECRECY: this table stores **alias names + toggles + budget only**. There is NO
raw API-key column, NO concrete provider/model string, and NO base-URL column —
keys live solely in ``backend/.env`` (``OPENROUTER_API_KEY``). Nothing in this
table can leak a secret because no secret is stored here.

The singleton is enforced by a ``unique`` constraint on ``scope`` (always
``'platform'`` for V1). ``org_id`` + the ``scope`` vocabulary are reserved so a
future ADR can add ``scope = 'university'`` rows without a table rewrite. The
Postgres CHECK on ``rollout_state`` lives in migration ``0022`` only; the SQLite
unit-test path enforces the vocabulary in the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base

# rollout_state vocabulary (ADR-0011 §1). ``paused``/``offline`` force real calls
# off at the next resolve while preserving aliases/flags for a clean re-enable.
ROLLOUT_ENABLED = "enabled"
ROLLOUT_PAUSED = "paused"
ROLLOUT_OFFLINE = "offline"
ROLLOUT_STATES = frozenset({ROLLOUT_ENABLED, ROLLOUT_PAUSED, ROLLOUT_OFFLINE})

PLATFORM_SCOPE = "platform"


class AiSettings(Base):
    """Admin-managed AI runtime governance (single ``'platform'`` row for V1)."""

    __tablename__ = "ai_settings"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)

    # Singleton guard. ``'platform'`` for V1; future ``'university'`` rows relax this.
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, default=PLATFORM_SCOPE
    )
    # Reserved for deferred per-university scope; NULL for the platform row.
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )

    # DB toggle, ANDed UNDER the env+key ceiling in the resolver (never an OR).
    real_calls_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    rollout_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ROLLOUT_ENABLED
    )

    # Selected alias NAMES per task family (validated against the allowlist; never
    # free text, never a concrete model id).
    chat_model_alias: Mapped[str] = mapped_column(
        String(60), nullable=False, default="chat_default"
    )
    reasoning_model_alias: Mapped[str] = mapped_column(
        String(60), nullable=False, default="reasoning_default"
    )
    embedding_model_alias: Mapped[str] = mapped_column(
        String(60), nullable=False, default="embedding_default"
    )
    rerank_model_alias: Mapped[str] = mapped_column(
        String(60), nullable=False, default="rerank_default"
    )
    eval_model_alias: Mapped[str] = mapped_column(
        String(60), nullable=False, default="eval_default"
    )

    # Feature flags.
    cv_llm_structuring_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    job_fit_ai_explanation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # Per-day USD ceiling (check seam; the metered ledger is deferred — ADR-0011 §4).
    daily_budget_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("1.00")
    )
    # Per-organization daily USD cap. NULL = no per-org cap (unlimited for that
    # org, bounded only by the platform budget above). When set, the budget_guard
    # sums today's ai_usage_daily.cost_usd for the given org and rejects new
    # calls that would push it over this limit. Additive column — migration 0079.
    per_org_daily_budget_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True, default=None
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
