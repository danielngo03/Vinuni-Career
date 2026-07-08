"""Organization profile read/update + the shared org-with-admin bootstrap.

:func:`create_org_with_admin` is the single transactional primitive that both
partner approval (``partner_registration_service``) and university bootstrap reuse
to create an organization, its system ``Admin`` role (``*:*``), the first admin's
identity + membership, and the audit trail. RBAC is enforced here, not in routers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.api import presenters
from app.modules.organization.application import role_seed
from app.modules.organization.application.errors import VersionConflictError
from app.modules.organization.application.org_resolution import resolve_managed_org
from app.modules.organization.domain import catalog
from app.modules.organization.domain.models import (
    Membership,
    MembershipRole,
    Organization,
    Permission,
    Role,
)
from app.modules.users.application import user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "organizations"

_UPDATABLE_FIELDS = {
    "display_name",
    "website_url",
    "description",
    "industry",
    "company_size",
    "founded_year",
    "headquarters_city",
    # ``logo_path`` is deliberately excluded: the logo is a validated binary asset
    # mutated only through the logo upload/remove endpoints, never a JSON field.
    "settings",
}


def _audit_ctx(
    principal: Principal, ctx: RequestContext, *, org_id: uuid.UUID | None = None
) -> AuditContext:
    # ``org_id`` (the RESOLVED managed org) is stamped as ``actor_org_id`` so a
    # superadmin's cross-org write lands in that org's audit trail; for an
    # ordinary actor the resolved org == ``principal.org_id`` (unchanged).
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=org_id if org_id is not None else principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _get_org(session: AsyncSession, org_id: uuid.UUID) -> Organization | None:
    stmt = select(Organization).where(
        Organization.id == org_id, Organization.deleted_at.is_(None)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def unique_slug(session: AsyncSession, display_name: str) -> str:
    base = catalog.slugify(display_name)
    candidate = base
    suffix = 1
    while True:
        exists = (
            await session.execute(
                select(Organization.id).where(Organization.slug == candidate)
            )
        ).first()
        if exists is None:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


@dataclass(slots=True)
class OrgBootstrapResult:
    organization: Organization
    admin_role: Role
    membership: Membership


async def create_org_with_admin(
    session: AsyncSession,
    *,
    org_type: str,
    display_name: str,
    admin_user_id: uuid.UUID,
    admin_persona: str,
    actor_id: uuid.UUID | None,
    ctx: RequestContext,
    status: str = "active",
    is_verified: bool = False,
    verified_by: uuid.UUID | None = None,
    trust_level: str = "standard",
    subscription_tier: str = "free",
    company_fields: dict | None = None,
) -> OrgBootstrapResult:
    """Create org + system Admin role (``*:*``) + first admin membership.

    No commit — the caller owns the transaction so the whole bootstrap is atomic.
    """

    now = datetime.now(tz=UTC)
    slug = await unique_slug(session, display_name)
    org = Organization(
        slug=slug,
        display_name=display_name,
        org_type=org_type,
        status=status,
        is_verified=is_verified,
        verified_at=now if is_verified else None,
        verified_by=verified_by,
        trust_level=trust_level,
        subscription_tier=subscription_tier,
        **(company_fields or {}),
    )
    session.add(org)
    await session.flush()

    admin_role = Role(
        org_id=org.id,
        name=catalog.SYSTEM_ADMIN_ROLE_NAME,
        description="System administrator (full access).",
        is_system=True,
    )
    session.add(admin_role)
    await session.flush()
    session.add(
        Permission(
            role_id=admin_role.id,
            resource_type=catalog.ADMIN_WILDCARD_RESOURCE,
            action=catalog.ADMIN_WILDCARD_ACTION,
        )
    )

    identity = await user_service.add_identity(
        session, user_id=admin_user_id, persona=admin_persona, org_id=org.id
    )
    membership = Membership(
        user_id=admin_user_id,
        org_id=org.id,
        identity_id=identity.id,
        status="active",
    )
    session.add(membership)
    await session.flush()
    session.add(
        MembershipRole(
            membership_id=membership.id,
            role_id=admin_role.id,
            assigned_by=actor_id,
        )
    )
    org.owner_membership_id = membership.id
    await session.flush()

    audit_ctx = AuditContext(actor_id=actor_id, actor_org_id=org.id,
                             ip=ctx.ip, user_agent=ctx.user_agent)
    await write_audit(
        session, action="organization.created", resource_type="organization",
        resource_id=org.id, context=audit_ctx,
        after={"slug": slug, "org_type": org_type, "status": status,
               "trust_level": trust_level, "subscription_tier": subscription_tier},
    )
    await write_audit(
        session, action="role.created", resource_type="role",
        resource_id=admin_role.id, context=audit_ctx,
        after={"name": admin_role.name, "is_system": True, "permissions": ["*:*"]},
    )
    await write_audit(
        session, action="membership.created", resource_type="membership",
        resource_id=membership.id, context=audit_ctx,
        after={"user_id": str(admin_user_id), "roles": [str(admin_role.id)]},
    )
    return OrgBootstrapResult(
        organization=org, admin_role=admin_role, membership=membership
    )


# --------------------------------------------------------------------------- #
# Profile read / update                                                       #
# --------------------------------------------------------------------------- #


async def get_organization(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID | None = None,
    locale: str = "vi",
) -> dict:
    resolved = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(
        principal, _RESOURCE, "read", resource_org_id=resolved
    )
    org = await _get_org(session, resolved)
    if org is None:
        raise ResourceNotFoundError()
    return presenters.organization_detail(org, locale=locale)


async def update_organization(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    org_id: uuid.UUID | None = None,
    locale: str = "vi",
) -> dict:
    resolved = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(
        principal, _RESOURCE, "update", resource_org_id=resolved
    )
    org = await _get_org(session, resolved)
    if org is None:
        raise ResourceNotFoundError()

    expected_version = payload.pop("version", None)
    if expected_version is not None and expected_version != org.version:
        raise VersionConflictError()

    changed: dict[str, object] = {}
    for field in _UPDATABLE_FIELDS:
        if field in payload:
            setattr(org, field, payload[field])
            changed[field] = payload[field]
    if changed:
        org.version += 1
    await session.flush()
    await write_audit(
        session, action="organization.updated", resource_type="organization",
        resource_id=org.id, context=_audit_ctx(principal, ctx, org_id=resolved),
        after={"fields": sorted(changed.keys())},
    )
    await session.commit()
    return presenters.organization_detail(org, locale=locale)


async def create_university_org(
    session: AsyncSession,
    *,
    principal: Principal,
    display_name: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Superadmin-only university bootstrap (ADR-0002 §5.4)."""

    if not principal.is_superadmin:
        permission_checker.require(principal, _RESOURCE, "create")  # -> 403
    assert principal.user_id is not None
    result = await create_org_with_admin(
        session,
        org_type="university",
        display_name=display_name,
        admin_user_id=principal.user_id,
        admin_persona="university_staff",
        actor_id=principal.user_id,
        ctx=ctx,
        status="active",
        is_verified=True,
        verified_by=principal.user_id,
        trust_level="strategic",
    )
    # Seed editable starter roles (Career Services / Moderation / Partnerships /
    # Analytics) in the same transaction as the bootstrap. Idempotent.
    await role_seed.ensure_university_starter_roles(
        session, org_id=result.organization.id, actor_id=principal.user_id, ctx=ctx
    )
    await session.commit()
    return presenters.organization_detail(result.organization, locale=locale)
