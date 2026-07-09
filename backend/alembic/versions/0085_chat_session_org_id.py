"""chat_sessions.org_id — org-scope a partner (recruiter) chat session.

Additive migration for the partner AI overhaul: capture the acting principal's
org context on the chat session so a partner chat can be org-scoped and audited
at the table level. NULL for students / any principal without an org — no
behaviour change for existing sessions (no backfill required).

Revision ID: 0085_chat_session_org_id
Revises: 0084_ai_energy_accounts_and_usage_org
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0085_chat_session_org_id"
down_revision: str | None = "0084_ai_energy_accounts_and_usage_org"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "org_id")
