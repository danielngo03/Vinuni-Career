"""mock interview sessions + turns

Creates the ``mock_interview`` module tables: student-owned practice sessions and
their text-only transcript turns. Kept fully separate from ``recruitment`` real
interviews.

Revision ID: 0084_mock_interview
Revises: 0083_ai_billable_usage
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0084_mock_interview"
down_revision: str | None = "0083_ai_billable_usage"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "mock_interview_sessions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cv_profile_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("cv_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="vi"),
        sa.Column(
            "modality", sa.String(length=16), nullable=False, server_default="voice"
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "duration_seconds", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grounding_json", _JSON, nullable=True),
        sa.Column("report_json", _JSON, nullable=True),
        sa.Column(
            "share_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider_ref", sa.String(length=64), nullable=True),
        sa.Column("model_ref", sa.String(length=64), nullable=True),
        sa.Column(
            "grounding_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_mock_interview_sessions_user_id", "mock_interview_sessions", ["user_id"]
    )
    op.create_index(
        "ix_mock_interview_sessions_user_created",
        "mock_interview_sessions",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_mock_interview_sessions_job_id", "mock_interview_sessions", ["job_id"]
    )
    op.create_index(
        "ix_mock_interview_sessions_status", "mock_interview_sessions", ["status"]
    )

    op.create_table(
        "mock_interview_turns",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("mock_interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("text_redacted", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_mock_interview_turns_session_seq",
        "mock_interview_turns",
        ["session_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mock_interview_turns_session_seq", table_name="mock_interview_turns"
    )
    op.drop_table("mock_interview_turns")
    op.drop_index(
        "ix_mock_interview_sessions_status", table_name="mock_interview_sessions"
    )
    op.drop_index(
        "ix_mock_interview_sessions_job_id", table_name="mock_interview_sessions"
    )
    op.drop_index(
        "ix_mock_interview_sessions_user_created", table_name="mock_interview_sessions"
    )
    op.drop_index(
        "ix_mock_interview_sessions_user_id", table_name="mock_interview_sessions"
    )
    op.drop_table("mock_interview_sessions")
