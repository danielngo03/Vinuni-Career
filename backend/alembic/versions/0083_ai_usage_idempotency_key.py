"""ai_usage_log.idempotency_key: no-double-charge dedup key for the AI ledger.

Additive + nullable. A caller-supplied key lets a retried logical AI operation
reuse its existing ledger row instead of writing a second billable row
(AI_PRODUCT_SPEC §5.4; CLAUDE.md AI usage accounting rule). The UNIQUE constraint
enforces the guard at the DB level; multiple NULLs are permitted (PostgreSQL
treats NULLs as distinct), so calls that opt out of idempotency are unaffected.

Revision ID: 0083_ai_usage_idempotency_key
Revises: 0082_alert_rules_incidents
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0083_ai_usage_idempotency_key"
down_revision: str | None = "0082_alert_rules_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_usage_log",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_ai_usage_log_idempotency_key", "ai_usage_log", ["idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ai_usage_log_idempotency_key", "ai_usage_log", type_="unique"
    )
    op.drop_column("ai_usage_log", "idempotency_key")
