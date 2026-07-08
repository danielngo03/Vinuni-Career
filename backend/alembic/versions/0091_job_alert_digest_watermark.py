"""job_alerts.last_digest_at — scheduled email-digest watermark (WS-15, Task N).

Adds an independent watermark for the scheduled EMAIL job-alert digest so it can
find "newly-matched jobs since the last digest" without clobbering the real-time
in-app match nudge's own ``last_sent_at`` watermark. Nullable (never-digested
alerts fall back to a bounded lookback window in the sweep).

Chained after ``0090_ad_placement_metrics_daily``.

Revision ID: 0091_job_alert_digest_watermark
Revises: 0090_ad_placement_metrics_daily
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0091_job_alert_digest_watermark"
down_revision: str | None = "0090_ad_placement_metrics_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_alerts",
        sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_alerts", "last_digest_at")
