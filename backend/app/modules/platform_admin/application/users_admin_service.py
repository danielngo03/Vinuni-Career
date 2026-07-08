"""Platform Admin — superadmin users & access service (P4a).

Exposes:
- ``user_360``               — composited superadmin detail view for one user.
- ``list_platform_sessions`` — cursor-paginated active sessions across all users.
- ``revoke_platform_session``— admin-initiated session revoke with audit.
- ``list_users``             — thin superadmin wrapper over admin_users_service.
- ``suspend_user``           — audited suspend (admin_users_service does not audit).
- ``unsuspend_user``         — audited unsuspend.

Privacy rules (enforced here, not only in routers):
- No password hashes, raw tokens, ip_hash, raw IP, raw UA, or PII beyond email.
- Session projection: session_id, user_id, user_email, device_hint,
  city_level_location, last_seen_at, created_at, expires_at only.
- ``safe()`` wrapper around optional sub-queries so one failure never 500s the
  whole user_360 response.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.models import AiUsageLog
from app.modules.auth.application.session_facade import revoke_session
from app.modules.auth.domain.models import Session
from app.modules.users.application import admin_users_service
from app.modules.users.application.user_read_facade import (
    get_user_contacts,
)
from app.modules.users.domain.models import Identity, User
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_superadmin(principal: Principal) -> None:
    if not principal.is_superadmin:
        raise PermissionDeniedError()


async def _safe(coro: Any, fallback: Any = None) -> Any:
    """Execute a coroutine; return ``fallback`` on any exception.

    Prevents a partial sub-query failure from 500-ing the full user_360 view.
    """
    try:
        return await coro
    except Exception:  # noqa: BLE001
        return fallback


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# user_360
# ---------------------------------------------------------------------------


async def user_360(
    session: AsyncSession,
    *,
    principal: Principal,
    user_id: uuid.UUID,
) -> dict:
    """Compose a superadmin 360-view for ``user_id``.

    Sub-sections are each wrapped in ``_safe()`` so one DB miss never breaks
    the whole response.  Returns a dict with keys:
        core, identities, active_session_count, recent_ai_usage_count.
    """
    _require_superadmin(principal)

    # --- core user row ---
    user = (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise ResourceNotFoundError(details={"resource": "user"})

    core = {
        "id": str(user.id),
        "email": user.email,
        "is_active": user.is_active,
        "is_superadmin": user.is_superadmin,
        "email_verified": user.email_verified_at is not None,
        "created_at": _iso(user.created_at),
        "last_login_at": _iso(user.last_login_at),
    }

    # --- identities (persona + org_id) ---
    async def _fetch_identities() -> list[dict]:
        rows = (
            await session.execute(
                select(Identity.id, Identity.persona, Identity.org_id, Identity.is_primary)
                .where(Identity.user_id == user_id)
                .order_by(Identity.is_primary.desc(), Identity.created_at)
            )
        ).all()
        return [
            {
                "identity_id": str(r.id),
                "persona": r.persona,
                "org_id": str(r.org_id) if r.org_id else None,
                "is_primary": r.is_primary,
            }
            for r in rows
        ]

    identities: list[dict] = await _safe(_fetch_identities(), [])

    # --- active session count ---
    async def _fetch_session_count() -> int:
        now = datetime.now(tz=UTC)
        result = await session.execute(
            select(func.count()).select_from(Session).where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.expires_at > now,
            )
        )
        return result.scalar_one() or 0

    active_session_count: int = await _safe(_fetch_session_count(), 0)

    # --- recent AI usage count (last 30 days, cheap count) ---
    async def _fetch_ai_count() -> int:
        from datetime import timedelta

        cutoff = datetime.now(tz=UTC) - timedelta(days=30)
        result = await session.execute(
            select(func.count()).select_from(AiUsageLog).where(
                AiUsageLog.user_id == user_id,
                AiUsageLog.created_at >= cutoff,
            )
        )
        return result.scalar_one() or 0

    recent_ai_usage_count: int = await _safe(_fetch_ai_count(), 0)

    return {
        "core": core,
        "identities": identities,
        "active_session_count": active_session_count,
        "recent_ai_usage_count": recent_ai_usage_count,
    }


# ---------------------------------------------------------------------------
# list_platform_sessions  (cursor-paginated, cross-user)
# ---------------------------------------------------------------------------


async def list_platform_sessions(
    session: AsyncSession,
    *,
    principal: Principal,
    user_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> tuple[list[dict], str | None, int]:
    """Return active sessions across all users (or filtered to one user).

    Cursor is on ``(last_seen_at DESC, Session.id DESC)`` — newest-activity
    first.  Only active sessions are returned (revoked_at IS NULL AND
    expires_at > now).

    Privacy projection: session_id, user_id, user_email (enriched), device_hint,
    city_level_location, last_seen_at, created_at, expires_at.
    NEVER returns ip_hash, raw ip, raw UA, refresh tokens, or internal fields.
    """
    _require_superadmin(principal)
    page_limit = clamp_limit(limit)
    now = datetime.now(tz=UTC)

    stmt = select(Session).where(
        Session.revoked_at.is_(None),
        Session.expires_at > now,
    )
    if user_id is not None:
        stmt = stmt.where(Session.user_id == user_id)

    # Cursor: encoded {"last_seen": <iso>, "id": <str-uuid>}
    decoded = decode_cursor(cursor)
    if decoded is not None:
        try:
            cur_last_seen = datetime.fromisoformat(decoded["last_seen"])
            cur_id = uuid.UUID(decoded["id"])
            stmt = stmt.where(
                (Session.last_seen_at < cur_last_seen)
                | (
                    (Session.last_seen_at == cur_last_seen)
                    & (Session.id < cur_id)
                )
            )
        except (KeyError, ValueError):
            pass  # malformed cursor — treat as first page

    stmt = stmt.order_by(Session.last_seen_at.desc(), Session.id.desc()).limit(
        page_limit + 1
    )
    rows = list((await session.execute(stmt)).scalars().all())

    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda row: {
            "last_seen": _iso(row.last_seen_at),
            "id": str(row.id),
        },
    )

    # Enrich: bulk-fetch user emails for session rows
    user_ids = {r.user_id for r in page.items}
    contacts = await get_user_contacts(session, user_ids)

    items = [
        {
            "session_id": str(r.id),
            "user_id": str(r.user_id),
            "user_email": contacts[r.user_id].email if r.user_id in contacts else None,
            "device_hint": r.device_hint or "unknown",
            "city_level_location": r.city_level_location,
            "last_seen_at": _iso(r.last_seen_at),
            "created_at": _iso(r.created_at),
            "expires_at": _iso(r.expires_at),
        }
        for r in page.items
    ]
    return items, page.next_cursor, page.limit


# ---------------------------------------------------------------------------
# revoke_platform_session
# ---------------------------------------------------------------------------


async def revoke_platform_session(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any,
    session_id: uuid.UUID,
) -> dict:
    """Admin-revoke a session by ID.

    Looks up the session's owner, delegates to ``session_facade.revoke_session``,
    writes an audit row on a fresh revoke.  Already-revoked sessions are a
    safe no-op (idempotent).

    Returns:
        {"session_id": str, "newly_revoked": bool}
    """
    _require_superadmin(principal)

    # Fetch the session to get its user_id (no ownership check — superadmin)
    target = (
        await session.execute(select(Session).where(Session.id == session_id))
    ).scalar_one_or_none()
    if target is None:
        raise ResourceNotFoundError(details={"resource": "session"})

    target_user_id = target.user_id
    result = await revoke_session(session, user_id=target_user_id, session_id=session_id)
    # result is always non-None here (we confirmed the session exists)
    newly_revoked = result.newly_revoked if result is not None else False

    if newly_revoked:
        audit_ctx = AuditContext(
            actor_id=principal.user_id,
            actor_org_id=principal.org_id,
            session_id=getattr(ctx, "session_id", None),
            ip=getattr(ctx, "ip", None),
            user_agent=getattr(ctx, "user_agent", None),
        )
        await write_audit(
            session,
            action="session.revoked_by_admin",
            resource_type="session",
            resource_id=session_id,
            context=audit_ctx,
            after={"target_user_id": str(target_user_id)},
        )
        await session.commit()

    return {
        "session_id": str(session_id),
        "newly_revoked": newly_revoked,
    }


# ---------------------------------------------------------------------------
# Thin superadmin wrappers for list / suspend / unsuspend
# ---------------------------------------------------------------------------


async def list_users(
    session: AsyncSession,
    *,
    principal: Principal,
    persona: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict:
    """Superadmin-only list; delegates to admin_users_service (which re-checks RBAC)."""
    _require_superadmin(principal)
    return await admin_users_service.list_platform_users(
        session,
        principal=principal,
        persona=persona,
        q=q,
        page=page,
        page_size=page_size,
    )


async def suspend_user(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any,
    user_id: uuid.UUID,
) -> dict:
    """Superadmin suspend with audit.

    ``admin_users_service.suspend_user`` does NOT write an audit row — we write
    one here so every superadmin suspend action is recorded.
    """
    _require_superadmin(principal)

    # Fetch before-state for audit snapshot
    user_before = (
        await session.execute(
            select(User.is_active).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()

    result = await admin_users_service.suspend_user(
        session, principal=principal, user_id=user_id
    )

    audit_ctx = AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=getattr(ctx, "ip", None),
        user_agent=getattr(ctx, "user_agent", None),
    )
    await write_audit(
        session,
        action="user.suspended",
        resource_type="user",
        resource_id=user_id,
        context=audit_ctx,
        before={"is_active": user_before} if user_before is not None else None,
        after={"is_active": False},
    )
    await session.commit()
    return result


async def unsuspend_user(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any,
    user_id: uuid.UUID,
) -> dict:
    """Superadmin unsuspend with audit."""
    _require_superadmin(principal)

    user_before = (
        await session.execute(
            select(User.is_active).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()

    result = await admin_users_service.unsuspend_user(
        session, principal=principal, user_id=user_id
    )

    audit_ctx = AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=getattr(ctx, "ip", None),
        user_agent=getattr(ctx, "user_agent", None),
    )
    await write_audit(
        session,
        action="user.unsuspended",
        resource_type="user",
        resource_id=user_id,
        context=audit_ctx,
        before={"is_active": user_before} if user_before is not None else None,
        after={"is_active": True},
    )
    await session.commit()
    return result


# ---------------------------------------------------------------------------
# grant_superadmin / revoke_superadmin
# ---------------------------------------------------------------------------


async def grant_superadmin(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any,
    user_id: uuid.UUID,
) -> dict:
    """Promote ``user_id`` to superadmin.

    Superadmin-only.  Idempotent: if the user is already a superadmin, this is a
    no-op (no duplicate audit row).  Commits the state change and audit row
    atomically.

    Returns:
        ``{"id": str, "is_superadmin": True}``
    """
    _require_superadmin(principal)

    user = (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise ResourceNotFoundError(details={"resource": "user"})

    # Idempotent: already a superadmin → no-op, no duplicate audit.
    if user.is_superadmin:
        return {"id": str(user.id), "is_superadmin": True}

    user.is_superadmin = True
    await session.flush()

    audit_ctx = AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=getattr(ctx, "ip", None),
        user_agent=getattr(ctx, "user_agent", None),
    )
    await write_audit(
        session,
        action="user.superadmin_granted",
        resource_type="user",
        resource_id=user_id,
        context=audit_ctx,
        before={"is_superadmin": False},
        after={"is_superadmin": True},
    )
    await session.commit()
    return {"id": str(user.id), "is_superadmin": True}


async def revoke_superadmin(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any,
    user_id: uuid.UUID,
) -> dict:
    """Revoke superadmin from ``user_id``.

    Superadmin-only.  Idempotent: if the user is not a superadmin, no-op.
    GUARD: refuses to revoke if this would leave zero active superadmins
    (including the case of a superadmin revoking themselves while they are the
    last one).

    Returns:
        ``{"id": str, "is_superadmin": False}``
    """
    _require_superadmin(principal)

    user = (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if user is None:
        raise ResourceNotFoundError(details={"resource": "user"})

    # Idempotent: already not a superadmin → no-op.
    if not user.is_superadmin:
        return {"id": str(user.id), "is_superadmin": False}

    # Last-superadmin guard: count ACTIVE superadmins only.
    # A suspended (is_active=False) superadmin cannot log in, so they must NOT
    # be counted as a "remaining" admin — otherwise revoking the last active
    # superadmin would leave the system in an effective lockout state.
    superadmin_count_result = await session.execute(
        select(func.count()).select_from(User).where(
            User.is_superadmin.is_(True),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    superadmin_count = superadmin_count_result.scalar_one() or 0
    if superadmin_count <= 1:
        from app.shared.exceptions import ConflictError

        raise ConflictError(
            "Không thể thu hồi quyền superadmin khi đây là tài khoản superadmin duy nhất còn lại."
        )

    user.is_superadmin = False
    await session.flush()

    audit_ctx = AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=getattr(ctx, "ip", None),
        user_agent=getattr(ctx, "user_agent", None),
    )
    await write_audit(
        session,
        action="user.superadmin_revoked",
        resource_type="user",
        resource_id=user_id,
        context=audit_ctx,
        before={"is_superadmin": True},
        after={"is_superadmin": False},
    )
    await session.commit()
    return {"id": str(user.id), "is_superadmin": False}
