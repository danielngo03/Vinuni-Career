"""AI assistant SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Org context captured at session-creation time so a partner (recruiter)
    # chat can be org-scoped and audited at the table level. NULL for students
    # and any principal without an org (additive, no behaviour change).
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    persona: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage", back_populates="session", order_by="ChatMessage.created_at"
    )

    __table_args__ = (
        Index("ix_chat_sessions_user_id", "user_id"),
        Index("ix_chat_sessions_last_message_at", "last_message_at"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    # role: user | assistant | tool_call | tool_result
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    # Conversation-management fields (migration 0089).
    # ``seq`` is a monotonic per-session ordering index assigned at insert time so
    # the read path and truncate-and-replay (edit / regenerate) have a stable order
    # independent of ``created_at`` microsecond ties. NULL only for pre-migration
    # rows / ad-hoc fixtures — readers fall back to ``created_at`` when it is NULL.
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Set when a USER message is edited in place (edit-and-rerun); powers the
    # frontend "edited" affordance. Never mutated for assistant/tool rows.
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Soft-delete flag. Truncate-and-replay marks superseded messages
    # ``is_deleted=True`` instead of hard-deleting so the history stays auditable;
    # every read path excludes deleted rows.
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_session_id", "session_id"),
        Index("ix_chat_messages_created_at", "created_at"),
        Index("ix_chat_messages_session_seq", "session_id", "seq"),
    )


class ChatAttachment(Base):
    """A file/image a user attached to a chat session for AI analysis.

    Owner-scoped (``user_id`` + optional ``org_id``): a partner recruiter uploads
    a document/image to their own chat session and asks the assistant to analyse
    it (``analyze_attachment`` tool). The raw bytes live in signed blob storage
    addressed by ``storage_key`` — that key is INTERNAL and is NEVER returned to
    any client (only a safe descriptor id/filename/content_type/size/status is).
    ``analysis_json`` caches the structured, leakage-safe analysis result so a
    re-analysis returns it without re-charging energy.
    """

    __tablename__ = "chat_attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # Org context captured from the principal at upload time so a partner
    # (recruiter) attachment is org-scoped and can only be analysed by a member of
    # the same org. NULL for students / any principal without an org.
    org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Internal signed-storage object key — NEVER returned raw to any client.
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    # uploaded | analyzed | rejected
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="uploaded")
    # Structured, leakage-safe analysis result (see attachment_service). NULL until
    # analysed; cached so a re-analysis is idempotent and never re-charges.
    analysis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    __table_args__ = (
        Index("ix_chat_attachments_session_id", "session_id"),
        Index("ix_chat_attachments_user_id", "user_id"),
        Index("ix_chat_attachments_org_id", "org_id"),
    )
