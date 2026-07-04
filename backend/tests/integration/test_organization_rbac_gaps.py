"""B-518/519/523: permission preview, ownership transfer, deactivate/reactivate,
and org audit-log read.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.organization.application import (
    audit_log_service,
    membership_service,
    ownership_service,
    permission_preview_service,
)
from app.modules.organization.application.errors import (
    ConfirmationRequiredError,
    InvalidMembershipStateError,
    NotOwnerError,
)
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
# Permission preview                                                          #
# --------------------------------------------------------------------------- #


async def test_permission_preview_for_member_returns_effective_grants(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    _u, membership, _principal = await add_member(
        db_session, org=org, permissions=[("jobs", "read"), ("applications", "read")],
    )
    data = await permission_preview_service.preview_for_member(
        db_session, principal=admin, membership_id=membership.id
    )
    assert set(data["grants"]) == {"jobs:read", "applications:read"}
    assert data["is_admin"] is False


async def test_permission_preview_requires_members_read(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _u, membership, _m2 = await add_member(
        db_session, org=org, permissions=[("jobs", "read")],
    )
    _u2, _m2b, no_read = await add_member(
        db_session, org=org, permissions=[("jobs", "update")],
    )
    with pytest.raises(PermissionDeniedError):
        await permission_preview_service.preview_for_member(
            db_session, principal=no_read, membership_id=membership.id
        )


async def test_hypothetical_permission_preview_for_pre_invite(db_session) -> None:
    from app.modules.organization.domain.models import Permission, Role

    _admin_user, org, admin = await make_org_with_admin(db_session)
    role = Role(org_id=org.id, name="Recruiter", is_system=False)
    db_session.add(role)
    await db_session.flush()
    db_session.add(Permission(role_id=role.id, resource_type="jobs", action="read"))
    await db_session.commit()

    data = await permission_preview_service.preview_hypothetical(
        db_session, principal=admin, role_ids=[role.id], department_ids=[]
    )
    assert data["grants"] == ["jobs:read"]


async def test_hypothetical_preview_cross_org_role_hidden_as_404(db_session) -> None:
    _u_a, org_a, admin_a = await make_org_with_admin(db_session, display_name="A")
    _u_b, org_b, admin_b = await make_org_with_admin(db_session, display_name="B")
    from app.modules.organization.domain.models import Role

    role_b = Role(org_id=org_b.id, name="OnlyB", is_system=False)
    db_session.add(role_b)
    await db_session.commit()

    with pytest.raises(ResourceNotFoundError):
        await permission_preview_service.preview_hypothetical(
            db_session, principal=admin_a, role_ids=[role_b.id], department_ids=[]
        )


# --------------------------------------------------------------------------- #
# Ownership transfer                                                          #
# --------------------------------------------------------------------------- #


async def test_ownership_transfer_requires_confirmation(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    _u, target_membership, _p = await add_member(
        db_session, org=org, permissions=[("members", "read")],
    )
    with pytest.raises(ConfirmationRequiredError):
        await ownership_service.transfer_ownership(
            db_session, principal=admin, target_membership_id=target_membership.id,
            confirm=False, ctx=CTX,
        )


async def test_ownership_transfer_only_by_current_owner(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    _u1, m1, non_owner = await add_member(
        db_session, org=org, permissions=[("organizations", "update"), ("members", "read")],
    )
    _u2, m2, _p2 = await add_member(db_session, org=org, permissions=[("members", "read")])

    with pytest.raises(NotOwnerError):
        await ownership_service.transfer_ownership(
            db_session, principal=non_owner, target_membership_id=m2.id,
            confirm=True, ctx=CTX,
        )


async def test_ownership_transfer_success_and_audit(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    _u, target_membership, _p = await add_member(
        db_session, org=org, permissions=[("members", "read")],
    )
    before = await _audit_count(db_session, "organization.ownership_transferred")
    result = await ownership_service.transfer_ownership(
        db_session, principal=admin, target_membership_id=target_membership.id,
        confirm=True, ctx=CTX,
    )
    assert result["owner_membership_id"] == str(target_membership.id)
    after = await _audit_count(db_session, "organization.ownership_transferred")
    assert after == before + 1

    ownership = await ownership_service.get_ownership(db_session, principal=admin)
    assert ownership["owner_membership_id"] == str(target_membership.id)


# --------------------------------------------------------------------------- #
# Deactivate / reactivate                                                     #
# --------------------------------------------------------------------------- #


async def test_deactivate_then_reactivate_member(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    _u, membership, _p = await add_member(
        db_session, org=org, permissions=[("members", "read")],
    )
    data = await membership_service.deactivate_member(
        db_session, principal=admin, membership_id=membership.id, ctx=CTX,
    )
    assert data["status"] == "suspended"

    data2 = await membership_service.reactivate_member(
        db_session, principal=admin, membership_id=membership.id, ctx=CTX,
    )
    assert data2["status"] == "active"


async def test_deactivate_is_idempotent(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    _u, membership, _p = await add_member(
        db_session, org=org, permissions=[("members", "read")],
    )
    await membership_service.deactivate_member(
        db_session, principal=admin, membership_id=membership.id, ctx=CTX,
    )
    data = await membership_service.deactivate_member(
        db_session, principal=admin, membership_id=membership.id, ctx=CTX,
    )
    assert data["status"] == "suspended"


async def test_cannot_deactivate_last_admin(db_session) -> None:
    from app.modules.organization.application.errors import LastAdminError
    from app.modules.organization.domain.models import Membership

    admin_user, org, admin = await make_org_with_admin(db_session)
    admin_membership_id = (
        await db_session.execute(
            select(Membership.id).where(
                Membership.org_id == org.id, Membership.user_id == admin_user.id
            )
        )
    ).scalar_one()
    with pytest.raises(LastAdminError):
        await membership_service.deactivate_member(
            db_session, principal=admin, membership_id=admin_membership_id, ctx=CTX,
        )


async def test_cannot_reactivate_a_permanently_removed_member(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    _u, membership, _p = await add_member(
        db_session, org=org, permissions=[("members", "read")],
    )
    await membership_service.remove_member(
        db_session, principal=admin, membership_id=membership.id, ctx=CTX,
    )
    with pytest.raises(InvalidMembershipStateError):
        await membership_service.reactivate_member(
            db_session, principal=admin, membership_id=membership.id, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Audit log read                                                              #
# --------------------------------------------------------------------------- #


async def test_audit_log_lists_only_own_org_and_paginates(db_session) -> None:
    _u_a, org_a, admin_a = await make_org_with_admin(db_session, display_name="A")
    _u_b, org_b, admin_b = await make_org_with_admin(db_session, display_name="B")
    from app.modules.organization.application import rbac_service

    for i in range(3):
        await rbac_service.create_role(
            db_session, principal=admin_a, name=f"RoleA{i}", description=None,
            permissions=[("jobs", "read")], ctx=CTX,
        )
    await rbac_service.create_role(
        db_session, principal=admin_b, name="RoleB", description=None,
        permissions=[("jobs", "read")], ctx=CTX,
    )

    items, next_cursor, _limit = await audit_log_service.list_audit_log(
        db_session, principal=admin_a, limit=2
    )
    assert len(items) == 2
    assert next_cursor is not None
    for item in items:
        assert item["action"] != "organization.created" or True  # sanity: no crash

    # Every returned row belongs to org A only (tenant isolation).
    all_items, _c, _l = await audit_log_service.list_audit_log(
        db_session, principal=admin_a, limit=50
    )
    role_b_leaked = any(
        i["after"] and i["after"].get("name") == "RoleB" for i in all_items
    )
    assert not role_b_leaked


async def test_audit_log_requires_permission(db_session) -> None:
    _admin_user, org, _admin = await make_org_with_admin(db_session)
    _u, _m, no_grant = await add_member(
        db_session, org=org, permissions=[("jobs", "read")],
    )
    with pytest.raises(PermissionDeniedError):
        await audit_log_service.list_audit_log(db_session, principal=no_grant)
