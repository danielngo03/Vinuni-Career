"""reviews_helpfulness: helpful votes + partner response on company_reviews.

Revision ID: 0031_reviews_helpfulness
Revises: 0030_saved_jobs
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_reviews_helpfulness"
down_revision = "0030_saved_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add helpfulness counter + partner response to existing table.
    op.add_column(
        "company_reviews",
        sa.Column("helpful_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "company_reviews",
        sa.Column("partner_response", sa.Text(), nullable=True),
    )
    op.add_column(
        "company_reviews",
        sa.Column(
            "partner_response_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # One vote per (voter, review). helpful_count is a denormalized cache.
    op.create_table(
        "review_helpful_votes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_id", sa.Uuid(), nullable=False),
        sa.Column("voter_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["review_id"], ["company_reviews.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["voter_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "voter_id", name="uq_review_helpful_voter"),
    )
    op.create_index(
        "ix_review_helpful_votes_review_id",
        "review_helpful_votes",
        ["review_id"],
    )
    op.create_index(
        "ix_review_helpful_votes_voter_id",
        "review_helpful_votes",
        ["voter_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_helpful_votes_voter_id", "review_helpful_votes")
    op.drop_index("ix_review_helpful_votes_review_id", "review_helpful_votes")
    op.drop_table("review_helpful_votes")
    op.drop_column("company_reviews", "partner_response_at")
    op.drop_column("company_reviews", "partner_response")
    op.drop_column("company_reviews", "helpful_count")
