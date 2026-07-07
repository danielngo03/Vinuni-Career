"""ai_usage_daily: pre-aggregated rollup for AI cost/usage dashboards.

Grain: day × task_type × provider × model × org_id.
Provider and model default to empty string so the unique constraint
never contains NULLs (NULL equality is unreliable across databases).

Populated by ``app/ai/observability/ops_recorder.record_ops_event`` via a
read-modify-write upsert pattern that is safe on both SQLite (tests) and
PostgreSQL (production).

See ``docs/AI_PRODUCT_SPEC.md`` §5.6 and ``app/ai/observability/models.py``.

Revision ID: 0078_ai_usage_daily
Revises: 0077_ai_ops_event
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0078_ai_usage_daily"
down_revision: str | None = "0077_ai_ops_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_daily",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "day",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column(
            "provider",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "model",
            sa.String(128),
            nullable=False,
            server_default="",
        ),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "requests",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "errors",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "fallbacks",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "blocked",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(12, 7),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "latency_ms_sum",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "latency_ms_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.UniqueConstraint(
            "day",
            "task_type",
            "provider",
            "model",
            "org_id",
            name="uq_ai_usage_daily_grain",
        ),
    )

    op.create_index(
        "ix_ai_usage_daily_day",
        "ai_usage_daily",
        ["day"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_daily_day", table_name="ai_usage_daily")
    op.drop_table("ai_usage_daily")
