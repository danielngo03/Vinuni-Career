"""interview_sim_sessions + interview_sim_turns — durable interview practice (WS-6, Task K).

Makes the interview simulator persistent and STUDENT-SCOPED so a student can see a
progress/readiness trend across practice attempts (it was ephemeral before).

- ``interview_sim_sessions``: one row per practice attempt. ``job_id`` is nullable
  (``SET NULL`` on job delete) with a denormalized ``job_title`` so a student's
  history survives job removal. ``answered_count`` / ``avg_score`` are denormalized
  aggregates so the history read never scans every turn.
- ``interview_sim_turns``: one row per answered question (question + the student's
  own answer + coaching feedback). No provider/model/token/prompt internals are
  stored — only user-facing product content, owner-scoped by ``user_id``.

Chained after ``0088_recommendation_snapshots``.

Revision ID: 0089_interview_sim_sessions
Revises: 0088_recommendation_snapshots
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0089_interview_sim_sessions"
down_revision: str | None = "0088_recommendation_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_sim_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("questions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_score", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_sim_sessions_user_id", "interview_sim_sessions", ["user_id"]
    )
    op.create_index(
        "ix_interview_sim_sessions_job_id", "interview_sim_sessions", ["job_id"]
    )

    op.create_table(
        "interview_sim_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question_type", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rubric", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("praise", sa.Text(), nullable=True),
        sa.Column("improve", sa.Text(), nullable=True),
        sa.Column("hint", sa.Text(), nullable=True),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["interview_sim_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_sim_turns_session_id", "interview_sim_turns", ["session_id"]
    )
    op.create_index(
        "ix_interview_sim_turns_user_id", "interview_sim_turns", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_interview_sim_turns_user_id", table_name="interview_sim_turns")
    op.drop_index(
        "ix_interview_sim_turns_session_id", table_name="interview_sim_turns"
    )
    op.drop_table("interview_sim_turns")
    op.drop_index(
        "ix_interview_sim_sessions_job_id", table_name="interview_sim_sessions"
    )
    op.drop_index(
        "ix_interview_sim_sessions_user_id", table_name="interview_sim_sessions"
    )
    op.drop_table("interview_sim_sessions")
