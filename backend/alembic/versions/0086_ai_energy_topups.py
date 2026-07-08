"""ai_energy_topups — manual/bank-transfer AI energy top-up purchases.

Durable purchase/audit record for a partner org (or one of its members /
departments) buying more AI energy. A ``pending`` row is created at request; a
finance/university admin (or superadmin) confirms money received and the
purchased ``units`` are credited to the target scope's ``ai_energy_accounts``
wallet. ``price_amount``/``currency`` are a REAL product price (VND), like a
subscription — the hidden AI provider cost (tokens/USD/provider/model) is never
stored here or anywhere.

Revision ID: 0086_ai_energy_topups
Revises: 0085_chat_session_org_id
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0086_ai_energy_topups"
down_revision: str | None = "0085_chat_session_org_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_energy_topups",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="VND"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("payment_reference", sa.String(120), nullable=True),
        sa.Column("requested_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("paid_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pack_code", sa.String(32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_ai_energy_topups_org_id", "ai_energy_topups", ["org_id"])
    op.create_index(
        "ix_ai_energy_topups_scope",
        "ai_energy_topups",
        ["scope_type", "scope_id"],
    )
    op.create_index("ix_ai_energy_topups_status", "ai_energy_topups", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ai_energy_topups_status", table_name="ai_energy_topups")
    op.drop_index("ix_ai_energy_topups_scope", table_name="ai_energy_topups")
    op.drop_index("ix_ai_energy_topups_org_id", table_name="ai_energy_topups")
    op.drop_table("ai_energy_topups")
