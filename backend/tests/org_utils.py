"""Shared helpers for organization / RBAC tests."""

from __future__ import annotations

import uuid

from app.modules.organization.application import grant_resolver, organization_service
from app.modules.organization.domain.models import (
    Membership,
    MembershipRole,
    Permission,
    Role,
)
from app.modules.users.application import user_service
from app.modules.users.domain.models import Identity
from app.shared.permissions import Principal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import CTX, register_verified


def email(prefix: str = "org") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


async def _identity_for(
    session: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> Identity:
    return (
        await session.execute(
            select(Identity).where(Identity.user_id == user_id, Identity.org_id == org_id)
        )
    ).scalar_one()


async def principal_for(
    session: AsyncSession, *, user, org_id: uuid.UUID, superadmin: bool = False
) -> Principal:
    identity = await _identity_for(session, user_id=user.id, org_id=org_id)
    grants = await grant_resolver.resolve_grants(session, user_id=user.id, identity=identity)
    return Principal(
        user_id=user.id,
        persona=identity.persona,
        org_id=org_id,
        is_superadmin=superadmin,
        permissions=grants,
    )


async def make_org_with_admin(
    session: AsyncSession,
    *,
    admin_email: str | None = None,
    org_type: str = "partner",
    display_name: str = "Acme Corp",
):
    """Create an org + first admin (``*:*``) and return (user, org, admin_principal)."""

    user = await register_verified(session, email=admin_email or email("admin"))
    persona = "university_staff" if org_type == "university" else "partner_member"
    result = await organization_service.create_org_with_admin(
        session,
        org_type=org_type,
        display_name=display_name,
        admin_user_id=user.id,
        admin_persona=persona,
        actor_id=user.id,
        ctx=CTX,
        status="active",
        is_verified=True,
        trust_level="standard",
    )
    await session.commit()
    principal = await principal_for(session, user=user, org_id=result.organization.id)
    return user, result.organization, principal


async def add_member(
    session: AsyncSession,
    *,
    org,
    member_email: str | None = None,
    permissions: list[tuple[str, str]],
    role_name: str | None = None,
):
    """Add a member with a custom role; return (user, membership, principal)."""

    user = await register_verified(session, email=member_email or email("member"))
    role = Role(
        org_id=org.id,
        name=role_name or f"Member-{uuid.uuid4().hex[:8]}",
        is_system=False,
    )
    session.add(role)
    await session.flush()
    for resource, action in permissions:
        session.add(Permission(role_id=role.id, resource_type=resource, action=action))
    identity = await user_service.add_identity(
        session, user_id=user.id, persona="partner_member", org_id=org.id
    )
    membership = Membership(
        user_id=user.id, org_id=org.id, identity_id=identity.id, status="active"
    )
    session.add(membership)
    await session.flush()
    session.add(MembershipRole(membership_id=membership.id, role_id=role.id))
    await session.commit()
    principal = await principal_for(session, user=user, org_id=org.id)
    return user, membership, principal
