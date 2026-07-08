"""ai_ops_event: admin-only per-call operational telemetry table.

Stores one row per AI gateway call with provider, model, token counts,
latency, status, cost, and context IDs.  No prompt text or user PII
beyond optional user/org UUIDs.

See ``docs/AI_PRODUCT_SPEC.md`` §5.6 and ``app/ai/observability/models.py``.

Revision ID: 0077_ai_ops_event
Revises: 0076_ai_model_price
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077_ai_ops_event"
down_revision: str | None = "0076_ai_model_price"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_ops_event",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("alias", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="ok",
        ),
        sa.Column(
            "fallback_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "circuit_open",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("cost_usd", sa.Numeric(10, 7), nullable=True),
        sa.Column(
            "unpriced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("langfuse_trace_id", sa.String(128), nullable=True),
    )

    # Primary access patterns: time-range scans, per-org cost queries,
    # per-task dashboards, and per-model cost breakdowns.
    op.create_index(
        "ix_ai_ops_event_created_at",
        "ai_ops_event",
        ["created_at"],
    )
    op.create_index(
        "ix_ai_ops_event_org_created_at",
        "ai_ops_event",
        ["org_id", "created_at"],
    )
    op.create_index(
        "ix_ai_ops_event_task_created_at",
        "ai_ops_event",
        ["task_type", "created_at"],
    )
    op.create_index(
        "ix_ai_ops_event_model_created_at",
        "ai_ops_event",
        ["model", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_ops_event_model_created_at", table_name="ai_ops_event")
    op.drop_index("ix_ai_ops_event_task_created_at", table_name="ai_ops_event")
    op.drop_index("ix_ai_ops_event_org_created_at", table_name="ai_ops_event")
    op.drop_index("ix_ai_ops_event_created_at", table_name="ai_ops_event")
    op.drop_table("ai_ops_event")
