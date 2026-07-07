"""scheduler_job_runs: persistent run history for scheduled jobs.

One row per completed job execution. Enables the platform admin health
console to surface last-run status, duration, and result per job without
keeping in-memory state across restarts.

Revision ID: 0080_scheduler_job_runs
Revises: 0079_ai_settings_per_org_budget
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0080_scheduler_job_runs"
down_revision: str | None = "0079_ai_settings_per_org_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduler_job_runs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("job_name", sa.String(200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "result",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Primary access pattern: latest run per job (job_name, started_at DESC).
    op.create_index(
        "ix_scheduler_job_runs_job_name_started_at",
        "scheduler_job_runs",
        ["job_name", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduler_job_runs_job_name_started_at",
        table_name="scheduler_job_runs",
    )
    op.drop_table("scheduler_job_runs")
