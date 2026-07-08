"""Add ai_usage_log table for per-request AI cost tracking.

Implements mandatory cost observability per ``docs/AI_PRODUCT_SPEC.md`` §5.4.
The table is append-only. It stores only metadata: task type, internal model
alias, success flag, char-length buckets, optional user/session UUID, and an
optional cost estimate.

Never stored: provider name, real model name, API key, prompt text, response
text, PII, IP address, raw token counts.

Revision ID: 0040_ai_usage_log
Revises: 0039_job_embeddings
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_ai_usage_log"
down_revision = "0039_job_embeddings"
branch_labels = None
depends_on = None

_TABLE = "ai_usage_log"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("model_alias", sa.String(64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("prompt_chars_bucket", sa.String(16), nullable=True),
        sa.Column("completion_chars_bucket", sa.String(16), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 7), nullable=True),
    )

    op.create_index(
        "ix_ai_usage_log_created_at",
        _TABLE,
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_ai_usage_log_task_type",
        _TABLE,
        ["task_type", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_log_task_type", table_name=_TABLE)
    op.drop_index("ix_ai_usage_log_created_at", table_name=_TABLE)
    op.drop_table(_TABLE)
