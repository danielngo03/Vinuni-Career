"""add session_id to search_logs

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "search_logs",
        sa.Column("session_id", UUID(as_uuid=True), nullable=True, index=True),
    )
    # Index for per-session recent queries
    op.create_index("ix_search_logs_session_created", "search_logs", ["session_id", "created_at"])

def downgrade() -> None:
    op.drop_index("ix_search_logs_session_created", table_name="search_logs")
    op.drop_column("search_logs", "session_id")
