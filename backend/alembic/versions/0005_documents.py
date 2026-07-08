"""documents: CV Studio core (uploads, builder CVs, versions, exports, snapshots)

Phase 1d: the ``documents`` module owns uploaded CV originals, parse runs,
templates, builder CV profiles + sections + immutable versions, exports, the
signed-file access audit trail, and immutable application CV snapshots.

Postgres-only constructs are guarded by ``is_postgres``:

- partial discovery / idempotency indexes (``WHERE ... IS NULL`` / ``IS NOT NULL``)
- the partial unique index on ``application_cv_snapshots(application_id)``
- ``set_updated_at`` triggers on tables carrying ``updated_at``
- idempotent ``cv_templates`` seed (``ON CONFLICT (key) DO NOTHING``)

``application_cv_snapshots.application_id`` is a bare nullable UUID (no FK) because
the ``recruitment`` module's ``applications`` table does not exist yet; the FK +
NOT NULL are added by the recruitment migration. The SQLite unit-test path builds
the schema from ORM metadata and never runs this migration.

Revision ID: 0005_documents
Revises: 0004_opportunities
Create Date: 2026-06-27
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.documents.domain.catalog import TEMPLATE_SEEDS

revision: str = "0005_documents"
down_revision: str | None = "0004_opportunities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ---------------------------------------------------------- cv_templates
    op.create_table(
        "cv_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("name_vi", sa.String(200), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("layout_schema", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("preview_image", sa.String(1000), nullable=True),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # -------------------------------------------------------------- documents
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_type", sa.String(30), nullable=False, server_default="cv"),
        sa.Column("original_name", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("virus_scan_status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("virus_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ---------------------------------------------------------- cv_parse_runs
    op.create_table(
        "cv_parse_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("quality_code", sa.String(80), nullable=True),
        sa.Column("detected_language", sa.String(10), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("text_length", sa.Integer(), nullable=True),
        sa.Column("provider_alias", sa.String(100), nullable=True),
        sa.Column("extracted_data", postgresql.JSONB(), nullable=True),
        sa.Column("review_fields", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ----------------------------------------------------------- cv_profiles
    op.create_table(
        "cv_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="builder"),
        sa.Column("template_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("language", sa.String(10), nullable=False, server_default="vi"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("last_edited_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # ----------------------------------------------------------- cv_sections
    op.create_table(
        "cv_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("cv_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("content_json", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ----------------------------------------------------------- cv_versions
    op.create_table(
        "cv_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("cv_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("change_source", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("change_summary", sa.String(500), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("cv_id", "version_number", name="uq_cv_versions_cv_num"),
    )

    # ------------------------------------------------------------ cv_exports
    op.create_table(
        "cv_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("cv_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("export_format", sa.String(20), nullable=False, server_default="pdf"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("storage_key", sa.String(1000), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------- signed_file_accesses
    op.create_table(
        "signed_file_accesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("resource_kind", sa.String(30), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accessor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("accessor_org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("has_watermark", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("watermark_text", sa.String(500), nullable=True),
        sa.Column("signed_url_hash", sa.String(64), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # --------------------------------------------- application_cv_snapshots
    op.create_table(
        "application_cv_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cv_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("redacted_json", postgresql.JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    if is_postgres:
        op.create_index(
            "idx_documents_user", "documents", ["user_id", "doc_type"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_documents_idem", "documents", ["user_id", "idempotency_key"],
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )
        op.create_index(
            "idx_cv_parse_runs_doc", "cv_parse_runs",
            ["document_id", sa.text("created_at DESC")],
        )
        op.create_index(
            "idx_cv_profiles_user", "cv_profiles", ["user_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_cv_profiles_idem", "cv_profiles", ["user_id", "idempotency_key"],
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )
        op.create_index("idx_cv_sections_cv", "cv_sections", ["cv_id", "sort_order"])
        op.create_index(
            "idx_cv_versions_cv", "cv_versions",
            ["cv_id", sa.text("version_number DESC")],
        )
        op.create_index(
            "idx_cv_exports_cv", "cv_exports", ["cv_id", sa.text("created_at DESC")],
        )
        op.create_index(
            "idx_cv_exports_idem", "cv_exports", ["cv_id", "idempotency_key"],
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )
        op.create_index(
            "idx_file_access_resource", "signed_file_accesses",
            ["resource_kind", "resource_id", sa.text("accessed_at DESC")],
        )
        op.create_index(
            "idx_app_cv_snapshots_user", "application_cv_snapshots", ["user_id"],
        )
        op.create_index(
            "uq_app_cv_snapshots_app", "application_cv_snapshots", ["application_id"],
            unique=True, postgresql_where=sa.text("application_id IS NOT NULL"),
        )

        for table in ("cv_templates", "documents", "cv_profiles", "cv_sections"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
            op.execute(
                f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
            )

        # Idempotent template seed.
        for spec in TEMPLATE_SEEDS:
            op.execute(
                sa.text(
                    "INSERT INTO cv_templates "
                    "(id, key, name_vi, name_en, category, layout_schema, is_premium, is_active) "
                    "VALUES (gen_random_uuid(), :key, :name_vi, :name_en, :category, "
                    "CAST(:layout AS jsonb), :is_premium, TRUE) "
                    "ON CONFLICT (key) DO NOTHING"
                ).bindparams(
                    key=spec["key"],
                    name_vi=spec["name_vi"],
                    name_en=spec["name_en"],
                    category=spec["category"],
                    layout=json.dumps(spec["layout_schema"]),
                    is_premium=spec["is_premium"],
                )
            )
    else:
        op.create_index("idx_documents_user", "documents", ["user_id", "doc_type"])
        op.create_index("idx_cv_profiles_user", "cv_profiles", ["user_id", "status"])
        op.create_index("idx_cv_sections_cv", "cv_sections", ["cv_id", "sort_order"])
        # Avoid unused-import lint on the non-postgres path.
        _ = (json, uuid)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table in ("cv_templates", "documents", "cv_profiles", "cv_sections"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
        for name, table in (
            ("uq_app_cv_snapshots_app", "application_cv_snapshots"),
            ("idx_app_cv_snapshots_user", "application_cv_snapshots"),
            ("idx_file_access_resource", "signed_file_accesses"),
            ("idx_cv_exports_idem", "cv_exports"),
            ("idx_cv_exports_cv", "cv_exports"),
            ("idx_cv_versions_cv", "cv_versions"),
            ("idx_cv_sections_cv", "cv_sections"),
            ("idx_cv_profiles_idem", "cv_profiles"),
            ("idx_cv_profiles_user", "cv_profiles"),
            ("idx_cv_parse_runs_doc", "cv_parse_runs"),
            ("idx_documents_idem", "documents"),
            ("idx_documents_user", "documents"),
        ):
            op.drop_index(name, table_name=table)
    else:
        op.drop_index("idx_cv_sections_cv", table_name="cv_sections")
        op.drop_index("idx_cv_profiles_user", table_name="cv_profiles")
        op.drop_index("idx_documents_user", table_name="documents")

    op.drop_table("application_cv_snapshots")
    op.drop_table("signed_file_accesses")
    op.drop_table("cv_exports")
    op.drop_table("cv_versions")
    op.drop_table("cv_sections")
    op.drop_table("cv_profiles")
    op.drop_table("cv_parse_runs")
    op.drop_table("documents")
    op.drop_table("cv_templates")
