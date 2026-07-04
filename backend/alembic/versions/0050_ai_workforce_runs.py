"""ai workforce runs (multi-agent coordinator/worker pattern, AI_PRODUCT_SPEC §4.2)

Revision ID: 0050_ai_workforce_runs
Revises: 0049_ai_model_alias_fallback_chain
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0050_ai_workforce_runs"
down_revision = "0049_ai_model_alias_fallback_chain"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ai_workforce_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column(
            "context_json", _JSON, nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "subtask_keys_json", _JSON, nullable=False, server_default=sa.text("'[]'")
        ),
        sa.Column(
            "subtask_results_json",
            _JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("summary_json", _JSON, nullable=True),
    )
    op.create_index(
        "ix_ai_workforce_runs_task_type", "ai_workforce_runs", ["task_type"]
    )
    op.create_index(
        "ix_ai_workforce_runs_requested_by",
        "ai_workforce_runs",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_workforce_runs_requested_by", table_name="ai_workforce_runs")
    op.drop_index("ix_ai_workforce_runs_task_type", table_name="ai_workforce_runs")
    op.drop_table("ai_workforce_runs")
