"""Compliance ORM models (``docs/DATA_MODEL.md`` §35, ADR-0014).

Two tables, neither using ``BaseEntity`` (no partner/university org-scoped
soft-delete/version semantics apply — plain PK + explicit ``created_at``,
matching the house pattern already used by ``NotificationOutbox`` /
``HumanReviewItem`` / ``ReviewReport``):

- ``consents`` — current-state row per ``(user_id, consent_type)``. The two
  legal consent types are enforced in code (:data:`CONSENT_TYPES`), never a
  DB-configurable table in V1.
- ``privacy_requests`` — a student's self-service export/deletion request.
  Fulfillment is a manual admin action (queries existing tables); this table
  only tracks request lifecycle state, never orchestrates an auto-purge.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base

# --------------------------------------------------------------------------- #
# Consent vocabulary (code-enforced, not DB-configurable in V1)               #
# --------------------------------------------------------------------------- #

CONSENT_INTERVIEW_RECORDING = "interview_recording"
CONSENT_CAREER_OUTCOMES_DATA_SHARING = "career_outcomes_data_sharing"
CONSENT_TYPES: frozenset[str] = frozenset(
    {CONSENT_INTERVIEW_RECORDING, CONSENT_CAREER_OUTCOMES_DATA_SHARING}
)

# --------------------------------------------------------------------------- #
# Privacy request vocabulary                                                  #
# --------------------------------------------------------------------------- #

REQUEST_EXPORT = "export"
REQUEST_DELETION = "deletion"
REQUEST_TYPES: frozenset[str] = frozenset({REQUEST_EXPORT, REQUEST_DELETION})

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_FULFILLED = "fulfilled"
STATUS_REJECTED = "rejected"
OPEN_STATUSES: frozenset[str] = frozenset({STATUS_PENDING, STATUS_PROCESSING})
TERMINAL_STATUSES: frozenset[str] = frozenset({STATUS_FULFILLED, STATUS_REJECTED})
ALL_STATUSES: frozenset[str] = OPEN_STATUSES | TERMINAL_STATUSES


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("user_id", "consent_type", name="uq_consent_user_type"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PrivacyRequest(Base):
    __tablename__ = "privacy_requests"
    __table_args__ = (Index("idx_privacy_requests_status", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    request_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_PENDING)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    processed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
