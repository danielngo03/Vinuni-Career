"""Talent-pool ORM models.

``CvEmbedding`` is the pgvector-free semantic index over consented, discoverable
student CVs (see the ``0097_cv_embeddings`` migration for the full contract). The
``vector`` and ``skills`` columns use the shared cross-database ``JsonType``
(JSONB on Postgres, JSON on SQLite) so the same model backs the Postgres runtime
AND the SQLite test schema — ranking is done in Python via
``app.ai.retrieval.embeddings.top_k_by_cosine``, never the ``<=>`` operator.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class CvEmbedding(Base):
    """One embedding row per consented, discoverable CV per model alias.

    ``snapshot_id`` is a bare UUID (the immutable ``cv_versions`` snapshot the
    vector reflects; documents-owned, no hard FK). ``content_text`` is a capped,
    derived matching projection of the student's OWN CV — it powers the
    deterministic keyword fallback and is NEVER surfaced raw to a partner.
    """

    __tablename__ = "cv_embeddings"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "model_alias", name="uq_cv_embeddings_snapshot_model"),
        Index("ix_cv_embeddings_user", "user_id"),
        Index("ix_cv_embeddings_cv", "cv_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    model_alias: Mapped[str] = mapped_column(String(80), nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Portable embedding vector (list[float]) + lowercased skill names.
    vector: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    skills: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    experience_years: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
