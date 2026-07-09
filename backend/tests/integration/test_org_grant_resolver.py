"""Grant resolution: persona fallback, DB grants, suspended-drop, admin all-access."""

from __future__ import annotations

from app.modules.auth.domain.personas import permissions_for
from app.modules.organization.application import grant_resolver
from app.modules.organization.domain.models import Membership
from app.modules.users.domain.models import Identity
from app.shared.permissions import Principal, permission_checker
from sqlalchemy import select

from tests.auth_utils import register_verified
from tests.org_utils import add_member, email, make_org_with_admin


async def test_no_org_identity_keeps_persona_baseline(db_session) -> None:
    user = await register_verified(db_session, email=email("student"))
    identity = (
        await db_session.execute(select(Identity).where(Identity.user_id == user.id))
    ).scalar_one()
    grants = await grant_resolver.resolve_grants(db_session, user_id=user.id, identity=identity)
    assert grants == permissions_for("student")


async def test_partner_admin_resolves_wildcard_all_access(db_session) -> None:
    _user, org, principal = await make_org_with_admin(db_session)
    # Admin holds *:* so any org-scoped action is permitted within its org.
    assert "*:*" in principal.permissions
    assert permission_checker.can(principal, "roles", "create", resource_org_id=org.id)
    assert permission_checker.can(principal, "anything", "weird", resource_org_id=org.id)


async def test_member_resolves_only_db_grants_plus_baseline(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _u, _m, principal = await add_member(
        db_session, org=org, permissions=[("roles", "read"), ("members", "read")]
    )
    assert "roles:read" in principal.permissions
    assert "members:read" in principal.permissions
    # Common org baseline always present.
    assert "account:*" in principal.permissions
    # No grant beyond what the role confers.
    assert "*:*" not in principal.permissions
    assert not permission_checker.can(principal, "roles", "create", resource_org_id=org.id)


async def test_suspended_membership_drops_to_persona_baseline(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    user, membership, _principal = await add_member(
        db_session, org=org, permissions=[("roles", "read")]
    )
    # Suspend the membership.
    m = (
        await db_session.execute(select(Membership).where(Membership.id == membership.id))
    ).scalar_one()
    m.status = "suspended"
    await db_session.commit()

    identity = (
        await db_session.execute(
            select(Identity).where(Identity.user_id == user.id, Identity.org_id == org.id)
        )
    ).scalar_one()
    grants = await grant_resolver.resolve_grants(db_session, user_id=user.id, identity=identity)
    # Org grant dropped; falls back to the persona baseline (no org powers).
    assert grants == permissions_for(identity.persona)
    assert "roles:read" not in grants


async def test_superadmin_bypasses_grants(db_session) -> None:
    principal = Principal(
        user_id=__import__("uuid").uuid4(),
        persona="university_staff",
        is_superadmin=True,
        permissions=frozenset(),
    )
    assert permission_checker.can(principal, "partners", "approve")
