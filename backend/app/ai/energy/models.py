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

from sqlalchemy import (
    DateTime,
    Integer,
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
