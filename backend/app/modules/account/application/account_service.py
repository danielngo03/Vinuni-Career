"""Account self-service use cases: sessions, security events, password, TOTP.

RBAC is enforced here (not in routers): every operation is a ``account`` action
the principal performs on its own account. Device/session output is privacy-safe
— device hint + city-level location only, never raw IP, raw user-agent, or refresh
tokens (``docs/SECURITY_PRIVACY.md``, ``docs/API_CONTRACTS.md``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application import errors as auth_errors
from app.modules.auth.application.context import RequestContext
from app.modules.auth.application.password_facade import (
    hash_new_password,
    revoke_other_sessions,
    verify_password_matches,
)
from app.modules.auth.application.security_event_service import (
    list_security_events,
    record_security_event,
)
from app.modules.auth.application.session_facade import list_active_sessions
from app.modules.auth.application.session_facade import (
    revoke_session as facade_revoke_session,
)
from app.modules.auth.application.totp_facade import begin_setup, confirm_setup
from app.modules.auth.application.totp_facade import disable as facade_totp_disable
from app.modules.auth.domain import security_events as ev
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.users.application import preferences_service, user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "account"


def _audit_ctx(
    principal: Principal, ctx: RequestContext, *, session_id: uuid.UUID | None = None
) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        session_id=session_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


# --------------------------------------------------------------------------- #
# Preferences                                                                 #
# --------------------------------------------------------------------------- #


async def get_preferences(session: AsyncSession, *, principal: Principal) -> dict:
    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None
    return await preferences_service.get_preferences(session, principal.user_id)


async def update_preferences(
    session: AsyncSession, *, principal: Principal, payload: dict, ctx: RequestContext
) -> dict:
    permission_checker.require(principal, _RESOURCE, "write")
    assert principal.user_id is not None
    result = await preferences_service.patch_preferences(session, principal.user_id, payload)
    await write_audit(
        session,
        action="account.preferences_updated",
        resource_type=_RESOURCE,
        resource_id=principal.user_id,
        context=_audit_ctx(principal, ctx),
    )
    await session.commit()
    return result


# --------------------------------------------------------------------------- #
# Sessions / devices                                                          #
# --------------------------------------------------------------------------- #


async def list_sessions(
    session: AsyncSession, *, principal: Principal, current_session_id: uuid.UUID
) -> list[dict]:
    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None
    rows = await list_active_sessions(session, user_id=principal.user_id)
    return [
        {
            "id": str(row.id),
            "device_hint": row.device_hint,
            "city_level_location": row.city_level_location,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "current": row.id == current_session_id,
        }
        for row in rows
    ]


async def revoke_session(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    permission_checker.require(principal, _RESOURCE, "write")
    assert principal.user_id is not None
    result = await facade_revoke_session(session, user_id=principal.user_id, session_id=session_id)
    if result is None:
        raise ResourceNotFoundError()
    if result.newly_revoked:
        await record_security_event(
            session,
            user_id=principal.user_id,
            event_type=ev.SESSION_REVOKED,
            ctx=ctx,
            session_id=result.session_id,
        )
        await write_audit(
            session,
            action="account.session_revoked",
            resource_type="session",
            resource_id=result.session_id,
            context=_audit_ctx(principal, ctx, session_id=result.session_id),
        )
    await session.commit()


# --------------------------------------------------------------------------- #
# Security events                                                             #
# --------------------------------------------------------------------------- #


async def list_events(
    session: AsyncSession, *, principal: Principal, limit: int = 20
) -> list[dict]:
    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None
    events = await list_security_events(session, user_id=principal.user_id, limit=limit)
    return [
        {
            "id": str(e.id),
            "type": e.event_type,
            "label": ev.label_for(e.event_type, locale="vi"),
            "label_en": ev.label_for(e.event_type, locale="en"),
            "device_hint": e.device_hint or "unknown",
            "city_level_location": e.city_level_location,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


# --------------------------------------------------------------------------- #
# Password                                                                     #
# --------------------------------------------------------------------------- #


async def change_password(
    session: AsyncSession,
    *,
    principal: Principal,
    current_session_id: uuid.UUID,
    current_password: str,
    new_password: str,
    ctx: RequestContext,
) -> None:
    permission_checker.require(principal, _RESOURCE, "write")
    assert principal.user_id is not None
    if len(new_password) < 8:
        raise ValidationFailedError(details={"field": "new_password"})

    user = await user_service.get_by_id(session, principal.user_id)
    if user is None:
        raise ResourceNotFoundError()
    # Re-authenticate with the current password before allowing a change.
    if not verify_password_matches(current_password, user.password_hash):
        raise auth_errors.InvalidCredentialsError()

    user.password_hash = hash_new_password(new_password)

    # Revoke every OTHER active session; keep the current one signed in.
    now = datetime.now(tz=UTC)
    await revoke_other_sessions(session, user_id=user.id, keep_session_id=current_session_id)

    await record_security_event(
        session,
        user_id=user.id,
        event_type=ev.PASSWORD_CHANGED,
        ctx=ctx,
        session_id=current_session_id,
    )
    await enqueue_notification(
        session,
        recipient_id=user.id,
        template_key="account.password_changed",
        channel="email",
        locale=user.preferred_language,
        variables={"email": user.email, "name": user.full_name or ""},
        dedupe_key=f"pwd_changed:{user.id}:{now.isoformat()}",
    )
    await write_audit(
        session,
        action="account.password_changed",
        resource_type=_RESOURCE,
        resource_id=user.id,
        context=_audit_ctx(principal, ctx, session_id=current_session_id),
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# TOTP (scaffold)                                                             #
# --------------------------------------------------------------------------- #


async def totp_setup(session: AsyncSession, *, principal: Principal, ctx: RequestContext) -> dict:
    permission_checker.require(principal, _RESOURCE, "write")
    assert principal.user_id is not None
    user = await user_service.get_by_id(session, principal.user_id)
    if user is None:
        raise ResourceNotFoundError()

    setup = await begin_setup(
        session,
        user_id=user.id,
        account_email=user.email,
        issuer_name=get_settings().email_from_name,
    )
    await write_audit(
        session,
        action="account.totp_setup",
        resource_type=_RESOURCE,
        resource_id=user.id,
        context=_audit_ctx(principal, ctx),
    )
    await session.commit()
    # Secret + URI are returned exactly once for enrolment.
    return {"secret": setup.secret, "otpauth_uri": setup.otpauth_uri, "confirmed": False}


async def totp_verify(
    session: AsyncSession, *, principal: Principal, code: str, ctx: RequestContext
) -> dict:
    permission_checker.require(principal, _RESOURCE, "write")
    assert principal.user_id is not None
    outcome = await confirm_setup(session, user_id=principal.user_id, code=code)
    if not outcome.ok:
        raise ValidationFailedError(details={"reason": outcome.reason})

    await record_security_event(
        session,
        user_id=principal.user_id,
        event_type=ev.TOTP_ENABLED,
        ctx=ctx,
    )
    await write_audit(
        session,
        action="account.totp_enabled",
        resource_type=_RESOURCE,
        resource_id=principal.user_id,
        context=_audit_ctx(principal, ctx),
    )
    await session.commit()
    return {"confirmed": True}


async def totp_disable(
    session: AsyncSession, *, principal: Principal, code: str, ctx: RequestContext
) -> dict:
    permission_checker.require(principal, _RESOURCE, "write")
    assert principal.user_id is not None
    outcome = await facade_totp_disable(session, user_id=principal.user_id, code=code)
    if not outcome.ok:
        raise ValidationFailedError(details={"reason": outcome.reason})

    await record_security_event(
        session,
        user_id=principal.user_id,
        event_type=ev.TOTP_DISABLED,
        ctx=ctx,
    )
    await write_audit(
        session,
        action="account.totp_disabled",
        resource_type=_RESOURCE,
        resource_id=principal.user_id,
        context=_audit_ctx(principal, ctx),
    )
    await session.commit()
    return {"confirmed": False}
