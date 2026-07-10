"""advertising: campaign-grade allocation engine (spec §7.0)

Four ADDITIVE tables for the real allocation/distribution engine (owner decision
2026-07-10). They sit ALONGSIDE the target-based ``sponsored_placements`` system
(migration ``0017``) and never replace it:

- ``ad_slots`` — finite sponsored-slot inventory per public surface (seeded ref
  data). ``capacity`` = paid positions; ``max_sponsored_share`` = ratio guard so
  sponsored inventory never exceeds a fraction of the surface.
- ``ad_campaigns`` — a partner's budgeted, coarse-targeted campaign. ``targeting``
  is an allowlisted coarse-dimension JSONB (NEVER GPS / sensitive categories);
  ``disclosure_class`` defaults to ``paid_sponsored`` (non-removable disclosure).
- ``ad_allocations`` — the auditable computed plan: which campaign fills which slot
  for which coarse segment, with the match reason + pacing state. Upserted on
  ``(slot_id, segment_key, position)`` so it reflects the CURRENT plan, bounded.
- ``ad_events`` — per-campaign / per-slot / per-day privacy-safe aggregate of
  impressions / clicks / apply-starts / register-intents + accumulated spend
  (pacing + reporting; NO PII / GPS / raw IP).

Postgres-only constructs (CHECKs, partial/extra indexes, unique constraints,
``set_updated_at`` triggers) are guarded by ``is_postgres``; the SQLite test path
creates the schema from ORM metadata and enforces the invariants in the service
layer.

Revision ID: 0098_advertising_engine
Revises: 0097_cv_embeddings
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "0098_advertising_engine"
down_revision: str | None = "0097_cv_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True)
_JSONB = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


# Seed rows for ad_slots (spec §7.0 "Slot inventory"). Stable codes -> idempotent.
_SEED_SLOTS: list[dict] = [
    {
        "code": "discovery_feed_sponsored",
        "surface": "discovery_feed",
        "name_vi": "Vị trí tài trợ trong bảng tin khám phá",
        "name_en": "Discovery feed sponsored slots",
        "capacity": 2,
        "max_sponsored_share": 0.20,
    },
    {
        "code": "public_job_board_rail",
        "surface": "public_job_board",
        "name_vi": "Banner cột phải bảng việc làm",
        "name_en": "Public job board right-rail banner",
        "capacity": 1,
        "max_sponsored_share": 0.15,
    },
    {
        "code": "company_directory_banner",
        "surface": "company_directory",
        "name_vi": "Banner danh bạ doanh nghiệp",
        "name_en": "Company directory banner",
        "capacity": 1,
        "max_sponsored_share": 0.15,
    },
    {
        "code": "homepage_hero",
        "surface": "homepage",
        "name_vi": "Banner hero trang chủ",
        "name_en": "Homepage hero banner",
        "capacity": 1,
        "max_sponsored_share": 0.25,
    },
    {
        "code": "events_featured",
        "surface": "events",
        "name_vi": "Vị trí sự kiện nổi bật tài trợ",
        "name_en": "Events featured sponsored slot",
        "capacity": 1,
        "max_sponsored_share": 0.20,
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    now_default = sa.text("NOW()") if is_postgres else sa.func.now()

    # ----------------------------------------------------------------- ad_slots
    ad_slots = op.create_table(
        "ad_slots",
        sa.Column("id", _UUID, primary_key=True, server_default=uuid_default),
        sa.Column("code", sa.String(60), nullable=False, unique=True),
        sa.Column("surface", sa.String(40), nullable=False),
        sa.Column("name_vi", sa.String(160), nullable=False),
        sa.Column("name_en", sa.String(160), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_sponsored_share", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
    )
    op.create_index("ix_ad_slots_surface", "ad_slots", ["surface"])

    # ------------------------------------------------------------- ad_campaigns
    op.create_table(
        "ad_campaigns",
        sa.Column("id", _UUID, primary_key=True, server_default=uuid_default),
        sa.Column("org_id", _UUID, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by", _UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("objective", sa.String(30), nullable=False),
        sa.Column("surface", sa.String(40), nullable=False),
        sa.Column("budget_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("spent_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("cpm_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False, server_default="VND"),
        sa.Column("pacing", sa.String(10), nullable=False, server_default="even"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("disclosure_class", sa.String(20), nullable=False, server_default="paid_sponsored"),
        sa.Column("disclosure_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("targeting", _JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")),
        sa.Column("creative", _JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")),
        sa.Column("target_type", sa.String(12), nullable=True),
        sa.Column("target_id", _UUID, nullable=True),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("moderation_reason_code", sa.String(30), nullable=True),
        sa.Column("approved_by", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payment_reference", sa.String(120), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by", _UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # ----------------------------------------------------------- ad_allocations
    op.create_table(
        "ad_allocations",
        sa.Column("id", _UUID, primary_key=True, server_default=uuid_default),
        sa.Column("campaign_id", _UUID, sa.ForeignKey("ad_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_id", _UUID, sa.ForeignKey("ad_slots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("surface", sa.String(40), nullable=False),
        sa.Column("slot_code", sa.String(60), nullable=False),
        sa.Column("segment_key", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("match_reason", _JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")),
        sa.Column("pacing_state", _JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres else sa.text("'{}'")),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
    )
    op.create_index("ix_ad_allocations_campaign", "ad_allocations", ["campaign_id"])
    op.create_index("ix_ad_allocations_slot", "ad_allocations", ["slot_id"])

    # ---------------------------------------------------------------- ad_events
    op.create_table(
        "ad_events",
        sa.Column("id", _UUID, primary_key=True, server_default=uuid_default),
        sa.Column("campaign_id", _UUID, sa.ForeignKey("ad_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_id", _UUID, sa.ForeignKey("ad_slots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("surface", sa.String(40), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("apply_starts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("register_intents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spend_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default),
    )
    op.create_index("ix_ad_events_campaign", "ad_events", ["campaign_id"])
    op.create_index("ix_ad_events_slot", "ad_events", ["slot_id"])
    op.create_index("ix_ad_events_date", "ad_events", ["event_date"])

    if is_postgres:
        op.create_check_constraint(
            "ck_ad_campaign_window", "ad_campaigns", "end_at > start_at",
        )
        op.create_check_constraint(
            "ck_ad_campaign_budget", "ad_campaigns", "budget_amount > 0",
        )
        op.create_check_constraint(
            "ck_ad_campaign_pacing", "ad_campaigns", "pacing IN ('even','asap')",
        )
        op.create_index(
            "idx_ad_campaigns_org", "ad_campaigns", ["org_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_ad_campaigns_serve", "ad_campaigns", ["surface", "status", "start_at", "end_at"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        # One campaign per slot position per coarse segment (current plan).
        op.create_index(
            "uq_ad_allocation_slot_segment_position", "ad_allocations",
            ["slot_id", "segment_key", "position"], unique=True,
        )
        # One aggregate row per (campaign, slot, day).
        op.create_index(
            "uq_ad_events_campaign_slot_day", "ad_events",
            ["campaign_id", "slot_id", "event_date"], unique=True,
        )
        for table in ("ad_slots", "ad_campaigns", "ad_allocations", "ad_events"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
            op.execute(
                f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
            )
    else:
        op.create_index(
            "uq_ad_allocation_slot_segment_position", "ad_allocations",
            ["slot_id", "segment_key", "position"], unique=True,
        )
        op.create_index(
            "uq_ad_events_campaign_slot_day", "ad_events",
            ["campaign_id", "slot_id", "event_date"], unique=True,
        )

    # ---------------------------------------------------- seed the slot inventory
    if context.is_offline_mode():
        rows = _SEED_SLOTS
    else:
        existing = set(bind.execute(sa.select(ad_slots.c.code)).scalars().all())
        rows = [r for r in _SEED_SLOTS if r["code"] not in existing]
    if rows:
        op.bulk_insert(ad_slots, rows)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table in ("ad_events", "ad_allocations", "ad_campaigns", "ad_slots"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")

    op.drop_index("uq_ad_events_campaign_slot_day", table_name="ad_events")
    op.drop_index("ix_ad_events_date", table_name="ad_events")
    op.drop_index("ix_ad_events_slot", table_name="ad_events")
    op.drop_index("ix_ad_events_campaign", table_name="ad_events")
    op.drop_table("ad_events")

    op.drop_index("uq_ad_allocation_slot_segment_position", table_name="ad_allocations")
    op.drop_index("ix_ad_allocations_slot", table_name="ad_allocations")
    op.drop_index("ix_ad_allocations_campaign", table_name="ad_allocations")
    op.drop_table("ad_allocations")

    if is_postgres:
        op.drop_index("idx_ad_campaigns_serve", table_name="ad_campaigns")
        op.drop_index("idx_ad_campaigns_org", table_name="ad_campaigns")
    op.drop_table("ad_campaigns")

    op.drop_index("ix_ad_slots_surface", table_name="ad_slots")
    op.drop_table("ad_slots")
