"""Expand CV template catalog for industry-specific starting points."""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from app.modules.documents.domain.catalog import TEMPLATE_SEEDS

revision = "0046_cv_template_catalog"
down_revision = "0045"
branch_labels = None
depends_on = None


_NEW_TEMPLATE_KEYS = {
    "data_analytics_research",
    "finance_consulting",
    "marketing_growth",
    "healthcare_impact",
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for spec in TEMPLATE_SEEDS:
        if spec["key"] not in _NEW_TEMPLATE_KEYS:
            continue
        op.execute(
            sa.text(
                "INSERT INTO cv_templates "
                "(id, key, name_vi, name_en, category, layout_schema, is_premium, is_active) "
                "VALUES (gen_random_uuid(), :key, :name_vi, :name_en, :category, "
                "CAST(:layout AS jsonb), :is_premium, TRUE) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(
                key=spec["key"],
                name_vi=spec["name_vi"],
                name_en=spec["name_en"],
                category=spec["category"],
                layout=json.dumps(spec["layout_schema"]),
                # Read defensively: the live ``TEMPLATE_SEEDS`` catalog dropped
                # ``is_premium`` in the 2026-07-05 owner cleanup and migration
                # 0068 drops the column. At this revision the column still
                # exists, so default to ``False`` when the catalog spec omits the
                # key (a hard ``spec["is_premium"]`` would ``KeyError`` on a fresh
                # full-chain upgrade if these industry keys are re-added).
                is_premium=spec.get("is_premium", False),
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        sa.text("DELETE FROM cv_templates WHERE key = ANY(:keys)").bindparams(
            sa.bindparam("keys", list(_NEW_TEMPLATE_KEYS), type_=sa.ARRAY(sa.String()))
        )
    )
