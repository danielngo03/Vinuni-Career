"""ai_billable_usage.department_id + ai_capacity_requests — university control plane.

Additive migration for the university AI energy governance (P1):

1. ``ai_billable_usage.department_id`` (+ ``(department_id, created_at)`` index) —
   attribute each billable AI charge to the acting member's primary department so
   department-level energy ceilings + read-models can be computed.
2. ``ai_capacity_requests`` — the university capacity-request workflow: a staff
   member asks the superadmin to distribute more weekly AI energy (approve → raise
   the target ``AiEnergyAccount`` ceiling; deny). University energy is
   DISTRIBUTION, not billing.

Revision ID: 0085_ai_capacity_requests_and_usage_department
Revises: 0084_ai_energy_accounts_and_usage_org
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0085_ai_capacity_requests_and_usage_department"
down_revision: str | None = "0084_ai_energy_accounts_and_usage_org"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. department attribution on the billable-usage ledger.
    op.add_column(
        "ai_billable_usage",
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_ai_billable_usage_department_id_created_at",
        "ai_billable_usage",
        ["department_id", "created_at"],
    )

    # 2. university capacity-request workflow.
    op.create_table(
        "ai_capacity_requests",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("requested_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_units", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column("decided_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_ai_capacity_requests_status_created",
        "ai_capacity_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_ai_capacity_requests_requested_by",
        "ai_capacity_requests",
        ["requested_by", "created_at"],
    )
    op.create_index(
        "ix_ai_capacity_requests_org",
        "ai_capacity_requests",
        ["org_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_capacity_requests_org", table_name="ai_capacity_requests"
    )
    op.drop_index(
        "ix_ai_capacity_requests_requested_by", table_name="ai_capacity_requests"
    )
    op.drop_index(
        "ix_ai_capacity_requests_status_created", table_name="ai_capacity_requests"
    )
    op.drop_table("ai_capacity_requests")
    op.drop_index(
        "ix_ai_billable_usage_department_id_created_at",
        table_name="ai_billable_usage",
    )
    op.drop_column("ai_billable_usage", "department_id")
