"""Add knowledge_base, knowledge_base_documents, knowledge_base_chunks tables.

Supports platform/partner/job-scoped RAG retrieval (AI_PRODUCT_SPEC §6, ARCHITECTURE.md).
Chunks store embedding vector as JSON text (pgvector upgrade path via 0044).

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- knowledge_bases ---------------------------------------------------
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=True),  # NULL = platform-wide
        sa.Column("job_id", sa.UUID(), nullable=True),  # NULL = not job-scoped
        sa.Column("scope", sa.String(20), nullable=False),  # platform|partner|job
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_kb_org_id", "knowledge_bases", ["org_id"])
    op.create_index("ix_kb_scope", "knowledge_bases", ["scope"])
    op.create_index("ix_kb_job_id", "knowledge_bases", ["job_id"])

    # --- knowledge_base_documents -----------------------------------------
    op.create_table(
        "knowledge_base_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kb_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(400), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),  # internal — never exposed
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        # pending | ingesting | ready | failed
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_kbdoc_kb_id", "knowledge_base_documents", ["kb_id"])
    op.create_index("ix_kbdoc_status", "knowledge_base_documents", ["status"])

    # --- knowledge_base_chunks --------------------------------------------
    # Embedding stored as JSON text now; pgvector column added in 0044 when
    # the extension is available on the target DB.
    op.create_table(
        "knowledge_base_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("kb_id", sa.UUID(), nullable=False),  # denormalised for fast scope filter
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),  # plain text — never raw PDF/image
        sa.Column("section_heading", sa.String(300), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding_json", sa.Text(), nullable=True),  # JSON float array
        sa.Column("embedding_model_alias", sa.String(60), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_base_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_kbchunk_kb_id", "knowledge_base_chunks", ["kb_id"])
    op.create_index("ix_kbchunk_document_id", "knowledge_base_chunks", ["document_id"])
    op.create_index(
        "ix_kbchunk_kb_id_chunk_index",
        "knowledge_base_chunks",
        ["kb_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_table("knowledge_base_chunks")
    op.drop_table("knowledge_base_documents")
    op.drop_table("knowledge_bases")
