"""University control-plane account governance (cross-persona).

The university control plane governs BOTH student and partner-member accounts
("university kiểm soát được cả student, partner"). This service is the
university-facing account admin; it is grant-gated in the service layer:

RBAC (``_require_account_governor``): platform superadmin bypasses; otherwise the
principal must hold ``accounts:govern`` AND be acting from a **university** org
(``org_reporting_facade.is_university_org``). This mirrors the
``support``/``privacy``/``abuse``/``taxonomy`` precedent, so a partner Admin
holding ``*:*`` can never govern accounts, and a misconfigured partner role can
never hold the grant in effect.

Governance writes are audited with a required, non-empty ``reason``:
- ``suspend_user``   -> audit ``account.suspended``  (+ reason, target persona)
- ``unsuspend_user`` -> audit ``account.reinstated`` (+ reason, target persona)

A non-superadmin governor may never suspend/reinstate/inspect another
**superadmin** account (superadmin-target protection); only a superadmin can.

Privacy: the list/detail projections return account-admin fields (email/name are
legitimate for a granted governor) but never CVs, raw tokens, AI internals, raw
IP/UA, or other users' data.

The superadmin path lives in ``platform_admin.users_admin_service`` and consumes
the raw flip helper :func:`set_user_active` (no gate/audit of its own here).
"""

from __future__ import annotations

import math
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application import session_facade
from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_reporting_facade
from app.modules.users.domain.models import Identity, User
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal, permission_checker

_VALID_PERSONAS = {"student", "partner_member", "university_staff"}
_REASON_MAX_LEN = 500


# --------------------------------------------------------------------------- #
# RBAC gate                                                                    #
# --------------------------------------------------------------------------- #


async def _require_account_governor(session: AsyncSession, principal: Principal) -> None:
    """``accounts:govern`` + acting-university-org gate (superadmin bypasses).

    Mirrors ``platform_support._shared.require_support`` /
    ``review_queue_service._require_university``: the org-type check means a
    partner Admin's ``*:*`` wildcard can never govern accounts.
    """

    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "accounts", "govern"):
        raise PermissionDeniedError()
    if not await org_reporting_facade.is_university_org(session, principal.org_id):
        raise PermissionDeniedError(details={"reason": "university_only"})


def _validate_reason(reason: str | None) -> str:
    """Return a trimmed, non-empty, length-bounded reason or raise 422."""

    cleaned = (reason or "").strip()
    if not cleaned:
        raise ValidationFailedError(details={"field": "reason", "reason": "required"})
    if len(cleaned) > _REASON_MAX_LEN:
        raise ValidationFailedError(
            details={"field": "reason", "reason": "too_long", "max": _REASON_MAX_LEN}
        )
    return cleaned


