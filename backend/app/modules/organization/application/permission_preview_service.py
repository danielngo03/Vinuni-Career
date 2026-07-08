"""Permission preview (B-518/519): "what would this person be able to do".

Two shapes:

- :func:`preview_for_member` — the *actual* effective grant set for an existing
  membership (post-invite / already-on-the-team check).
- :func:`preview_hypothetical` — a *what-if* preview for a candidate
  role/department combination before an invite is sent, so the inviter can see
  the resulting capability set without creating anything.

Both are gated by ``members:read`` (the same grant that lets an actor browse the
team roster) since a permission preview reveals another person's effective
access, not just their own.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.application import grant_resolver
from app.modules.organization.application.org_resolution import resolve_managed_org
from app.modules.organization.domain.models import Membership, Role
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker


def _grants_summary(grants: frozenset[str]) -> dict:
    by_resource: dict[str, list[str]] = {}
    for grant in sorted(grants):
        resource, _, action = grant.partition(":")
        by_resource.setdefault(resource, []).append(action)
    return {
        "grants": sorted(grants),
        "is_admin": "*:*" in grants or "*" in grants,
        "by_resource": by_resource,
    }


async def preview_for_member(
    session: AsyncSession, *, principal: Principal, membership_id: uuid.UUID,
    org_id: uuid.UUID | None = None,
) -> dict:
    """Effective grant set for an existing member (tenant-isolated, 404 hidden)."""

    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(principal, "members", "read", resource_org_id=org_id)

    membership = (
        await session.execute(
            select(Membership).where(
                Membership.id == membership_id, Membership.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise ResourceNotFoundError()

    grants = await grant_resolver.grants_for_membership(
        session, membership_id=membership.id
    )
    result = _grants_summary(grants)
    result["membership_id"] = str(membership.id)
    result["membership_status"] = membership.status
    return result


async def preview_hypothetical(
    session: AsyncSession,
    *,
    principal: Principal,
    role_ids: list[uuid.UUID],
    department_ids: list[uuid.UUID] | None = None,
    org_id: uuid.UUID | None = None,
) -> dict:
    """What-if preview for a candidate role set, e.g. before sending an invite.

    Department ids are echoed back (informational scope tag) but do not further
    restrict grants in the current RBAC model — roles are the sole grant source.
    """

    org_id = await resolve_managed_org(session, principal, org_id=org_id)
    permission_checker.require(principal, "members", "read", resource_org_id=org_id)

    target_ids = list(dict.fromkeys(role_ids))
    roles = (
        await session.execute(
            select(Role.id).where(Role.id.in_(target_ids), Role.org_id == org_id)
        )
    ).scalars().all() if target_ids else []
    if len(roles) != len(target_ids):
        raise ResourceNotFoundError()

    grants = await grant_resolver.grants_for_roles(session, role_ids=target_ids)
    result = _grants_summary(grants)
    result["role_ids"] = [str(r) for r in target_ids]
    result["department_ids"] = [str(d) for d in (department_ids or [])]
    return result
