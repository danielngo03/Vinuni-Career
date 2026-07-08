"""cv_job_fit_scores.explanation_structured: persist the structured matching detail.

The semantic fit EXPLAINER already produces per-requirement matched evidence (with
an evidence-strength label), confirmed gaps (each with an advisory suggestion), and
an overall suggestion — but only the free-text ``explanation`` summary was being
persisted, so the structured detail was discarded on every reload. This adds a
nullable JSON column that stores the leak-safe structured analysis
(``semantic_scorer.analysis_payload``) alongside the summary, keyed to the same
``(cv_id, job_id)`` row, so the on-demand fit-analysis sub-call can return the full
detail without re-invoking the model.

CV-specific (owner-scoped by the row) so it is NOT shared through the cross-CV
``cv_fit_explanation_cache``. Leak-safe: no score/provider/model/token internals.
Cleared alongside ``explanation`` whenever the row's content stamps move.

Revision ID: 0085_cv_job_fit_explanation_structured
Revises: 0084_ai_energy_accounts_and_usage_org
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0085_cv_job_fit_explanation_structured"
down_revision: str | None = "0084_ai_energy_accounts_and_usage_org"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSONB on PostgreSQL (runtime); plain JSON on SQLite (unit tests) — mirrors the
# cross-database ``JsonType`` used by the ORM (``app/shared/models.py``).
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "cv_job_fit_scores",
        sa.Column("explanation_structured", _JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cv_job_fit_scores", "explanation_structured")
