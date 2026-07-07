"""student_profiles: identity-only profile (drop career columns + child tables)

Owner decision (2026-07-06): the student profile is identity-only. All career
content — education, experience, skills, headline/summary, major/degree — now
lives exclusively in the student's CVs (``documents`` module). Recruiters view
CVs, never a separate career profile. The only career signal the profile keeps is
the ``is_open_to_work`` boolean.

Upgrade:
- Drop 7 ``student_profiles`` columns: ``headline``, ``summary``, ``major``,
  ``degree_level``, ``graduation_year``, ``open_to_work_types``,
  ``profile_completion``.
- Drop the 4 child tables: ``student_links`` / ``student_skills`` /
  ``student_experience`` / ``student_education`` (dropped child-first so the
  ``student_profiles`` FKs on them go away cleanly, though ``student_profiles``
  itself is retained).

Downgrade re-creates a reasonable reconstruction of the prior shape (columns
nullable/defaulted, child tables with their prior columns, Postgres partial
indexes + ``set_updated_at`` triggers). Data in dropped columns/tables is not
recoverable — this is a structural, not data-preserving, reversal.

Revision ID: 0069_identity_only_student_profile
Revises: 0068_remove_cv_template_is_premium
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0069_identity_only_student_profile"
down_revision: str | None = "0068_remove_cv_template_is_premium"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ``student_profiles`` columns removed by this migration (upgrade order = drop order).
_REMOVED_PROFILE_COLUMNS = (
    "headline",
    "summary",
    "major",
    "degree_level",
    "graduation_year",
    "open_to_work_types",
    "profile_completion",
)

# Child tables removed by this migration (child-first drop order).
_CHILD_TABLES = (
    "student_links",
    "student_skills",
    "student_experience",
    "student_education",
)


def _ts_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # --- child tables -------------------------------------------------------
    if is_postgres:
        for table in _CHILD_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
        for idx, table in (
            ("idx_student_links_profile", "student_links"),
            ("idx_student_skills_profile", "student_skills"),
            ("idx_student_experience_profile", "student_experience"),
            ("idx_student_education_profile", "student_education"),
        ):
            op.execute(f"DROP INDEX IF EXISTS {idx};")

    for table in _CHILD_TABLES:
        op.drop_table(table)

    # --- student_profiles columns ------------------------------------------
    for column in _REMOVED_PROFILE_COLUMNS:
        op.drop_column("student_profiles", column)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB() if is_postgres else sa.JSON()
    json_default = sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'")

    # --- student_profiles columns (re-added nullable/defaulted) -------------
    op.add_column(
        "student_profiles", sa.Column("headline", sa.String(255), nullable=True)
    )
    op.add_column(
        "student_profiles", sa.Column("summary", sa.Text(), nullable=True)
    )
    op.add_column(
        "student_profiles", sa.Column("major", sa.String(200), nullable=True)
    )
    op.add_column(
        "student_profiles", sa.Column("degree_level", sa.String(30), nullable=True)
    )
    op.add_column(
        "student_profiles", sa.Column("graduation_year", sa.SmallInteger(), nullable=True)
    )
    op.add_column(
        "student_profiles",
        sa.Column("open_to_work_types", json_type, nullable=False,
                  server_default=json_default),
    )
    op.add_column(
        "student_profiles",
        sa.Column("profile_completion", sa.SmallInteger(), nullable=False,
                  server_default="0"),
    )

    # --- child tables (prior shape) ----------------------------------------
    op.create_table(
        "student_education",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("institution", sa.String(255), nullable=False),
        sa.Column("degree", sa.String(100), nullable=True),
        sa.Column("field_of_study", sa.String(200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gpa", sa.Numeric(3, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        *_ts_columns(),
    )

    op.create_table(
        "student_experience",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("employment_type", sa.String(30), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("skills_used", json_type, nullable=False, server_default=json_default),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        *_ts_columns(),
    )

    op.create_table(
        "student_skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("proficiency", sa.SmallInteger(), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        *_ts_columns(),
        sa.UniqueConstraint("student_id", "name", name="uq_student_skill_name"),
    )

    op.create_table(
        "student_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("student_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("student_profiles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        *_ts_columns(),
    )

    if is_postgres:
        op.create_index(
            "idx_student_education_profile", "student_education", ["student_id"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_student_experience_profile", "student_experience", ["student_id"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_student_skills_profile", "student_skills", ["student_id"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_student_links_profile", "student_links", ["student_id"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        for table in _CHILD_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
            op.execute(
                f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
            )
    else:
        op.create_index(
            "idx_student_education_profile", "student_education", ["student_id"]
        )
        op.create_index(
            "idx_student_experience_profile", "student_experience", ["student_id"]
        )
        op.create_index("idx_student_skills_profile", "student_skills", ["student_id"])
        op.create_index("idx_student_links_profile", "student_links", ["student_id"])
