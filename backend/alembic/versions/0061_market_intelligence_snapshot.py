"""dashboards: market_intelligence_snapshots (B-558 read-model governance)

Singleton snapshot table (``id=1``) backing the market-intelligence read model:
source is ``opportunities.job_read_facade.market_aggregates``, refresh is a
scheduled sweep (``dashboards.market_intelligence_refresh_sweep``), and a read
falls back to a live recompute (persisting a fresh snapshot) when the stored
row is missing or older than ``market_intelligence_stale_after_seconds``. See
``app.modules.dashboards.application.snapshot_service`` for the full contract.

Revision ID: 0061_market_intelligence_snapshot
Revises: 0060_platform_trust
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061_market_intelligence_snapshot"
down_revision: str | None = "0060_platform_trust"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    now_default = sa.text("NOW()") if is_postgres else sa.func.now()

    op.create_table(
        "market_intelligence_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report", json_type, nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres
                  else sa.text("'{}'")),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now_default),
    )


def downgrade() -> None:
    op.drop_table("market_intelligence_snapshots")
