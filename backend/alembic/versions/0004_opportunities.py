"""opportunities: jobs + screening questions

Phase 1c: ``jobs`` (postings + lifecycle + moderation state) and
``screening_questions`` (per-job applicant questions, CASCADE on job delete).

Postgres-only constructs are guarded by ``is_postgres``:

- ``jobs.tsv_search`` full-text ``tsvector`` GENERATED column + GIN index
- GIN index on ``required_skills`` (JSONB)
- partial discovery indexes (``WHERE deleted_at IS NULL``)
- the ``set_updated_at`` trigger on ``jobs``

The SQLite unit-test path creates the schema from ORM metadata and skips these.

Revision ID: 0004_opportunities
Revises: 0003_organization_rbac
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_opportunities"
down_revision: str | None = "0003_organization_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ------------------------------------------------------------------- jobs
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("posted_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(300), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("benefits", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.String(30), nullable=False),
        sa.Column("location_type", sa.String(20), nullable=False),
        sa.Column("location_city", sa.String(100), nullable=True),
        sa.Column("location_country", sa.String(100), nullable=False,
                  server_default="Vietnam"),
        sa.Column("required_skills", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("preferred_skills", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("experience_min_years", sa.SmallInteger(), nullable=True),
        sa.Column("experience_max_years", sa.SmallInteger(), nullable=True),
        sa.Column("degree_required", sa.String(30), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(5), nullable=False,
                  server_default="VND"),
        sa.Column("salary_is_disclosed", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("headcount", sa.SmallInteger(), nullable=False,
                  server_default="1"),
        sa.Column("application_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visibility", sa.String(20), nullable=False,
                  server_default="public"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("moderation_status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("application_count", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("is_featured", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("is_sponsored", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("settings", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # ------------------------------------------------- screening_questions
    op.create_table(
        "screening_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("q_type", sa.String(20), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False,
                  server_default="0"),
    )
    op.create_index("idx_screening_job", "screening_questions", ["job_id"])

    if is_postgres:
        # Full-text search column (DB-managed; not mapped on the ORM model).
        op.execute(
            "ALTER TABLE jobs ADD COLUMN tsv_search tsvector "
            "GENERATED ALWAYS AS ("
            "to_tsvector('simple', coalesce(title,'') || ' ' || "
            "coalesce(description,''))) STORED"
        )
        op.create_index(
            "idx_jobs_org", "jobs", ["org_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_jobs_status", "jobs",
            ["status", "moderation_status", sa.text("published_at DESC")],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_jobs_visibility", "jobs", ["visibility"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_jobs_tsv", "jobs", ["tsv_search"], postgresql_using="gin",
        )
        op.create_index(
            "idx_jobs_skills", "jobs", ["required_skills"], postgresql_using="gin",
        )

        op.execute("DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs;")
        op.execute(
            "CREATE TRIGGER trg_jobs_updated_at BEFORE UPDATE ON jobs "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
    else:
        op.create_index("idx_jobs_org", "jobs", ["org_id", "status"])
        op.create_index(
            "idx_jobs_status", "jobs",
            ["status", "moderation_status", "published_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs;")
        op.drop_index("idx_jobs_skills", table_name="jobs")
        op.drop_index("idx_jobs_tsv", table_name="jobs")
        op.drop_index("idx_jobs_visibility", table_name="jobs")
        op.drop_index("idx_jobs_status", table_name="jobs")
        op.drop_index("idx_jobs_org", table_name="jobs")
    else:
        op.drop_index("idx_jobs_status", table_name="jobs")
        op.drop_index("idx_jobs_org", table_name="jobs")

    op.drop_index("idx_screening_job", table_name="screening_questions")
    op.drop_table("screening_questions")
    op.drop_table("jobs")
