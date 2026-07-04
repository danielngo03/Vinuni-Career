"""Add ordered fallback-provider chain to AI model aliases (AI_PRODUCT_SPEC §5.2)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049_ai_model_alias_fallback_chain"
down_revision = "0048_workflow_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_model_aliases",
        sa.Column("fallback_provider_names", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_model_aliases", "fallback_provider_names")
