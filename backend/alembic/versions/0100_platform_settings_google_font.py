"""Reconcile ``platform_settings`` with its ORM model (model-ahead drift fix).

The ``PlatformSettings`` model (``platform_settings/domain/models.py``) was
refactored to store a Google Fonts CSS URL + family name
(``google_font_url``, ``google_font_family``), but no migration ever added those
columns — the table still only had the older ``font_key`` column. As a result,
EVERY query that selects ``platform_settings`` (branding/appearance is loaded on
many surfaces, e.g. the student job-intelligence panel) raised
``UndefinedColumnError: column platform_settings.google_font_url does not exist``
on any cleanly-migrated database.

This adds the two missing columns. It is deliberately:

- **Idempotent** — ``ADD COLUMN IF NOT EXISTS`` so it is a no-op on databases
  that were create_all'd or already patched (some environments already have the
  columns), and safe to run anywhere.
- **Non-destructive** — the obsolete ``font_key`` column is left in place. It is
  no longer mapped by the ORM (SQLAlchemy only selects mapped columns), so it is
  harmless; dropping it would risk losing an operator's prior appearance value
  and is not required to fix the crash.

Chain: down_revision ``0099_company_profile_approval`` (current head).
"""

from __future__ import annotations

from alembic import op

revision: str = "0100_platform_settings_google_font"
down_revision: str | None = "0099_company_profile_approval"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Postgres-native IF NOT EXISTS keeps this safe on DBs that already have the
    # columns (create_all / manually patched environments).
    op.execute(
        "ALTER TABLE platform_settings "
        "ADD COLUMN IF NOT EXISTS google_font_url VARCHAR(512)"
    )
    op.execute(
        "ALTER TABLE platform_settings "
        "ADD COLUMN IF NOT EXISTS google_font_family VARCHAR(100)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE platform_settings DROP COLUMN IF EXISTS google_font_family")
    op.execute("ALTER TABLE platform_settings DROP COLUMN IF EXISTS google_font_url")
