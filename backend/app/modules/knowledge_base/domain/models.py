"""ORM models for the Knowledge Base module.

Three table families:
- ``knowledge_bases``: scoped containers (platform, partner-org, per-job).
- ``knowledge_base_documents``: uploaded documents with ingestion lifecycle.
- ``knowledge_base_chunks``: chunked + embedded text ready for hybrid retrieval.

Tenant isolation is enforced via ``org_id`` / ``job_id`` scope columns.
Cross-KB leakage is prevented in every query by filtering on ``kb_id``.
pgvector column degrades to TEXT JSON when the extension is unavailable so
the schema migration always runs regardless of pgvector install state.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import Base

if TYPE_CHECKING:
    pass

# KB scope types
KB_SCOPE_PLATFORM = "platform"   # visible to all authenticated users
KB_SCOPE_PARTNER = "partner"     # visible to applicants to that org's jobs
KB_SCOPE_JOB = "job"             # visible only to applicants to a specific job

# Document ingestion status lifecycle
DOC_STATUS_PENDING = "pending"
DOC_STATUS_PROCESSING = "processing"
DOC_STATUS_DONE = "done"
DOC_STATUS_FAILED = "failed"


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default=KB_SCOPE_PLATFORM)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    documents: Mapped[list[KnowledgeBaseDocument]] = relationship(
        "KnowledgeBaseDocument", back_populates="kb", cascade="all, delete-orphan"
    )


class KnowledgeBaseDocument(Base):
    __tablename__ = "knowledge_base_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunking_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DOC_STATUS_PENDING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    kb: Mapped[KnowledgeBase] = relationship("KnowledgeBase", back_populates="documents")
    chunks: Mapped[list[KnowledgeBaseChunk]] = relationship(
        "KnowledgeBaseChunk", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_kb_document_kb_status", "kb_id", "status"),
    )


class KnowledgeBaseChunk(Base):
    __tablename__ = "knowledge_base_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_base_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    section_heading: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Stored as JSON text when pgvector is unavailable (migration always runs)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    document: Mapped[KnowledgeBaseDocument] = relationship(
        "KnowledgeBaseDocument", back_populates="chunks"
    )

    __table_args__ = (
        Index("ix_kb_chunk_kb_id_deleted", "kb_id", "is_deleted"),
        Index("ix_kb_chunk_document_index", "document_id", "chunk_index"),
    )
