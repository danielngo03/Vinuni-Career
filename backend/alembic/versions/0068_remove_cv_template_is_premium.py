"""Remove the CV template premium concept: drop cv_templates.is_premium.

Owner cleanup (2026-07-05): ALL CV templates are free. The paid/"premium" template
gate never shipped as a real entitlement, so the flag is removed from the model,
seeds, admin service, presenter, and API schemas. This migration drops the backing
column.

- Upgrade: drop ``cv_templates.is_premium``.
- Downgrade: re-add ``cv_templates.is_premium BOOLEAN NOT NULL DEFAULT false`` so the
  schema round-trips to the prior shape (all rows default to non-premium, matching
  the seed data that existed before removal).

Revision ID: 0068_remove_cv_template_is_premium
Revises: 0067_cv_matching_json
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0068_remove_cv_template_is_premium"
down_revision: str | None = "0067_cv_matching_json"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("cv_templates", "is_premium")


def downgrade() -> None:
    op.add_column(
        "cv_templates",
        sa.Column(
            "is_premium",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
