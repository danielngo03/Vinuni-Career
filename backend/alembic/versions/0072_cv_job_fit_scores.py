"""cv_job_fit_scores: persisted, version-stamped CV-to-job fit store.

The CV-JD fit result (deterministic 8-band product score + optional AI
explanation for the recommended CV) is now persisted, one row per
``(cv_id, job_id)``. Each row is stamped with the CV/JD content versions and the
deterministic ``scorer_version`` at compute time, so a reload reuses the stored
value and the score/explanation is only recomputed when the CV or JD changes
(owner requirement 2026-07-06). PII-safe: only the user-facing explanation text
is stored — never provider/model/token/prompt internals.

Revision ID: 0072_cv_job_fit_scores
Revises: 0071_job_cv_language_required
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0072_cv_job_fit_scores"
down_revision: str | None = "0071_job_cv_language_required"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "cv_job_fit_scores",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if is_pg else None,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("cv_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column(
            "bands",
            _JSON,
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if is_pg else sa.text("'{}'"),
        ),
        sa.Column(
            "matched_skills",
            _JSON,
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_pg else sa.text("'[]'"),
        ),
        sa.Column(
            "gaps",
            _JSON,
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_pg else sa.text("'[]'"),
        ),
        sa.Column("signal", sa.String(20), nullable=False),
        sa.Column(
            "stale", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "last_updated_days", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("cv_version", sa.Integer(), nullable=False),
        sa.Column("job_version", sa.Integer(), nullable=False),
        sa.Column("scorer_version", sa.String(20), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("explanation_prompt_version", sa.Integer(), nullable=True),
        sa.Column("explanation_lang", sa.String(5), nullable=True),
        sa.Column(
            "explanation_generated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
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
        sa.ForeignKeyConstraint(["cv_id"], ["cv_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "cv_id", "job_id", name="uq_cv_job_fit_scores_cv_job"
        ),
    )
    op.create_index(
        "ix_cv_job_fit_scores_user_id", "cv_job_fit_scores", ["user_id"]
    )
    op.create_index(
        "ix_cv_job_fit_scores_cv_id", "cv_job_fit_scores", ["cv_id"]
    )
    op.create_index(
        "ix_cv_job_fit_scores_job_id", "cv_job_fit_scores", ["job_id"]
    )
    op.create_index(
        "ix_cv_job_fit_scores_user_job",
        "cv_job_fit_scores",
        ["user_id", "job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cv_job_fit_scores_user_job", table_name="cv_job_fit_scores")
    op.drop_index("ix_cv_job_fit_scores_job_id", table_name="cv_job_fit_scores")
    op.drop_index("ix_cv_job_fit_scores_cv_id", table_name="cv_job_fit_scores")
    op.drop_index("ix_cv_job_fit_scores_user_id", table_name="cv_job_fit_scores")
    op.drop_table("cv_job_fit_scores")
