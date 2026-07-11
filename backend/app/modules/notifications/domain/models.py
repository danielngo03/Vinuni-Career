"""Notification ORM models (``docs/DATA_MODEL.md`` §34, spec §4/§7).

- ``notification_templates``: versioned, immutable-when-active templates with a
  declared ``variables_schema`` (required + allowed variables).
- ``notification_outbox``: transactional dispatch queue. A product write enqueues
  a row in the same transaction; a worker renders + delivers asynchronously so no
  product workflow waits synchronously on SMTP/push.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    owner_scope: Mapped[str] = mapped_column(String(20), nullable=False)  # university|partner
    owner_org_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    key: Mapped[str] = mapped_column(String(150), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # email|in_app|push
    locale: Mapped[str] = mapped_column(String(5), nullable=False)  # vi|en
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft|active|archived
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    variables_schema: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class NotificationOutbox(Base):
    """Pending notification dispatch records (rendered + delivered by worker)."""

    __tablename__ = "notification_outbox"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    template_key: Mapped[str] = mapped_column(String(150), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="vi")
    variables: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|sent|failed|skipped|dead
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # NULL = eligible for delivery immediately; a future value defers reclaim after
    # a transient send failure (exponential backoff, ADR-0003 §3). The drain claim
    # gate is ``status='pending' AND (next_attempt_at IS NULL OR next_attempt_at<=now)``.
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Drain-claim covering index (PostgreSQL runtime; ORM-built SQLite test schema
    # gets it too for parity). Migration 0011 creates the runtime index.
    __table_args__ = (Index("idx_outbox_due", "status", "next_attempt_at"),)


class Notification(Base):
    """Canonical in-app notification feed row (``docs/DATA_MODEL.md`` §14).

    This is the bell-center / Notification Center feed with per-row read state. It
    is distinct from ``notification_outbox`` (the async email/push dispatch queue):
    a product event may BOTH enqueue an outbox row AND insert one of these rows in
    the same transaction. Rows are recipient-scoped — a user only ever reads its
    own ``recipient_id`` rows.

    ``channels`` (list) and ``delivered_at`` (``{channel: iso-timestamp}``) are
    stored via the project's cross-database ``JsonType`` (JSONB on PostgreSQL,
    JSON on the SQLite unit-test path) rather than a native PG ``VARCHAR[]`` so the
    same ORM model runs on both backends — matching how every other list/map field
    in the codebase is persisted.

    Title/body are pre-rendered, user-safe strings (no provider/model/internal
    codes, and partner-facing rows carry only the anonymous candidate handle).
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    notif_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    channels: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    delivered_at: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # The runtime (PostgreSQL) index orders ``created_at DESC`` — see migration
    # 0009. The ORM-built SQLite test schema only needs the covering columns.
    __table_args__ = (
        Index(
            "idx_notif_recipient",
            "recipient_id",
            "is_read",
            "created_at",
        ),
    )
