"""cv_fit_explanation_cache: cross-CV reuse cache for CV-JD fit explanations.

The "learning" cache. Two DIFFERENT CVs that produce the SAME deterministic
evidence (matched skills + gaps) against the SAME JD version share ONE generated
explanation, keyed by a content ``fingerprint`` (sha256 hex). The second CV
reuses the first CV's summary at 0 extra tokens instead of triggering its own
LLM call.

PII-safe: stores ONLY the user-facing, requirement-centric explanation text
(prompt v3 rule 9 keeps it CV-agnostic). No user_id / cv_id / provider / model /
token / prompt internals are stored — the text is not user-specific by
construction.

Revision ID: 0074_cv_fit_explanation_cache
Revises: 0073_fit_score_avg_skill_level
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0074_cv_fit_explanation_cache"
down_revision: str | None = "0073_fit_score_avg_skill_level"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cv_fit_explanation_cache",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(5), nullable=False),
        sa.Column(
            "hit_count", sa.Integer(), nullable=False, server_default="0"
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
    )


def downgrade() -> None:
    op.drop_table("cv_fit_explanation_cache")
