"""billing: subscription_plans + subscriptions (ADR-0010, V1 manual-billed)

The missing monetization layer that *sets a tier* (and the CV cap's first real
consumer):

- ``subscription_plans`` — a small seeded, audience-typed reference table of named
  tiers, each carrying its granted **limits as a structured JSON map**. Four rows
  are seeded idempotently in this migration's data step: ``student_free`` /
  ``student_pro`` / ``partner_basic`` / ``partner_pro``.
- ``subscriptions`` — a polymorphic per-principal record of a PAID plan. The
  principal is a ``user`` (student) or an ``org`` (partner): ``principal_type`` +
  ``principal_id`` with NO foreign key (it points at two tables); a CHECK
  constrains ``principal_type`` and the service layer validates ownership. The
  free/default tier needs NO row (absence == default-plan limits).

Postgres-only constructs are guarded by ``is_postgres``:

- partial principal/window indexes (``WHERE deleted_at IS NULL``)
- the partial unique one-in-flight-per-principal index
  (``WHERE status IN ('pending','active')``)
- the ``principal_type`` / ``status`` / plan ``audience`` / ``billing_period``
  CHECK constraints
- the ``set_updated_at`` triggers

The SQLite unit-test path creates the schema from ORM metadata and skips these;
the one-in-flight rule, audience match, and window are enforced there by the
service-layer guards.

Revision ID: 0019_subscriptions_and_manual_billing
Revises: 0018_career_outcome_records
Create Date: 2026-06-28
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision: str = "0019_subscriptions_billing"
down_revision: str | None = "0018_career_outcome_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Seed rows for subscription_plans (ADR-0010 §1). Stable codes -> idempotent upsert.
# V1 only *enforces* ``cv_active_quota``; the other keys are stored so surfaces can
# display what a tier grants and later slices enforce them through the same facade.
_SEED_PLANS: list[dict] = [
    {
        "code": "student_free",
        "name": "Sinh viên — Miễn phí",
        "name_en": "Student — Free",
        "audience": "student",
        "billing_period": "monthly",
        "duration_days": 30,
        "price_amount": "0.00",
        "currency": "VND",
        "limits": {
            "cv_active_quota": 5,
            "pdf_exports_per_month": 3,
            "premium_templates": False,
            "mass_apply_limit": 0,
            "ai_daily_cost_quota_usd": 0.02,
        },
        "is_default": True,
        "is_visible": True,
        "sort_order": 0,
    },
    {
        "code": "student_pro",
        "name": "Sinh viên — Pro",
        "name_en": "Student — Pro",
        "audience": "student",
        "billing_period": "monthly",
        "duration_days": 30,
        "price_amount": "99000.00",
        "currency": "VND",
        "limits": {
            "cv_active_quota": 10,
            "pdf_exports_per_month": 50,
            "premium_templates": True,
            "mass_apply_limit": 10,
            "ai_daily_cost_quota_usd": 0.75,
            # Masked weekly AI-energy allowance (opaque product credits, NOT USD).
            # A paid tier's explicit value overrides the per-segment default; the
            # free student tier has none and resolves from the segment (VinUni 300 /
            # external 120) in ``limit_facade``.
            "ai_weekly_energy_units": 1500,
        },
        "is_default": False,
        "is_visible": True,
        "sort_order": 1,
    },
    {
        "code": "partner_basic",
        "name": "Đối tác — Cơ bản",
        "name_en": "Partner — Basic",
        "audience": "partner",
        "billing_period": "monthly",
        "duration_days": 30,
        "price_amount": "0.00",
        "currency": "VND",
        "limits": {
            "job_post_quota": 5,
            "featured_job_slots": 0,
            "passive_search_quota": 0,
            "email_blast_quota": 0,
            "ai_daily_cost_quota_usd": 0.05,
            # Masked weekly AI-energy pool for the partner org (opaque credits).
            "ai_weekly_energy_units": 400,
        },
        "is_default": True,
        "is_visible": True,
        "sort_order": 0,
    },
    {
        "code": "partner_pro",
        "name": "Đối tác — Pro",
        "name_en": "Partner — Pro",
        "audience": "partner",
        "billing_period": "monthly",
        "duration_days": 30,
        "price_amount": "2000000.00",
        "currency": "VND",
        "limits": {
            "job_post_quota": 20,
            "featured_job_slots": 3,
            "passive_search_quota": 50,
            "email_blast_quota": 10,
            "ai_daily_cost_quota_usd": 1.50,
            # Masked weekly AI-energy pool for the partner org (opaque credits).
            "ai_weekly_energy_units": 1500,
        },
        "is_default": False,
        "is_visible": True,
        "sort_order": 1,
    },
]


def _sql_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_bool(value: object) -> str:
    return "TRUE" if bool(value) else "FALSE"


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_variant = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")

    # ----------------------------------------------------- subscription_plans
    subscription_plans = op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("name_en", sa.String(120), nullable=False),
        sa.Column("audience", sa.String(10), nullable=False),
        sa.Column("billing_period", sa.String(10), nullable=False,
                  server_default="monthly"),
        sa.Column("duration_days", sa.Integer(), nullable=False,
                  server_default="30"),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False,
                  server_default="0"),
        sa.Column("currency", sa.String(5), nullable=False, server_default="VND"),
        sa.Column("limits", json_variant, nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres
                  else sa.text("'{}'")),
        sa.Column("is_default", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("is_visible", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False,
                  server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()") if is_postgres
                  else sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()") if is_postgres
                  else sa.func.now()),
    )

    # ---------------------------------------------------------- subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("principal_type", sa.String(10), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("billing_period", sa.String(10), nullable=False),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False, server_default="VND"),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reference", sa.String(120), nullable=True),
        sa.Column("paid_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("expiring_notified_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings", json_variant, nullable=False,
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
            "ck_plan_audience", "subscription_plans",
            "audience IN ('student','partner')",
        )
        op.create_check_constraint(
            "ck_plan_billing_period", "subscription_plans",
            "billing_period IN ('monthly','annual')",
        )
        op.create_check_constraint(
            "ck_subscription_principal_type", "subscriptions",
            "principal_type IN ('user','org')",
        )
        op.create_check_constraint(
            "ck_subscription_status", "subscriptions",
            "status IN ('pending','active','expired','cancelled')",
        )
        op.create_index(
            "idx_subscriptions_principal", "subscriptions",
            ["principal_type", "principal_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_subscriptions_window", "subscriptions", ["status", "end_at"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        # One in-flight subscription per principal (pending|active).
        op.create_index(
            "uq_subscription_inflight", "subscriptions",
            ["principal_type", "principal_id"], unique=True,
            postgresql_where=sa.text("status IN ('pending','active')"),
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_subscription_plans_updated_at "
            "ON subscription_plans;"
        )
        op.execute(
            "CREATE TRIGGER trg_subscription_plans_updated_at BEFORE UPDATE ON "
            "subscription_plans FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON subscriptions;"
        )
        op.execute(
            "CREATE TRIGGER trg_subscriptions_updated_at BEFORE UPDATE ON "
            "subscriptions FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
    else:
        op.create_index(
            "idx_subscriptions_principal", "subscriptions",
            ["principal_type", "principal_id", "status"],
        )
        op.create_index(
            "idx_subscriptions_window", "subscriptions", ["status", "end_at"],
        )

    # ----------------------------------------------- seed the four plans
    # Idempotent: skip any code already present (safe to re-run). The ``limits``
    # column's bound JSON/JSONB type encodes the dict exactly once — passing a
    # pre-serialized string would double-encode it.
    if context.is_offline_mode():
        for spec in _SEED_PLANS:
            limits = _sql_quote(json.dumps(spec["limits"], ensure_ascii=False))
            op.execute(
                "INSERT INTO subscription_plans "
                "(code, name, name_en, audience, billing_period, duration_days, "
                "price_amount, currency, limits, is_default, is_visible, sort_order) "
                "VALUES ("
                f"{_sql_quote(spec['code'])}, "
                f"{_sql_quote(spec['name'])}, "
                f"{_sql_quote(spec['name_en'])}, "
                f"{_sql_quote(spec['audience'])}, "
                f"{_sql_quote(spec['billing_period'])}, "
                f"{int(spec['duration_days'])}, "
                f"{_sql_quote(spec['price_amount'])}, "
                f"{_sql_quote(spec['currency'])}, "
                f"{limits}::jsonb, "
                f"{_sql_bool(spec['is_default'])}, "
                f"{_sql_bool(spec['is_visible'])}, "
                f"{int(spec['sort_order'])}"
                ");"
            )
        rows = []
    else:
        existing = set(
            bind.execute(sa.select(subscription_plans.c.code)).scalars().all()
        )
        rows = [dict(spec) for spec in _SEED_PLANS if spec["code"] not in existing]
    if rows:
        op.bulk_insert(subscription_plans, rows)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON subscriptions;"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_subscription_plans_updated_at "
            "ON subscription_plans;"
        )
        op.drop_index("uq_subscription_inflight", table_name="subscriptions")
        op.drop_index("idx_subscriptions_window", table_name="subscriptions")
        op.drop_index("idx_subscriptions_principal", table_name="subscriptions")
    else:
        op.drop_index("idx_subscriptions_window", table_name="subscriptions")
        op.drop_index("idx_subscriptions_principal", table_name="subscriptions")

    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
