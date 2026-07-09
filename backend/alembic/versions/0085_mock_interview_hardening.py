"""mock interview concurrency guarantees

Adds the DB-level integrity the layered cost/ordering model in ``caps.py`` and
``session_service`` assumed but did not enforce:

- ``uq_mock_interview_one_active_per_user`` — partial UNIQUE(user_id) WHERE
  status='active' so two racing ``POST /sessions`` cannot both create a live
  session (the "1 concurrent session" cap becomes a DB guarantee, not a
  check-then-insert race).
- ``uq_mock_interview_turns_session_seq`` — UNIQUE(session_id, seq) so two
  concurrent turn writers cannot mint the same seq and corrupt the transcript.

Revision ID: 0085_mock_interview_hardening
Revises: 0084_mock_interview
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0085_mock_interview_hardening"
down_revision: str | None = "0084_mock_interview"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Turn seq: replace the non-unique index with a unique one.
    op.drop_index(
        "ix_mock_interview_turns_session_seq", table_name="mock_interview_turns"
    )
    op.create_index(
        "uq_mock_interview_turns_session_seq",
        "mock_interview_turns",
        ["session_id", "seq"],
        unique=True,
    )
    # One active session per user (partial unique).
    op.create_index(
        "uq_mock_interview_one_active_per_user",
        "mock_interview_sessions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_mock_interview_one_active_per_user",
        table_name="mock_interview_sessions",
    )
    op.drop_index(
        "uq_mock_interview_turns_session_seq", table_name="mock_interview_turns"
    )
    op.create_index(
        "ix_mock_interview_turns_session_seq",
        "mock_interview_turns",
        ["session_id", "seq"],
    )
