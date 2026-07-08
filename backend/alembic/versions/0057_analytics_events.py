"""analytics: analytics_events (B-548 platform-wide product-analytics contract)

Append-only, privacy-safe product-analytics ledger for the categories not
already covered by ``discovery_events`` (impressions/clicks/saves/ad-attribution
on discovery/ad surfaces): job/application/cv-export/ai/event/notification/
workflow facts. See ``app.modules.analytics.domain.models`` for the full
rationale and ``taxonomy.py`` for the event_type/aggregate_type vocabularies +
the properties allowlist gate enforced by the service layer.

Revision ID: 0057_analytics_events
Revises: 0056_notification_template_governance
Create Date: 2026-07-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057_analytics_events"
down_revision: str | None = "0056_notification_template_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    now_default = sa.text("NOW()") if is_postgres else sa.func.now()

    op.create_table(
        "analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(20), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("properties", json_type, nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres
                  else sa.text("'{}'")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now_default),
    )
    op.create_index("ix_analytics_events_type", "analytics_events", ["event_type"])
    op.create_index(
        "ix_analytics_events_aggregate", "analytics_events",
        ["aggregate_type", "aggregate_id"],
    )
    op.create_index(
        "ix_analytics_events_type_time", "analytics_events",
        ["event_type", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_events_type_time", table_name="analytics_events")
    op.drop_index("ix_analytics_events_aggregate", table_name="analytics_events")
    op.drop_index("ix_analytics_events_type", table_name="analytics_events")
    op.drop_table("analytics_events")
