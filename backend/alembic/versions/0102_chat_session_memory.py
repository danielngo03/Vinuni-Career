"""chat_sessions: persistent rolling conversation memory.

Adds the two columns the AI-assistant persistent-memory layer needs:

- ``memory_summary``        TEXT NULL — leak-scrubbed rolling summary of the
                            oldest part of the conversation. Written by the
                            chat pipeline after a turn pushes the history past
                            the compression threshold; read at prompt-assembly
                            time so long sessions keep context without
                            re-sending (or re-summarizing) every old message.
- ``memory_message_count``  INTEGER NOT NULL DEFAULT 0 — how many leading
                            messages (in ``seq`` order) the summary already
                            covers, so each turn only summarizes the delta.

Reversible.

Revision ID: 0102_chat_session_memory
Revises: 0101_interview_plan_coverage
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0102_chat_session_memory"
down_revision: str | None = "0101_interview_plan_coverage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("memory_summary", sa.Text(), nullable=True))
    op.add_column(
        "chat_sessions",
        sa.Column(
            "memory_message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "memory_message_count")
    op.drop_column("chat_sessions", "memory_summary")
