"""add cv_language_required to jobs

Revision ID: 0071_job_cv_language_required
Revises: 0070_ai_provider_key_rotation
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0071_job_cv_language_required"
down_revision: str | None = "0070_ai_provider_key_rotation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "cv_language_required",
            sa.String(5),
            nullable=False,
            server_default="any",
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "cv_language_required")
