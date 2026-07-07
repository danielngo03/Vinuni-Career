"""CV library lifecycle: cv_profiles.finalized_at + backfill existing CVs to ready.

Two-tier CV library (design spec 2026-07-05, owner-approved): only CVs COMMITTED
to the library (``status='ready'``) count against the 5-cap and are usable for
apply / job-fit; unlimited scratch CVs stay ``draft``.

- Adds ``cv_profiles.finalized_at TIMESTAMPTZ NULL`` — when a CV entered the library
  (set on finalize + upload import; NULL for drafts).
- Data (PG-guarded, idempotent): before this change EVERY non-archived CV was
  usable for apply/job-fit and counted toward the old quota, so preserve that —
  promote every existing non-archived, non-deleted CV to ``status='ready'`` with
  ``finalized_at=now()``. Idempotent: a row already ``ready`` with a ``finalized_at``
  is left untouched, so re-running the step never double-stamps.

Downgrade drops the column. (It does NOT revert the status backfill: ``draft`` and
``ready`` were both valid before this migration, so leaving CVs ``ready`` is
harmless and avoids guessing which rows were originally drafts.)

Revision ID: 0066_cv_finalized_at
Revises: 0065_cv_template_themes_governance
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066_cv_finalized_at"
down_revision: str | None = "0065_cv_template_themes_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.add_column(
        "cv_profiles",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill (idempotent): every existing usable CV becomes a library CV so the
    # behaviour students already had (apply/job-fit with any non-archived CV) is
    # preserved under the new ``ready``-only semantics.
    if is_pg:
        bind.execute(
            sa.text(
                "UPDATE cv_profiles "
                "SET status = 'ready', finalized_at = now() "
                "WHERE deleted_at IS NULL "
                "  AND status <> 'archived' "
                "  AND (status <> 'ready' OR finalized_at IS NULL)"
            )
        )


def downgrade() -> None:
    op.drop_column("cv_profiles", "finalized_at")
