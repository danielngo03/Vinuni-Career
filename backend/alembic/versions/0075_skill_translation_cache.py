"""skill_translation_cache: permanent VN→EN canonical-skill-term cache.

Cross-lingual CV-JD matching translates each non-English skill term to its
canonical English form once (temperature 0, so deterministic) and reuses it
forever. This replaces the removed embedding match tier, which could not
separate true VN↔EN skill pairs from same-language confusables at any usable
cosine threshold.

PII-safe: stores ONLY generic skill strings (source term + English form) — never
user data, CV text, provider/model/token/prompt internals.

Revision ID: 0075_skill_translation_cache
Revises: 0074_cv_fit_explanation_cache
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0075_skill_translation_cache"
down_revision: str | None = "0074_cv_fit_explanation_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skill_translation_cache",
        sa.Column("source_norm", sa.String(255), primary_key=True),
        sa.Column("translated", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("skill_translation_cache")
