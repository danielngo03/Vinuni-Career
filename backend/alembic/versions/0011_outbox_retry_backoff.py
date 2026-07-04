"""outbox retry/backoff: next_attempt_at + drain-claim index

Adds ``notification_outbox.next_attempt_at`` (``TIMESTAMPTZ NULL``) and the
``idx_outbox_due (status, next_attempt_at)`` covering index used by the scheduler
drain claim (ADR-0003 §3, ``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §7).

``next_attempt_at`` defers a row's next delivery attempt after a transient send
failure (exponential backoff). NULL means "eligible immediately". The terminal
``dead`` dead-letter status is a code-only addition to the ``status`` value set —
the column is ``String(20)`` with no DB enum/check, so there is **no DDL** for it.

The SQLite unit-test path builds the schema from ORM metadata and never runs this
migration; the equivalent column + index live on the ORM model.

Revision ID: 0011_outbox_retry_backoff
Revises: 0010_totp_secret_encryption
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_outbox_retry_backoff"
down_revision: str | None = "0010_totp_secret_encryption"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_outbox",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_outbox_due",
        "notification_outbox",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_due", table_name="notification_outbox")
    op.drop_column("notification_outbox", "next_attempt_at")
