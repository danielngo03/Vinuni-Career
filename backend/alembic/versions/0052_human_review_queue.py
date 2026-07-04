"""human review queue for AI advisory findings (AI_PRODUCT_SPEC §9.3)

Revision ID: 0052_human_review_queue
Revises: 0051_ai_routing_graphs
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0052_human_review_queue"
down_revision = "0051_ai_routing_graphs"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "human_review_queue",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # bias_detection | content_moderation | fraud_detection | agent_loop
        sa.Column("source", sa.String(length=32), nullable=False),
        # job | jd_draft | ad | review | event | organization | profile
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="PENDING"
        ),
        sa.Column(
            "findings_json", _JSON, nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_human_review_queue_status", "human_review_queue", ["status"])
    op.create_index("ix_human_review_queue_source", "human_review_queue", ["source"])
    op.create_index("ix_human_review_queue_org_id", "human_review_queue", ["org_id"])
    op.create_index(
        "ix_human_review_queue_resource",
        "human_review_queue",
        ["resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_human_review_queue_resource", table_name="human_review_queue")
    op.drop_index("ix_human_review_queue_org_id", table_name="human_review_queue")
    op.drop_index("ix_human_review_queue_source", table_name="human_review_queue")
    op.drop_index("ix_human_review_queue_status", table_name="human_review_queue")
    op.drop_table("human_review_queue")
