"""Messaging ORM models (ADR-0012 §2 — institutional in-app threads).

Three tables — ``message_threads`` / ``message_thread_participants`` /
``messages`` — back a *governed institutional channel* (university↔student,
university↔partner, partner↔candidate). They are deliberately PII-light: the only
identity stored is a ``user_id`` reference (delivery needs it); a student's
name/email is NEVER stored here. Partner-side identity masking is a projection-time
decision (``thread_view.py``) driven by the denormalized ``is_anonymous`` flag and
the recruitment reveal handshake — messaging never becomes a side-channel that
leaks a student's identity before reveal.

Types use the shared cross-database variants so the same models run on PostgreSQL
(runtime) and SQLite (unit tests). Postgres-only constructs — the partial unique
indexes (idempotent dedupe key; one direct thread per (context, participants)) and
the ``set_updated_at`` trigger — live in migration ``0023`` only and are NOT
declared on the ORM model so ``create_all`` omits them on SQLite (the service layer
carries the equivalent guard).
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

from app.shared.models import Base


class MessageThread(Base):
    """One conversation surface: a ``direct`` thread or a one-way ``announcement``.

    ``context_type``/``context_id`` bind the thread to its governing relationship
    (``application`` -> ``applications.id`` by convention; ``support``/``team`` ->
    null id). ``org_id`` is the tenant-isolation key (partner org for
    application/team threads; university org for support/announcement). ``is_anonymous``
    is denormalized from the bound application at create and drives partner-side
    masking; it is never re-read into the student's identity here.
    """

    __tablename__ = "message_threads"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="direct")
    context_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # FK-by-convention to ``applications.id`` for application threads — referenced by
    # id only (no hard cross-module FK / ORM relationship).
    context_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
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


class MessageThreadParticipant(Base):
    """A user's membership + read-state in a thread (PK ``(thread_id, user_id)``).

    ``can_reply`` is ``false`` for announcement recipients (one-way) and for the
    student side of a partner-initiated application thread only if explicitly muted
    — students may reply into partner threads (ADR-0012 §1). ``muted`` suppresses
    notifications (student "block"/mute) and stops the inactive-application cap from
    being refreshed. Unread is derived (``messages`` newer than ``last_read_at``).
    """

    __tablename__ = "message_thread_participants"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message_threads.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    role_in_thread: Mapped[str] = mapped_column(
        String(20), nullable=False, default="member"
    )
    can_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Message(Base):
    """One posted message in a thread.

    ``sender_id`` null = system message (undeletable). ``client_dedupe_key`` makes a
    retried POST idempotent (unique per ``(thread_id, sender_id, client_dedupe_key)``
    where present — PG partial unique in migration ``0023``; service guard on SQLite).
    ``deleted_at`` soft-deletes -> rendered as the "message was deleted" placeholder.
    The row carries NO sender name/email — only the ``user_id`` reference.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    client_dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
