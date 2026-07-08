"""Add multi-location JSONB column to jobs and max_team_members to organizations.

Revision ID: 0032_jobs_multi_location
Revises: 0031_reviews_helpfulness
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0032_jobs_multi_location"
down_revision = "0031_reviews_helpfulness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Multi-location array for job postings.
    op.add_column(
        "jobs",
        sa.Column(
            "locations",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    # Partner seat cap per subscription tier (default 4 for free accounts).
    op.add_column(
        "organizations",
        sa.Column(
            "max_team_members",
            sa.Integer(),
            nullable=False,
            server_default="4",
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "locations")
    op.drop_column("organizations", "max_team_members")
