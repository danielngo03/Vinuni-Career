"""ai_settings: add per_org_daily_budget_usd nullable column.

Additive change — NULL means no per-org cap (unlimited, bounded only by
the platform daily_budget_usd).  The budget_guard queries this column
to enforce per-organization daily AI spend limits using the pre-aggregated
``ai_usage_daily`` rollup for low-latency lookups.

Revision ID: 0079_ai_settings_per_org_budget
Revises: 0078_ai_usage_daily
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0079_ai_settings_per_org_budget"
down_revision: str | None = "0078_ai_usage_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_settings",
        sa.Column(
            "per_org_daily_budget_usd",
            sa.Numeric(10, 2),
            nullable=True,
            comment=(
                "Per-organization daily AI spend cap in USD. "
                "NULL = no per-org cap (platform budget still applies)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_settings", "per_org_daily_budget_usd")
