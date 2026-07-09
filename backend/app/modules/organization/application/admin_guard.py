"""Security-critical invariants: escalation ceiling + last-admin protection.

These helpers are shared by ``rbac_service`` and ``membership_service`` and are
the single source of truth for two privilege-safety rules (ADR-0002 §6.4):

- **Escalation ceiling:** an actor may only grant/assign permissions that are a
  subset of its own effective grants (``*:*`` / superadmin bypass).
- **Last-admin protection:** the org must always retain >=1 active membership
  whose roles confer the ``*:*`` (admin) grant.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.application.errors import PermissionEscalationError
from app.modules.organization.domain.catalog import (
    ADMIN_WILDCARD_ACTION,
    ADMIN_WILDCARD_RESOURCE,
)
from app.modules.organization.domain.models import (
    Membership,
    MembershipRole,
    Permission,
)
from app.shared.permissions import Principal, permission_checker


def assert_can_grant(principal: Principal, requested: Iterable[tuple[str, str]]) -> None:
    """Raise :class:`PermissionEscalationError` unless every requested
    ``(resource, action)`` is within the actor's own effective grants."""

    if principal.is_superadmin:
        return
    for resource, action in requested:
        # can() with no resource_org_id == pure grant-membership check.
        if not permission_checker.can(principal, resource, action):
            raise PermissionEscalationError()


async def admin_membership_ids(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    exclude_role_id: uuid.UUID | None = None,
    exclude_membership_id: uuid.UUID | None = None,
) -> set[uuid.UUID]:
    """Active memberships in ``org_id`` that hold the ``*:*`` grant.

    ``exclude_role_id`` simulates deleting/stripping that role (its grant no
    longer counts); ``exclude_membership_id`` simulates removing that member.
    """

    stmt = (
        select(Membership.id)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(Permission, Permission.role_id == MembershipRole.role_id)
        .where(
            Membership.org_id == org_id,
            Membership.status == "active",
            Permission.resource_type == ADMIN_WILDCARD_RESOURCE,
            Permission.action == ADMIN_WILDCARD_ACTION,
        )
    )
    if exclude_role_id is not None:
        stmt = stmt.where(MembershipRole.role_id != exclude_role_id)
    if exclude_membership_id is not None:
        stmt = stmt.where(Membership.id != exclude_membership_id)
    return {row[0] for row in (await session.execute(stmt)).all()}


async def role_grants_admin_for_membership(
    session: AsyncSession, *, membership_id: uuid.UUID
) -> bool:
    """True if any role currently assigned to ``membership_id`` grants ``*:*``."""

    stmt = (
        select(Permission.id)
        .join(MembershipRole, MembershipRole.role_id == Permission.role_id)
        .where(
            MembershipRole.membership_id == membership_id,
            Permission.resource_type == ADMIN_WILDCARD_RESOURCE,
            Permission.action == ADMIN_WILDCARD_ACTION,
        )
    )
    return (await session.execute(stmt)).first() is not None


async def role_grants_admin(session: AsyncSession, *, role_id: uuid.UUID) -> bool:
    """True if ``role_id`` confers the ``*:*`` grant."""

    stmt = select(Permission.id).where(
        Permission.role_id == role_id,
        Permission.resource_type == ADMIN_WILDCARD_RESOURCE,
        Permission.action == ADMIN_WILDCARD_ACTION,
    )
    return (await session.execute(stmt)).first() is not None
