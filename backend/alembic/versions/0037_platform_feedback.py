"""Add user_feedback table for in-app platform feedback submissions.

Revision ID: 0037_platform_feedback
Revises: 0036_job_application_invitations
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_platform_feedback"
down_revision = "0036_job_application_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_feedback_user_id", "user_feedback", ["user_id"])
    op.create_index("ix_user_feedback_created_at", "user_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_feedback_created_at", table_name="user_feedback")
    op.drop_index("ix_user_feedback_user_id", table_name="user_feedback")
    op.drop_table("user_feedback")
