"""industry_taxonomy: self-referential 3-level industry / career-field table.

Revision ID: 0027_industry_taxonomy
Revises: 0026_platform_settings
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_industry_taxonomy"
down_revision = "0026_platform_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "industries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name_vi", sa.String(150), nullable=False),
        sa.Column("name_en", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["industries.id"],
            ondelete="RESTRICT",
            name="fk_industries_parent_id",
        ),
        sa.UniqueConstraint("slug", name="uq_industries_slug"),
    )
    op.create_index("ix_industries_parent_id", "industries", ["parent_id"])
    op.create_index("ix_industries_level", "industries", ["level"])
    op.create_index(
        "ix_industries_active_level",
        "industries",
        ["is_active", "level", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_industries_active_level", table_name="industries")
    op.drop_index("ix_industries_level", table_name="industries")
    op.drop_index("ix_industries_parent_id", table_name="industries")
    op.drop_table("industries")
