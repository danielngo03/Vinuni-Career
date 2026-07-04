"""workflow engine tables

Revision ID: 0048_workflow_engine
Revises: 0047_ai_provider_encrypted_keys
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0048_workflow_engine"
down_revision = "0047_ai_provider_encrypted_keys"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "workflow_flows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.String(length=60), nullable=False),
        sa.Column("graph", _JSON, nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workflow_flows_trigger_status",
        "workflow_flows",
        ["trigger_type", "status"],
    )

    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "flow_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_flows.id"),
            nullable=False,
        ),
        sa.Column("trigger_event", _JSON, nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "node_logs", _JSON, nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.create_index(
        "ix_workflow_executions_idempotency",
        "workflow_executions",
        ["flow_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_executions_idempotency", table_name="workflow_executions")
    op.drop_table("workflow_executions")
    op.drop_index("ix_workflow_flows_trigger_status", table_name="workflow_flows")
    op.drop_table("workflow_flows")
