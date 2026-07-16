"""Backfill ``jobs.language_code`` from each row's own content.

Historically every job was written with ``language_code = 'en'`` (the model /
server default) because :func:`detect_language` was never called on write. The
write path now detects and persists the real language, but pre-existing rows are
still stamped ``'en'`` — which breaks the student JD "translate" pre-warm (a
Vietnamese JD wrongly reads as English, so the opposite-language cache targets
the wrong direction).

This migration re-derives ``language_code`` for every existing ``jobs`` row using
the SAME zero-dependency heuristic the write path uses
(:func:`app.modules.opportunities.domain.language_detection.detect_language`).

Deliberately:

- **Pure Python + SQL** — NO AI calls. The heuristic has no external deps, so it
  is safe to import inside the migration.
- **Keyset-batched** — reads in id-ordered batches so a large table does not load
  entirely into memory; ``language_code`` is not the ordering column, so updates
  never disturb the pagination.
- **Conservative** — rows with no computable content (all of title/description/
  requirements/benefits empty) are left as-is; nothing is fabricated.

Chain: down_revision ``0101_interview_plan_coverage`` (current head).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0102_job_language_backfill"
down_revision: str | None = "0101_interview_plan_coverage"
branch_labels: str | None = None
depends_on: str | None = None

_BATCH = 500


def upgrade() -> None:
    # Zero-dependency heuristic — safe to import in a migration (no AI, no I/O).
    from app.modules.opportunities.domain.language_detection import detect_language

    bind = op.get_bind()
    last_id = None
    while True:
        if last_id is None:
            rows = bind.execute(
                sa.text(
                    "SELECT id, title, description, requirements, benefits "
                    "FROM jobs ORDER BY id LIMIT :limit"
                ),
                {"limit": _BATCH},
            ).fetchall()
        else:
            rows = bind.execute(
                sa.text(
                    "SELECT id, title, description, requirements, benefits "
                    "FROM jobs WHERE id > :last ORDER BY id LIMIT :limit"
                ),
                {"limit": _BATCH, "last": last_id},
            ).fetchall()
        if not rows:
            break
        for row in rows:
            combined = "\n".join(
                part
                for part in (row.title, row.description, row.requirements, row.benefits)
                if part
            )
            if not combined.strip():
                # No content to detect from — leave the existing value untouched.
                continue
            lang = detect_language(combined)
            bind.execute(
                sa.text("UPDATE jobs SET language_code = :lang WHERE id = :id"),
                {"lang": lang, "id": row.id},
            )
        last_id = rows[-1].id


def downgrade() -> None:
    # No-op by design: the detected language is strictly more correct than the
    # historical blanket ``'en'`` default, and there is no captured "before"
    # value to restore. Downgrading the schema does not require reverting the
    # backfilled data. Safe / idempotent.
    pass
