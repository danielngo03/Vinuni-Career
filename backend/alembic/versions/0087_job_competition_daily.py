"""job_competition_daily — per-job competition read model (WS-5, Task B).

A materialized projection of the caliber-of-real-applicants inputs the
student-facing competition signal needs (seats, active-application volume, and
the caliber distribution over SCORED active applicants), so the hot job-detail
read hits ONE indexed row instead of a live ``applications`` ×
``application_cv_snapshots`` multi-domain join. Grain: one CURRENT-STATE row per
``job_id`` (unique). Recomputed (upsert, overwrite in place) on each apply event
and by a nightly sweep; ``refreshed_at`` stamps freshness.

No PII, individual scores, or identities are stored — only coarse per-job
aggregates. The four ``dist_*`` buckets partition scored active applicants;
NULL-fit applicants count in ``active_applications`` but not in any bucket.

Chained after ``0086_application_snapshot_fit_score`` (the snapshot ``fit_score``
this projection aggregates).

Revision ID: 0087_job_competition_daily
Revises: 0086_application_snapshot_fit_score
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0087_job_competition_daily"
down_revision: str | None = "0086_application_snapshot_fit_score"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_competition_daily",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "active_applications", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("dist_developing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dist_mixed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dist_strong", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dist_top", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_job_competition_daily_job"),
    )
    op.create_index(
        "ix_job_competition_daily_org_id", "job_competition_daily", ["org_id"]
    )
    op.create_index(
        "ix_job_competition_daily_job_id", "job_competition_daily", ["job_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_competition_daily_job_id", table_name="job_competition_daily")
    op.drop_index("ix_job_competition_daily_org_id", table_name="job_competition_daily")
    op.drop_table("job_competition_daily")
