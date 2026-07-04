"""Platform trust: consents, privacy_requests, content_reports (ADR-0014, E36).

``docs/DATA_MODEL.md`` §35. Three new tables, none using ``BaseEntity`` (no
partner/university org-scoped soft-delete/version semantics apply) — plain PK
+ explicit ``created_at``, matching the house pattern already used by
``NotificationOutbox`` / ``HumanReviewItem`` / ``ReviewReport``.

Revision ID: 0060_platform_trust
Revises: 0059_merge_heads
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0060_platform_trust"
down_revision = "0059_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consent_type", sa.String(50), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "consent_type", name="uq_consent_user_type"),
    )
    op.create_index("idx_consents_user", "consents", ["user_id"])

    op.create_table(
        "privacy_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "requested_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "processed_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_privacy_requests_requested_by", "privacy_requests", ["requested_by"]
    )
    op.create_index(
        "idx_privacy_requests_status", "privacy_requests", ["status", "created_at"]
    )

    op.create_table(
        "content_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "reporter_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reporter_org_id", sa.Uuid(), nullable=True),
        sa.Column("reason_code", sa.String(30), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column(
            "review_item_id",
            sa.Uuid(),
            sa.ForeignKey("human_review_queue.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "reporter_id", "entity_type", "entity_id",
            name="uq_content_report_reporter_entity",
        ),
    )
    op.create_index(
        "idx_content_reports_entity", "content_reports", ["entity_type", "entity_id"]
    )
    op.create_index(
        "idx_content_reports_status", "content_reports", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_content_reports_status", table_name="content_reports")
    op.drop_index("idx_content_reports_entity", table_name="content_reports")
    op.drop_table("content_reports")

    op.drop_index("idx_privacy_requests_status", table_name="privacy_requests")
    op.drop_index("idx_privacy_requests_requested_by", table_name="privacy_requests")
    op.drop_table("privacy_requests")

    op.drop_index("idx_consents_user", table_name="consents")
    op.drop_table("consents")
