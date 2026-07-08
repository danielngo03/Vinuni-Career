"""Organization profile read/update + the shared org-with-admin bootstrap.

:func:`create_org_with_admin` is the single transactional primitive that both
partner approval (``partner_registration_service``) and university bootstrap reuse
to create an organization, its system ``Admin`` role (``*:*``), the first admin's
identity + membership, and the audit trail. RBAC is enforced here, not in routers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.api import presenters
from app.modules.organization.application.errors import VersionConflictError
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


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
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


# --------------------------------------------------------------------------- #
# Starter partner roles (GAP A)                                               #
# --------------------------------------------------------------------------- #
#
# On partner-org creation only the system ``Admin`` role (``*:*``) used to be
# seeded, so a partner admin had to hand-build every non-admin role before it
# could delegate anything. We now seed a small set of READY-TO-ASSIGN,
# NON-SYSTEM roles (``is_system=False``) with sensible capability bundles drawn
# ONLY from ``catalog.PERMISSION_CATALOG`` (each tuple is validated with
# ``catalog.is_catalog_permission`` at seed time). These are ordinary roles the
# admin can freely edit/rename/delete/assign through ``rbac_service`` — they are
# convenience bundles, NOT hardcoded capability sources: every runtime
# authorization still gates on the ``resource:action`` grant, never the role
# name (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md``). University orgs are unchanged.
#
# ``candidate_identity`` is deliberately split across the bundles so the
# fine-grained CV/identity grants actually restrict something: Recruiter carries
# the full sensitive set (request reveal + view revealed identity + view/download
# CV); Hiring Manager may view a CV and a revealed identity but NOT download the
# file; Analyst/Coordinator hold NO candidate_identity at all.
PARTNER_STARTER_ROLES: dict[str, tuple[tuple[str, str], ...]] = {
    "Recruiter": (
        ("jobs", "read"),
        ("jobs", "create"),
        ("jobs", "update"),
        ("applications", "read"),
        ("applications", "update"),
        ("applications", "review"),
        ("pipeline", "read"),
        ("pipeline", "move_candidate"),
        ("pipeline", "rollback"),
        ("scorecards", "read"),
        ("scorecards", "submit"),
        ("interviews", "read"),
        ("interviews", "schedule"),
        ("candidate_identity", "request_reveal"),
        ("candidate_identity", "view_revealed_identity"),
        ("candidate_identity", "view_cv"),
        ("candidate_identity", "download_cv"),
        ("ai_recruiting", "draft_jd"),
        ("ai_recruiting", "screen_candidate"),
        ("ai_recruiting", "suggest_scorecard"),
    ),
    "Hiring Manager": (
        ("applications", "read"),
        ("pipeline", "read"),
        ("pipeline", "move_candidate"),
        ("scorecards", "read"),
        ("scorecards", "submit"),
        ("scorecards", "read_aggregate"),
        ("interviews", "read"),
        ("interviews", "schedule"),
        ("interviews", "assign"),
        ("interviews", "complete"),
        ("interviews", "cancel"),
        ("offers", "create"),
        ("offers", "approve"),
        ("offers", "send"),
        ("candidate_identity", "view_cv"),
        ("candidate_identity", "view_revealed_identity"),
        ("analytics", "view_job_metrics"),
    ),
    "Analyst": (
        ("analytics", "view_job_metrics"),
        ("analytics", "view_clicks"),
        ("analytics", "export"),
        ("applications", "read"),
    ),
    "Coordinator": (
        ("interviews", "read"),
        ("interviews", "schedule"),
        ("interviews", "assign"),
        ("interviews", "complete"),
        ("interviews", "cancel"),
        ("events", "read"),
        ("events", "create"),
        ("events", "update"),
        ("events", "register"),
        ("applications", "read"),
    ),
}

_STARTER_ROLE_DESCRIPTIONS: dict[str, str] = {
    "Recruiter": (
        "Sources and screens candidates: jobs, applications, pipeline, "
        "scorecards, interviews, candidate identity + CV access, and AI "
        "recruiting assists."
    ),
    "Hiring Manager": (
        "Decides on candidates: applications, pipeline, scorecards, "
        "interviews, offers, CV/identity view (no CV download), and job "
        "metrics."
    ),
    "Analyst": (
        "Read-only recruiting analytics (job metrics, clicks, export) plus "
        "application read. No candidate identity or CV access."
    ),
    "Coordinator": (
        "Logistics: schedules interviews, manages events, and reads "
        "applications. No candidate identity or CV access."
    ),
}


async def _seed_partner_starter_roles(
    session: AsyncSession,
    *,
    org: Organization,
    audit_ctx: AuditContext,
) -> list[Role]:
    """Seed the ready-to-assign non-system partner roles (idempotent).

    Skips any role whose name already exists for the org, so re-running against
    an org that already has (some of) these roles never creates duplicates. Each
    creation is audited exactly like the Admin role. No commit — the caller owns
    the transaction so the whole bootstrap stays atomic.
    """

    existing_names = set(
        (
            await session.execute(select(Role.name).where(Role.org_id == org.id))
        ).scalars().all()
    )
    seeded: list[Role] = []
    for name, grants in PARTNER_STARTER_ROLES.items():
        if name in existing_names:
            continue  # idempotent: never duplicate an already-present role
        # Defensive: a bundle referencing a non-catalog permission is a coding
        # error (it would also be un-authorable via rbac_service) — fail loud.
        for resource, action in grants:
            if not catalog.is_catalog_permission(resource, action):
                raise ValueError(
                    f"starter role {name!r} references non-catalog permission "
                    f"{resource}:{action}"
                )
        role = Role(
            org_id=org.id,
            name=name,
            description=_STARTER_ROLE_DESCRIPTIONS[name],
            is_system=False,
        )
        session.add(role)
        await session.flush()
        for resource, action in grants:
            session.add(
                Permission(role_id=role.id, resource_type=resource, action=action)
            )
        await session.flush()
        await write_audit(
            session, action="role.created", resource_type="role",
            resource_id=role.id, context=audit_ctx,
            after={
                "name": name,
                "is_system": False,
                "permissions": sorted(f"{r}:{a}" for r, a in grants),
            },
        )
        seeded.append(role)
    return seeded


@dataclass(slots=True)
class OrgBootstrapResult:
    organization: Organization
    admin_role: Role
    membership: Membership
    # Ready-to-assign non-system roles seeded for partner orgs (empty for
    # university orgs). Convenience for callers/tests; the roles are also plain
    # rows queryable through ``rbac_service``.
    starter_roles: list[Role] = field(default_factory=list)


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

    # GAP A: seed ready-to-assign non-system roles for PARTNER orgs only, so a
    # partner admin can delegate immediately without hand-building every role.
    # University seeding is intentionally left unchanged.
    starter_roles: list[Role] = []
    if org_type == "partner":
        starter_roles = await _seed_partner_starter_roles(
            session, org=org, audit_ctx=audit_ctx
        )

    return OrgBootstrapResult(
        organization=org, admin_role=admin_role, membership=membership,
        starter_roles=starter_roles,
    )


# --------------------------------------------------------------------------- #
# Profile read / update                                                       #
# --------------------------------------------------------------------------- #


async def get_organization(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "read", resource_org_id=principal.org_id
    )
    org = await _get_org(session, principal.org_id)
    if org is None:
        raise ResourceNotFoundError()
    return presenters.organization_detail(org, locale=locale)


async def update_organization(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "update", resource_org_id=principal.org_id
    )
    org = await _get_org(session, principal.org_id)
    if org is None:
        raise ResourceNotFoundError()

    expected_version = payload.pop("version", None)
    if expected_version is not None and expected_version != org.version:
        raise VersionConflictError()

    changed: dict[str, object] = {}
    for field_name in _UPDATABLE_FIELDS:
        if field_name in payload:
            setattr(org, field_name, payload[field_name])
            changed[field_name] = payload[field_name]
    if changed:
        org.version += 1
    await session.flush()
    await write_audit(
        session, action="organization.updated", resource_type="organization",
        resource_id=org.id, context=_audit_ctx(principal, ctx),
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
    await session.commit()
    return presenters.organization_detail(result.organization, locale=locale)
