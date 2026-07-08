"""events: events + event_registrations (ADR-0008, Phase 2 foundation)

Free single-admission events alongside jobs in the ``opportunities`` module:

- ``events`` — postings + lifecycle (draft|pending_review|published|cancelled|
  completed|rejected) + moderation state + sponsored/featured + event-level
  ``capacity``/``registration_count``. Soft delete, optimistic ``version``.
- ``event_registrations`` — one free admission per (event, user). Ticketing / QR /
  payment columns are intentionally OMITTED (deferred ticketing ADR).

Postgres-only constructs are guarded by ``is_postgres``:

- partial discovery indexes (``WHERE deleted_at IS NULL``)
- the partial unique active-registration index (``WHERE status <> 'cancelled'``)
- the ``set_updated_at`` triggers

The SQLite unit-test path creates the schema from ORM metadata and skips these;
the active-registration uniqueness is enforced there by the service-layer guard.

Revision ID: 0016_events_registration_and_checkin
Revises: 0015_recruitment_offers
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_events_registration"
down_revision: str | None = "0015_recruitment_offers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ----------------------------------------------------------------- events
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("slug", sa.String(600), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("cover_image_path", sa.String(1000), nullable=True),
        sa.Column("venue_name", sa.String(300), nullable=True),
        sa.Column("venue_address", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False,
                  server_default="Asia/Ho_Chi_Minh"),
        sa.Column("registration_opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("registration_count", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("visibility", sa.String(20), nullable=False,
                  server_default="public"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("moderation_status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_featured", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("is_sponsored", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("tags", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("settings", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # ------------------------------------------------- event_registrations
    op.create_table(
        "event_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("event_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="confirmed"),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_in_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    if is_postgres:
        op.create_index(
            "idx_events_org", "events", ["org_id", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        op.create_index(
            "idx_events_dates", "events", ["starts_at", "status"],
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
        # Capacity counts + attendee list + FIFO waitlist all key on (event, status).
        op.create_index(
            "idx_event_reg_event_status", "event_registrations",
            ["event_id", "status"],
        )
        # One ACTIVE registration per (event, user); a cancelled row frees the slot
        # so the user may re-register.
        op.create_index(
            "uq_event_reg_active", "event_registrations", ["event_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("status <> 'cancelled'"),
        )

        op.execute("DROP TRIGGER IF EXISTS trg_events_updated_at ON events;")
        op.execute(
            "CREATE TRIGGER trg_events_updated_at BEFORE UPDATE ON events "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_event_registrations_updated_at "
            "ON event_registrations;"
        )
        op.execute(
            "CREATE TRIGGER trg_event_registrations_updated_at BEFORE UPDATE ON "
            "event_registrations FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )
    else:
        op.create_index("idx_events_org", "events", ["org_id", "status"])
        op.create_index("idx_events_dates", "events", ["starts_at", "status"])
        op.create_index(
            "idx_event_reg_event_status", "event_registrations",
            ["event_id", "status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            "DROP TRIGGER IF EXISTS trg_event_registrations_updated_at "
            "ON event_registrations;"
        )
        op.execute("DROP TRIGGER IF EXISTS trg_events_updated_at ON events;")
        op.drop_index("uq_event_reg_active", table_name="event_registrations")
        op.drop_index("idx_event_reg_event_status", table_name="event_registrations")
        op.drop_index("idx_events_dates", table_name="events")
        op.drop_index("idx_events_org", table_name="events")
    else:
        op.drop_index("idx_event_reg_event_status", table_name="event_registrations")
        op.drop_index("idx_events_dates", table_name="events")
        op.drop_index("idx_events_org", table_name="events")

    op.drop_table("event_registrations")
    op.drop_table("events")
