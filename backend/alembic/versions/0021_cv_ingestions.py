"""cv_ingestions: adapter-based CV ingestion jobs

Adds the ``cv_ingestions`` table (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §5): the
product-facing ingestion state for an uploaded document — a user-safe friendly
``status`` + ``quality_code``, field-level ``review_fields`` (needs-review
markers), ``next_actions``, and ``detected_language``/``mixed_language``.

INTERNAL-only columns (``engine_family``, ``engine_version``, ``text_length``,
``error_code``, ``extracted_data``) are persisted for diagnostics/import but are
never surfaced in any user-facing response.

``imported_cv_id`` uses ``SET NULL`` so ingestion history survives a CV delete.
The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration.

Revision ID: 0021_cv_ingestions
Revises: 0020_discovery_sessions_events
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_cv_ingestions"
down_revision: str | None = "0020_discovery_sessions_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB() if is_postgres else sa.JSON()

    op.create_table(
        "cv_ingestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("quality_code", sa.String(80), nullable=True),
        sa.Column("detected_language", sa.String(10), nullable=True),
        sa.Column("mixed_language", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("text_length", sa.Integer(), nullable=True),
        sa.Column("engine_family", sa.String(60), nullable=True),
        sa.Column("engine_version", sa.String(80), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("extracted_data", json_type, nullable=True),
        sa.Column("review_fields", json_type, nullable=True),
        sa.Column("next_actions", json_type, nullable=True),
        sa.Column("imported_cv_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_cv_ingestions_document_id", "cv_ingestions", ["document_id"])
    op.create_index("ix_cv_ingestions_user_id", "cv_ingestions", ["user_id"])
    op.create_index(
        "idx_cv_ingestions_doc_recent", "cv_ingestions",
        ["document_id", sa.text("created_at DESC")],
    )

    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS trg_cv_ingestions_updated_at ON cv_ingestions;")
        op.execute(
            "CREATE TRIGGER trg_cv_ingestions_updated_at BEFORE UPDATE ON cv_ingestions "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_cv_ingestions_updated_at ON cv_ingestions;")
    op.drop_index("idx_cv_ingestions_doc_recent", table_name="cv_ingestions")
    op.drop_index("ix_cv_ingestions_user_id", table_name="cv_ingestions")
    op.drop_index("ix_cv_ingestions_document_id", table_name="cv_ingestions")
    op.drop_table("cv_ingestions")
