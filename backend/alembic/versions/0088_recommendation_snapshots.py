"""recommendation_snapshots — privacy-safe audit/repro/eval of served rails (WS-12)

Persists WHAT a guest/student was shown at a recommendation-serving point
(``marketplace/overview`` + ``/jobs/recommendations``): ordered job ids + honest
per-item source + product score + user-safe reason codes, plus the list-level
honest source label and personalization flag. NO PII, NO CV text/title, NO raw
model prompt/confidence — only coarse, reproducible ranking outputs
(``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §8).

``session_id`` FK is ``ON DELETE SET NULL`` so pruning a short-TTL discovery
session never cascade-deletes its longer-retained snapshots (the TTL sweep prunes
snapshots by ``created_at`` on the same retention window as ``discovery_events``).
``user_id`` is FK-less (high-volume append-only ledger, mirrors ``discovery_events``).

The ``coarse_tags`` JSON-shape change to a weighted ``{value: {count, last_seen}}``
map is intentionally NOT a schema migration (same JSONB column, service-layer +
ranker change only), so nothing about it appears here.

Revision ID: 0088_recommendation_snapshots
Revises: 0087_job_competition_daily
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0088_recommendation_snapshots"
down_revision: str | None = "0087_job_competition_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None
    json_type = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    now_default = sa.text("NOW()") if is_postgres else sa.func.now()

    op.create_table(
        "recommendation_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=uuid_default,
        ),
        sa.Column("surface", sa.String(50), nullable=False),
        sa.Column("list_source", sa.String(20), nullable=False),
        sa.Column(
            "personalized", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("discovery_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Plain (FK-less) — high-volume append-only ledger, mirrors discovery_events.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "items",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_postgres else sa.text("'[]'"),
        ),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=now_default,
        ),
    )
    op.create_index(
        "idx_recommendation_snapshots_created",
        "recommendation_snapshots",
        ["created_at"],
    )
    op.create_index(
        "idx_recommendation_snapshots_session",
        "recommendation_snapshots",
        ["session_id"],
    )
    op.create_index(
        "idx_recommendation_snapshots_user",
        "recommendation_snapshots",
        ["user_id"],
    )
    op.create_index(
        "idx_recommendation_snapshots_surface",
        "recommendation_snapshots",
        ["surface", "created_at"],
    )

    if is_postgres:
        op.create_check_constraint(
            "ck_recommendation_snapshot_scope",
            "recommendation_snapshots",
            "scope IN ('anonymous','session','user')",
        )


def downgrade() -> None:
    op.drop_index(
        "idx_recommendation_snapshots_surface",
        table_name="recommendation_snapshots",
    )
    op.drop_index(
        "idx_recommendation_snapshots_user", table_name="recommendation_snapshots"
    )
    op.drop_index(
        "idx_recommendation_snapshots_session", table_name="recommendation_snapshots"
    )
    op.drop_index(
        "idx_recommendation_snapshots_created", table_name="recommendation_snapshots"
    )
    op.drop_table("recommendation_snapshots")
