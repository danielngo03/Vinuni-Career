"""ORM models for the AI governance (university control plane) module.

``AiCapacityRequest`` is the university capacity-request workflow: a staff member
asks the superadmin to distribute more weekly AI energy to their scope (their own
user allocation, or a department they belong to). University energy is
DISTRIBUTION, not billing — the resolution is an admin decision, never a
self-serve upgrade/top-up. Approving a request raises the target
``AiEnergyAccount`` ceiling.

Never stores tokens, USD, provider, or model — only the request reason, the
requested/granted energy-credit amount, and the decision trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base

# Request lifecycle.
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"

# Scope a request targets (mirrors AiEnergyAccount sub-allocation scopes).
REQUEST_SCOPE_USER = "user"
REQUEST_SCOPE_DEPARTMENT = "department"


class AiCapacityRequest(Base):
    """A university member's request for more distributed weekly AI energy."""

    __tablename__ = "ai_capacity_requests"
    __table_args__ = (
        Index("ix_ai_capacity_requests_status_created", "status", "created_at"),
        Index("ix_ai_capacity_requests_requested_by", "requested_by", "created_at"),
        Index("ix_ai_capacity_requests_org", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # "user" | "department"
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Requested weekly ceiling in energy credits (optional — admin may decide).
    requested_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "pending" | "approved" | "denied"
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=STATUS_PENDING
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
