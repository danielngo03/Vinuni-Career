"""student_profiles: core profile + education/experience/skills/links

Phase 1f: the ``student_profiles`` module owns the canonical student profile
aggregate — the ``student_profiles`` row plus its child collections
(``student_education``, ``student_experience``, ``student_skills``,
``student_links``). See ``docs/DATA_MODEL.md`` §6 and the module model docstring
for the documented column reconciliation (per-field privacy folded into the
profile row; ``JsonType`` arrays for cross-database builds; namespaced child
tables).

Postgres-only constructs are guarded by ``is_postgres``:

- partial indexes (``WHERE deleted_at IS NULL``) for active-row lookups
- the partial unique index on (student_id, name) for active skills
- ``set_updated_at`` triggers (the function is created in ``0001_baseline``)

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration.

Revision ID: 0007_student_profiles
Revises: 0006_recruitment
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_student_profiles"
down_revision: str | None = "0006_recruitment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES_WITH_UPDATED_AT = (
    "student_profiles",
    "student_education",
    "student_experience",
    "student_skills",
    "student_links",
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
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB() if is_postgres else sa.JSON()

    # --------------------------------------------------------- student_profiles
    op.create_table(
        "student_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("headline", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("location_city", sa.String(100), nullable=True),
        sa.Column("location_country", sa.String(100), nullable=False,
                  server_default="Vietnam"),
        sa.Column("major", sa.String(200), nullable=True),
        sa.Column("degree_level", sa.String(30), nullable=True),
        sa.Column("graduation_year", sa.SmallInteger(), nullable=True),
        sa.Column("profile_visibility", sa.String(20), nullable=False,
                  server_default="vinuni_only"),
        sa.Column("show_email", sa.String(20), nullable=False,
                  server_default="invited"),
        sa.Column("show_phone", sa.String(20), nullable=False,
                  server_default="hidden"),
        sa.Column("is_open_to_work", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("open_to_work_types", json_type, nullable=False,
                  server_default=sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'")),
        sa.Column("profile_completion", sa.SmallInteger(), nullable=False,
                  server_default="0"),
        *_ts_columns(),
        sa.UniqueConstraint("user_id", name="uq_student_profiles_user"),
    )

    # -------------------------------------------------------- student_education
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

    # ------------------------------------------------------- student_experience
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
        sa.Column("skills_used", json_type, nullable=False,
                  server_default=sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'")),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        *_ts_columns(),
    )

    # ----------------------------------------------------------- student_skills
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

    # ------------------------------------------------------------ student_links
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
        # Discovery support for passive search (visible, active, open-to-work).
        op.create_index(
            "idx_student_profiles_visibility", "student_profiles",
            ["profile_visibility", "is_open_to_work"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )

        for table in _TABLES_WITH_UPDATED_AT:
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


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table in _TABLES_WITH_UPDATED_AT:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
        op.drop_index("idx_student_profiles_visibility", table_name="student_profiles")

    op.drop_index("idx_student_links_profile", table_name="student_links")
    op.drop_index("idx_student_skills_profile", table_name="student_skills")
    op.drop_index("idx_student_experience_profile", table_name="student_experience")
    op.drop_index("idx_student_education_profile", table_name="student_education")

    op.drop_table("student_links")
    op.drop_table("student_skills")
    op.drop_table("student_experience")
    op.drop_table("student_education")
    op.drop_table("student_profiles")
