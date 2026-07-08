"""Org RBAC service tests: tenant isolation, escalation ceiling, last-admin,
system-role immutability, optimistic concurrency, and audit-on-write."""

from __future__ import annotations

import uuid

import pytest
from app.modules.organization.application import (
    membership_service,
    rbac_service,
)
from app.modules.organization.application.errors import (
    LastAdminError,
    PermissionEscalationError,
    SystemRoleImmutableError,
    VersionConflictError,
)
from app.modules.organization.domain.models import Role
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin


async def _audit_count(db_session, action: str) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# RBAC boundaries                                                             #
# --------------------------------------------------------------------------- #


async def test_member_without_permission_denied_403(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _u, _m, principal = await add_member(
        db_session, org=org, permissions=[("members", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await rbac_service.create_role(
            db_session, principal=principal, name="X", description=None,
            permissions=[("members", "read")], ctx=CTX,
        )


async def test_admin_can_create_role_and_audits(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    before = await _audit_count(db_session, "role.created")
    role = await rbac_service.create_role(
        db_session, principal=admin, name="Recruiter", description="hires",
        permissions=[("members", "read"), ("jobs", "read")], ctx=CTX,
    )
    assert role["name"] == "Recruiter"
    assert set(role["permissions"]) == {"members:read", "jobs:read"}
    after = await _audit_count(db_session, "role.created")
    assert after == before + 1


# --------------------------------------------------------------------------- #
# Tenant isolation                                                            #
# --------------------------------------------------------------------------- #


async def test_cross_tenant_role_read_returns_404(db_session) -> None:
    _u_a, org_a, admin_a = await make_org_with_admin(
        db_session, display_name="Org A"
    )
    _u_b, org_b, admin_b = await make_org_with_admin(
        db_session, display_name="Org B"
    )
    role_b = await rbac_service.create_role(
        db_session, principal=admin_b, name="OnlyB", description=None,
        permissions=[("jobs", "read")], ctx=CTX,
    )
    # Admin A cannot see Org B's role -> hidden as 404, never 403.
    with pytest.raises(ResourceNotFoundError):
        await rbac_service.get_role(
            db_session, principal=admin_a, role_id=uuid.UUID(role_b["id"])
        )


async def test_list_roles_never_leaks_other_org(db_session) -> None:
    _u_a, org_a, admin_a = await make_org_with_admin(db_session, display_name="A")
    _u_b, org_b, admin_b = await make_org_with_admin(db_session, display_name="B")
    await rbac_service.create_role(
        db_session, principal=admin_b, name="SecretB", description=None,
        permissions=[("jobs", "read")], ctx=CTX,
    )
    roles_a = await rbac_service.list_roles(db_session, principal=admin_a)
    names = {r["name"] for r in roles_a}
    assert "SecretB" not in names


# --------------------------------------------------------------------------- #
# Escalation ceiling                                                          #
# --------------------------------------------------------------------------- #


async def test_non_admin_cannot_mint_wildcard_role(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    # A member who CAN create roles but only holds limited grants.
    _u, _m, creator = await add_member(
        db_session, org=org,
        permissions=[("roles", "create"), ("roles", "read"), ("members", "read")],
    )
    with pytest.raises(PermissionEscalationError):
        await rbac_service.create_role(
            db_session, principal=creator, name="GodMode", description=None,
            permissions=[("*", "*")], ctx=CTX,
        )


async def test_subset_ceiling_blocks_grant_beyond_actor(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _u, _m, creator = await add_member(
        db_session, org=org,
        permissions=[("roles", "create"), ("members", "read")],
    )
    # creator lacks members:remove, so cannot grant it.
    with pytest.raises(PermissionEscalationError):
        await rbac_service.create_role(
            db_session, principal=creator, name="Strong", description=None,
            permissions=[("members", "remove")], ctx=CTX,
        )
    # But may grant what it holds.
    ok = await rbac_service.create_role(
        db_session, principal=creator, name="Weak", description=None,
        permissions=[("members", "read")], ctx=CTX,
    )
    assert ok["permissions"] == ["members:read"]


async def test_member_role_assignment_respects_ceiling(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    # Build a high-power role (admin-created) and a limited manager.
    strong = await rbac_service.create_role(
        db_session, principal=admin, name="Strong", description=None,
        permissions=[("members", "remove"), ("members", "update")], ctx=CTX,
    )
    target_user, target_membership, _tp = await add_member(
        db_session, org=org, permissions=[("members", "read")]
    )
    # A manager who can update members but does not hold members:remove.
    _u, _m, manager = await add_member(
        db_session, org=org,
        permissions=[("members", "update"), ("members", "read"), ("roles", "read")],
    )
    with pytest.raises(PermissionEscalationError):
        await membership_service.update_member(
            db_session, principal=manager, membership_id=target_membership.id,
            role_ids=[uuid.UUID(strong["id"])], department_ids=None, version=None,
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Last-admin protection                                                       #
# --------------------------------------------------------------------------- #


async def test_cannot_remove_last_admin(db_session) -> None:
    admin_user, org, admin = await make_org_with_admin(db_session)
    # The admin's own membership id.
    from app.modules.organization.domain.models import Membership

    membership = (
        await db_session.execute(
            select(Membership).where(
                Membership.user_id == admin_user.id, Membership.org_id == org.id
            )
        )
    ).scalar_one()
    with pytest.raises(LastAdminError):
        await membership_service.remove_member(
            db_session, principal=admin, membership_id=membership.id, ctx=CTX
        )


async def test_cannot_strip_admin_role_from_last_admin(db_session) -> None:
    admin_user, org, admin = await make_org_with_admin(db_session)
    from app.modules.organization.domain.models import Membership

    membership = (
        await db_session.execute(
            select(Membership).where(
                Membership.user_id == admin_user.id, Membership.org_id == org.id
            )
        )
    ).scalar_one()
    # Replace roles with an empty set -> would leave org with no admin.
    with pytest.raises(LastAdminError):
        await membership_service.update_member(
            db_session, principal=admin, membership_id=membership.id,
            role_ids=[], department_ids=None, version=None, ctx=CTX,
        )


async def test_cannot_delete_last_admin_role(db_session) -> None:
    admin_user, org, admin = await make_org_with_admin(db_session)
    admin_role = (
        await db_session.execute(
            select(Role).where(Role.org_id == org.id, Role.is_system.is_(True))
        )
    ).scalar_one()
    with pytest.raises(SystemRoleImmutableError):
        await rbac_service.delete_role(
            db_session, principal=admin, role_id=admin_role.id, ctx=CTX
        )


async def test_second_admin_lets_first_be_removed(db_session) -> None:
    admin_user, org, admin = await make_org_with_admin(db_session)
    # Promote a second member to admin by assigning the system Admin role.
    admin_role = (
        await db_session.execute(
            select(Role).where(Role.org_id == org.id, Role.is_system.is_(True))
        )
    ).scalar_one()
    _u2, m2, _p2 = await add_member(
        db_session, org=org, permissions=[("members", "read")]
    )
    await membership_service.update_member(
        db_session, principal=admin, membership_id=m2.id,
        role_ids=[admin_role.id], department_ids=None, version=None, ctx=CTX,
    )
    # Now the first admin can be removed.
    from app.modules.organization.domain.models import Membership

    m1 = (
        await db_session.execute(
            select(Membership).where(
                Membership.user_id == admin_user.id, Membership.org_id == org.id
            )
        )
    ).scalar_one()
    await membership_service.remove_member(
        db_session, principal=admin, membership_id=m1.id, ctx=CTX
    )
    refreshed = (
        await db_session.execute(
            select(Membership).where(Membership.id == m1.id)
        )
    ).scalar_one()
    assert refreshed.status == "left"


# --------------------------------------------------------------------------- #
# System-role immutability                                                    #
# --------------------------------------------------------------------------- #


async def test_system_role_cannot_be_renamed(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    admin_role = (
        await db_session.execute(
            select(Role).where(Role.org_id == org.id, Role.is_system.is_(True))
        )
    ).scalar_one()
    with pytest.raises(SystemRoleImmutableError):
        await rbac_service.update_role(
            db_session, principal=admin, role_id=admin_role.id, name="Renamed",
            description=None, permissions=None, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Optimistic concurrency                                                      #
# --------------------------------------------------------------------------- #


async def test_membership_version_conflict(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    _u, membership, _p = await add_member(
        db_session, org=org, permissions=[("members", "read")]
    )
    # Stale version -> conflict.
    with pytest.raises(VersionConflictError):
        await membership_service.update_member(
            db_session, principal=admin, membership_id=membership.id,
            role_ids=None, department_ids=[], version=999, ctx=CTX,
        )
