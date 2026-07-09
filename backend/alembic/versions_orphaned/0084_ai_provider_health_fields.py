"""Add AI provider health and alias routing fields.

Revision ID: 0084_ai_provider_health_fields
Revises: 0083_ai_billable_usage
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0084_ai_provider_health_fields"
down_revision: str | None = "0083_ai_billable_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_provider_configs",
        sa.Column("last_health_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "ai_provider_configs",
        sa.Column("last_health_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_model_aliases",
        sa.Column(
            "rotation_strategy",
            sa.String(length=20),
            nullable=False,
            server_default="priority",
        ),
    )
    op.add_column(
        "ai_model_aliases",
        sa.Column("fallback_bindings", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_model_aliases",
        sa.Column("last_health_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "ai_model_aliases",
        sa.Column("last_health_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_model_aliases", "last_health_checked_at")
    op.drop_column("ai_model_aliases", "last_health_status")
    op.drop_column("ai_model_aliases", "fallback_bindings")
    op.drop_column("ai_model_aliases", "rotation_strategy")
    op.drop_column("ai_provider_configs", "last_health_checked_at")
    op.drop_column("ai_provider_configs", "last_health_status")
