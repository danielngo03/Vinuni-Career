"""Add structured job requirements and industry links.

Revision ID: 0053_job_requirements_industry_links
Revises: 0052_human_review_queue
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0053_job_requirements_industry_links"
down_revision = "0052_human_review_queue"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("industry_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_organizations_industry_id_industries",
        "organizations",
        "industries",
        ["industry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_organizations_industry_id",
        "organizations",
        ["industry_id"],
    )

    op.add_column("jobs", sa.Column("industry_id", sa.Uuid(), nullable=True))
    op.add_column("jobs", sa.Column("seniority_level", sa.String(length=30), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "candidate_requirements",
            _JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_foreign_key(
        "fk_jobs_industry_id_industries",
        "jobs",
        "industries",
        ["industry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_industry_id", "jobs", ["industry_id"])
    op.alter_column("jobs", "candidate_requirements", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_jobs_industry_id", table_name="jobs")
    op.drop_constraint("fk_jobs_industry_id_industries", "jobs", type_="foreignkey")
    op.drop_column("jobs", "candidate_requirements")
    op.drop_column("jobs", "seniority_level")
    op.drop_column("jobs", "industry_id")

    op.drop_index("ix_organizations_industry_id", table_name="organizations")
    op.drop_constraint(
        "fk_organizations_industry_id_industries",
        "organizations",
        type_="foreignkey",
    )
    op.drop_column("organizations", "industry_id")
