"""Members + invitations: role/department assignment and invite lifecycle.

Enforces RBAC, tenant isolation, escalation ceiling, last-admin protection, and
optimistic concurrency (``memberships.version``) at this layer (ADR-0002 §6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.auth.application.token_facade import generate_token, hash_token
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.organization.api import presenters
from app.modules.organization.application import admin_guard
from app.modules.organization.application.errors import (
    InvalidMembershipStateError,
    InvitationError,
    LastAdminError,
    SeatLimitReachedError,
    VersionConflictError,
)
from app.modules.organization.domain.models import (
    Department,
    Invitation,
    Membership,
    MembershipDepartment,
    MembershipRole,
    Organization,
    Permission,
    Role,
)
from app.modules.users.application import user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ConflictError, ResourceNotFoundError
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal, permission_checker

INVITATION_TTL_DAYS = 7


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _require_org(principal: Principal) -> uuid.UUID:
    if principal.org_id is None:
        raise ResourceNotFoundError()
    return principal.org_id


async def _get_membership(
    session: AsyncSession, *, org_id: uuid.UUID, membership_id: uuid.UUID
) -> Membership | None:
    stmt = select(Membership).where(Membership.id == membership_id, Membership.org_id == org_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _membership_role_ids(session: AsyncSession, membership_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (
        await session.execute(
            select(MembershipRole.role_id).where(MembershipRole.membership_id == membership_id)
        )
    ).all()
    return [r[0] for r in rows]


async def _membership_department_ids(
    session: AsyncSession, membership_id: uuid.UUID
) -> list[uuid.UUID]:
    rows = (
        await session.execute(
            select(MembershipDepartment.department_id).where(
                MembershipDepartment.membership_id == membership_id
            )
        )
    ).all()
    return [r[0] for r in rows]


async def _permissions_of_roles(
    session: AsyncSession, role_ids: list[uuid.UUID]
) -> list[tuple[str, str]]:
    if not role_ids:
        return []
    rows = (
        await session.execute(
            select(Permission.resource_type, Permission.action).where(
                Permission.role_id.in_(role_ids)
            )
        )
    ).all()
    return [(r, a) for r, a in rows]


# --------------------------------------------------------------------------- #
# Members                                                                     #
# --------------------------------------------------------------------------- #


async def list_members(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    status: str | None = None,
    role_id: uuid.UUID | None = None,
    locale: str = "vi",
):
    org_id = _require_org(principal)
    permission_checker.require(principal, "members", "read", resource_org_id=org_id)
    page_limit = clamp_limit(limit)

    stmt = select(Membership).where(Membership.org_id == org_id)
    if status is not None:
        stmt = stmt.where(Membership.status == status)
    if role_id is not None:
        stmt = stmt.join(MembershipRole, MembershipRole.membership_id == Membership.id).where(
            MembershipRole.role_id == role_id
        )

    decoded = decode_cursor(cursor)
    if decoded is not None and "id" in decoded:
        stmt = stmt.where(Membership.id > uuid.UUID(decoded["id"]))
    stmt = stmt.order_by(Membership.id).limit(page_limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(rows, limit=page_limit, cursor_builder=lambda m: {"id": str(m.id)})
    items = []
    for m in page.items:
        user = await user_service.get_by_id(session, m.user_id)
        role_ids = await _membership_role_ids(session, m.id)
        dept_ids = await _membership_department_ids(session, m.id)
        items.append(
            presenters.member_summary(
                membership=m,
                email=user.email if user else "",
                full_name=user.full_name if user else None,
                role_ids=[str(r) for r in role_ids],
                department_ids=[str(d) for d in dept_ids],
                locale=locale,
            )
        )
    return items, page.next_cursor, page.limit


async def update_member(
    session: AsyncSession,
    *,
    principal: Principal,
    membership_id: uuid.UUID,
    role_ids: list[uuid.UUID] | None,
    department_ids: list[uuid.UUID] | None,
    version: int | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = _require_org(principal)
    permission_checker.require(principal, "members", "update", resource_org_id=org_id)
    membership = await _get_membership(session, org_id=org_id, membership_id=membership_id)
    if membership is None:
        raise ResourceNotFoundError()
    if version is not None and version != membership.version:
        raise VersionConflictError()

    before_roles = await _membership_role_ids(session, membership.id)

    if role_ids is not None:
        target_ids = list(dict.fromkeys(role_ids))
        roles = (
            (
                await session.execute(
                    select(Role).where(Role.id.in_(target_ids), Role.org_id == org_id)
                )
            )
            .scalars()
            .all()
            if target_ids
            else []
        )
        if len(roles) != len(target_ids):
            raise ResourceNotFoundError()  # a role from another org / missing

        # Escalation ceiling: actor may only assign roles within its own grants.
        requested = await _permissions_of_roles(session, target_ids)
        admin_guard.assert_can_grant(principal, requested)

        # Last-admin protection: do not strip admin from the org's only admin.
        new_grants_admin = False
        for rid in target_ids:
            if await admin_guard.role_grants_admin(session, role_id=rid):
                new_grants_admin = True
                break
        if not new_grants_admin:
            current_admins = await admin_guard.admin_membership_ids(session, org_id=org_id)
            if membership.id in current_admins and current_admins == {membership.id}:
                raise LastAdminError()

        await session.execute(
            delete(MembershipRole).where(MembershipRole.membership_id == membership.id)
        )
        for rid in target_ids:
            session.add(
                MembershipRole(
                    membership_id=membership.id,
                    role_id=rid,
                    assigned_by=principal.user_id,
                )
            )

    if department_ids is not None:
        target_dept_ids = list(dict.fromkeys(department_ids))
        depts = (
            (
                await session.execute(
                    select(Department.id).where(
                        Department.id.in_(target_dept_ids), Department.org_id == org_id
                    )
                )
            ).all()
            if target_dept_ids
            else []
        )
        if len(depts) != len(target_dept_ids):
            raise ResourceNotFoundError()
        await session.execute(
            delete(MembershipDepartment).where(MembershipDepartment.membership_id == membership.id)
        )
        for did in target_dept_ids:
            session.add(
                MembershipDepartment(
                    membership_id=membership.id,
                    department_id=did,
                    assigned_by=principal.user_id,
                )
            )

    membership.version += 1
    await session.flush()
    await write_audit(
        session,
        action="membership.updated",
        resource_type="membership",
        resource_id=membership.id,
        context=_audit_ctx(principal, ctx),
        before={"roles": [str(r) for r in before_roles]},
        after={"roles": [str(r) for r in await _membership_role_ids(session, membership.id)]},
    )
    await session.commit()

    user = await user_service.get_by_id(session, membership.user_id)
    return presenters.member_summary(
        membership=membership,
        email=user.email if user else "",
        full_name=user.full_name if user else None,
        role_ids=[str(r) for r in await _membership_role_ids(session, membership.id)],
        department_ids=[str(d) for d in await _membership_department_ids(session, membership.id)],
        locale=locale,
    )


async def remove_member(
    session: AsyncSession,
    *,
    principal: Principal,
    membership_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    org_id = _require_org(principal)
    permission_checker.require(principal, "members", "remove", resource_org_id=org_id)
    membership = await _get_membership(session, org_id=org_id, membership_id=membership_id)
    if membership is None:
        raise ResourceNotFoundError()
    if membership.status == "left":
        return  # idempotent

    admins = await admin_guard.admin_membership_ids(session, org_id=org_id)
    if membership.id in admins and admins == {membership.id}:
        raise LastAdminError()

    membership.status = "left"
    membership.left_at = datetime.now(tz=UTC)
    membership.version += 1
    await session.flush()
    await write_audit(
        session,
        action="membership.removed",
        resource_type="membership",
        resource_id=membership.id,
        context=_audit_ctx(principal, ctx),
        after={"status": "left"},
    )
    await session.commit()


async def deactivate_member(
    session: AsyncSession,
    *,
    principal: Principal,
    membership_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Suspend a member's access (reversible) — distinct from permanent removal.

    Idempotent: re-deactivating an already-``suspended`` member is a no-op.
    ``left`` (permanently removed) members cannot be deactivated; they must be
    re-invited instead.
    """

    org_id = _require_org(principal)
    permission_checker.require(principal, "members", "remove", resource_org_id=org_id)
    membership = await _get_membership(session, org_id=org_id, membership_id=membership_id)
    if membership is None:
        raise ResourceNotFoundError()
    if membership.status == "left":
        raise InvalidMembershipStateError("member_left")
    if membership.status == "suspended":
        return await _member_view(session, membership=membership, locale=locale)

    admins = await admin_guard.admin_membership_ids(session, org_id=org_id)
    if membership.id in admins and admins == {membership.id}:
        raise LastAdminError()

    membership.status = "suspended"
    membership.version += 1
    await session.flush()
    await write_audit(
        session,
        action="membership.deactivated",
        resource_type="membership",
        resource_id=membership.id,
        context=_audit_ctx(principal, ctx),
        before={"status": "active"},
        after={"status": "suspended"},
    )
    await session.commit()
    return await _member_view(session, membership=membership, locale=locale)


