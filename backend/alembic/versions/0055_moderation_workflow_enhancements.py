"""Moderation workflow enhancements: claim/assign, SLA due-by, structured
reason codes for jobs, events, and sponsored placements.

Revision ID: 0055_moderation_workflow_enhancements
Revises: 0054_otp_and_onboarding
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055_moderation_workflow_enhancements"
down_revision = "0054_otp_and_onboarding"
branch_labels = None
depends_on = None

_TABLES = ("jobs", "events", "sponsored_placements")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table, sa.Column("moderation_reason_code", sa.String(30), nullable=True)
        )
        op.add_column(
            table, sa.Column("due_by", sa.DateTime(timezone=True), nullable=True)
        )
        op.add_column(
            table, sa.Column("claimed_by", sa.Uuid(), nullable=True)
        )
        op.add_column(
            table, sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True)
        )
        op.create_foreign_key(
            f"fk_{table}_claimed_by_users",
            table,
            "users",
            ["claimed_by"],
            ["id"],
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"fk_{table}_claimed_by_users", table, type_="foreignkey")
        op.drop_column(table, "claimed_at")
        op.drop_column(table, "claimed_by")
        op.drop_column(table, "due_by")
        op.drop_column(table, "moderation_reason_code")
