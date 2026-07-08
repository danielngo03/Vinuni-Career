"""add rerank model alias to ai settings

Revision ID: 0045
Revises: 0044
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_settings",
        sa.Column(
            "rerank_model_alias",
            sa.String(length=60),
            nullable=False,
            server_default="rerank_cheap",
        ),
    )
    op.alter_column("ai_settings", "rerank_model_alias", server_default=None)


def downgrade() -> None:
    op.drop_column("ai_settings", "rerank_model_alias")
