"""ad_placement_metrics_daily — per-campaign advertising analytics read model (WS-13, Task P).

A genuine per ``(placement_id, metric_date)`` AGGREGATE projection of the
privacy-safe ``discovery_events`` ledger, following the
``partner_job_metrics_daily`` / ``job_competition_daily`` projection pattern. It
powers the partner campaign-analytics endpoint (impressions / clicks / CTR /
apply-starts / cost-per-apply-start) without scanning the event ledger on every
read. Aggregates only — no viewer/session/candidate id, no PII. ``org_id`` is
denormalized so a partner-scoped read enforces tenant isolation without a join.

Chained after ``0089_interview_sim_sessions``.

Revision ID: 0090_ad_placement_metrics_daily
Revises: 0089_interview_sim_sessions
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0090_ad_placement_metrics_daily"
down_revision: str | None = "0089_interview_sim_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ad_placement_metrics_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("placement_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("apply_starts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("save_intents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "event_register_intents",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
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
        sa.ForeignKeyConstraint(
            ["placement_id"], ["sponsored_placements.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "placement_id", "metric_date", name="uq_ad_placement_metrics_daily"
        ),
    )
    op.create_index(
        op.f("ix_ad_placement_metrics_daily_placement_id"),
        "ad_placement_metrics_daily",
        ["placement_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ad_placement_metrics_daily_org_id"),
        "ad_placement_metrics_daily",
        ["org_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ad_placement_metrics_daily_metric_date"),
        "ad_placement_metrics_daily",
        ["metric_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ad_placement_metrics_daily_metric_date"),
        table_name="ad_placement_metrics_daily",
    )
    op.drop_index(
        op.f("ix_ad_placement_metrics_daily_org_id"),
        table_name="ad_placement_metrics_daily",
    )
    op.drop_index(
        op.f("ix_ad_placement_metrics_daily_placement_id"),
        table_name="ad_placement_metrics_daily",
    )
    op.drop_table("ad_placement_metrics_daily")
