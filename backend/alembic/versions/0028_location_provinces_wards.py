"""location_provinces_wards: read-only reference tables for provinces and wards.

Revision ID: 0028_location_provinces_wards
Revises: 0027_industry_taxonomy
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_location_provinces_wards"
down_revision = "0027_industry_taxonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provinces",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("is_central", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("code"),
        sa.UniqueConstraint("slug", name="uq_provinces_slug"),
    )

    op.create_table(
        "wards",
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(130), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("province_code", sa.String(10), nullable=False),
        sa.PrimaryKeyConstraint("code"),
        sa.ForeignKeyConstraint(
            ["province_code"],
            ["provinces.code"],
            ondelete="RESTRICT",
            name="fk_wards_province_code",
        ),
    )
    op.create_index("ix_wards_province_code", "wards", ["province_code"])
    op.create_index("ix_wards_slug", "wards", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_wards_slug", table_name="wards")
    op.drop_index("ix_wards_province_code", table_name="wards")
    op.drop_table("wards")
    op.drop_table("provinces")
