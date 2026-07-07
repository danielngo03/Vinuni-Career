"""cv_job_fit_scores: add avg_skill_level ranking tie-breaker column.

Average self-rated skill proficiency (0-100) of the CV's leveled skills. Used
ONLY as a ranking tie-breaker between CVs with the same product score — never
part of the score. Persisted so the store's fast path ranks ties identically to
a fresh recompute. Neutral 50.0 default when the CV states no numeric levels.

Revision ID: 0073_fit_score_avg_skill_level
Revises: 0072_cv_job_fit_scores
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0073_fit_score_avg_skill_level"
down_revision: str | None = "0072_cv_job_fit_scores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cv_job_fit_scores",
        sa.Column(
            "avg_skill_level",
            sa.Float(),
            nullable=False,
            server_default=sa.text("50.0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("cv_job_fit_scores", "avg_skill_level")
