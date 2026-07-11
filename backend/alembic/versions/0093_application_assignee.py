"""applications candidate ownership (assignee) for multi-person recruiting teams.

Adds durable candidate ownership so an enterprise recruiting team can route each
candidate to an accountable recruiter, filter by "assigned to me", and drive an
SLA/worklist. Distinct from ``candidate_stages.entered_by`` (who last moved the
card) — this is the standing owner.

- ``assigned_to_membership_id`` UUID NULL FK -> memberships.id (SET NULL on member
  removal, so a departed recruiter's candidates surface as unassigned, never
  dangling)
- ``assigned_at``               TIMESTAMPTZ NULL (when ownership was last set)
- index ``ix_applications_assigned_to`` on (assigned_to_membership_id)

Backfill: existing rows stay unassigned (NULL) — assignment is an opt-in team
workflow, never retroactively invented.

Revision ID: 0091_application_assignee
Revises: 0092_mock_interview_hardening
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0093_application_assignee"
down_revision: str | None = "0092_mock_interview_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_applications_assigned_to"
_FK = "fk_applications_assigned_to_membership_id"


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "assigned_to_membership_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "applications",
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        _FK,
        "applications",
        "memberships",
        ["assigned_to_membership_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        _INDEX,
        "applications",
        ["assigned_to_membership_id"],
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="applications")
    op.drop_constraint(_FK, "applications", type_="foreignkey")
    op.drop_column("applications", "assigned_at")
    op.drop_column("applications", "assigned_to_membership_id")
