"""Add persisted adaptive AI interview sessions and turns."""

from __future__ import annotations

from sqlalchemy import inspect

from alembic import op
from app.platform.database import models  # noqa: F401
from app.platform.database.session import Base

revision = "20260622_0005"
down_revision = "20260618_0004"
branch_labels = None
depends_on = None

TABLES = ("ai_interview_sessions", "ai_interview_turns")


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
