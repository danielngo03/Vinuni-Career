"""Invitation lifecycle: create, accept (creates membership), expired, reused,
email mismatch, revoke."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.organization.application import membership_service
from app.modules.organization.application.errors import InvitationError
from app.modules.organization.domain.models import Invitation, Membership
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import CTX, register_verified
from tests.org_utils import email, make_org_with_admin


async def _invite_token(db_session) -> str:
    rows = (
        (
            await db_session.execute(
                select(NotificationOutbox)
                .where(NotificationOutbox.template_key == "org.member_invitation")
                .order_by(NotificationOutbox.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return str(rows[0].variables["token"])


def _user_principal(user) -> Principal:
    # Accepting user acts with a no-org identity (student baseline).
    return Principal(user_id=user.id, persona="student", permissions=frozenset())


async def test_create_and_accept_invitation_creates_membership(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    invitee_email = email("invitee")
    inv = await membership_service.create_invitation(
        db_session,
        principal=admin,
        email=invitee_email,
        role_id=None,
        department_id=None,
        ctx=CTX,
    )
    assert inv["status"] == "pending"
    token = await _invite_token(db_session)

    invitee = await register_verified(db_session, email=invitee_email)
    result = await membership_service.accept_invitation(
        db_session, principal=_user_principal(invitee), token=token, ctx=CTX
    )
    assert result["status"] == "active"
    membership = (
        await db_session.execute(
            select(Membership).where(Membership.user_id == invitee.id, Membership.org_id == org.id)
        )
    ).scalar_one()
    assert membership.status == "active"


async def test_accept_reused_token_rejected(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    invitee_email = email("invitee")
    await membership_service.create_invitation(
        db_session,
        principal=admin,
        email=invitee_email,
        role_id=None,
        department_id=None,
        ctx=CTX,
    )
    token = await _invite_token(db_session)
    invitee = await register_verified(db_session, email=invitee_email)
    await membership_service.accept_invitation(
        db_session, principal=_user_principal(invitee), token=token, ctx=CTX
    )
    with pytest.raises(InvitationError):
        await membership_service.accept_invitation(
            db_session, principal=_user_principal(invitee), token=token, ctx=CTX
        )


async def test_accept_expired_token_rejected(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    invitee_email = email("invitee")
    inv = await membership_service.create_invitation(
        db_session,
        principal=admin,
        email=invitee_email,
        role_id=None,
        department_id=None,
        ctx=CTX,
    )
    token = await _invite_token(db_session)
    # Force-expire the invitation.
    row = (
        await db_session.execute(select(Invitation).where(Invitation.id == uuid.UUID(inv["id"])))
    ).scalar_one()
    row.expires_at = datetime.now(tz=UTC) - timedelta(hours=1)
    await db_session.commit()

    invitee = await register_verified(db_session, email=invitee_email)
    with pytest.raises(InvitationError):
        await membership_service.accept_invitation(
            db_session, principal=_user_principal(invitee), token=token, ctx=CTX
        )


async def test_accept_email_mismatch_forbidden(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    await membership_service.create_invitation(
        db_session,
        principal=admin,
        email=email("invited"),
        role_id=None,
        department_id=None,
        ctx=CTX,
    )
    token = await _invite_token(db_session)
    other = await register_verified(db_session, email=email("someone-else"))
    with pytest.raises(PermissionDeniedError):
        await membership_service.accept_invitation(
            db_session, principal=_user_principal(other), token=token, ctx=CTX
        )


async def test_revoke_invitation(db_session) -> None:
    _admin_user, org, admin = await make_org_with_admin(db_session)
    inv = await membership_service.create_invitation(
        db_session,
        principal=admin,
        email=email("invitee"),
        role_id=None,
        department_id=None,
        ctx=CTX,
    )
    await membership_service.revoke_invitation(
        db_session, principal=admin, invitation_id=uuid.UUID(inv["id"]), ctx=CTX
    )
    row = (
        await db_session.execute(select(Invitation).where(Invitation.id == uuid.UUID(inv["id"])))
    ).scalar_one()
    assert row.status == "revoked"


async def test_invite_role_escalation_blocked(db_session) -> None:
    from app.modules.organization.application import rbac_service
    from app.modules.organization.application.errors import PermissionEscalationError

    from tests.org_utils import add_member

    _admin_user, org, admin = await make_org_with_admin(db_session)
    strong = await rbac_service.create_role(
        db_session,
        principal=admin,
        name="Strong",
        description=None,
        permissions=[("members", "remove")],
        ctx=CTX,
    )
    # An inviter who can invite but does not hold members:remove.
    _u, _m, inviter = await add_member(
        db_session,
        org=org,
        permissions=[("members", "invite"), ("members", "read"), ("roles", "read")],
    )
    with pytest.raises(PermissionEscalationError):
        await membership_service.create_invitation(
            db_session,
            principal=inviter,
            email=email("x"),
            role_id=uuid.UUID(strong["id"]),
            department_id=None,
            ctx=CTX,
        )
