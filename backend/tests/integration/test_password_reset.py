"""Service-level tests for forgot/reset password and verification resend.

Covers anti-enumeration (identical response for known vs unknown email, token
created only for a real account), reset token lifecycle (happy / expired / used /
invalid), session revocation on reset, and prior-token invalidation on resend.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.auth.application import auth_service, errors
from app.modules.auth.domain import security_events as ev
from app.modules.auth.domain.models import EmailVerification, SecurityEvent, Session
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.users.application import user_service
from app.shared.models import AuditLog
from sqlalchemy import select

from tests.auth_utils import CTX, fetch_verification_token, register_verified


def _email() -> str:
    return f"reset_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


async def _reset_token(session, user_id) -> str:
    variables = await _reset_variables(session, user_id)
    return str(variables["token"])


async def _reset_variables(session, user_id) -> dict:
    rows = (
        await session.execute(
            select(NotificationOutbox)
            .where(NotificationOutbox.recipient_id == user_id)
            .order_by(NotificationOutbox.created_at.desc())
        )
    ).scalars().all()
    for row in rows:
        if row.template_key == "account.password_reset":
            return dict(row.variables)
    raise AssertionError("no password-reset token enqueued")


async def _count_reset_tokens(session, user_id) -> int:
    rows = (
        await session.execute(
            select(EmailVerification).where(
                EmailVerification.user_id == user_id,
                EmailVerification.purpose == "password_reset",
            )
        )
    ).scalars().all()
    return len(rows)


# --------------------------------------------------------------------------- #
# forgot-password anti-enumeration                                            #
# --------------------------------------------------------------------------- #


async def test_forgot_password_same_response_known_and_unknown(db_session) -> None:
    email = _email()
    await register_verified(db_session, email=email)

    known = await auth_service.forgot_password(db_session, email=email, ctx=CTX)
    unknown = await auth_service.forgot_password(
        db_session, email=_email(), ctx=CTX
    )
    # Identical generic shape regardless of account existence.
    assert known["status"] == unknown["status"] == "reset_email_sent"
    assert set(known.keys()) == set(unknown.keys())


async def test_forgot_password_creates_token_only_for_real_user(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    missing_email = _email()

    await auth_service.forgot_password(db_session, email=email, ctx=CTX)
    await auth_service.forgot_password(db_session, email=missing_email, ctx=CTX)

    # Real account -> exactly one reset token + one enqueued reset email.
    assert await _count_reset_tokens(db_session, user.id) == 1
    variables = await _reset_variables(db_session, user.id)
    token = str(variables["token"])
    assert token and len(token) > 10
    assert str(variables["otp_code"]).isdigit()
    assert len(str(variables["otp_code"])) == 6

    # Unknown email -> no user, hence no token rows anywhere for it.
    assert await user_service.get_by_email(db_session, missing_email) is None


async def test_forgot_password_action_url_points_to_frontend_with_locale(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email, locale="en")
    await auth_service.forgot_password(db_session, email=email, ctx=CTX)

    row = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.password_reset",
            )
        )
    ).scalar_one()
    action_url = str(row.variables["action_url"])
    assert action_url.startswith("http://localhost:3000/en/auth/reset-password?token=")
    assert "localhost:8000" not in action_url


# --------------------------------------------------------------------------- #
# reset-password lifecycle                                                     #
# --------------------------------------------------------------------------- #


async def test_verification_email_action_url_points_to_frontend_with_locale(db_session) -> None:
    email = _email()
    await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name="A",
        locale="vi", ctx=CTX,
    )
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    row = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.email_verification",
            )
        )
    ).scalar_one()
    action_url = str(row.variables["action_url"])
    assert action_url.startswith("http://localhost:3000/vi/auth/verify-email?token=")
    assert "localhost:8000" not in action_url


async def test_reset_password_happy_path_and_revokes_all_sessions(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    # Two active logins (sessions) prior to reset.
    login1 = await auth_service.login(
        db_session, email=email, password="Sup3rSecret!", ctx=CTX
    )
    login2 = await auth_service.login(
        db_session, email=email, password="Sup3rSecret!", ctx=CTX
    )

    await auth_service.forgot_password(db_session, email=email, ctx=CTX)
    token = await _reset_token(db_session, user.id)

    await auth_service.reset_password(
        db_session, token=token, password="BrandNewPass1!", ctx=CTX
    )

    # New password works.
    relog = await auth_service.login(
        db_session, email=email, password="BrandNewPass1!", ctx=CTX
    )
    assert relog.tokens.access_token

    # Old password rejected.
    with pytest.raises(errors.InvalidCredentialsError):
        await auth_service.login(
            db_session, email=email, password="Sup3rSecret!", ctx=CTX
        )

    # All pre-reset sessions revoked; their refresh tokens rejected.
    for login in (login1, login2):
        with pytest.raises(errors.SessionExpiredError):
            await auth_service.refresh(
                db_session, refresh_token=login.tokens.refresh_token, ctx=CTX
            )
    pre_reset = (
        await db_session.execute(
            select(Session).where(
                Session.user_id == user.id,
                Session.revoked_reason == "password_reset",
            )
        )
    ).scalars().all()
    assert len(pre_reset) == 2

    # Security event + audit recorded.
    events = (
        await db_session.execute(
            select(SecurityEvent).where(
                SecurityEvent.user_id == user.id,
                SecurityEvent.event_type == ev.PASSWORD_RESET,
            )
        )
    ).scalars().all()
    assert len(events) == 1
    audits = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "auth.password_reset")
        )
    ).scalars().all()
    assert len(audits) == 1
    # Confirmation email enqueued.
    confirm = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.password_changed",
            )
        )
    ).scalars().all()
    assert len(confirm) == 1


async def test_reset_password_with_otp_happy_path(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    login = await auth_service.login(
        db_session, email=email, password="Sup3rSecret!", ctx=CTX
    )

    await auth_service.forgot_password(db_session, email=email, ctx=CTX)
    variables = await _reset_variables(db_session, user.id)
    otp = str(variables["otp_code"])

    await auth_service.reset_password_otp(
        db_session,
        email=email,
        otp_code=otp,
        password="OtpFresh2026!",
        ctx=CTX,
    )

    relog = await auth_service.login(
        db_session, email=email, password="OtpFresh2026!", ctx=CTX
    )
    assert relog.tokens.access_token

    with pytest.raises(errors.InvalidCredentialsError):
        await auth_service.login(
            db_session, email=email, password="Sup3rSecret!", ctx=CTX
        )
    with pytest.raises(errors.SessionExpiredError):
        await auth_service.refresh(
            db_session, refresh_token=login.tokens.refresh_token, ctx=CTX
        )


async def test_reset_password_otp_wrong_attempts_are_counted(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    await auth_service.forgot_password(db_session, email=email, ctx=CTX)

    with pytest.raises(errors.InvalidTokenError) as exc:
        await auth_service.reset_password_otp(
            db_session,
            email=email,
            otp_code="000000",
            password="OtpFresh2026!",
            ctx=CTX,
        )
    assert exc.value.details["reason"].startswith("otp_wrong")

    record = (
        await db_session.execute(
            select(EmailVerification).where(
                EmailVerification.user_id == user.id,
                EmailVerification.purpose == "password_reset",
            )
        )
    ).scalar_one()
    assert record.otp_attempts == 1


async def test_reset_password_token_is_single_use(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    await auth_service.forgot_password(db_session, email=email, ctx=CTX)
    token = await _reset_token(db_session, user.id)

    await auth_service.reset_password(
        db_session, token=token, password="BrandNewPass1!", ctx=CTX
    )
    with pytest.raises(errors.InvalidTokenError) as exc:
        await auth_service.reset_password(
            db_session, token=token, password="AnotherPass1!", ctx=CTX
        )
    assert exc.value.details["reason"] == "reset_used"


async def test_reset_password_rejects_expired_token(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    await auth_service.forgot_password(db_session, email=email, ctx=CTX)
    token = await _reset_token(db_session, user.id)

    record = (
        await db_session.execute(
            select(EmailVerification).where(
                EmailVerification.user_id == user.id,
                EmailVerification.purpose == "password_reset",
            )
        )
    ).scalar_one()
    record.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    await db_session.commit()

    with pytest.raises(errors.InvalidTokenError) as exc:
        await auth_service.reset_password(
            db_session, token=token, password="BrandNewPass1!", ctx=CTX
        )
    assert exc.value.details["reason"] == "reset_expired"


async def test_reset_password_rejects_invalid_token(db_session) -> None:
    with pytest.raises(errors.InvalidTokenError) as exc:
        await auth_service.reset_password(
            db_session, token="totally-bogus-token", password="BrandNewPass1!", ctx=CTX
        )
    assert exc.value.details["reason"] == "reset_invalid"


async def test_forgot_password_invalidates_prior_reset_token(db_session) -> None:
    from app.modules.auth.domain.models import AuthThrottle
    from app.modules.auth.infrastructure.rate_limit import _key_hash

    email = _email()
    user = await register_verified(db_session, email=email)

    await auth_service.forgot_password(db_session, email=email, ctx=CTX)
    first_token = await _reset_token(db_session, user.id)

    # Bypass the resend cooldown (unrelated to what this test verifies) by
    # backdating the throttle row past the cooldown window, same technique as
    # tests/integration/test_auth_rate_limit_and_oauth.py.
    row = (
        await db_session.execute(
            select(AuthThrottle).where(
                AuthThrottle.scope == "forgot_password",
                AuthThrottle.key_hash == _key_hash(email),
            )
        )
    ).scalar_one()
    row.last_attempt_at = datetime.now(tz=UTC) - timedelta(hours=1)
    row.window_started_at = datetime.now(tz=UTC) - timedelta(hours=1)
    row.attempt_count = 0
    await db_session.flush()

    await auth_service.forgot_password(db_session, email=email, ctx=CTX)

    # The first token is now invalidated (used); only the newest is valid.
    with pytest.raises(errors.InvalidTokenError) as exc:
        await auth_service.reset_password(
            db_session, token=first_token, password="BrandNewPass1!", ctx=CTX
        )
    assert exc.value.details["reason"] == "reset_used"


# --------------------------------------------------------------------------- #
# verify-email/resend anti-enumeration                                        #
# --------------------------------------------------------------------------- #


async def test_resend_verification_same_response_all_cases(db_session) -> None:
    # Unverified user.
    email = _email()
    await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name="A", ctx=CTX
    )
    # Already-verified user.
    verified_email = _email()
    await register_verified(db_session, email=verified_email)
    # Unknown email.
    unknown = await auth_service.resend_verification(
        db_session, email=_email(), ctx=CTX
    )
    pending = await auth_service.resend_verification(db_session, email=email, ctx=CTX)
    already = await auth_service.resend_verification(
        db_session, email=verified_email, ctx=CTX
    )
    assert unknown["status"] == pending["status"] == already["status"] == "verification_sent"
    assert set(unknown.keys()) == set(pending.keys()) == set(already.keys())


async def test_resend_verification_invalidates_prior_token(db_session) -> None:
    email = _email()
    await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name="A", ctx=CTX
    )
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    first_token = await fetch_verification_token(db_session, user.id)

    await auth_service.resend_verification(db_session, email=email, ctx=CTX)

    # The original token is invalidated; the fresh one verifies.
    with pytest.raises(errors.InvalidTokenError):
        await auth_service.verify_email(db_session, token=first_token, ctx=CTX)

    tokens = {
        str(row.variables["token"])
        for row in (
            await db_session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.recipient_id == user.id,
                    NotificationOutbox.template_key == "account.email_verification",
                )
            )
        ).scalars().all()
    }
    new_tokens = tokens - {first_token}
    assert len(new_tokens) == 1
    new_token = new_tokens.pop()
    verified = await auth_service.verify_email(db_session, token=new_token, ctx=CTX)
    assert verified.is_email_verified is True


async def test_resend_verification_no_email_for_verified_user(db_session) -> None:
    email = _email()
    user = await register_verified(db_session, email=email)
    before = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.email_verification",
            )
        )
    ).scalars().all()
    await auth_service.resend_verification(db_session, email=email, ctx=CTX)
    after = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.email_verification",
            )
        )
    ).scalars().all()
    # No additional verification email for an already-verified account.
    assert len(after) == len(before)
