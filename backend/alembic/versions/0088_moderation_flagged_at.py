"""jobs.moderation_flagged_at + events.moderation_flagged_at (B-579).

The AI human-review queue surfaces items with ``moderation_status = 'flagged'``
and computes a tight human-review SLA (``ai_review_moderation_sla_hours``, 4h per
``docs/BUSINESS_LOGIC.md`` §11) anchored on *when the flag was raised*. Before
this migration there was no such timestamp, so the read-model would have to fall
back to ``updated_at`` (imprecise — any edit moves it). This adds a dedicated,
nullable ``moderation_flagged_at`` to both ``jobs`` and ``events``.

Strictly additive: every existing row is NULL (never-flagged, or a legacy flagged
row for which the read-model still falls back to ``updated_at``), so behavior is
unchanged. Set by the escalate/flag path and cleared when a human upholds
(reject) or dismisses the flag.

Revision ID: 0088_moderation_flagged_at
Revises: 0087_membership_role_department_scope
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0088_moderation_flagged_at"
down_revision: str | None = "0087_membership_role_department_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("moderation_flagged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "events",
        sa.Column("moderation_flagged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("events", "moderation_flagged_at")
    op.drop_column("jobs", "moderation_flagged_at")
