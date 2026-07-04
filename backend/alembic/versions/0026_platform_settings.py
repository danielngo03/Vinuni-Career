"""platform_settings: singleton row for admin-controlled self-hosted font selection.

Admin selects a font_key from the self-hosted catalogue (Plus Jakarta Sans, Inter,
Be Vietnam Pro, Manrope, Nunito, Lexend). NULL means the platform default
(Plus Jakarta Sans). No Google Fonts URLs are stored — all fonts are served locally.

Revision ID: 0026_platform_settings
Revises: 0025_company_reviews_and_ratings
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_platform_settings"
down_revision = "0025_company_reviews_and_ratings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("font_key", sa.String(50), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope"),
    )
    op.execute(
        "INSERT INTO platform_settings (id, scope) "
        "VALUES (gen_random_uuid(), 'platform') "
        "ON CONFLICT (scope) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
