"""application_cv_snapshots.fit_score + scorer_version — apply-time CV-JD fit.

Additive, nullable columns on the IMMUTABLE ``application_cv_snapshots`` table so
the deterministic CV-JD fit of the CHOSEN CV vs the job can be captured at apply
time and frozen with the snapshot (student-ai phase 2, WS-5 foundation). This
makes the competition applicant-quality pool the set of REAL applicants — point
in time — instead of fit-score VIEWERS.

- ``fit_score`` — deterministic 0-100 product score of the submitted CV against
  the job at apply time; NULL when no deterministic score could be computed
  (uploaded-document apply with no scoreable CV profile, or a job no longer
  loadable). Never fabricated.
- ``scorer_version`` — the ``app.ai.cv.job_fit.SCORER_VERSION`` stamp used, so a
  later scorer bump is distinguishable when the competition read-model aggregates.

No backfill: the competition quality pool is complete only for applies made after
this migration; historical snapshots keep ``fit_score = NULL`` (history is never
invented).

Chained after ``0085_cv_job_fit_explanation_structured`` (the parallel WS-3 task's
migration off the same ``0084`` head) so the revision history stays linear —
independent, non-conflicting column adds on different tables.

Revision ID: 0086_application_snapshot_fit_score
Revises: 0085_cv_job_fit_explanation_structured
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0086_application_snapshot_fit_score"
down_revision: str | None = "0085_cv_job_fit_explanation_structured"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_cv_snapshots",
        sa.Column("fit_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "application_cv_snapshots",
        sa.Column("scorer_version", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("application_cv_snapshots", "scorer_version")
    op.drop_column("application_cv_snapshots", "fit_score")
