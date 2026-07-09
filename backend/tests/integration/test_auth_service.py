"""Service-level auth tests: register/verify/login/refresh/logout + edge cases."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.auth.application import auth_service, errors
from app.modules.auth.domain import security_events as ev
from app.modules.auth.domain.models import RefreshToken, SecurityEvent, Session
from app.modules.users.application import user_service
from app.shared.models import AuditLog
from sqlalchemy import select

from tests.auth_utils import CTX, fetch_verification_token, register_verified


def _email() -> str:
    return f"user_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


async def test_register_creates_unverified_user_and_enqueues_token(db_session) -> None:
    email = _email()
    result = await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name="A", ctx=CTX
    )
    assert result == {"status": "verification_sent", "email": email}
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    assert user.is_email_verified is False
    assert user.password_hash and "Sup3rSecret!" not in user.password_hash
    token = await fetch_verification_token(db_session, user.id)
    assert token and len(token) > 10  # raw token surfaced via outbox only


async def test_duplicate_register_does_not_create_second_user(db_session) -> None:
    # A VERIFIED duplicate stays blocked (unverified duplicates instead resume
    # the pending registration — see test_register_resumes_pending_registration
    # below, E36 B-542/B-543).
    email = _email()
    await register_verified(db_session, email=email)
    with pytest.raises(errors.EmailAlreadyRegisteredError):
        await auth_service.register(
            db_session, email=email, password="Other!", full_name="B", ctx=CTX
        )
    rows = (
        (
            await db_session.execute(
                select(user_service.User).where(user_service.User.email == email)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_register_resumes_pending_registration(db_session) -> None:
    # Registering again with an email that exists but is NOT yet verified
    # resumes the pending signup instead of returning a 409 conflict: the
    # submitted password/name overwrite the abandoned attempt's, and a fresh
    # verification token is issued.
    email = _email()
    await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name="A", ctx=CTX
    )
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    old_hash = user.password_hash

    result = await auth_service.register(
        db_session, email=email, password="BrandNewPass1!", full_name="B", ctx=CTX
    )
    assert result == {"status": "verification_sent", "email": email}

    rows = (
        (
            await db_session.execute(
                select(user_service.User).where(user_service.User.email == email)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1  # no second user created
    resumed = rows[0]
    assert resumed.full_name == "B"
    assert resumed.password_hash != old_hash
    assert resumed.is_email_verified is False

    token = await fetch_verification_token(db_session, user.id)
    assert token and len(token) > 10


async def test_verify_email_marks_verified_and_rejects_bad_token(db_session) -> None:
    email = _email()
    await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name="A", ctx=CTX
    )
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    with pytest.raises(errors.InvalidTokenError):
        await auth_service.verify_email(db_session, token="not-a-real-token", ctx=CTX)
    token = await fetch_verification_token(db_session, user.id)
    verified = await auth_service.verify_email(db_session, token=token, ctx=CTX)
    assert verified.is_email_verified is True


async def test_login_blocked_until_email_verified(db_session) -> None:
    email = _email()
    await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name="A", ctx=CTX
    )
    with pytest.raises(errors.EmailNotVerifiedError):
        await auth_service.login(db_session, email=email, password="Sup3rSecret!", ctx=CTX)


async def test_login_invalid_credentials(db_session) -> None:
    email = _email()
    await register_verified(db_session, email=email)
    with pytest.raises(errors.InvalidCredentialsError):
        await auth_service.login(db_session, email=email, password="wrong", ctx=CTX)
    # Unknown account also returns invalid credentials (no enumeration).
    with pytest.raises(errors.InvalidCredentialsError):
        await auth_service.login(db_session, email=_email(), password="whatever", ctx=CTX)


async def test_login_lockout_after_five_failures(db_session) -> None:
    email = _email()
    await register_verified(db_session, email=email)
    for _ in range(5):
        with pytest.raises(errors.InvalidCredentialsError):
            await auth_service.login(db_session, email=email, password="bad", ctx=CTX)
    # 6th attempt is locked out even with the correct password.
    with pytest.raises(errors.AccountLockedError):
        await auth_service.login(db_session, email=email, password="Sup3rSecret!", ctx=CTX)


async def test_login_success_writes_session_event_and_audit(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    result = await auth_service.login(db_session, email=email, password="Sup3rSecret!", ctx=CTX)
    assert result.tokens.access_token
    assert result.tokens.refresh_token
    sessions = (
        (await db_session.execute(select(Session).where(Session.user_id == user.id)))
        .scalars()
        .all()
    )
    assert len(sessions) == 1
    events = (
        (
            await db_session.execute(
                select(SecurityEvent).where(
                    SecurityEvent.user_id == user.id,
                    SecurityEvent.event_type == ev.LOGIN_SUCCESS,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    # security event stores only hashed IP, never the raw value
    assert events[0].ip_hash and events[0].ip_hash != CTX.ip
    audits = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "auth.login", AuditLog.actor_id == user.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


async def test_refresh_rotation_and_concurrent_double_submit(db_session) -> None:
    email = _email()
    await register_verified(db_session, email=email)
    login = await auth_service.login(db_session, email=email, password="Sup3rSecret!", ctx=CTX)
    t1 = login.tokens.refresh_token
    rotated = await auth_service.refresh(db_session, refresh_token=t1, ctx=CTX)
    t2 = rotated.refresh_token
    assert t2 and t2 != t1
    # Re-submitting the immediately-previous token (its replacement still active)
    # is treated as a benign concurrent retry, NOT reuse — session stays alive.
    with pytest.raises(errors.SessionExpiredError) as exc:
        await auth_service.refresh(db_session, refresh_token=t1, ctx=CTX)
    assert exc.value.details["reason"] == "concurrent_refresh"
    # t2 still works.
    again = await auth_service.refresh(db_session, refresh_token=t2, ctx=CTX)
    assert again.refresh_token not in {t1, t2}


async def test_refresh_reuse_revokes_session(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    login = await auth_service.login(db_session, email=email, password="Sup3rSecret!", ctx=CTX)
    t1 = login.tokens.refresh_token
    t2 = (await auth_service.refresh(db_session, refresh_token=t1, ctx=CTX)).refresh_token
    # advance the chain so t1 is genuinely stale (its replacement is rotated)
    await auth_service.refresh(db_session, refresh_token=t2, ctx=CTX)
    with pytest.raises(errors.SessionExpiredError) as exc:
        await auth_service.refresh(db_session, refresh_token=t1, ctx=CTX)
    assert exc.value.details["reason"] == "token_reuse"
    # Session is revoked and a security event recorded.
    sessions = (
        (await db_session.execute(select(Session).where(Session.user_id == user.id)))
        .scalars()
        .all()
    )
    assert all(s.revoked_at is not None for s in sessions)
    reuse_events = (
        (
            await db_session.execute(
                select(SecurityEvent).where(
                    SecurityEvent.user_id == user.id,
                    SecurityEvent.event_type == ev.TOKEN_REUSE_DETECTED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(reuse_events) == 1


async def test_expired_refresh_token_rejected(db_session) -> None:
    email = _email()
    await register_verified(db_session, email=email)
    login = await auth_service.login(db_session, email=email, password="Sup3rSecret!", ctx=CTX)
    token_hash_row = (await db_session.execute(select(RefreshToken))).scalars().all()[-1]
    token_hash_row.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    await db_session.commit()
    with pytest.raises(errors.SessionExpiredError):
        await auth_service.refresh(db_session, refresh_token=login.tokens.refresh_token, ctx=CTX)


async def test_logout_revokes_session(db_session) -> None:
    from app.modules.auth.infrastructure.jwt import decode_access_token
    from app.shared.permissions import Principal

    email = _email()
    user = await register_verified(db_session, email=email)
    login = await auth_service.login(db_session, email=email, password="Sup3rSecret!", ctx=CTX)
    claims = decode_access_token(login.tokens.access_token)
    principal = Principal(user_id=user.id, persona="student")
    await auth_service.logout(
        db_session,
        principal=principal,
        session_id=claims.session_id,
        jti=claims.jti,
        access_expires_at=claims.expires_at,
        ctx=CTX,
    )
    sess = (
        await db_session.execute(select(Session).where(Session.id == claims.session_id))
    ).scalar_one()
    assert sess.revoked_at is not None
    # The rotated refresh token is no longer usable.
    with pytest.raises(errors.SessionExpiredError):
        await auth_service.refresh(db_session, refresh_token=login.tokens.refresh_token, ctx=CTX)
