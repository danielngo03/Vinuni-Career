"""Add the frozen interview PLAN + deterministic COVERAGE columns.

The mock-interview brain became a layered, grounded system: a strong-model PLANNER
runs ONCE at session create and is FROZEN on the session row (competency map +
tiered question bank + opening), then reused by every turn/tier/report; a
deterministic COVERAGE state (no LLM) tracks which planned competency has been
asked/covered and the current difficulty tier, driving which competency the next
turn targets and the "what's left / covered" progress the client shows.

This adds three nullable columns to ``mock_interview_sessions``:

- ``plan_json``     JSONB — the frozen interview plan (leak-safe product data).
- ``plan_version``  INTEGER — the plan schema version.
- ``coverage_json`` JSONB — the deterministic coverage/tier state.

All three are NULLABLE with no backfill: existing sessions simply have no plan
(the services treat a missing plan as "no plan slice", degrading to the pre-planner
behaviour), and every session created after this migration carries them.

Deliberately:

- **Idempotent** — ``ADD COLUMN IF NOT EXISTS`` so it is a no-op on databases that
  were ``create_all``'d or already patched (mirrors 0100's Postgres-native pattern).
- **Non-destructive** — downgrade drops only the three new columns.

Chain: down_revision ``0100_platform_settings_google_font`` (current head).
"""

from __future__ import annotations

from alembic import op

revision: str = "0101_interview_plan_coverage"
down_revision: str | None = "0100_platform_settings_google_font"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mock_interview_sessions "
        "ADD COLUMN IF NOT EXISTS plan_json JSONB"
    )
    op.execute(
        "ALTER TABLE mock_interview_sessions "
        "ADD COLUMN IF NOT EXISTS plan_version INTEGER"
    )
    op.execute(
        "ALTER TABLE mock_interview_sessions "
        "ADD COLUMN IF NOT EXISTS coverage_json JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE mock_interview_sessions DROP COLUMN IF EXISTS coverage_json")
    op.execute("ALTER TABLE mock_interview_sessions DROP COLUMN IF EXISTS plan_version")
    op.execute("ALTER TABLE mock_interview_sessions DROP COLUMN IF EXISTS plan_json")
