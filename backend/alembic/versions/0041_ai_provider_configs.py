"""Add ai_provider_configs and ai_model_aliases tables for multi-provider AI admin.

Revision ID: 0041
Revises: 0040
Revises: 0040_ai_usage_log
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040_ai_usage_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column(
            "provider_type",
            sa.String(30),
            nullable=False,
            server_default="openai_compatible",
        ),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_ai_provider_configs_name"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_provider_configs_name", "ai_provider_configs", ["name"])
    op.create_index("ix_ai_provider_configs_is_active", "ai_provider_configs", ["is_active"])

    op.create_table(
        "ai_model_aliases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("alias_name", sa.String(60), nullable=False),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("task_families", sa.String(200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alias_name", name="uq_ai_model_aliases_alias_name"),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_provider_configs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_model_aliases_alias_name", "ai_model_aliases", ["alias_name"])
    op.create_index("ix_ai_model_aliases_provider_id", "ai_model_aliases", ["provider_id"])
    op.create_index("ix_ai_model_aliases_is_active", "ai_model_aliases", ["is_active"])


def downgrade() -> None:
    op.drop_table("ai_model_aliases")
    op.drop_table("ai_provider_configs")
