"""discovery: discovery_sessions + discovery_events (privacy-safe guest signals)

First slice of the Discovery/Recommendation/Ads rescue
(``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §3/§8):

- ``discovery_sessions`` — a first-party anonymous session keyed by a RANDOM uuid
  (NOT derived from user PII). The only signal store is ``coarse_tags`` (JSONB),
  which the service layer constrains to an allowlist (no name/email/phone, exact
  GPS, raw IP, raw CV text, sensitive categories, or third-party ad ids). ``user_id``
  is a nullable link populated only once a session-holder logs in. Short ``expires_at``
  TTL; the ``discovery.session_cleanup`` sweep prunes past it.
- ``discovery_events`` — append-only privacy-safe analytics ledger. ``placement_id``
  is an FK-LESS reference to ``sponsored_placements`` set ONLY for sponsored surfaces.
  ``idempotency_key`` is unique (same key → one row). ``session_id`` FK is
  ``ON DELETE SET NULL`` so pruning a short-TTL session never cascade-deletes its
  longer-retained events.

Postgres-only constructs (extra indexes, the ``set_updated_at`` trigger n/a here)
are guarded by ``is_postgres``; the SQLite unit-test path builds the schema from ORM
metadata and enforces the privacy allowlist + idempotency in the service layer.

Revision ID: 0020_discovery_sessions_events
Revises: 0019_subscriptions_billing
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_discovery_sessions_events"
down_revision: str | None = "0019_subscriptions_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    now_default = sa.text("NOW()") if is_postgres else sa.func.now()

    # --------------------------------------------------------- discovery_sessions
    op.create_table(
        "discovery_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("locale", sa.String(10), nullable=True),
        sa.Column("coarse_tags", json_type, nullable=False,
                  server_default=sa.text("'{}'::jsonb") if is_postgres
                  else sa.text("'{}'")),
        sa.Column("opt_out", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now_default),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now_default),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_discovery_sessions_expires", "discovery_sessions", ["expires_at"]
    )
    op.create_index(
        "idx_discovery_sessions_user", "discovery_sessions", ["user_id"]
    )

    # ----------------------------------------------------------- discovery_events
    op.create_table(
        "discovery_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("source_surface", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        # FK-LESS reference to sponsored_placements (set only on sponsored surfaces).
        sa.Column("placement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("discovery_sessions.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=now_default),
    )
    op.create_index(
        "uq_discovery_events_idempotency", "discovery_events",
        ["idempotency_key"], unique=True,
    )
    op.create_index(
        "idx_discovery_events_target", "discovery_events",
        ["target_type", "target_id"],
    )
    op.create_index(
        "idx_discovery_events_placement", "discovery_events", ["placement_id"]
    )
    op.create_index(
        "idx_discovery_events_created", "discovery_events", ["created_at"]
    )

    if is_postgres:
        op.create_check_constraint(
            "ck_discovery_event_type", "discovery_events",
            "event_type IN ('impression','click','view','apply_start',"
            "'save_intent','event_register_intent')",
        )
        op.create_check_constraint(
            "ck_discovery_target_type", "discovery_events",
            "target_type IN ('job','event','company','banner')",
        )
        op.create_check_constraint(
            "ck_discovery_scope", "discovery_events",
            "scope IN ('anonymous','session','user')",
        )


def downgrade() -> None:
    op.drop_index("idx_discovery_events_created", table_name="discovery_events")
    op.drop_index("idx_discovery_events_placement", table_name="discovery_events")
    op.drop_index("idx_discovery_events_target", table_name="discovery_events")
    op.drop_index("uq_discovery_events_idempotency", table_name="discovery_events")
    op.drop_table("discovery_events")

    op.drop_index("idx_discovery_sessions_user", table_name="discovery_sessions")
    op.drop_index("idx_discovery_sessions_expires", table_name="discovery_sessions")
    op.drop_table("discovery_sessions")
