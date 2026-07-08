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
    """Render the ORG-WIDE permission tuples reachable from a membership's roles.

    Org-wide = role assignments whose ``department_id IS NULL``. When a
    membership has no department-scoped role assignments (the only state that
    exists before P2/WS2.1), every ``membership_roles`` row is NULL-scoped and
    this returns exactly today's full set — the ``IS NULL`` predicate is a no-op.
    """

    stmt = (
        select(Permission.resource_type, Permission.action)
        .join(MembershipRole, MembershipRole.role_id == Permission.role_id)
        .where(
            MembershipRole.membership_id == membership_id,
            MembershipRole.department_id.is_(None),
        )
    )
    rows = (await session.execute(stmt)).all()
    return frozenset(f"{resource}:{action}" for resource, action in rows)


async def department_grants_for_membership(
    session: AsyncSession, *, membership_id: uuid.UUID
) -> dict[uuid.UUID, frozenset[str]]:
    """Group a membership's DEPARTMENT-SCOPED grants by ``department_id``.

    Only role assignments with a non-NULL ``department_id`` contribute. Returns
    an empty dict when the membership has no scoped assignments (today's state),
    so the resulting :class:`~app.shared.permissions.Principal` is unchanged.
    """

    stmt = (
        select(
            MembershipRole.department_id,
            Permission.resource_type,
            Permission.action,
        )
        .join(Permission, Permission.role_id == MembershipRole.role_id)
        .where(
            MembershipRole.membership_id == membership_id,
            MembershipRole.department_id.is_not(None),
        )
    )
    rows = (await session.execute(stmt)).all()
    grouped: dict[uuid.UUID, set[str]] = {}
    for dept_id, resource, action in rows:
        grouped.setdefault(dept_id, set()).add(f"{resource}:{action}")
    return {dept_id: frozenset(grants) for dept_id, grants in grouped.items()}


async def grants_for_roles(
    session: AsyncSession, *, role_ids: list[uuid.UUID]
) -> frozenset[str]:
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


async def resolve_scoped_grants(
    session: AsyncSession, *, user_id: uuid.UUID, identity
) -> tuple[frozenset[str], dict[uuid.UUID, frozenset[str]]]:
    """Resolve both the org-wide grant set and the department-scoped grant map.

    Returns ``(org_wide_grants, department_grants)``:

    - No org context -> ``(persona baseline, {})`` (unchanged).
    - Org context but no active membership -> ``(persona baseline, {})``.
    - Active membership -> ``(org-wide DB grants + common baseline, dept grants)``.

    ``org_wide_grants`` is byte-for-byte the pre-department :func:`resolve_grants`
    result whenever no department-scoped role assignments exist (the state before
    P2/WS2.1), and ``department_grants`` is ``{}`` in that case.
    """

    org_id = getattr(identity, "org_id", None)
    persona = getattr(identity, "persona", "guest")
    if org_id is None:
        return permissions_for(persona), {}

    membership = await active_membership(session, user_id=user_id, org_id=org_id)
    if membership is None:
        return permissions_for(persona), {}

    grants = await grants_for_membership(session, membership_id=membership.id)
    dept_grants = await department_grants_for_membership(
        session, membership_id=membership.id
    )
    return grants | _COMMON_ORG_BASELINE, dept_grants


async def resolve_grants(
    session: AsyncSession, *, user_id: uuid.UUID, identity
) -> frozenset[str]:
    """Resolve the effective ORG-WIDE permission set (backwards-compatible view).

    Thin wrapper over :func:`resolve_scoped_grants` that discards the
    department-scoped map, so every existing caller keeps the exact
    ``frozenset[str]`` contract. Department-aware callers use
    :func:`resolve_scoped_grants` (auth dependency).
    """

    grants, _ = await resolve_scoped_grants(
        session, user_id=user_id, identity=identity
    )
    return grants
