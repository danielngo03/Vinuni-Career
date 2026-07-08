"""cv_ai_suggestions: pending AI CV suggestion diffs

Adds the ``cv_ai_suggestions`` table (``docs/CV_STUDIO_SPEC.md`` §6,
``docs/DATA_MODEL.md``): a reviewable, non-destructive AI diff that is applied to
a CV only on explicit acceptance (which creates a new ``cv_versions`` row). The
``diff_json`` payload is metadata + grounded content only and never contains
provider/model/token/prompt internals.

``job_id`` is a bare UUID (no FK) to avoid coupling ``documents`` ->
``opportunities``; ``target_section_id`` / ``applied_version_id`` use ``SET NULL``
so suggestion history survives section/version churn.

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration.

Revision ID: 0008_cv_ai_suggestions
Revises: 0007_student_profiles
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_cv_ai_suggestions"
down_revision: str | None = "0007_student_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB() if is_postgres else sa.JSON()

    op.create_table(
        "cv_ai_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("cv_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("target_section_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_sections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("diff_json", json_type, nullable=False),
        sa.Column("credits_charged", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("accept_idempotency_key", sa.String(200), nullable=True),
        sa.Column("applied_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cv_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cv_id", "idempotency_key", name="uq_cv_ai_suggestions_idem"),
    )
    op.create_index(
        "ix_cv_ai_suggestions_cv_id", "cv_ai_suggestions", ["cv_id"]
    )
    op.create_index(
        "ix_cv_ai_suggestions_requested_by", "cv_ai_suggestions", ["requested_by"]
    )
    op.create_index(
        "ix_cv_ai_suggestions_cv_status", "cv_ai_suggestions", ["cv_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_cv_ai_suggestions_cv_status", table_name="cv_ai_suggestions")
    op.drop_index("ix_cv_ai_suggestions_requested_by", table_name="cv_ai_suggestions")
    op.drop_index("ix_cv_ai_suggestions_cv_id", table_name="cv_ai_suggestions")
    op.drop_table("cv_ai_suggestions")
