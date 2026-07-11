"""Company profile approval workflow (``company_profile_change_requests``) +
sensitive/legal org profile columns (owner decision 2026-07-10).

Partner admins may edit their own company page, but sensitive legal identity
fields (legal name, tax code, business registration number, public display
name) and ANY attached company file must wait for a university reviewer to
approve them. This migration adds:

- Sensitive/legal columns on ``organizations``: ``legal_name``, ``tax_code``,
  ``registration_number``, coarse ``headquarters_country``, and a JSONB
  ``verification_documents`` list of APPROVED legal/verification doc refs (each
  ref stores an internal storage key that is NEVER serialized — presenters emit
  a signed delivery URL instead).
- ``company_profile_change_requests``: the approval-queue entity. A JSONB diff
  of proposed field changes + attached file refs, a ``pending/approved/rejected/
  withdrawn`` status, and an immutable reviewer trail. A partial unique index
  guarantees at most one OPEN request per org so two competing diffs can never
  corrupt the live profile.

Chain: down_revision ``0098_advertising_engine`` (Lane 2C-A, created in
parallel). Do not rechain onto 0097.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0099_company_profile_approval"
down_revision: str | None = "0098_advertising_engine"
branch_labels: str | None = None
depends_on: str | None = None

_UUID = postgresql.UUID(as_uuid=True)
_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    # --- Sensitive / legal columns on organizations ------------------------- #
    op.add_column("organizations", sa.Column("headquarters_country", sa.String(100), nullable=True))
    op.add_column("organizations", sa.Column("legal_name", sa.String(255), nullable=True))
    op.add_column("organizations", sa.Column("tax_code", sa.String(50), nullable=True))
    op.add_column(
        "organizations", sa.Column("registration_number", sa.String(100), nullable=True)
    )
    op.add_column(
        "organizations",
        sa.Column(
            "verification_documents",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # --- Approval queue entity --------------------------------------------- #
    op.create_table(
        "company_profile_change_requests",
        sa.Column("id", _UUID, primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column(
            "org_id",
            _UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SET NULL keeps the immutable review trail if the submitter is deleted.
        sa.Column(
            "submitted_by",
            _UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # {field: {"from": <old|None>, "to": <new>}} — metadata only, no secrets.
        sa.Column(
            "proposed_changes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # [{id, kind, filename, content_type, size, storage_key}] — storage_key
        # is never serialized; the presenter emits a signed delivery URL.
        sa.Column(
            "attached_files",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "reviewer_id",
            _UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index(
        "ix_company_profile_change_requests_org_id",
        "company_profile_change_requests",
        ["org_id"],
    )
    op.create_index(
        "ix_company_change_req_status",
        "company_profile_change_requests",
        ["status"],
    )
    # At most one OPEN request per org (concurrency-safe merge contract).
    op.create_index(
        "uq_company_change_req_one_pending_per_org",
        "company_profile_change_requests",
        ["org_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_company_change_req_one_pending_per_org",
        table_name="company_profile_change_requests",
    )
    op.drop_index(
        "ix_company_change_req_status", table_name="company_profile_change_requests"
    )
    op.drop_index(
        "ix_company_profile_change_requests_org_id",
        table_name="company_profile_change_requests",
    )
    op.drop_table("company_profile_change_requests")
    op.drop_column("organizations", "verification_documents")
    op.drop_column("organizations", "registration_number")
    op.drop_column("organizations", "tax_code")
    op.drop_column("organizations", "legal_name")
    op.drop_column("organizations", "headquarters_country")
