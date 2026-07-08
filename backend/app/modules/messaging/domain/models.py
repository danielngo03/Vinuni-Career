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
    BigInteger,
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
    # Messaging V2 (owner decision 2026-07-09). ``thread_kind`` is the richer,
    # denormalized discriminator (``org_dm`` | ``org_to_org`` | ``internal`` |
    # ``application`` | ``support`` | ``announcement``); the legacy ``kind`` column
    # stays (``direct`` | ``announcement``) for back-compat. NULL on legacy rows.
    thread_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # First-contact "message request" gate. ``accepted`` (the default) means the
    # thread is open both ways; ``pending`` means only the initiator may post, up
    # to ``request_message_count`` <= settings.messaging_request_message_limit,
    # until the recipient party accepts. ``declined``/``blocked`` stop the initiator.
    request_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted"
    )
    request_message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # FK-by-convention to ``message_thread_parties.id`` (no hard FK — avoids a
    # threads<->parties create-order cycle on SQLite ``create_all``; the parties
    # table already hard-references the thread, which is the load-bearing edge).
    initiator_party_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
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
    # Which side (party) this user belongs to. NULL on legacy rows; the service
    # sets it for V2 threads so a user's membership resolves to a ``user`` or
    # ``org`` party (Messaging V2). Read-state for a ``user`` party lives here
    # (``last_read_at``); for an ``org`` party the shared cursor lives on the party.
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message_thread_parties.id", ondelete="CASCADE"), nullable=True
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
    # Which party sent it (Messaging V2) — lets the projection render an org Page
    # label without re-resolving the sender's org membership. NULL on legacy/system.
    sender_party_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message_thread_parties.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_attachments: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
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


class MessageThreadParty(Base):
    """One SIDE of a conversation (Messaging V2, owner decision 2026-07-09).

    A thread has one or two parties. A ``user`` party is a single individual
    (a student/alumni representing themselves, or one staff member in an internal
    DM). An ``org`` party is a partner/university acting as a single **Page** — a
    shared team inbox whose staff act on its behalf and, to outsiders, appear only
    as the org. ``identity_mode`` decides how this party renders to the OTHER side:
    ``org`` (Page — the staff member's name is never shown) or ``person``.

    Org-side read-state is shared (``last_read_at`` on the party); a member does
    not need a per-user participant row to see the org's inbox — access is computed
    from RBAC (``messaging`` capability) + department scope. ``assigned_*`` route a
    thread to a department and/or a responsible staff member.
    """

    __tablename__ = "message_thread_parties"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    party_kind: Mapped[str] = mapped_column(String(10), nullable=False)  # user | org
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    identity_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="person"  # person | org
    )
    assigned_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assignment_state: Mapped[str] = mapped_column(
        String(12), nullable=False, default="unassigned"  # unassigned|assigned|resolved
    )
    last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageAttachment(Base):
    """A file/image bound to a message (Messaging V2).

    Rows are created ``message_id``-null on upload and bound to the message on send
    (so an unsent draft's attachment is orphan-collectable). ``storage_key`` is the
    documents-store key — NEVER returned raw; downloads go through a gated endpoint
    that re-checks thread access every time (`.claude/rules/backend.md` signed-URL
    rule). Type allowlist + size cap enforced in the service.
    """

    __tablename__ = "message_attachments"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploader_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # image | file
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
