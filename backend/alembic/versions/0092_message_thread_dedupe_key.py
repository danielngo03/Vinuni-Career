"""messaging: thread dedupe_key + partial unique index (TOCTOU guard)

Closes the concurrent-create race for the two idempotent thread axes — an application
thread (one per ``(org, application)``) and a direct org-Page thread (one live thread
per ``(initiator, target org)``). The service already dedupes with a check-then-insert
query, but that has a TOCTOU window: two concurrent requests both see "none" and both
insert. A deterministic ``message_threads.dedupe_key`` plus a PARTIAL UNIQUE index turns
the race into a DB-enforced guarantee — the losing INSERT raises ``IntegrityError`` and
the service returns the winner instead of a duplicate.

Kept as its own revision (not folded into ``0091``) because the live ``vinuni_career``
DB already applied ``0091`` without this column; an already-applied migration must not be
edited. Postgres builds the partial index here; the SQLite unit-test path builds it from
ORM metadata (the index is declared on the model with ``sqlite_where`` too, so the
constraint — and thus the concurrency test — is real on SQLite as well).

Revision ID: 0092_message_thread_dedupe_key
Revises: 0091_messaging_v2
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0092_message_thread_dedupe_key"
down_revision: str | None = "0091_messaging_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.add_column(
        "message_threads",
        sa.Column("dedupe_key", sa.String(120), nullable=True),
    )
    if is_postgres:
        op.create_index(
            "uq_threads_dedupe", "message_threads", ["dedupe_key"], unique=True,
            postgresql_where=sa.text("dedupe_key IS NOT NULL AND deleted_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.drop_index("uq_threads_dedupe", table_name="message_threads")
    op.drop_column("message_threads", "dedupe_key")
