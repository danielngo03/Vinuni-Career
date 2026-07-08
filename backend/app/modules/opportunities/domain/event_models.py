"""Events ORM models (ADR-0008; ``docs/DATA_MODEL.md`` §10, V1 free-admission).

``events`` is a sibling of ``jobs`` inside ``opportunities`` — it mirrors the jobs
lifecycle/moderation/sponsored/org-ownership shape but with an event-appropriate
status vocabulary and time fields. ``event_registrations`` is the free single
admission per event; ticket types, QR codes, and payment are deferred (their FKs
are named in the ADR so they attach later without rework).

Additions documented in ADR-0008 (beyond the canonical DATA_MODEL §10 shape):
``visibility``, ``moderation_*``, ``submitted_at``/``published_at``/``approved_*``,
``version``, and the event-level ``capacity``/``registration_count`` (V1 has no
ticket types). ``event_registrations.status`` adds ``no_show``.

Types use the shared cross-database variants so the same models run on PostgreSQL
(runtime) and SQLite (unit tests). Postgres-only constructs (partial unique index,
``set_updated_at`` trigger) live in migration ``0016`` only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class Event(Base):
    """An organizer event posting. Never hard-deleted (soft delete via ``deleted_at``)."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(600), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)

    cover_image_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    venue_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    venue_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="Asia/Ho_Chi_Minh"
    )
    registration_opens_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    registration_closes_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registration_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="public"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft|pending_review|published|cancelled|completed|rejected
    moderation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|approved|rejected|flagged
    moderation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured rejection/escalation reason code (``app.shared.moderation``);
    # ``moderation_note`` remains the optional supplementary free-text field.
    moderation_reason_code: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # SLA deadline computed at submission time (``settings.event_moderation_sla_hours``).
    due_by: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_sponsored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
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


class EventRegistration(Base):
    """A free single admission to an event.

    Capacity lives on ``events.capacity``; a registration references the event,
    not a ticket type (ticketing is deferred). One *active* registration per
    ``(event, user)`` is enforced by a partial unique index (Postgres) plus the
    service-layer guard (SQLite tests).
    """

    __tablename__ = "event_registrations"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="confirmed"
    )  # confirmed|waitlisted|cancelled|attended|no_show

    check_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_in_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
