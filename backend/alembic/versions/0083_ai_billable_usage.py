"""ai_billable_usage: durable, idempotent billable AI usage ledger.

Additive migration. Creates ``ai_billable_usage`` — the charge-decision source
of truth for plan/package credit limits (PRODUCT_OPERATING_MODEL.md §3.1),
distinct from ``ai_usage_log`` and ``ai_ops_event``. Unique ``idempotency_key``
makes retries/redeliveries/cache-reuse non-double-charging.

Revision ID: 0083_ai_billable_usage
Revises: 0082_alert_rules_incidents
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0083_ai_billable_usage"
down_revision: str | None = "0082_alert_rules_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_billable_usage",
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
            server_default=sa.text("now()"),
        ),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_persona", sa.String(24), nullable=False),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("billing_scope", sa.String(16), nullable=False),
        sa.Column("feature_key", sa.String(48), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=True),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("units_charged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_cost_usd", sa.Numeric(10, 7), nullable=True),
        sa.Column("result_status", sa.String(24), nullable=False),
        sa.Column("ai_usage_log_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("ai_ops_event_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_ai_billable_usage_idempotency"),
    )
    op.create_index(
        "ix_ai_billable_usage_created_at", "ai_billable_usage", ["created_at"]
    )
    op.create_index(
        "ix_ai_billable_usage_actor_user_id", "ai_billable_usage", ["actor_user_id"]
    )
    op.create_index("ix_ai_billable_usage_org_id", "ai_billable_usage", ["org_id"])
    op.create_index(
        "ix_ai_billable_usage_feature_key", "ai_billable_usage", ["feature_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_billable_usage_feature_key", table_name="ai_billable_usage")
    op.drop_index("ix_ai_billable_usage_org_id", table_name="ai_billable_usage")
    op.drop_index("ix_ai_billable_usage_actor_user_id", table_name="ai_billable_usage")
    op.drop_index("ix_ai_billable_usage_created_at", table_name="ai_billable_usage")
    op.drop_table("ai_billable_usage")
