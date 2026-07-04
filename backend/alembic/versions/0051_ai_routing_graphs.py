"""ai provider/model routing canvas tables

Revision ID: 0051_ai_routing_graphs
Revises: 0050_ai_workforce_runs
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0051_ai_routing_graphs"
down_revision = "0050_ai_workforce_runs"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "ai_routing_graphs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_family", sa.String(length=20), nullable=False),
        sa.Column("graph", _JSON, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "compiled_alias_id", sa.Uuid(), sa.ForeignKey("ai_model_aliases.id"), nullable=True
        ),
    )
    op.create_index(
        "ix_ai_routing_graphs_task_family_status", "ai_routing_graphs", ["task_family", "status"]
    )

    op.create_table(
        "ai_routing_graph_activations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "graph_id", sa.Uuid(), sa.ForeignKey("ai_routing_graphs.id"), nullable=False
        ),
        sa.Column("graph_version", sa.Integer(), nullable=False),
        sa.Column("activated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "activated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("previous_active_graph_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ai_routing_graph_activations")
    op.drop_index("ix_ai_routing_graphs_task_family_status", table_name="ai_routing_graphs")
    op.drop_table("ai_routing_graphs")
