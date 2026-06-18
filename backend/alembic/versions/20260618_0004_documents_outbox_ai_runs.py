"""Add documents, outbox events, and AI run lifecycle tables.

Revision ID: 20260618_0004
Revises: 20260618_0003

The early development baseline may already contain these tables because
revision 0001 bootstrapped metadata for empty databases. Keep this migration
idempotent until the final fresh production baseline replaces the development
chain.
"""

from __future__ import annotations

from sqlalchemy import inspect

from alembic import op
from app.platform.database import models  # noqa: F401
from app.platform.database.session import Base

revision = "20260618_0004"
down_revision = "20260618_0003"
branch_labels = None
depends_on = None

TABLES = ("documents", "outbox_events", "ai_runs", "ai_run_events")


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for table_name in TABLES:
        if table_name not in existing:
            Base.metadata.tables[table_name].create(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for table_name in reversed(TABLES):
        if table_name in existing:
            op.drop_table(table_name)
