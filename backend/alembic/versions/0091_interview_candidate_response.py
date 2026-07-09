"""interview candidate response: candidate confirm/decline/reschedule fields

Additive migration. Adds the candidate self-response columns to ``interviews`` so
a student can confirm attendance, decline, or request a reschedule of their OWN
interview (Theme D of the student-experience completion spec):

- ``candidate_response`` VARCHAR(20) NULL — ``confirmed | declined |
  reschedule_requested`` (NULL until the student responds). Distinct from the
  partner-owned ``status``; it records what the candidate said and never mutates
  the partner lifecycle.
- ``candidate_responded_at`` TIMESTAMPTZ NULL — when the candidate responded.
- ``candidate_response_note`` TEXT NULL — the candidate's own optional note.

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration; the columns exist on the ``Interview`` model for both paths.

Revision ID: 0091_interview_candidate_response
Revises: 0090_chat_export_files
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0091_interview_candidate_response"
down_revision: str | None = "0090_chat_export_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("candidate_response", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "interviews",
        sa.Column(
            "candidate_responded_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "interviews",
        sa.Column("candidate_response_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interviews", "candidate_response_note")
    op.drop_column("interviews", "candidate_responded_at")
    op.drop_column("interviews", "candidate_response")