async def reactivate_member(
    session: AsyncSession,
    *,
    principal: Principal,
    membership_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Restore a previously-suspended member's access.

    Idempotent for an already-``active`` member. A ``left`` (permanently
    removed) member cannot be reactivated — a new invitation is required.
    """

    org_id = _require_org(principal)
    permission_checker.require(principal, "members", "update", resource_org_id=org_id)
    membership = await _get_membership(session, org_id=org_id, membership_id=membership_id)
    if membership is None:
        raise ResourceNotFoundError()
    if membership.status == "left":
        raise InvalidMembershipStateError("member_left")
    if membership.status == "active":
        return await _member_view(session, membership=membership, locale=locale)

    membership.status = "active"
    membership.version += 1
    await session.flush()
    await write_audit(
        session,
        action="membership.reactivated",
        resource_type="membership",
        resource_id=membership.id,
        context=_audit_ctx(principal, ctx),
        before={"status": "suspended"},
        after={"status": "active"},
    )
    await session.commit()
    return await _member_view(session, membership=membership, locale=locale)


async def _member_view(session: AsyncSession, *, membership: Membership, locale: str) -> dict:
    user = await user_service.get_by_id(session, membership.user_id)
    role_ids = await _membership_role_ids(session, membership.id)
    dept_ids = await _membership_department_ids(session, membership.id)
    return presenters.member_summary(
        membership=membership,
        email=user.email if user else "",
        full_name=user.full_name if user else None,
        role_ids=[str(r) for r in role_ids],
        department_ids=[str(d) for d in dept_ids],
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Invitations                                                                 #
# --------------------------------------------------------------------------- #


async def _get_role(session: AsyncSession, *, org_id: uuid.UUID, role_id: uuid.UUID) -> Role | None:
    return (
        await session.execute(select(Role).where(Role.id == role_id, Role.org_id == org_id))
    ).scalar_one_or_none()


async def create_invitation(
    session: AsyncSession,
    *,
    principal: Principal,
    email: str,
    role_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = _require_org(principal)
    permission_checker.require(principal, "members", "invite", resource_org_id=org_id)
    norm_email = email.strip().lower()

    # ── Seat-limit enforcement ────────────────────────────────────────────────
    org = (
        await session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    if org.max_team_members != -1:  # -1 = unlimited (enterprise)
        active_count = (
            await session.execute(
                select(func.count(Membership.id)).where(
                    Membership.org_id == org_id,
                    Membership.status == "active",
                )
            )
        ).scalar_one()
        if active_count >= org.max_team_members:
            raise SeatLimitReachedError(current=active_count, limit=org.max_team_members)

    if role_id is not None:
        role = await _get_role(session, org_id=org_id, role_id=role_id)
        if role is None:
            raise ResourceNotFoundError()
        # Escalation ceiling: cannot invite into a role beyond the actor's grants.
        admin_guard.assert_can_grant(principal, await _permissions_of_roles(session, [role_id]))
    if department_id is not None:
        dept = (
            await session.execute(
                select(Department.id).where(
                    Department.id == department_id, Department.org_id == org_id
                )
            )
        ).first()
        if dept is None:
            raise ResourceNotFoundError()

    pending = (
        (
            await session.execute(
                select(Invitation.id).where(
                    Invitation.org_id == org_id,
                    Invitation.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    # Application-level dedupe (Postgres partial-unique index is the race backstop).
    for inv_id in pending:
        existing = (
            await session.execute(select(Invitation).where(Invitation.id == inv_id))
        ).scalar_one()
        if existing.email.lower() == norm_email:
            raise ConflictError(
                "Đã có lời mời đang chờ cho địa chỉ email này.",
                details={"reason": "duplicate_invitation"},
            )

    raw = generate_token()
    invitation = Invitation(
        org_id=org_id,
        email=norm_email,
        role_id=role_id,
        department_id=department_id,
        token_hash=hash_token(raw),
        status="pending",
        invited_by=principal.user_id,
        expires_at=datetime.now(tz=UTC) + timedelta(days=INVITATION_TTL_DAYS),
    )
    session.add(invitation)
    await session.flush()

    org = (
        await session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    await enqueue_notification(
        session,
        recipient_id=None,
        template_key="org.member_invitation",
        channel="email",
        locale=locale,
        variables={
            "email": norm_email,
            "org_name": org.display_name,
            "token": raw,
            "action_url": _invite_link(token=raw, locale=locale),
        },
        dedupe_key=f"invite:{invitation.id}",
    )
    await write_audit(
        session,
        action="invitation.created",
        resource_type="invitation",
        resource_id=invitation.id,
        context=_audit_ctx(principal, ctx),
        after={"email": norm_email, "role_id": str(role_id) if role_id else None},
    )
    await session.commit()
    return presenters.invitation_summary(invitation, locale=locale)


def _invite_link(*, token: str, locale: str) -> str:
    from app.core.config import get_settings

    base = get_settings().frontend_url.rstrip("/")
    return f"{base}/{locale}/organizations/invitations/accept?token={token}"


async def list_invitations(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> list[dict]:
    org_id = _require_org(principal)
    permission_checker.require(principal, "members", "read", resource_org_id=org_id)
    rows = (
        (
            await session.execute(
                select(Invitation)
                .where(
                    Invitation.org_id == org_id,
                    Invitation.status.in_(("pending", "expired")),
                )
                .order_by(Invitation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [presenters.invitation_summary(i, locale=locale) for i in rows]


async def revoke_invitation(
    session: AsyncSession,
    *,
    principal: Principal,
    invitation_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    org_id = _require_org(principal)
    permission_checker.require(principal, "members", "invite", resource_org_id=org_id)
    inv = (
        await session.execute(
            select(Invitation).where(Invitation.id == invitation_id, Invitation.org_id == org_id)
        )
    ).scalar_one_or_none()
    if inv is None:
        raise ResourceNotFoundError()
    if inv.status == "pending":
        inv.status = "revoked"
        await session.flush()
        await write_audit(
            session,
            action="invitation.revoked",
            resource_type="invitation",
            resource_id=inv.id,
            context=_audit_ctx(principal, ctx),
        )
    await session.commit()


async def accept_invitation(
    session: AsyncSession,
    *,
    principal: Principal,
    token: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Accept an invitation as the authenticated user (token bound to email)."""

    if principal.user_id is None:
        raise ResourceNotFoundError()
    inv = (
        await session.execute(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    ).scalar_one_or_none()
    if inv is None:
        raise InvitationError("invite_invalid")
    now = datetime.now(tz=UTC)
    if inv.status == "accepted":
        raise InvitationError("invite_used")
    if inv.status in ("revoked", "expired"):
        raise InvitationError("invite_invalid")
    from app.shared.models import ensure_aware

    if ensure_aware(inv.expires_at) <= now:
        inv.status = "expired"
        await session.commit()
        raise InvitationError("invite_expired")

    user = await user_service.get_by_id(session, principal.user_id)
    if user is None:
        raise ResourceNotFoundError()
    if user.email.lower() != inv.email.lower():
        # Token is bound to the invited email.
        from app.shared.exceptions import PermissionDeniedError

        raise PermissionDeniedError(details={"reason": "invite_email_mismatch"})

    existing = (
        await session.execute(
            select(Membership).where(Membership.user_id == user.id, Membership.org_id == inv.org_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            "Bạn đã là thành viên của tổ chức này.",
            details={"reason": "already_member"},
        )

    org = (
        await session.execute(select(Organization).where(Organization.id == inv.org_id))
    ).scalar_one()
    persona = "university_staff" if org.org_type == "university" else "partner_member"
    identity = await user_service.add_identity(
        session, user_id=user.id, persona=persona, org_id=org.id
    )
    membership = Membership(
        user_id=user.id, org_id=org.id, identity_id=identity.id, status="active"
    )
    session.add(membership)
    await session.flush()
    if inv.role_id is not None:
        session.add(
            MembershipRole(
                membership_id=membership.id,
                role_id=inv.role_id,
                assigned_by=inv.invited_by,
            )
        )
    if inv.department_id is not None:
        session.add(
            MembershipDepartment(
                membership_id=membership.id,
                department_id=inv.department_id,
                assigned_by=inv.invited_by,
            )
        )
    inv.status = "accepted"
    inv.accepted_at = now
    await session.flush()
    await write_audit(
        session,
        action="membership.created",
        resource_type="membership",
        resource_id=membership.id,
        context=AuditContext(
            actor_id=user.id, actor_org_id=org.id, ip=ctx.ip, user_agent=ctx.user_agent
        ),
        after={"via": "invitation", "invitation_id": str(inv.id)},
    )
    await session.commit()

    role_ids = await _membership_role_ids(session, membership.id)
    dept_ids = await _membership_department_ids(session, membership.id)
    return presenters.member_summary(
        membership=membership,
        email=user.email,
        full_name=user.full_name,
        role_ids=[str(r) for r in role_ids],
        department_ids=[str(d) for d in dept_ids],
        locale=locale,
    )
