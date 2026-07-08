"""CV template visual themes + versioning/governance.

Turns CV templates into real, themed, governed designs (design spec P1):

- ``cv_templates`` gains governance columns: ``status`` (draft|published|archived),
  ``version``, ``owner_org_id``, ``published_at``, ``archived_at``.
- New immutable ``cv_template_versions`` table (one row per published design
  version), so republishing never restyles CVs bound to an older version.
- ``cv_profiles.template_version_id`` binds a CV to an exact design version.
- Data migration: every legacy template's ``layout_schema`` (which only held
  ``{section_order, typography.font, page}``) is UPGRADED to a full visual theme,
  legacy keys are mapped to the 8 new theme keys (upgrade-in-place — the row id is
  preserved so no ``cv_profiles.template_id`` is orphaned), a matching
  ``cv_template_versions`` row is inserted, and any of the 8 built-in themes not
  already present is seeded.

Revision ID: 0065_cv_template_themes_governance
Revises: 0064_remove_cv_primary_flags
Create Date: 2026-07-05
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.modules.documents.domain import themes
from app.modules.documents.domain.catalog import TEMPLATE_SEEDS
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0065_cv_template_themes_governance"
down_revision: str | None = "0064_remove_cv_primary_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # ---------------------------------------------------- governance columns
    op.add_column(
        "cv_templates",
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="published"
        ),
    )
    op.add_column(
        "cv_templates",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "cv_templates", sa.Column("owner_org_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "cv_templates",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cv_templates",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_cv_templates_owner_org",
        "cv_templates",
        "organizations",
        ["owner_org_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---------------------------------------------------- template versions
    op.create_table(
        "cv_template_versions",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if is_pg else None,
        ),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "design_json",
            _JSON,
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if is_pg else sa.text("'{}'"),
        ),
        sa.Column("preview_image", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["cv_templates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "template_id", "version_number", name="uq_cv_template_versions_num"
        ),
    )
    op.create_index(
        "ix_cv_template_versions_template_id",
        "cv_template_versions",
        ["template_id"],
    )

    # ---------------------------------------------------- profile binding
    op.add_column(
        "cv_profiles", sa.Column("template_version_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_cv_profiles_template_version",
        "cv_profiles",
        "cv_template_versions",
        ["template_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---------------------------------------------------- data: upgrade themes
    if is_pg:
        _upgrade_data_pg(bind)


def _upgrade_data_pg(bind) -> None:
    """Converge the template catalog to exactly the 8 built-ins (+ any custom rows).

    Deterministic and idempotent regardless of prior state (fresh install, legacy
    templates only, or a DB where the lifespan seeder already inserted the 8 keys):

    1. Upsert the 8 canonical built-ins by key with their real theme (self-heals any
       row previously seeded with a stale/generic theme; inserts any missing).
    2. Repoint every ``cv_profiles.template_id`` off a legacy template onto its
       mapped canonical template, then delete the legacy rows — so no CV is orphaned
       and the gallery ends with just the 8 built-ins (plus custom university rows).
    3. Upgrade any remaining custom template in place to a full theme.
    4. Ensure one immutable ``cv_template_versions`` row per template.
    """

    # 1) Upsert the 8 canonical built-ins with their real themes.
    canonical_id_by_key: dict[str, object] = {}
    for spec in TEMPLATE_SEEDS:
        row_id = bind.execute(
            sa.text(
                "INSERT INTO cv_templates "
                "(id, key, name_vi, name_en, category, layout_schema, is_premium, "
                " is_active, status, version, published_at) "
                "VALUES (gen_random_uuid(), :key, :name_vi, :name_en, :category, "
                " CAST(:layout AS jsonb), :is_premium, TRUE, 'published', 1, now()) "
                "ON CONFLICT (key) DO UPDATE SET "
                " name_vi = EXCLUDED.name_vi, name_en = EXCLUDED.name_en, "
                " category = EXCLUDED.category, layout_schema = EXCLUDED.layout_schema, "
                " is_premium = EXCLUDED.is_premium, is_active = TRUE, status = 'published', "
                " published_at = COALESCE(cv_templates.published_at, now()) "
                "RETURNING id"
            ).bindparams(
                key=spec["key"],
                name_vi=spec["name_vi"],
                name_en=spec["name_en"],
                category=spec["category"],
                layout=json.dumps(spec["layout_schema"]),
                is_premium=spec["is_premium"],
            )
        ).scalar()
        canonical_id_by_key[spec["key"]] = row_id

    # 2) Repoint CVs off legacy templates onto the mapped canonical row, then delete
    #    the legacy rows (their cv_template_versions cascade-delete).
    for legacy_key, canonical_key in themes.LEGACY_KEY_TO_THEME.items():
        if legacy_key in themes.BUILTIN_THEMES:
            continue
        canonical_id = canonical_id_by_key.get(canonical_key)
        if canonical_id is None:
            continue
        legacy_id = bind.execute(
            sa.text("SELECT id FROM cv_templates WHERE key = :k").bindparams(k=legacy_key)
        ).scalar()
        if legacy_id is None:
            continue
        bind.execute(
            sa.text(
                "UPDATE cv_profiles SET template_id = :cid WHERE template_id = :lid"
            ).bindparams(cid=canonical_id, lid=legacy_id)
        )
        bind.execute(
            sa.text("DELETE FROM cv_templates WHERE id = :lid").bindparams(lid=legacy_id)
        )

    # 3) Upgrade any remaining custom (non-canonical) template in place.
    for row in (
        bind.execute(sa.text("SELECT id, key, layout_schema FROM cv_templates"))
        .mappings()
        .all()
    ):
        if row["key"] in themes.BUILTIN_THEMES:
            continue
        schema = row["layout_schema"] if isinstance(row["layout_schema"], dict) else {}
        if themes.is_full_theme(schema):
            continue
        theme = themes.upgrade_layout_schema(row["key"], schema)
        bind.execute(
            sa.text(
                "UPDATE cv_templates SET layout_schema = CAST(:theme AS jsonb), "
                "status = 'published', version = 1, "
                "published_at = COALESCE(published_at, now()) WHERE id = :tid"
            ).bindparams(theme=json.dumps(theme), tid=row["id"])
        )

    # 4) Ensure one immutable version row per template (idempotent).
    for row in (
        bind.execute(sa.text("SELECT id, layout_schema FROM cv_templates"))
        .mappings()
        .all()
    ):
        bind.execute(
            sa.text(
                "INSERT INTO cv_template_versions "
                "(id, template_id, version_number, design_json, created_at) "
                "SELECT gen_random_uuid(), :tid, 1, CAST(:theme AS jsonb), now() "
                "WHERE NOT EXISTS (SELECT 1 FROM cv_template_versions "
                "WHERE template_id = :tid AND version_number = 1)"
            ).bindparams(tid=row["id"], theme=json.dumps(row["layout_schema"]))
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_cv_profiles_template_version", "cv_profiles", type_="foreignkey"
    )
    op.drop_column("cv_profiles", "template_version_id")

    op.drop_index(
        "ix_cv_template_versions_template_id", table_name="cv_template_versions"
    )
    op.drop_table("cv_template_versions")

    op.drop_constraint(
        "fk_cv_templates_owner_org", "cv_templates", type_="foreignkey"
    )
    op.drop_column("cv_templates", "archived_at")
    op.drop_column("cv_templates", "published_at")
    op.drop_column("cv_templates", "owner_org_id")
    op.drop_column("cv_templates", "version")
    op.drop_column("cv_templates", "status")
