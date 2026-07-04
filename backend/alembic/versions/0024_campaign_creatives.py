"""advertising: campaign_creatives + sponsored_placements.disclosure_class

Adds the campaign/banner CREATIVE ASSET layer and the public inventory-class
disclosure taxonomy (``docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md`` §4/§5/§6,
``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §7):

- ``sponsored_placements.disclosure_class`` — the public inventory class shown to
  end users (``paid_sponsored`` default for partner placements; the university may
  relabel a non-paid placement ``university_curated`` / ``strategic_partner`` /
  ``featured``). Only ``paid_sponsored`` is PAID (non-removable disclosure).
- ``campaign_creatives`` — uploaded banner images per delivery slot
  (``homepage_hero`` / ``right_rail`` / ``inline_card`` / ``event_banner``). Public
  marketing media (no Fernet), gated by a magic-byte image allowlist + size cap.
  Carries alt vi/en, responsive focal point, click target, an independent review
  state machine, an optional display window, and the analytics source surface.
  The internal ``image_path`` storage key is never exposed; public surfaces get a
  resolved serve URL.

Postgres-only constructs (CHECK constraints, partial indexes, ``set_updated_at``
trigger) are guarded by ``is_postgres``; the SQLite unit-test path builds the
schema from ORM metadata and enforces the vocabularies in the service layer.

Revision ID: 0024_campaign_creatives
Revises: 0023_messaging_institutional
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_campaign_creatives"
down_revision: str | None = "0023_messaging_institutional"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ---------------------------------------- sponsored_placements.disclosure_class
    op.add_column(
        "sponsored_placements",
        sa.Column(
            "disclosure_class",
            sa.String(20),
            nullable=False,
            server_default="paid_sponsored",
        ),
    )
    if is_postgres:
        op.create_check_constraint(
            "ck_placement_disclosure_class", "sponsored_placements",
            "disclosure_class IN "
            "('paid_sponsored','university_curated','strategic_partner','featured')",
        )

    # ------------------------------------------------------- campaign_creatives
    op.create_table(
        "campaign_creatives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("placement_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sponsored_placements.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("slot", sa.String(20), nullable=False),
        sa.Column("image_path", sa.String(400), nullable=False),
        sa.Column("media_type", sa.String(40), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alt_vi", sa.String(300), nullable=True),
        sa.Column("alt_en", sa.String(300), nullable=True),
        sa.Column("focal_x", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("focal_y", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("click_target", sa.String(500), nullable=True),
        sa.Column("moderation_status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analytics_source_surface", sa.String(60), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()") if is_postgres else sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()") if is_postgres else sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    if is_postgres:
        op.create_check_constraint(
            "ck_creative_slot", "campaign_creatives",
            "slot IN ('homepage_hero','right_rail','inline_card','event_banner')",
        )
        op.create_check_constraint(
            "ck_creative_status", "campaign_creatives",
            "moderation_status IN ('pending','approved','rejected')",
        )
        op.create_check_constraint(
            "ck_creative_focal_range", "campaign_creatives",
            "focal_x >= 0 AND focal_x <= 1 AND focal_y >= 0 AND focal_y <= 1",
        )
        # Per-placement creative lookup; partial discovery index for the public
        # banner read (approved + live creatives by slot).
        op.create_index(
            "idx_creatives_placement", "campaign_creatives", ["placement_id"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_creatives_slot_live", "campaign_creatives",
            ["slot", "moderation_status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_campaign_creatives_updated_at "
            "ON campaign_creatives;"
        )
        op.execute(
            "CREATE TRIGGER trg_campaign_creatives_updated_at BEFORE UPDATE ON "
            "campaign_creatives FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
    else:
        op.create_index(
            "idx_creatives_placement", "campaign_creatives", ["placement_id"]
        )
        op.create_index(
            "idx_creatives_slot_live", "campaign_creatives",
            ["slot", "moderation_status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_campaign_creatives_updated_at "
            "ON campaign_creatives;"
        )
    op.drop_index("idx_creatives_slot_live", table_name="campaign_creatives")
    op.drop_index("idx_creatives_placement", table_name="campaign_creatives")
    op.drop_table("campaign_creatives")

    if is_postgres:
        op.drop_constraint(
            "ck_placement_disclosure_class", "sponsored_placements",
            type_="check",
        )
    op.drop_column("sponsored_placements", "disclosure_class")
