"""``GET /organizations/members/me`` — the caller's own effective capability map.

The redesigned partner + university workspaces gate every nav group, quick
action, and page control on what the acting member may actually do. Rather than
each surface re-deriving that from scattered role checks, this read returns the
caller's effective grant set once, plus a curated boolean ``capabilities`` map
keyed by the ``resource:action`` tuples the IA needs, plus ``is_org_admin`` and
the member's department scope.

Read-only, no audit. RBAC: any authenticated org member may read THEIR OWN
capabilities (there is no cross-member disclosure here — a member's own effective
access is not privileged information to that member). Reuses
``grant_resolver`` for the authoritative DB grant set and the shared
``permission_checker`` for the wildcard/superadmin-aware capability booleans, so
this never invents a parallel authorization path.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.application import grant_resolver
from app.modules.organization.domain.models import Department, MembershipDepartment
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal, permission_checker

# The capability tuples the redesigned partner + university IA gates on. Kept as a
# flat, explicit catalog (not derived) so a nav/action gate always resolves to a
# stable boolean, ``True`` for wildcard admins and any member holding the grant.
_CAPABILITY_CATALOG: tuple[str, ...] = (
    # --- partner: overview / hiring ---
    "jobs:read",
    "jobs:create",
    "jobs:update",
    "jobs:submit",
    "applications:read",
    "pipeline:move_candidate",
    "candidate_identity:view_cv",
    "candidate_identity:download_cv",
    "candidate_identity:request_reveal",
    # --- partner: growth ---
    "analytics:view_job_metrics",
    "analytics:view_clicks",
    "analytics:export",
    "advertising:view",
    "advertising:create",
    "advertising:submit",
    "events:read",
    "events:create",
    "events:update",
    # --- partner: workspace ---
    "members:read",
    "billing:view",
    "billing:manage",
    "billing:subscribe",
    # --- university: governance / operations / institution ---
    "jobs:moderate",
    "events:moderate",
    "advertising:moderate",
    "partners:read",
    "partners:approve",
    "partners:reject",
    "reviews:moderate",
    "cv_templates:read",
    "cv_templates:create",
    "cv_templates:update",
    "ai_settings:read",
    "ai_settings:manage",
    "organizations:read",
)


def _is_admin(grants: frozenset[str], principal: Principal) -> bool:
    return principal.is_superadmin or "*:*" in grants or "*" in grants


def _by_resource(grants: frozenset[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for grant in sorted(grants):
        resource, _, action = grant.partition(":")
        out.setdefault(resource, []).append(action)
    return out


async def _departments_for_membership(
    session: AsyncSession, *, membership_id: uuid.UUID
) -> list[dict]:
    rows = (
        await session.execute(
            select(Department.id, Department.name)
            .join(MembershipDepartment, MembershipDepartment.department_id == Department.id)
            .where(MembershipDepartment.membership_id == membership_id)
            .order_by(Department.name)
        )
    ).all()
    return [{"id": str(dept_id), "name": name} for dept_id, name in rows]


async def get_my_capabilities(session: AsyncSession, *, principal: Principal) -> dict:
    """The caller's own effective grants, capability booleans, and department scope."""

    user_id = principal.user_id
    if user_id is None:
        raise AuthRequiredError()
    org_id = principal.org_id
    if org_id is None:
        # Non-org personas (students/alumni/guests) have no org capability map.
        raise PermissionDeniedError()

    membership = await grant_resolver.active_membership(
        session, user_id=user_id, org_id=org_id
    )
    if membership is not None:
        grants = await grant_resolver.grants_for_membership(session, membership_id=membership.id)
        departments = await _departments_for_membership(session, membership_id=membership.id)
        membership_id: str | None = str(membership.id)
        membership_status: str | None = membership.status
    else:
        # Active identity with org context but no active membership row (e.g. a
        # superadmin acting in an org): fall back to the already-resolved principal
        # grant set rather than fabricating one.
        grants = frozenset(principal.permissions)
        departments = []
        membership_id = None
        membership_status = None

    capabilities = {
        key: permission_checker.can(
            principal, key.split(":", 1)[0], key.split(":", 1)[1], resource_org_id=org_id
        )
        for key in _CAPABILITY_CATALOG
    }

    return {
        "org_id": str(org_id),
        "membership_id": membership_id,
        "membership_status": membership_status,
        "is_org_admin": _is_admin(grants, principal),
        "grants": sorted(grants),
        "by_resource": _by_resource(grants),
        "capabilities": capabilities,
        "departments": departments,
    }
