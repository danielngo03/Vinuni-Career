"""Organization ownership transfer (B-518/519).

Extends the existing ``*:*`` admin-wildcard model instead of inventing a
parallel concept: "owner" is a single designated membership
(``organizations.owner_membership_id``) that must always hold the admin
wildcard grant. Only the current owner may transfer ownership, transfer
requires explicit confirmation, and the target becomes an admin (if not
already one) atomically with the pointer flip — the previous owner keeps
their own admin grant (still an admin, just no longer "the" owner), so
last-admin protection is never at risk from this action.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import admin_guard
from app.modules.organization.application.errors import (
    ConfirmationRequiredError,
    NotOwnerError,
)
from app.modules.organization.domain import catalog
from app.modules.organization.domain.models import (
    Membership,
    MembershipRole,
    Organization,
    Role,
)
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker


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


async def _get_org(session: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = (
        await session.execute(
            select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if org is None:
        raise ResourceNotFoundError()
    return org


async def current_owner_membership_id(
    session: AsyncSession, *, org: Organization
) -> uuid.UUID | None:
    """The org's designated owner membership id, with a safe legacy fallback.

    Legacy orgs bootstrapped before ``owner_membership_id`` existed fall back to
    the oldest active membership holding the ``*:*`` grant — the same admin set
    ``admin_guard`` already treats as the org's admin pool.
    """

    if org.owner_membership_id is not None:
        return org.owner_membership_id
    admin_ids = await admin_guard.admin_membership_ids(session, org_id=org.id)
    if not admin_ids:
        return None
    rows = (
        (
            await session.execute(
                select(Membership.id)
                .where(Membership.id.in_(admin_ids))
                .order_by(Membership.joined_at.asc(), Membership.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return rows[0] if rows else None


async def get_ownership(session: AsyncSession, *, principal: Principal) -> dict:
    org_id = _require_org(principal)
    permission_checker.require(principal, "organizations", "read", resource_org_id=org_id)
    org = await _get_org(session, org_id)
    owner_id = await current_owner_membership_id(session, org=org)
    return {"owner_membership_id": str(owner_id) if owner_id else None}


async def transfer_ownership(
    session: AsyncSession,
    *,
    principal: Principal,
    target_membership_id: uuid.UUID,
    confirm: bool,
    ctx: RequestContext,
) -> dict:
    org_id = _require_org(principal)
    # Ownership transfer is the most sensitive org action available; gate it on
    # the full org admin grant (not merely `members:update`).
    permission_checker.require(principal, "organizations", "update", resource_org_id=org_id)
    if not confirm:
        raise ConfirmationRequiredError()

    org = await _get_org(session, org_id)
    owner_id = await current_owner_membership_id(session, org=org)

    my_membership = (
        await session.execute(
            select(Membership.id).where(
                Membership.org_id == org_id,
                Membership.user_id == principal.user_id,
                Membership.status == "active",
            )
        )
    ).scalar_one_or_none()
    if owner_id is None or my_membership is None or my_membership != owner_id:
        raise NotOwnerError()

    target = (
        await session.execute(
            select(Membership).where(
                Membership.id == target_membership_id, Membership.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise ResourceNotFoundError()
    if target.status != "active":
        raise ValidationFailedError(
            "Không thể chuyển quyền sở hữu cho một thành viên không hoạt động.",
            details={"reason": "target_not_active"},
        )
    if target.id == owner_id:
        raise ValidationFailedError(
            "Thành viên này đã là chủ sở hữu hiện tại.",
            details={"reason": "already_owner"},
        )

    # Ensure the new owner holds the admin wildcard grant.
    if not await admin_guard.role_grants_admin_for_membership(session, membership_id=target.id):
        admin_role = (
            await session.execute(
                select(Role).where(
                    Role.org_id == org_id, Role.name == catalog.SYSTEM_ADMIN_ROLE_NAME
                )
            )
        ).scalar_one_or_none()
        if admin_role is None:
            raise ResourceNotFoundError()
        session.add(
            MembershipRole(
                membership_id=target.id,
                role_id=admin_role.id,
                assigned_by=principal.user_id,
            )
        )

    before_owner = str(owner_id)
    org.owner_membership_id = target.id
    org.version += 1
    await session.flush()
    await write_audit(
        session,
        action="organization.ownership_transferred",
        resource_type="organization",
        resource_id=org.id,
        context=_audit_ctx(principal, ctx),
        before={"owner_membership_id": before_owner},
        after={"owner_membership_id": str(target.id)},
    )
    await session.commit()
    return {"owner_membership_id": str(target.id)}
