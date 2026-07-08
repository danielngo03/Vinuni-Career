"""alert_rules_incidents: platform admin P7 — alert rules and incidents.

Additive migration. Creates two new tables:
  ``alert_rules`` — superadmin-defined threshold rules over operational metrics.
  ``incidents``   — open/acknowledged/resolved incidents opened by alert evaluation.

Revision ID: 0082_alert_rules_incidents
Revises: 0081_feature_flags
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0082_alert_rules_incidents"
down_revision: str | None = "0081_feature_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("metric", sa.String(80), nullable=False),
        sa.Column("comparison", sa.String(10), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("channels", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
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
    )

    op.create_table(
        "incidents",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("rule_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("metric", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["alert_rules.id"],
            name="fk_incidents_rule_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_incidents_status_triggered_at",
        "incidents",
        ["status", "triggered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_status_triggered_at", table_name="incidents")
    op.drop_table("incidents")
    op.drop_table("alert_rules")
