"""DB-backed grant resolution for the request :class:`Principal`.

Replaces the Phase 1a static persona-baseline grants for *org* personas. The auth
dependency calls :func:`resolve_grants` to build ``Principal.permissions`` from
``memberships -> membership_roles -> roles -> permissions`` scoped to the active
identity's ``org_id``. Students/alumni (no org) and members whose membership is
not ``active`` fall back to the persona baseline (ADR-0002 §4.3).

This is the only read interface the ``auth`` module imports from ``organization``
(one-way auth -> organization dependency).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain.personas import permissions_for
from app.modules.organization.domain.models import (
    Membership,
    MembershipRole,
    Permission,
)

# Self-service baseline every authenticated persona keeps, org or not.
_COMMON_ORG_BASELINE = frozenset({"account:*", "notifications:read", "notifications:write"})


async def active_membership(
    session: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> Membership | None:
    stmt = select(Membership).where(
        Membership.user_id == user_id,
        Membership.org_id == org_id,
        Membership.status == "active",
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def grants_for_membership(
    session: AsyncSession, *, membership_id: uuid.UUID
) -> frozenset[str]:
    """Render every permission tuple reachable from a membership's roles."""

    stmt = (
        select(Permission.resource_type, Permission.action)
        .join(MembershipRole, MembershipRole.role_id == Permission.role_id)
        .where(MembershipRole.membership_id == membership_id)
    )
    rows = (await session.execute(stmt)).all()
    return frozenset(f"{resource}:{action}" for resource, action in rows)


async def grants_for_roles(session: AsyncSession, *, role_ids: list[uuid.UUID]) -> frozenset[str]:
    """Render every permission tuple reachable from a set of role ids directly.

    Used by permission-preview for a hypothetical (not-yet-assigned) role
    combination, e.g. before an invite is sent (ADR-0002 grant-preview slice).
    """

    if not role_ids:
        return frozenset()
    stmt = select(Permission.resource_type, Permission.action).where(
        Permission.role_id.in_(role_ids)
    )
    rows = (await session.execute(stmt)).all()
    return frozenset(f"{resource}:{action}" for resource, action in rows)


async def resolve_grants(session: AsyncSession, *, user_id: uuid.UUID, identity) -> frozenset[str]:
    """Resolve the effective permission set for ``user_id`` acting as ``identity``.

    - No org context -> Phase 1a persona baseline (unchanged).
    - Org context but no active membership -> persona baseline (safe drop).
    - Active membership -> DB role grants + the common org baseline.
    """

    org_id = getattr(identity, "org_id", None)
    persona = getattr(identity, "persona", "guest")
    if org_id is None:
        return permissions_for(persona)

    membership = await active_membership(session, user_id=user_id, org_id=org_id)
    if membership is None:
        return permissions_for(persona)

    grants = await grants_for_membership(session, membership_id=membership.id)
    return grants | _COMMON_ORG_BASELINE
