"""Student affiliation + verified-student badge + verification student_kind.

Persists the three student personas (VinUni student / alumni / external) that
previously collapsed to a single ``identity.persona = 'student'``:

- ``student_profiles.affiliation``          VARCHAR(30) NOT NULL DEFAULT 'general'
  ('vinuni_student' | 'alumni' | 'external' | 'general'). The authoritative,
  surfaced VinUni-vs-external fact, written only via the affiliation facade.
- ``student_profiles.student_verified_at``  TIMESTAMPTZ NULL — verified-student
  badge source; set on successful student verification.
- ``student_verifications.student_kind``    VARCHAR(20) NULL — which persona the
  verification asserts ('vinuni_student' | 'vinuni_alumni' | 'external'); drives
  the institution-domain enforcement + resulting affiliation.

Backfill: existing rows default to ``general`` (unverified) via the column
DEFAULT; ``student_verified_at`` / ``student_kind`` stay NULL.

Revision ID: 0092_student_affiliation
Revises: 0091_interview_candidate_response
Create Date: 2026-07-09

Note: chained on top of ``0091_interview_candidate_response`` (a parallel
THEME D migration that also branched off ``0090``) to keep a single alembic head.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0092_student_affiliation"
down_revision: str | None = "0091_interview_candidate_response"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "student_profiles",
        sa.Column(
            "affiliation",
            sa.String(length=30),
            nullable=False,
            server_default="general",
        ),
    )
    op.add_column(
        "student_profiles",
        sa.Column(
            "student_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "student_verifications",
        sa.Column(
            "student_kind",
            sa.String(length=20),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("student_verifications", "student_kind")
    op.drop_column("student_profiles", "student_verified_at")
    op.drop_column("student_profiles", "affiliation")
