"""ai_energy_accounts + ai_usage_log.org_id — partner AI energy metering.

Additive migration for the AI energy meter (partner overhaul P1):

1. ``ai_usage_log.org_id`` — attribute each provider call to a partner org so
   per-org request/cost metering is possible (the log previously carried only
   ``user_id``/``session_id``).
2. ``ai_energy_accounts`` — weekly allowance CEILING override + non-resetting
   top-up WALLET per (org | department | user) scope. Consumption is NOT stored
   here; it is summed on demand from ``ai_billable_usage``.

Revision ID: 0084_ai_energy_accounts_and_usage_org
Revises: 0083_ai_billable_usage
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0084_ai_energy_accounts_and_usage_org"
down_revision: str | None = "0083_ai_billable_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. org attribution on the PII-safe usage log.
    op.add_column(
        "ai_usage_log",
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_ai_usage_log_org_id_created_at",
        "ai_usage_log",
        ["org_id", "created_at"],
    )

    # 2. energy allowance + wallet per scope.
    op.create_table(
        "ai_energy_accounts",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("weekly_allowance_units", sa.Integer(), nullable=True),
        sa.Column(
            "wallet_units", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "scope_type", "scope_id", name="uq_ai_energy_accounts_scope"
        ),
    )
    op.create_index(
        "ix_ai_energy_accounts_org_id", "ai_energy_accounts", ["org_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_energy_accounts_org_id", table_name="ai_energy_accounts")
    op.drop_table("ai_energy_accounts")
    op.drop_index("ix_ai_usage_log_org_id_created_at", table_name="ai_usage_log")
    op.drop_column("ai_usage_log", "org_id")
