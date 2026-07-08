"""remove_cv_primary_flags

All active CVs are now equal candidates. Job-fit, quick-apply, and AI assistant
flows recommend the best CV per job instead of relying on a global "primary CV".

Revision ID: 0064_remove_cv_primary_flags
Revises: 0063_workflow_tz_aware_timestamps
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064_remove_cv_primary_flags"
down_revision: str | None = "0063_workflow_tz_aware_timestamps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("cv_profiles", "is_primary")
    op.drop_column("documents", "is_primary")


def downgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "cv_profiles",
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
