"""search_logs: privacy-safe store for raw search queries (analytics only).

Revision ID: 0029_search_logs
Revises: 0028_location_provinces_wards
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_search_logs"
down_revision = "0028_location_provinces_wards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column(
            "locale",
            sa.String(10),
            nullable=False,
            server_default="vi",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_logs_locale_created",
        "search_logs",
        ["locale", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_search_logs_locale_created", table_name="search_logs")
    op.drop_table("search_logs")
