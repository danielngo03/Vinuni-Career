"""Billing ORM models (ADR-0010 §1/§2/§6).

Two tables:

- ``subscription_plans`` — a small seeded, **audience-typed** reference table of
  named tiers (``student``/``partner``), each carrying its granted **limits as a
  structured JSON map** rather than a wide column-per-quota schema. Mirrors
  ``ad_packages``: one reference table, seeded in migration ``0019``.
- ``subscriptions`` — a polymorphic per-principal record of a **PAID** plan. The
  principal is either a ``user`` (student) or an ``org`` (partner): ``principal_type``
  + ``principal_id`` with **no DB foreign key** (it points at two tables); a CHECK
  constrains ``principal_type`` and the service layer validates ownership. The
  free/default tier needs **no row** — absence of an active paid subscription ==
  default-plan limits.

Types use the shared cross-database variants so the same models run on PostgreSQL
(runtime) and SQLite (unit tests). Postgres-only constructs (partial unique
in-flight index, partial window/principal indexes, CHECK constraints,
``set_updated_at`` trigger) live in migration ``0019`` only; the SQLite test path
enforces the invariants in the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class SubscriptionPlan(Base):
    """An audience-typed, fixed-price tier (reference data; seeded in ``0019``)."""

    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), nullable=False)
    audience: Mapped[str] = mapped_column(String(10), nullable=False)  # student|partner
    billing_period: Mapped[str] = mapped_column(
        String(10), nullable=False, default="monthly"
    )  # monthly|annual
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    price_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(5), nullable=False, default="VND")
    # Structured limits map the facade resolves (e.g. {"cv_active_quota": 10, ...}).
    limits: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class Subscription(Base):
    """A principal's record of a PAID plan (one window == one row, one payment).

    Never hard-deleted (soft delete via ``deleted_at``). ``status`` is the lifecycle
    state machine in :mod:`app.modules.billing.domain.lifecycle`.
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)

    # Polymorphic principal — NO FK (points at users OR organizations); CHECK on
    # principal_type, service-layer ownership validation.
    principal_type: Mapped[str] = mapped_column(String(10), nullable=False)  # user|org
    principal_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscription_plans.id"), nullable=False
    )
    billing_period: Mapped[str] = mapped_column(String(10), nullable=False)
    # Frozen snapshot of the plan price at request (price freeze).
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False, default="VND")

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|active|expired|cancelled

    # The active window; set at mark_paid (end_at = paid_at + plan.duration_days).
    start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    # Manual/bank-transfer payment record (fields-on-row, ADR-0010 §4).
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paid_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # T-7d "expiring soon" notification dedupe stamp.
    expiring_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    settings: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
