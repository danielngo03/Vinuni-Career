"""Add avatar_path to student_profiles.

Revision ID: 0034_student_avatar
Revises: 0033_ai_assistant_sessions
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_student_avatar"
down_revision = "0033_ai_assistant_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "student_profiles",
        sa.Column("avatar_path", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("student_profiles", "avatar_path")
