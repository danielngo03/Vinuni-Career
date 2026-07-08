"""Platform Admin ORM models.

Tables:
  feature_flag — generalised feature flag registry (superadmin-managed).
                 Additive; the existing hardcoded AI booleans in ai_settings
                 are NOT migrated here; they can be folded in later.
  alert_rule   — superadmin-defined threshold rules over operational metrics.
  incident     — open/acknowledged/resolved incidents raised by alert evaluation.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base


class FeatureFlag(Base):
    """A named feature toggle with optional staged-rollout support.

    ``rollout_percentage`` is an integer 0-100:
      - 0   → always disabled (unless ``enabled`` is False, which also → disabled)
      - 100 → always enabled for all subjects
      - 1-99 → deterministic per-subject bucketing via SHA-256 hash

    ``updated_by`` records the superadmin UUID who made the last change.
    """

    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("key", name="uq_feature_flags_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    rollout_percentage: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ---------------------------------------------------------------------------
# P7: Alert Rules & Incidents
# ---------------------------------------------------------------------------

_VALID_METRICS = frozenset(
    {"ai_spend_vs_budget_pct", "ai_error_rate", "queue_depth", "outbox_failed"}
)
_VALID_COMPARISONS = frozenset({"gt", "lt", "gte", "lte"})
_VALID_SEVERITIES = frozenset({"info", "warning", "critical"})


class AlertRule(Base):
    """Superadmin-defined threshold rule over an operational metric.

    ``metric``     — one of ``_VALID_METRICS``.
    ``comparison`` — one of ``gt | lt | gte | lte``.
    ``threshold``  — numeric threshold value.
    ``window_days``— aggregation window forwarded to the metric source (default 1).
    ``severity``   — ``info | warning | critical``.
    ``enabled``    — only enabled rules are evaluated by the scheduler job.
    ``channels``   — JSON list of delivery channels, e.g. ``["in_app","email"]``.
    ``updated_by`` — superadmin UUID who made the last change.
    """

    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    comparison: Mapped[str] = mapped_column(String(10), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="warning", default="warning"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    channels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Incident(Base):
    """An incident opened when an AlertRule threshold is breached.

    ``status``          — ``open | acknowledged | resolved``.
    ``message``         — user-safe description, e.g. "AI error rate 12% exceeded threshold 5%".
                          Never exposes provider/model/prompt/cost internals.
    ``value``           — metric value at trigger time.
    ``threshold``       — rule threshold at trigger time (snapshot).
    ``triggered_at``    — when the evaluator opened this incident.
    ``acknowledged_at`` — set when a superadmin acknowledges.
    ``acknowledged_by`` — superadmin UUID.
    ``resolved_at``     — set when resolved (auto or manual).
    """

    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status_triggered_at", "status", "triggered_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        default=uuid.uuid4,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open", default="open"
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
