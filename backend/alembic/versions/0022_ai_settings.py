"""ai_settings: admin-managed AI provider/model/budget governance (ADR-0011)

Adds the ``ai_settings`` table — a SINGLE platform-scoped governance row storing
**alias names + toggles + budget only**. There is NO raw API-key column, NO
concrete provider/model string, and NO base-URL column: keys live solely in
``backend/.env`` (``OPENROUTER_API_KEY``). The singleton is enforced by a unique
constraint on ``scope`` (always ``'platform'`` for V1); ``org_id`` + the ``scope``
vocabulary are reserved for the deferred per-university scope.

A single ``'platform'`` row is SEEDED with defaults mirroring ``config.py`` so
runtime behaviour is byte-identical to today the moment it ships (real calls off
unless env+key permit, offline provider, cv-llm structuring off, job-fit
explanation on, budget from ``ai_daily_cost_limit_usd``). The seed reads
``AI_REAL_CALLS_ENABLED`` / ``AI_DAILY_COST_LIMIT_USD`` from the migration process
env (falling back to the config defaults) — it never persists a key.

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration; the rollout_state CHECK lives here (Postgres) only.

Revision ID: 0022_ai_settings
Revises: 0021_cv_ingestions
Create Date: 2026-06-28
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_ai_settings"
down_revision: str | None = "0021_cv_ingestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    op.create_table(
        "ai_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("scope", sa.String(20), nullable=False, server_default="platform"),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("real_calls_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("rollout_state", sa.String(20), nullable=False,
                  server_default="enabled"),
        sa.Column("chat_model_alias", sa.String(60), nullable=False,
                  server_default="chat_cheap"),
        sa.Column("reasoning_model_alias", sa.String(60), nullable=False,
                  server_default="reasoning_cheap"),
        sa.Column("embedding_model_alias", sa.String(60), nullable=False,
                  server_default="embedding_cheap"),
        sa.Column("eval_model_alias", sa.String(60), nullable=False,
                  server_default="eval_cheap"),
        sa.Column("cv_llm_structuring_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("job_fit_ai_explanation_enabled", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("daily_budget_usd", sa.Numeric(10, 2), nullable=False,
                  server_default="1.00"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("scope", name="uq_ai_settings_scope"),
    )

    if is_postgres:
        op.create_check_constraint(
            "ck_ai_settings_rollout_state",
            "ai_settings",
            "rollout_state IN ('enabled', 'paused', 'offline')",
        )
        op.execute("DROP TRIGGER IF EXISTS trg_ai_settings_updated_at ON ai_settings;")
        op.execute(
            "CREATE TRIGGER trg_ai_settings_updated_at BEFORE UPDATE ON ai_settings "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )

    # Seed the single 'platform' row mirroring config.py. Defaults come from the
    # migration-process env (same source config.py reads); NO key is persisted.
    real_calls = _env_bool("AI_REAL_CALLS_ENABLED", False)
    daily_budget = _env_float("AI_DAILY_COST_LIMIT_USD", 1.0)
    op.execute(
        sa.text(
            "INSERT INTO ai_settings "
            "(scope, real_calls_enabled, rollout_state, daily_budget_usd) "
            "VALUES ('platform', :real_calls, 'enabled', :budget)"
        ).bindparams(real_calls=real_calls, budget=round(daily_budget, 2))
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_ai_settings_updated_at ON ai_settings;")
    op.drop_table("ai_settings")
