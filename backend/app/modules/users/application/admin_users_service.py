"""University admin: platform user management.

RBAC mirrors ``university_dashboard._require_university``:
platform superadmin OR a member of a university org holding ``jobs:moderate``.

Exposed endpoints:
- list_platform_users  -> GET  /admin/users
- suspend_user         -> POST /admin/users/{id}/suspend
- unsuspend_user       -> POST /admin/users/{id}/unsuspend
"""

from __future__ import annotations

import math
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organization.application import org_reporting_facade
from app.modules.users.domain.models import Identity, User
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_VALID_PERSONAS = {"student", "partner_member", "university_staff"}


async def _require_university_admin(session: AsyncSession, principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "jobs", "moderate"):
        raise PermissionDeniedError()
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


async def list_platform_users(
    session: AsyncSession,
    *,
    principal: Principal,
    persona: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict:
    await _require_university_admin(session, principal)

    if persona and persona not in _VALID_PERSONAS:
        persona = None

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    # Base query: User JOIN primary Identity
    stmt = (
        select(
            User.id,
            User.email,
            User.full_name,
            User.is_active,
            User.email_verified_at,
            User.created_at,
            Identity.persona,
            Identity.org_id,
        )
        .join(Identity, Identity.user_id == User.id)
        .where(User.deleted_at.is_(None), Identity.is_primary.is_(True))
    )

    if persona:
        stmt = stmt.where(Identity.persona == persona)

    if q:
        q_like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(q_like),
                func.lower(func.coalesce(User.full_name, "")).like(q_like),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one() or 0

    stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    rows = (await session.execute(stmt)).all()

    items = [
        {
            "id": str(r.id),
            "email": r.email,
            "full_name": r.full_name or "",
            "is_active": r.is_active,
            "email_verified": r.email_verified_at is not None,
            "persona": r.persona,
            "org_id": str(r.org_id) if r.org_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


async def _get_user_or_404(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = (
        await session.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if user is None:
        # AppError.__init__ only accepts (message, *, details) — resource/
        # resource_id kwargs don't exist and previously raised TypeError
        # instead of a clean 404. Match the codebase convention (grep other
        # ResourceNotFoundError() call sites): default user-safe message,
        # non-PII details.
        raise ResourceNotFoundError(details={"resource": "user"})
    return user


async def suspend_user(
    session: AsyncSession,
    *,
    principal: Principal,
    user_id: uuid.UUID,
) -> dict:
    await _require_university_admin(session, principal)
    if str(user_id) == str(principal.user_id):
        raise PermissionDeniedError(details={"reason": "cannot_suspend_self"})
    user = await _get_user_or_404(session, user_id)
    user.is_active = False
    await session.flush()
    return {"id": str(user.id), "is_active": False}


async def unsuspend_user(
    session: AsyncSession,
    *,
    principal: Principal,
    user_id: uuid.UUID,
) -> dict:
    await _require_university_admin(session, principal)
    user = await _get_user_or_404(session, user_id)
    user.is_active = True
    await session.flush()
    return {"id": str(user.id), "is_active": True}