async def _get_user_or_404(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        # AppError.__init__ only accepts (message, *, details): default user-safe
        # message + non-PII details (grep other ResourceNotFoundError() sites).
        raise ResourceNotFoundError(details={"resource": "user"})
    return user


async def _primary_persona(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """The user's primary-identity persona (for audit context), or ``None``."""

    return (
        await session.execute(
            select(Identity.persona)
            .where(Identity.user_id == user_id, Identity.is_primary.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()


def _guard_not_protected_superadmin(principal: Principal, target: User) -> None:
    """Only a superadmin may govern another superadmin's account."""

    if target.is_superadmin and not principal.is_superadmin:
        raise PermissionDeniedError(details={"reason": "cannot_govern_superadmin"})


# --------------------------------------------------------------------------- #
# Shared raw flip (used by the superadmin path in platform_admin)              #
# --------------------------------------------------------------------------- #


async def set_user_active(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    active: bool,
    actor_user_id: uuid.UUID | None = None,
) -> dict:
    """Flip ``is_active`` on a user (no RBAC/audit/commit — caller owns those).

    Enforces the self-suspend guard: an actor may never suspend their OWN
    account (``actor_user_id`` is the acting principal). Raises 404 if the user
    does not exist. Returns ``{"id", "is_active"}``.
    """

    if not active and actor_user_id is not None and user_id == actor_user_id:
        raise PermissionDeniedError(details={"reason": "cannot_suspend_self"})
    user = await _get_user_or_404(session, user_id)
    user.is_active = active
    await session.flush()
    return {"id": str(user.id), "is_active": active}


# --------------------------------------------------------------------------- #
# list_platform_users — cross-persona, privacy-safe                            #
# --------------------------------------------------------------------------- #


async def list_platform_users(
    session: AsyncSession,
    *,
    principal: Principal,
    persona: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict:
    """Account-governor-gated cross-persona account list."""

    await _require_account_governor(session, principal)
    return await query_users(
        session, persona=persona, q=q, page=page, page_size=page_size
    )


async def query_users(
    session: AsyncSession,
    *,
    persona: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict:
    """Raw cross-persona account read (NO RBAC gate — callers authorize first).

    Used by the account-governor list and by the platform-support console lookup
    (which is authorized by its own ``support:read`` gate, not ``accounts:govern``).
    """

    if persona and persona not in _VALID_PERSONAS:
        persona = None

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    # Base query: User JOIN primary Identity. Cross-persona by default (student,
    # partner_member, university_staff) — the control plane governs both.
    stmt = (
        select(
            User.id,
            User.email,
            User.full_name,
            User.is_active,
            User.is_superadmin,
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
            "is_superadmin": r.is_superadmin,
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


# --------------------------------------------------------------------------- #
# get_account_detail — grant-gated, privacy-safe                               #
# --------------------------------------------------------------------------- #


async def get_account_detail(
    session: AsyncSession,
    *,
    principal: Principal,
    user_id: uuid.UUID,
) -> dict:
    """Privacy-safe account detail for a granted governor.

    Never returns CVs, password hashes, raw tokens, raw IP/UA, or AI internals.
    A non-superadmin governor may not inspect a superadmin account.
    """

    await _require_account_governor(session, principal)
    user = await _get_user_or_404(session, user_id)
    _guard_not_protected_superadmin(principal, user)

    core = {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name or "",
        "is_active": user.is_active,
        "is_superadmin": user.is_superadmin,
        "email_verified": user.email_verified_at is not None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }

    identity_rows = (
        await session.execute(
            select(Identity.persona, Identity.org_id, Identity.is_primary)
            .where(Identity.user_id == user_id)
            .order_by(Identity.is_primary.desc(), Identity.created_at)
        )
    ).all()
    identities = [
        {
            "persona": r.persona,
            "org_id": str(r.org_id) if r.org_id else None,
            "is_primary": r.is_primary,
        }
        for r in identity_rows
    ]

    # Active session count via the auth-owned privacy-safe facade (no direct
    # Session ORM import / no raw device metadata exposed here).
    active_sessions = await session_facade.list_active_sessions(session, user_id=user_id)

    return {
        "core": core,
        "identities": identities,
        "active_session_count": len(active_sessions),
    }


# --------------------------------------------------------------------------- #
# Governance writes — reason required, audited                                 #
# --------------------------------------------------------------------------- #


def _audit_context(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def suspend_user(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    user_id: uuid.UUID,
    reason: str,
) -> dict:
    """Suspend an account (``is_active=False``) with a required audited reason."""

    await _require_account_governor(session, principal)
    clean_reason = _validate_reason(reason)
    target = await _get_user_or_404(session, user_id)
    _guard_not_protected_superadmin(principal, target)

    result = await set_user_active(
        session,
        user_id=user_id,
        active=False,
        actor_user_id=principal.user_id,
    )
    persona = await _primary_persona(session, user_id)

    await write_audit(
        session,
        action="account.suspended",
        resource_type="user",
        resource_id=user_id,
        context=_audit_context(principal, ctx),
        before={"is_active": True},
        after={"is_active": False, "reason": clean_reason, "target_persona": persona},
    )
    await session.commit()
    return result


async def unsuspend_user(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    user_id: uuid.UUID,
    reason: str,
) -> dict:
    """Reinstate an account (``is_active=True``) with a required audited reason."""

    await _require_account_governor(session, principal)
    clean_reason = _validate_reason(reason)
    target = await _get_user_or_404(session, user_id)
    _guard_not_protected_superadmin(principal, target)

    result = await set_user_active(
        session,
        user_id=user_id,
        active=True,
        actor_user_id=principal.user_id,
    )
    persona = await _primary_persona(session, user_id)

    await write_audit(
        session,
        action="account.reinstated",
        resource_type="user",
        resource_id=user_id,
        context=_audit_context(principal, ctx),
        before={"is_active": False},
        after={"is_active": True, "reason": clean_reason, "target_persona": persona},
    )
    await session.commit()
    return result
