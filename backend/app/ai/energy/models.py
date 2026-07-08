"""ORM model for AI energy allowance + wallet (per org / department / user).

Holds only the ALLOWANCE CONFIG and the non-resetting top-up WALLET. Actual
consumption is never stored here — it is summed on demand from the durable
``ai_billable_usage`` ledger (see :mod:`app.ai.energy.service`), so the two can
never drift.

Scope semantics:
- ``scope_type == "org"``  → the partner organization's weekly pool override
  (``weekly_allowance_units``; NULL = use the plan/persona default) plus the
  org's shared wallet.
- ``scope_type == "department"`` → an admin-partner sub-allocation ceiling for a
  department (bounded by the org pool) plus an optional department wallet.
- ``scope_type == "user"`` → an admin sub-allocation ceiling for one member plus
  that member's own purchased wallet (a member may top-up themselves).

Never stores tokens, USD, provider, or model — energy is a cost-weighted credit
abstraction only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base

SCOPE_ORG = "org"
SCOPE_DEPARTMENT = "department"
SCOPE_USER = "user"

# Top-up lifecycle statuses (manual/bank-transfer, mirrors billing subscriptions).
TOPUP_PENDING = "pending"
TOPUP_PAID = "paid"
TOPUP_CANCELLED = "cancelled"


class AiEnergyAccount(Base):
    """Weekly allowance override + non-resetting wallet for one scope."""

    __tablename__ = "ai_energy_accounts"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", name="uq_ai_energy_accounts_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    # "org" | "department" | "user"
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # The org id, department id, or user id (per scope_type).
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # Denormalized owning org (equals scope_id for org scope) so the whole tree
    # of a partner org resolves in one indexed query.
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    # Weekly allowance CEILING in credits. NULL = inherit (org: plan/persona
    # default; department/user: no sub-cap → share the org pool).
    weekly_allowance_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Non-resetting purchased top-up balance in credits (consumed only after the
    # weekly allowance is exhausted). Never negative.
    wallet_units: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    # Audit.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
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


class AiEnergyTopup(Base):
    """Durable purchase/audit record for a manual/bank-transfer energy top-up.

    A member (or an admin on behalf of a department/org) requests a pack; the row
    is created ``pending`` with bank-transfer instructions. A finance/university
    admin (or superadmin) confirms money received and the purchased ``units`` are
    credited to the target scope's :class:`AiEnergyAccount` wallet (idempotent —
    a paid row re-confirmed never double-credits).

    ``price_amount``/``currency`` are a REAL product price (VND), like a
    subscription — this is a purchase, distinct from the hidden AI provider cost
    (tokens/USD/provider/model are never stored or exposed anywhere).
    """

    __tablename__ = "ai_energy_topups"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Owning partner org (denormalized; nullable for a platform-scope grant).
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    # "org" | "department" | "user" — the wallet the purchase credits.
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # Credits purchased (added to the scope wallet on confirm).
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    # Real product price (VND) — frozen at request from the pack reference.
    price_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="VND", default="VND"
    )
    # "pending" | "paid" | "cancelled".
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=TOPUP_PENDING, default=TOPUP_PENDING
    )
    # Bank-transfer reference recorded by the confirming admin (not sensitive).
    payment_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    paid_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Internal pack reference (e.g. "small"|"medium"|"large").
    pack_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
