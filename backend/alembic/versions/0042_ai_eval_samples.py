"""Add ai_eval_samples table for 1% online sampling and human review (AI_PRODUCT_SPEC §10.2).

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_eval_samples",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("model_alias", sa.String(64), nullable=False),
        # Prompt + completion are hashed/bucketed only; raw content never stored (§15)
        sa.Column("prompt_chars_bucket", sa.String(8), nullable=False),
        sa.Column("completion_chars_bucket", sa.String(8), nullable=False),
        # Safe metadata for review
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        # Human review state
        sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("quality_score", sa.SmallInteger(), nullable=True),  # 1-5 or NULL
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_eval_samples_created_at", "ai_eval_samples", ["created_at"])
    op.create_index("ix_ai_eval_samples_task_type", "ai_eval_samples", ["task_type"])
    op.create_index("ix_ai_eval_samples_review_status", "ai_eval_samples", ["review_status"])


def downgrade() -> None:
    op.drop_table("ai_eval_samples")
