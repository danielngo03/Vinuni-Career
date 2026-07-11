"""Remove the anonymous-apply / identity-reveal / blind-screening schema.

Owner decision 2026-07-10: an application ALWAYS exposes the applicant's real
identity to a partner who passes the CV / candidate RBAC gate. The anonymous-apply
+ identity-reveal handshake is removed entirely. CV-access RBAC, the download
watermark, and audit logging of sensitive candidate access are retained.

This migration drops the now-dead schema:

- table ``application_reveal_requests`` (the reveal handshake; its indexes,
  ``uq_reveal_app_org`` unique constraint, and FKs go with the table);
- columns ``applications.is_anonymous``, ``applications.reveal_approved_by`` (its
  inline FK to ``users`` is dropped with the column), and
  ``applications.reveal_approved_at``;
- the retired ``candidate_identity`` reveal capability permission rows
  (``request_reveal`` / ``view_revealed_identity``). The CV-access actions
  (``view_cv`` / ``download_cv``) are KEPT.

``message_threads.is_anonymous`` and the ``reviews.is_anonymous`` column are
intentionally NOT touched — the former is retained (vestigial, always false) and
the latter belongs to the unrelated anonymous-company-review feature.

The downgrade recreates the table + columns exactly as migration ``0006`` did. It
does NOT re-seed the deleted ``candidate_identity`` reveal permission rows (the
role-grant seed owns permission data; the schema round-trip is what a downgrade
guarantees).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0095_remove_anonymous_apply_reveal"
down_revision: str | None = "0094_ai_kb_column_backfill"
branch_labels: str | None = None
depends_on: str | None = None

_UUID = postgresql.UUID(as_uuid=True)
_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1) Drop the dead reveal-request table. Its indexes (``idx_reveal_requests_app``),
    #    the ``uq_reveal_app_org`` unique constraint, and its FKs are dropped with it.
    op.drop_table("application_reveal_requests")

    # 2) Drop the now-dead anonymity / reveal columns on ``applications``.
    if is_postgres:
        # ``drop_column`` also removes the inline FK on ``reveal_approved_by``.
        op.drop_column("applications", "reveal_approved_at")
        op.drop_column("applications", "reveal_approved_by")
        op.drop_column("applications", "is_anonymous")
    else:
        with op.batch_alter_table("applications") as batch:
            batch.drop_column("reveal_approved_at")
            batch.drop_column("reveal_approved_by")
            batch.drop_column("is_anonymous")

    # 3) Retire the removed ``candidate_identity`` reveal capability rows (the
    #    CV-access ``view_cv`` / ``download_cv`` rows are KEPT). Idempotent on both
    #    dialects; a no-op when no such rows exist (e.g. a fresh reseeded DB).
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE resource_type = 'candidate_identity' "
            "AND action IN ('request_reveal', 'view_revealed_identity')"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1) Recreate the ``applications`` anonymity / reveal columns (as in 0006).
    if is_postgres:
        op.add_column(
            "applications",
            sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.add_column(
            "applications",
            sa.Column("reveal_approved_by", _UUID, nullable=True),
        )
        op.add_column(
            "applications",
            sa.Column("reveal_approved_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_foreign_key(
            "applications_reveal_approved_by_fkey",
            "applications",
            "users",
            ["reveal_approved_by"],
            ["id"],
            ondelete="SET NULL",
        )
    else:
        with op.batch_alter_table("applications") as batch:
            batch.add_column(
                sa.Column(
                    "is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()
                )
            )
            batch.add_column(sa.Column("reveal_approved_by", _UUID, nullable=True))
            batch.add_column(
                sa.Column("reveal_approved_at", sa.DateTime(timezone=True), nullable=True)
            )

    # 2) Recreate the reveal-request table (identical to 0006).
    op.create_table(
        "application_reveal_requests",
        sa.Column("id", _UUID, primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column(
            "application_id",
            _UUID,
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requester_id",
            _UUID,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "requester_org_id",
            _UUID,
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint("application_id", "requester_org_id", name="uq_reveal_app_org"),
    )
    op.create_index(
        "idx_reveal_requests_app",
        "application_reveal_requests",
        ["application_id", "status"],
    )
