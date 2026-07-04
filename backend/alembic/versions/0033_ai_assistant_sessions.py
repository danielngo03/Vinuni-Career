"""AI assistant chat sessions and messages.

Revision ID: 0033_ai_assistant_sessions
Revises: 0032_jobs_multi_location
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_ai_assistant_sessions"
down_revision = "0032_jobs_multi_location"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("persona", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("ix_chat_sessions_last_message_at", "chat_sessions", ["last_message_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),  # user | assistant | tool_call | tool_result
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=True),
        sa.Column("tool_args", sa.JSON(), nullable=True),
        sa.Column("tool_result", sa.JSON(), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_created_at", "chat_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
