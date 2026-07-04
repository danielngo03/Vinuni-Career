"""advertising: ad_packages + sponsored_placements (ADR-0009, V1 manual-billed)

The missing layer that *earns* a sponsored/featured flag:

- ``ad_packages`` — small seeded reference table of named fixed-price tiers (no
  bidding / no budget pacing). Three rows are seeded idempotently in this
  migration's data step: ``featured_7d`` / ``sponsored_14d`` / ``premium_30d``.
- ``sponsored_placements`` — a partner's request to sponsor/feature one owned job
  or event for a paid, date-windowed, university-approved period. The polymorphic
  target is ``target_type`` + ``target_id`` with NO foreign key (it points at two
  tables); a CHECK constrains ``target_type`` and the service layer validates
  ownership. ``sponsored_placements`` is the SOURCE OF TRUTH for sponsorship; the
  ``jobs/events.is_sponsored``/``is_featured`` columns are a recomputed projection.

Postgres-only constructs are guarded by ``is_postgres``:

- partial discovery/window/target indexes (``WHERE deleted_at IS NULL``)
- the partial unique one-in-flight-per-target index
  (``WHERE status IN ('pending_approval','approved','active')``)
- the ``target_type`` + ``end_at > start_at`` CHECK constraints
- the ``set_updated_at`` trigger

The SQLite unit-test path creates the schema from ORM metadata and skips these;
the per-target uniqueness, the window CHECK, and the per-org concurrency cap are
enforced there by the service-layer guards.

Revision ID: 0017_advertising_sponsored_placements
Revises: 0016_events_registration
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "0017_advertising_placements"
down_revision: str | None = "0016_events_registration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Seed rows for ad_packages (ADR-0009 §5). Stable codes -> idempotent upsert.
_SEED_PACKAGES: list[dict] = [
    {
        "code": "featured_7d",
        "name": "Nổi bật 7 ngày",
        "placement_type": "featured",
        "price_amount": "1500000.00",
        "currency": "VND",
        "duration_days": 7,
        "grants_sponsored": False,
        "grants_featured": True,
    },
    {
        "code": "sponsored_14d",
        "name": "Được tài trợ 14 ngày",
        "placement_type": "sponsored",
        "price_amount": "3000000.00",
        "currency": "VND",
        "duration_days": 14,
        "grants_sponsored": True,
        "grants_featured": False,
    },
    {
        "code": "premium_30d",
        "name": "Cao cấp 30 ngày",
        "placement_type": "both",
        "price_amount": "6000000.00",
        "currency": "VND",
        "duration_days": 30,
        "grants_sponsored": True,
        "grants_featured": True,
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # --------------------------------------------------------------- ad_packages
    ad_packages = op.create_table(
        "ad_packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("placement_type", sa.String(10), nullable=False),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False, server_default="VND"),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("grants_sponsored", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("grants_featured", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()") if is_postgres
                  else sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()") if is_postgres
                  else sa.func.now()),
    )

    # ------------------------------------------------- sponsored_placements
    op.create_table(
        "sponsored_placements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_type", sa.String(10), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("placement_type", sa.String(10), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ad_packages.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(5), nullable=False, server_default="VND"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("disclosure_confirmed", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reference", sa.String(120), nullable=True),
        sa.Column("paid_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ending_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings",
                  postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
                  nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres
                  else sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()") if is_postgres
                  else sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()") if is_postgres
                  else sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    if is_postgres:
        op.create_check_constraint(
            "ck_placement_target_type", "sponsored_placements",
            "target_type IN ('job','event')",
        )
        op.create_check_constraint(
            "ck_placement_window", "sponsored_placements", "end_at > start_at",
        )
        op.create_check_constraint(
            "ck_placement_type", "sponsored_placements",
            "placement_type IN ('sponsored','featured','both')",
        )
        op.create_index(
            "idx_placements_org", "sponsored_placements", ["org_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_placements_window", "sponsored_placements",
            ["status", "start_at", "end_at"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_placements_target", "sponsored_placements",
            ["target_type", "target_id"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        # One in-flight placement per target (pending_approval|approved|active).
        op.create_index(
            "uq_placement_inflight", "sponsored_placements",
            ["target_type", "target_id"], unique=True,
            postgresql_where=sa.text(
                "status IN ('pending_approval','approved','active')"
            ),
        )
        op.execute("DROP TRIGGER IF EXISTS trg_ad_packages_updated_at ON ad_packages;")
        op.execute(
            "CREATE TRIGGER trg_ad_packages_updated_at BEFORE UPDATE ON ad_packages "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_sponsored_placements_updated_at "
            "ON sponsored_placements;"
        )
        op.execute(
            "CREATE TRIGGER trg_sponsored_placements_updated_at BEFORE UPDATE ON "
            "sponsored_placements FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
    else:
        op.create_index("idx_placements_org", "sponsored_placements",
                        ["org_id", "status"])
        op.create_index("idx_placements_window", "sponsored_placements",
                        ["status", "start_at", "end_at"])
        op.create_index("idx_placements_target", "sponsored_placements",
                        ["target_type", "target_id"])

    # ----------------------------------------------- seed the three packages
    # Idempotent: skip any code already present (safe to re-run).
    if context.is_offline_mode():
        rows = _SEED_PACKAGES
    else:
        existing = set(
            bind.execute(sa.select(ad_packages.c.code)).scalars().all()
        )
        rows = [r for r in _SEED_PACKAGES if r["code"] not in existing]
    if rows:
        op.bulk_insert(ad_packages, rows)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_sponsored_placements_updated_at "
            "ON sponsored_placements;"
        )
        op.execute("DROP TRIGGER IF EXISTS trg_ad_packages_updated_at ON ad_packages;")
        op.drop_index("uq_placement_inflight", table_name="sponsored_placements")
        op.drop_index("idx_placements_target", table_name="sponsored_placements")
        op.drop_index("idx_placements_window", table_name="sponsored_placements")
        op.drop_index("idx_placements_org", table_name="sponsored_placements")
    else:
        op.drop_index("idx_placements_target", table_name="sponsored_placements")
        op.drop_index("idx_placements_window", table_name="sponsored_placements")
        op.drop_index("idx_placements_org", table_name="sponsored_placements")

    op.drop_table("sponsored_placements")
    op.drop_table("ad_packages")
