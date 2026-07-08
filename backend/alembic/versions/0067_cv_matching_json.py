"""CV finalize analysis: cv_profiles.matching_json (internal matching read model).

CV builder Canva redesign (design spec 2026-07-05, §"Data contracts" 3): finalize
("Lưu vào thư viện CV") derives a DETERMINISTIC matching representation from the
CV's structured sections — normalized skills, a keyword set, contact presence, and
the experience-entry count — and stores it on the CV so a committed library CV is
prepared for CV-JD matching (no OCR/AI tokens; the data is already structured).

- Adds ``cv_profiles.matching_json JSONB NULL`` — set on finalize
  (``cv_lifecycle_service._analyze_for_matching``); NULL for drafts. INTERNAL only:
  it is never surfaced in a student-facing response.

No backfill: only CVs finalized AFTER this change carry the representation; existing
``ready`` CVs get it on their next finalize/edit-finalize cycle, and matching
consumers treat a NULL ``matching_json`` as "not yet analyzed" (fall back to reading
sections directly).

Downgrade drops the column.

Revision ID: 0067_cv_matching_json
Revises: 0066_cv_finalized_at
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0067_cv_matching_json"
down_revision: str | None = "0066_cv_finalized_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# JSONB on PostgreSQL (runtime); plain JSON on SQLite (unit tests) — mirrors the
# cross-database ``JsonType`` used by the ORM (``app/shared/models.py``).
_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "cv_profiles",
        sa.Column("matching_json", _JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cv_profiles", "matching_json")
