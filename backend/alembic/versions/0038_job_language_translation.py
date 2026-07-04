"""Add language_code to jobs and job_translations cache table.

Revision ID: 0038_job_language_translation
Revises: 0037_platform_feedback
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_job_language_translation"
down_revision = "0037_platform_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "language_code",
            sa.String(10),
            nullable=False,
            server_default="en",
        ),
    )

    op.create_table(
        "job_translations",
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("target_lang", sa.String(10), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("benefits", sa.Text(), nullable=True),
        sa.Column("translated_by", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("job_id", "target_lang"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_job_translations_job_id", "job_translations", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_translations_job_id", table_name="job_translations")
    op.drop_table("job_translations")
    op.drop_column("jobs", "language_code")
