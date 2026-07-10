"""Organization / RBAC ORM models (``docs/DATA_MODEL.md`` §5, ADR-0002 §3).

Both partner and university organizations share one RBAC model; behaviour differs
by ``organizations.org_type`` (``partner`` | ``university``), not by table tree.
Types use the shared cross-database variants so the same models run on PostgreSQL
(runtime) and SQLite (unit tests). Postgres-only partial / ``lower()`` unique
indexes live in migration ``0003`` only — see that file's docstring.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class Organization(Base):
    """A partner company or the university org. Never hard-deleted (soft only)."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    org_type: Mapped[str] = mapped_column(String(20), nullable=False)  # partner|university
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("industries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_size: Mapped[str | None] = mapped_column(String(30), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    headquarters_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Coarse HQ country (never exact address/GPS). Cosmetic profile field.
    headquarters_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Sensitive legal identity (migration 0099). Editable only through an
    # approved ``company_profile_change_requests`` row — never a direct write.
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tax_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Approved legal/verification document refs. Each entry stores an INTERNAL
    # storage key that is NEVER serialized; presenters emit a short-lived signed
    # delivery URL instead (docs/SECURITY_PRIVACY.md, .claude/rules/backend.md).
    verification_documents: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|active|suspended
    subscription_tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free"
    )  # free|basic|premium|enterprise
    # -1 = unlimited (enterprise). Default 4 = free tier cap.
    max_team_members: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4, server_default="4"
    )
    trust_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="standard"
    )  # standard|verified|strategic
    # The membership currently designated as the org's single "owner" for
    # sensitive actions (ownership transfer). Nullable for legacy rows created
    # before this field existed; callers fall back to the oldest active
    # membership holding the ``*:*`` grant (see ``ownership_service``).
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "memberships.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_organizations_owner_membership_id",
        ),
        nullable=True,
    )
    # A university-staff user acting as this partner org's campus relationship
    # owner (CRM). Settable only by university-role actors (B-553).
    campus_relationship_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    settings: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_departments_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_roles_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Permission(Base):
    """A role-scoped grant tuple rendered as ``"{resource_type}:{action}"``."""

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "resource_type",
            "action",
            name="uq_permissions_role_resource_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)

    @property
    def grant(self) -> str:
        return f"{self.resource_type}:{self.action}"


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id", name="uq_memberships_user_org"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("identities.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active|suspended|left
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MembershipRole(Base):
    __tablename__ = "membership_roles"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class MembershipDepartment(Base):
    __tablename__ = "membership_departments"

    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), primary_key=True
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|accepted|revoked|expired
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PartnerRegistrationRequest(Base):
    """Pending partner self-registration; org created only on approval."""

    __tablename__ = "partner_registration_requests"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(30), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    logo_upload_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending_review"
    )  # pending_review|approved|rejected
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    # AI document verification fields (added in migration 0054)
    tax_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tax_id_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tax_id_api_result: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    document_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_doc_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending"
    )  # pending|passed|tampered|manual_review
    ai_doc_result: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrganizationRiskFlag(Base):
    """A structured risk/trust flag raised against a partner org (B-553 CRM).

    Replaces a single ``trust_level`` enum with a list of explainable flags
    (e.g. unverified tax id, spam reports, billing overdue). University-staff
    or platform-superadmin only: raised/resolved through ``crm_service``, never
    editable by the partner org itself.
    """

    __tablename__ = "organization_risk_flags"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flag_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium"
    )  # low|medium|high
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raised_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrganizationNote(Base):
    """A university-only CRM note about a partner org (never visible to the org).

    Append-only from the partner's perspective: notes are never shown on any
    partner-facing endpoint, only on the university partner-management surface.
    """

    __tablename__ = "organization_notes"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CompanyProfileChangeRequest(Base):
    """Partner-submitted sensitive profile edits / file attachments awaiting
    university approval (owner decision 2026-07-10; migration ``0099``).

    Sensitive identity fields (legal name, tax code, business registration
    number, public display name) and ANY attached company file do NOT touch the
    live ``organizations`` row until a university reviewer approves this request.
    Cosmetic fields (description, website, industry, size, founded year, coarse
    HQ) bypass this table and apply immediately in ``company_profile_service``.

    Concurrency: at most one ``pending`` request may exist per org at a time
    (partial unique index). Further sensitive edits MERGE into the open pending
    request rather than spawning a competing diff, so two requests can never
    corrupt the live profile. Approval/reject/withdraw are single-transaction,
    row-locked, and idempotent.
    """

    __tablename__ = "company_profile_change_requests"
    __table_args__ = (
        # One open request per org — enforced on both Postgres (runtime) and
        # SQLite (unit tests) so the merge/concurrency contract holds everywhere.
        Index(
            "uq_company_change_req_one_pending_per_org",
            "org_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
        Index("ix_company_change_req_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable + SET NULL so the immutable review trail survives user deletion.
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # {field: {"from": <old|None>, "to": <new>}} — metadata only, no secrets.
    proposed_changes: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    # [{id, kind, filename, content_type, size, storage_key}]. ``storage_key`` is
    # NEVER serialized to any client; the presenter emits a signed delivery URL.
    attached_files: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|approved|rejected|withdrawn
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
