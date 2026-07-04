"""organization rbac + partner registration

Phase 1b: organizations, departments, roles, permissions, memberships,
membership_roles, membership_departments, invitations, and
partner_registration_requests. Wires the three deferred FKs to ``organizations``
that the baseline/auth-core left as plain UUID columns:

- ``identities.org_id`` -> ``organizations(id)`` (RESTRICT; orgs never hard-deleted)
- ``audit_logs.actor_org_id`` -> ``organizations(id)`` (SET NULL; audit is append-only)
- ``notification_templates.owner_org_id`` -> ``organizations(id)`` (RESTRICT)

Postgres-only constructs (partial / ``lower()`` unique indexes, deferred FKs,
``set_updated_at`` triggers) are guarded by ``is_postgres``; the SQLite unit-test
path creates the schema from ORM metadata and skips these.

Revision ID: 0003_organization_rbac
Revises: 0002_auth_identity_core
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_organization_rbac"
down_revision: str | None = "0002_auth_identity_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGER_TABLES = ["organizations", "roles", "partner_registration_requests"]


def _attach_updated_at_trigger(table: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
    op.execute(
        f"CREATE TRIGGER trg_{table}_updated_at "
        f"BEFORE UPDATE ON {table} "
        f"FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    uuid_default = sa.text("gen_random_uuid()") if is_postgres else None

    # ----------------------------------------------------------- organizations
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("org_type", sa.String(20), nullable=False),  # partner | university
        sa.Column("logo_path", sa.String(500), nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("company_size", sa.String(30), nullable=True),
        sa.Column("founded_year", sa.SmallInteger(), nullable=True),
        sa.Column("headquarters_city", sa.String(100), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("subscription_tier", sa.String(20), nullable=False,
                  server_default="free"),
        sa.Column("trust_level", sa.String(20), nullable=False,
                  server_default="standard"),
        sa.Column("settings", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("idx_orgs_slug", "organizations", ["slug"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index("idx_orgs_type", "organizations", ["org_type", "status"],
                    postgresql_where=sa.text("deleted_at IS NULL"))

    # ------------------------------------------------------------- departments
    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "name", name="uq_departments_org_name"),
    )
    op.create_index("idx_departments_org", "departments", ["org_id"])

    # ------------------------------------------------------------------- roles
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "name", name="uq_roles_org_name"),
    )
    op.create_index("idx_roles_org", "roles", ["org_id"])

    # ------------------------------------------------------------- permissions
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("role_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.UniqueConstraint("role_id", "resource_type", "action",
                            name="uq_permissions_role_resource_action"),
    )
    op.create_index("idx_permissions_role", "permissions", ["role_id"])

    # ------------------------------------------------------------- memberships
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("identities.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.UniqueConstraint("user_id", "org_id", name="uq_memberships_user_org"),
    )
    op.create_index("idx_memberships_org", "memberships", ["org_id"],
                    postgresql_where=sa.text("status = 'active'"))

    # -------------------------------------------------------- membership_roles
    op.create_table(
        "membership_roles",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("memberships.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )

    # -------------------------------------------------- membership_departments
    op.create_table(
        "membership_departments",
        sa.Column("membership_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("memberships.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("departments.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
    )

    # ------------------------------------------------------------- invitations
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roles.id"), nullable=True),
        sa.Column("department_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("idx_invitations_org", "invitations", ["org_id"])

    # ------------------------------------------- partner_registration_requests
    op.create_table(
        "partner_registration_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=uuid_default),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("tax_code", sa.String(50), nullable=True),
        sa.Column("company_website", sa.String(500), nullable=True),
        sa.Column("company_size", sa.String(30), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("contact_title", sa.String(150), nullable=True),
        sa.Column("contact_email", sa.String(320), nullable=False),
        sa.Column("contact_phone", sa.String(30), nullable=True),
        sa.Column("logo_upload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending_review"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ----------------------------------- Postgres-only partial / lower indexes
    if is_postgres:
        op.create_index(
            "uq_invitations_pending_email", "invitations",
            ["org_id", sa.text("lower(email)")], unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        )
        op.create_index(
            "uq_partner_reg_taxcode", "partner_registration_requests",
            ["tax_code"], unique=True,
            postgresql_where=sa.text(
                "status = 'pending_review' AND tax_code IS NOT NULL"
            ),
        )
        op.create_index(
            "uq_partner_reg_email", "partner_registration_requests",
            [sa.text("lower(contact_email)")], unique=True,
            postgresql_where=sa.text("status = 'pending_review'"),
        )

        # ---------------------------------- deferred FKs to organizations
        op.create_foreign_key(
            "fk_identities_org", "identities", "organizations",
            ["org_id"], ["id"], ondelete="RESTRICT",
        )
        op.create_foreign_key(
            "fk_audit_logs_actor_org", "audit_logs", "organizations",
            ["actor_org_id"], ["id"], ondelete="SET NULL",
        )
        op.create_foreign_key(
            "fk_notif_templates_owner_org", "notification_templates",
            "organizations", ["owner_org_id"], ["id"], ondelete="RESTRICT",
        )

        for table in _TRIGGER_TABLES:
            _attach_updated_at_trigger(table)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table in _TRIGGER_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")
        op.drop_constraint("fk_notif_templates_owner_org",
                           "notification_templates", type_="foreignkey")
        op.drop_constraint("fk_audit_logs_actor_org", "audit_logs",
                           type_="foreignkey")
        op.drop_constraint("fk_identities_org", "identities", type_="foreignkey")
        op.drop_index("uq_partner_reg_email",
                      table_name="partner_registration_requests")
        op.drop_index("uq_partner_reg_taxcode",
                      table_name="partner_registration_requests")
        op.drop_index("uq_invitations_pending_email", table_name="invitations")

    op.drop_table("partner_registration_requests")
    op.drop_index("idx_invitations_org", table_name="invitations")
    op.drop_table("invitations")
    op.drop_table("membership_departments")
    op.drop_table("membership_roles")
    op.drop_index("idx_memberships_org", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("idx_permissions_role", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("idx_roles_org", table_name="roles")
    op.drop_table("roles")
    op.drop_index("idx_departments_org", table_name="departments")
    op.drop_table("departments")
    op.drop_index("idx_orgs_type", table_name="organizations")
    op.drop_index("idx_orgs_slug", table_name="organizations")
    op.drop_table("organizations")
