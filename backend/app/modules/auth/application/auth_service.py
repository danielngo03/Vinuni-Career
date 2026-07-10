"""Authentication use cases: register, verify-email, login, refresh, logout, and
multi-identity switching.

All business rules live here (routers stay HTTP-only). Every write records audit
data and, where user-relevant, a security event. Passwords are Argon2-hashed,
refresh tokens are stored hashed and rotated on every use, and token reuse after
rotation revokes the session (``docs/SECURITY_PRIVACY.md``,
``docs/EDGE_CASES_FAILURE_MODES.md``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application import errors
from app.modules.auth.application.context import RequestContext
from app.modules.auth.application.security_event_service import record_security_event
from app.modules.auth.domain import security_events as ev
from app.modules.auth.domain.models import (
    EmailVerification,
    RefreshToken,
    SecurityEvent,
    Session,
    UserTotp,
    ensure_aware,
)
from app.modules.auth.infrastructure import jwt as jwt_infra
from app.modules.auth.infrastructure import token_revocation
from app.modules.auth.infrastructure.passwords import hash_password, verify_password
from app.modules.auth.infrastructure.rate_limit import check_and_touch_throttle
from app.modules.auth.infrastructure.tokens import (
    generate_otp,
    generate_token,
    hash_otp,
    hash_token,
)
from app.modules.auth.infrastructure.totp_crypto import (
    decrypt_totp_secret,
    encrypt_totp_secret,
)
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.users.application import user_service
from app.modules.users.application.user_write_facade import (
    Identity,
    User,
    create_identity,
    create_user,
    set_preference,
)
from app.modules.workflow.application.trigger_service import dispatch_trigger
from app.shared.audit import AuditContext, write_audit
from app.shared.hashing import device_hint, hash_ip
from app.shared.permissions import Principal

EMAIL_VERIFICATION_TTL_HOURS = 24
DEFAULT_PERSONA = "student"
DEFAULT_LOCALE = "vi"

PURPOSE_REGISTER = "register"
PURPOSE_PASSWORD_RESET = "password_reset"
PURPOSE_STUDENT_EMAIL = "student_email"
OTP_TTL_MINUTES = 10  # overridable via settings


def _frontend_link(*, path: str, locale: str | None, token: str) -> str:
    """Build a locale-scoped public web-app link, e.g.
    ``http://localhost:3000/vi/auth/reset-password?token=...``.

    Account emails must point users at the FRONTEND app, never the backend API
    origin (``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md``).
    """

    base = get_settings().frontend_url.rstrip("/")
    lang = locale or DEFAULT_LOCALE
    return f"{base}/{lang}/{path.lstrip('/')}?token={token}"


def _greeting_name(user: User) -> str:
    """A never-empty greeting token for account emails.

    Registration is email/password only — a name belongs to onboarding / profile
    / CV confirmation and may not exist yet (``CLAUDE.md``). Account-email
    templates must never render an empty ``Chào ,`` / ``Hi ,`` greeting, so fall
    back to the account's own email address when no display name is set. The
    email is always the notification recipient, so echoing it leaks nothing.
    """

    return (user.full_name or "").strip() or user.email


@dataclass(slots=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


@dataclass(slots=True)
class LoginResult:
    user: User
    identity: Identity
    tokens: AuthTokens


@dataclass(slots=True)
class LoginChallenge:
    """A pending login that still needs a second factor. Carries no tokens — the
    client must complete ``/auth/login/totp`` with the signed challenge token."""

    challenge_token: str


def _audit_ctx(
    ctx: RequestContext,
    *,
    actor_id: uuid.UUID | None,
    session_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
) -> AuditContext:
    return AuditContext(
        actor_id=actor_id,
        actor_org_id=org_id,
        session_id=session_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


# --------------------------------------------------------------------------- #
# Registration + email verification                                           #
# --------------------------------------------------------------------------- #


async def _invalidate_outstanding(
    session: AsyncSession, *, user_id: uuid.UUID, purpose: str
) -> None:
    """Mark any unused, unexpired tokens of ``purpose`` as used (single-use reset
    / verification: only the most recently issued link stays valid)."""

    now = datetime.now(tz=UTC)
    stmt = select(EmailVerification).where(
        EmailVerification.user_id == user_id,
        EmailVerification.purpose == purpose,
        EmailVerification.used_at.is_(None),
    )
    for record in (await session.execute(stmt)).scalars().all():
        record.used_at = now


async def _issue_email_verification(
    session: AsyncSession,
    *,
    user: User,
    purpose: str,
    override_email: str | None = None,
) -> tuple[str, str]:
    """Issue a dual-mode verification: magic-link token + 6-digit OTP.

    Returns ``(raw_token, otp_code)`` — both are plaintext and returned once only.
    ``override_email`` is used for the student secondary email flow so the OTP
    is sent to a different address than ``user.email``.
    """
    settings = get_settings()
    raw = generate_token()
    otp = generate_otp()
    ttl_minutes = settings.otp_ttl_minutes  # OTP window (email copy + verify check)
    # The record lives for the full magic-link window (24h). The OTP is
    # additionally constrained to the shorter ``ttl_minutes`` window at
    # verification time (checked against ``created_at`` in ``verify_otp``), so a
    # magic link stays valid for the advertised 24h while the OTP still expires in
    # ``ttl_minutes``. Previously the whole record expired at OTP time (10 min),
    # silently breaking the 24h magic link (and disagreeing with the resend path,
    # which already used 24h).
    expires_at = datetime.now(tz=UTC) + timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS)

    record = EmailVerification(
        user_id=user.id,
        token_hash=hash_token(raw),
        otp_code_hash=hash_otp(otp),
        otp_attempts=0,
        purpose=purpose,
        expires_at=expires_at,
    )
    session.add(record)
    await session.flush()

    recipient_email = override_email or user.email
    if purpose == PURPOSE_STUDENT_EMAIL:
        template_key = "account.student_email_verification"
    else:
        template_key = "account.email_verification"

    await enqueue_notification(
        session,
        recipient_id=user.id,
        template_key=template_key,
        channel="email",
        locale=user.preferred_language,
        variables={
            "email": recipient_email,
            "name": _greeting_name(user),
            "otp_code": otp,
            "token": raw,
            "action_url": _frontend_link(
                path="auth/verify-email", locale=user.preferred_language, token=raw
            ),
            "ttl_minutes": str(ttl_minutes),
        },
        dedupe_key=f"verify:{user.id}:{purpose}:{raw[:12]}",
    )
    return raw, otp


async def verify_email_otp(
    session: AsyncSession,
    *,
    email: str,
    otp_code: str,
    purpose: str = PURPOSE_REGISTER,
    ctx: RequestContext,
) -> User:
    """Verify a 6-digit OTP for email verification.

    Increments ``otp_attempts`` on each wrong guess. After ``OTP_MAX_ATTEMPTS``
    wrong attempts the record is marked used (forcing a resend). Returns the
    verified user on success.
    """
    from app.modules.users.application import user_service as _us  # local import

    settings = get_settings()
    normalized = _us.normalize_email(email)
    user = await _us.get_by_email(session, normalized)
    if user is None:
        raise errors.InvalidTokenError("otp_invalid")

    now = datetime.now(tz=UTC)
    stmt = (
        select(EmailVerification)
        .where(
            EmailVerification.user_id == user.id,
            EmailVerification.purpose == purpose,
            EmailVerification.used_at.is_(None),
        )
        .order_by(EmailVerification.created_at.desc())
        .limit(1)
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None or ensure_aware(record.expires_at) <= now:
        raise errors.InvalidTokenError("otp_expired")
    # The record lives the full 24h magic-link window; the OTP is valid only within
    # the shorter OTP window, enforced here against ``created_at``.
    otp_deadline = ensure_aware(record.created_at) + timedelta(minutes=settings.otp_ttl_minutes)
    if otp_deadline <= now:
        raise errors.InvalidTokenError("otp_expired")

    if record.otp_attempts >= settings.otp_max_attempts:
        record.used_at = now  # force resend
        await session.flush()
        raise errors.InvalidTokenError("otp_max_attempts")

    if record.otp_code_hash != hash_otp(otp_code):
        record.otp_attempts += 1
        remaining = settings.otp_max_attempts - record.otp_attempts
        if record.otp_attempts >= settings.otp_max_attempts:
            record.used_at = now
        await session.flush()
        raise errors.InvalidTokenError(f"otp_wrong:{remaining}")

    # Correct OTP — mark as used and verify account email
    record.used_at = now
    if purpose == PURPOSE_REGISTER and not user.is_email_verified:
        user.email_verified_at = now
    await write_audit(
        session,
        action="auth.verify_email_otp",
        resource_type="user",
        resource_id=user.id,
        context=_audit_ctx(ctx, actor_id=user.id),
        after={"purpose": purpose},
    )
    await session.flush()
    return user


async def _resume_pending_registration(
    session: AsyncSession,
    *,
    user: User,
    password: str,
    full_name: str | None,
    ctx: RequestContext,
) -> dict[str, str]:
    """Resume an abandoned/pending (unverified, active) registration in place.

    The prior unverified password was never used to log in, so overwriting it
    with the newly-submitted password is safe. Re-issuing verification is
    subject to the resend cooldown/rate-limit (``scope="register_resume"``) —
    but unlike ``forgot_password``/``resend_verification``, hitting the throttle
    here does NOT surface a 429: it silently skips sending a new email so the
    response contract (202 ``verification_sent``) never changes for the caller,
    making retry-spam invisible without changing frontend behaviour.
    """

    throttled = False
    try:
        await check_and_touch_throttle(session, scope="register_resume", email=user.email)
    except errors.RateLimitedError:
        throttled = True

    if full_name:
        user.full_name = full_name
    user.password_hash = hash_password(password)
    await session.flush()

    if not throttled:
        await _invalidate_outstanding(session, user_id=user.id, purpose=PURPOSE_REGISTER)
        await _issue_email_verification(session, user=user, purpose=PURPOSE_REGISTER)

    await write_audit(
        session,
        action="auth.register_resumed",
        resource_type="user",
        resource_id=user.id,
        context=_audit_ctx(ctx, actor_id=user.id),
        after={"email": user.email},
    )
    await session.commit()
    return {"status": "verification_sent", "email": user.email}


async def register(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None,
    locale: str = "vi",
    ctx: RequestContext,
) -> dict[str, str]:
    """Register a local account.

    Registration is an explicit account-creation flow, so a VERIFIED duplicate
    email is rejected with a stable 409 that the UI can route to login or
    password reset. A duplicate that is still *unverified* (an abandoned/pending
    registration) is instead resumed in place: the password/full name are
    refreshed and a fresh verification email is (re-)issued, returning the same
    202 response shape so retrying registration needs no special-case handling
    on the frontend. Enumeration-sensitive flows such as forgot-password keep
    their own generic response shape separately.
    """

    normalized = user_service.normalize_email(email)
    existing = await user_service.get_by_email(session, normalized)

    if existing is not None and existing.is_email_verified:
        raise errors.EmailAlreadyRegisteredError()

    if existing is not None and not existing.is_email_verified:
        if not existing.is_active:
            # Disabled account: keep the conflict response, never silently resume.
            raise errors.EmailAlreadyRegisteredError()
        return await _resume_pending_registration(
            session,
            user=existing,
            password=password,
            full_name=full_name,
            ctx=ctx,
        )

    # Rate-limit brand-new account creation per email (anti-abuse: caps how often
    # a given address can be signed up + emailed a verification code). The
    # verified-duplicate (409) and disabled-account branches short-circuit above,
    # and the pending-resume path has its own ``register_resume`` throttle, so
    # this guards only genuine first-time registrations. Reuses the shared
    # enumeration-safe throttle infra (``scope="register"``) rather than adding a
    # new dependency; a 429 here surfaces the rate-limit state to the UI.
    await check_and_touch_throttle(session, scope="register", email=normalized)

    try:
        user = await create_user(
            session,
            email=normalized,
            password_hash=hash_password(password),
            full_name=full_name,
            preferred_language=locale,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise errors.EmailAlreadyRegisteredError() from exc

    await create_identity(session, user_id=user.id, persona=DEFAULT_PERSONA, is_primary=True)
    await set_preference(session, user_id=user.id, locale=locale, timezone=user.timezone)
    await session.flush()
    await _issue_email_verification(session, user=user, purpose="register")
    await write_audit(
        session,
        action="auth.register",
        resource_type="user",
        resource_id=user.id,
        context=_audit_ctx(ctx, actor_id=user.id),
        after={"email": normalized, "persona": DEFAULT_PERSONA},
    )
    await session.commit()
    return {"status": "verification_sent", "email": normalized}


async def verify_email(session: AsyncSession, *, token: str, ctx: RequestContext) -> User:
    stmt = select(EmailVerification).where(
        EmailVerification.token_hash == hash_token(token),
        EmailVerification.purpose == "register",
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    now = datetime.now(tz=UTC)
    if record is None or record.used_at is not None or ensure_aware(record.expires_at) <= now:
        raise errors.InvalidTokenError("verification_invalid")

    user = await user_service.get_by_id(session, record.user_id)
    if user is None:
        raise errors.InvalidTokenError("verification_invalid")

    if not user.is_email_verified:
        user.email_verified_at = now
    record.used_at = now
    await session.flush()
    await record_security_event(session, user_id=user.id, event_type=ev.EMAIL_VERIFIED, ctx=ctx)
    await write_audit(
        session,
        action="auth.email_verified",
        resource_type="user",
        resource_id=user.id,
        context=_audit_ctx(ctx, actor_id=user.id),
    )
    await dispatch_trigger(
        session,
        trigger_type="system.student_registered",
        payload={"user_id": str(user.id), "email": user.email},
        idempotency_key=f"student_registered:{user.id}",
    )
    await session.commit()
    return user


async def issue_activation_token(session: AsyncSession, *, user: User) -> str:
    """Mint a single-use activation (email-verification) token for a passwordless
    account (e.g. an approved partner admin). The caller owns the transaction and
    enqueues its own notification; this only persists the hashed token.
    """

    await _invalidate_outstanding(session, user_id=user.id, purpose=PURPOSE_REGISTER)
    raw = generate_token()
    session.add(
        EmailVerification(
            user_id=user.id,
            token_hash=hash_token(raw),
            purpose=PURPOSE_REGISTER,
            expires_at=datetime.now(tz=UTC) + timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS),
        )
    )
    await session.flush()
    return raw


async def activate_account(
    session: AsyncSession, *, token: str, password: str, ctx: RequestContext
) -> User:
    """Set the first password for a passwordless account AND verify its email.

    Used by partner-admin activation: the activation link was emailed to the
    contact, so completing it proves email ownership. Only valid while the account
    has no password set; otherwise the generic verify/reset flows apply.
    """

    now = datetime.now(tz=UTC)
    stmt = select(EmailVerification).where(
        EmailVerification.token_hash == hash_token(token),
        EmailVerification.purpose == PURPOSE_REGISTER,
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None or record.used_at is not None or ensure_aware(record.expires_at) <= now:
        raise errors.InvalidTokenError("activation_invalid")
    user = await user_service.get_by_id(session, record.user_id)
    if user is None or not user.is_active or user.password_hash is not None:
        raise errors.InvalidTokenError("activation_invalid")

    user.password_hash = hash_password(password)
    user.email_verified_at = now
    record.used_at = now
    await session.flush()
    await record_security_event(session, user_id=user.id, event_type=ev.EMAIL_VERIFIED, ctx=ctx)
    await write_audit(
        session,
        action="auth.account_activated",
        resource_type="user",
        resource_id=user.id,
        context=_audit_ctx(ctx, actor_id=user.id),
    )
    await session.commit()
    return user


async def resend_verification(
    session: AsyncSession, *, email: str, ctx: RequestContext
) -> dict[str, str]:
    """Re-send the email-verification link without enumeration.

    Always returns the same generic result. Only when an *unverified* account
    exists do we invalidate prior outstanding verification tokens and enqueue a
    fresh link — there is no behavioural difference (timing aside) for unknown or
    already-verified emails (``docs/EDGE_CASES_FAILURE_MODES.md``).
    """

    await check_and_touch_throttle(session, scope="resend_verification", email=email)

    normalized = user_service.normalize_email(email)
    user = await user_service.get_by_email(session, normalized)
    if user is not None and user.is_active and not user.is_email_verified:
        await _invalidate_outstanding(session, user_id=user.id, purpose=PURPOSE_REGISTER)
        await _issue_email_verification(session, user=user, purpose=PURPOSE_REGISTER)
        await write_audit(
            session,
            action="auth.verification_resent",
            resource_type="user",
            resource_id=user.id,
            context=_audit_ctx(ctx, actor_id=user.id),
        )
    await session.commit()
    return {"status": "verification_sent", "email": normalized}


# --------------------------------------------------------------------------- #
# Password reset (forgot / reset)                                             #
# --------------------------------------------------------------------------- #


async def forgot_password(
    session: AsyncSession, *, email: str, ctx: RequestContext
) -> dict[str, str]:
    """Begin a password reset without enumeration.

    Always returns the same generic result whether or not the email maps to an
    account. For a real active account we invalidate prior outstanding reset
    tokens, mint a single-use hashed token (short TTL), and enqueue a reset email
    with a FRONTEND link (``docs/SECURITY_PRIVACY.md``).
    """

    await check_and_touch_throttle(session, scope="forgot_password", email=email)

    normalized = user_service.normalize_email(email)
    user = await user_service.get_by_email(session, normalized)
    if user is not None and user.is_active:
        await _invalidate_outstanding(session, user_id=user.id, purpose=PURPOSE_PASSWORD_RESET)
        raw = generate_token()
        otp = generate_otp()
        ttl_minutes = get_settings().password_reset_ttl_minutes
        session.add(
            EmailVerification(
                user_id=user.id,
                token_hash=hash_token(raw),
                otp_code_hash=hash_otp(otp),
                otp_attempts=0,
                purpose=PURPOSE_PASSWORD_RESET,
                expires_at=datetime.now(tz=UTC) + timedelta(minutes=ttl_minutes),
            )
        )
        await session.flush()
        await enqueue_notification(
            session,
            recipient_id=user.id,
            template_key="account.password_reset",
            channel="email",
            locale=user.preferred_language,
            variables={
                "email": user.email,
                "name": _greeting_name(user),
                "token": raw,
                "otp_code": otp,
                "ttl_minutes": str(ttl_minutes),
                "action_url": _frontend_link(
                    path="auth/reset-password",
                    locale=user.preferred_language,
                    token=raw,
                ),
            },
            dedupe_key=f"pwd_reset:{user.id}:{raw[:12]}",
        )
        await write_audit(
            session,
            action="auth.password_reset_requested",
            resource_type="user",
            resource_id=user.id,
            context=_audit_ctx(ctx, actor_id=user.id),
        )
    await session.commit()
    return {"status": "reset_email_sent", "email": normalized}


async def _complete_password_reset(
    session: AsyncSession,
    *,
    user: User,
    record: EmailVerification,
    password: str,
    ctx: RequestContext,
) -> None:
    now = datetime.now(tz=UTC)
    user.password_hash = hash_password(password)
    record.used_at = now

    # Revoke every active session + refresh token: a reset implies the account may
    # have been compromised, so all existing logins are terminated.
    active = await _active_sessions(session, user.id)
    for sess in active:
        sess.revoked_at = now
        sess.revoked_reason = "password_reset"
        await _revoke_session_tokens(session, sess.id)

    await record_security_event(session, user_id=user.id, event_type=ev.PASSWORD_RESET, ctx=ctx)
    await enqueue_notification(
        session,
        recipient_id=user.id,
        template_key="account.password_changed",
        channel="email",
        locale=user.preferred_language,
        variables={"email": user.email, "name": _greeting_name(user)},
        dedupe_key=f"pwd_changed:{user.id}:{now.isoformat()}",
    )
    await write_audit(
        session,
        action="auth.password_reset",
        resource_type="user",
        resource_id=user.id,
        context=_audit_ctx(ctx, actor_id=user.id),
    )
    await session.commit()


async def reset_password(
    session: AsyncSession, *, token: str, password: str, ctx: RequestContext
) -> None:
    """Complete a password reset.

    Validates the single-use reset token (exists / unused / unexpired / correct
    purpose), sets the new Argon2 hash, marks the token used, revokes **all** of
    the user's sessions + refresh tokens, records a ``password_reset`` security
    event + audit, and enqueues a confirmation email.
    """

    now = datetime.now(tz=UTC)
    stmt = select(EmailVerification).where(
        EmailVerification.token_hash == hash_token(token),
        EmailVerification.purpose == PURPOSE_PASSWORD_RESET,
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise errors.InvalidTokenError("reset_invalid")
    if record.used_at is not None:
        raise errors.InvalidTokenError("reset_used")
    if ensure_aware(record.expires_at) <= now:
        raise errors.InvalidTokenError("reset_expired")

    user = await user_service.get_by_id(session, record.user_id)
    if user is None or not user.is_active:
        raise errors.InvalidTokenError("reset_invalid")

    await _complete_password_reset(session, user=user, record=record, password=password, ctx=ctx)


async def reset_password_otp(
    session: AsyncSession,
    *,
    email: str,
    otp_code: str,
    password: str,
    ctx: RequestContext,
) -> None:
    """Complete password reset using the 6-digit code from the reset email."""
    settings = get_settings()
    normalized = user_service.normalize_email(email)
    user = await user_service.get_by_email(session, normalized)
    if user is None or not user.is_active:
        raise errors.InvalidTokenError("reset_invalid")

    now = datetime.now(tz=UTC)
    stmt = (
        select(EmailVerification)
        .where(
            EmailVerification.user_id == user.id,
            EmailVerification.purpose == PURPOSE_PASSWORD_RESET,
            EmailVerification.used_at.is_(None),
        )
        .order_by(EmailVerification.created_at.desc())
        .limit(1)
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise errors.InvalidTokenError("reset_invalid")
    if ensure_aware(record.expires_at) <= now:
        raise errors.InvalidTokenError("reset_expired")

    if record.otp_attempts >= settings.otp_max_attempts:
        record.used_at = now
        await session.flush()
        raise errors.InvalidTokenError("otp_max_attempts")

    if record.otp_code_hash != hash_otp(otp_code):
        record.otp_attempts += 1
        remaining = settings.otp_max_attempts - record.otp_attempts
        if record.otp_attempts >= settings.otp_max_attempts:
            record.used_at = now
        await session.flush()
        raise errors.InvalidTokenError(f"otp_wrong:{remaining}")

    await _complete_password_reset(session, user=user, record=record, password=password, ctx=ctx)


# --------------------------------------------------------------------------- #
# Sessions + tokens                                                           #
# --------------------------------------------------------------------------- #


async def _active_sessions(session: AsyncSession, user_id: uuid.UUID) -> list[Session]:
    now = datetime.now(tz=UTC)
    stmt = (
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
        .order_by(Session.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def _revoke_session_tokens(session: AsyncSession, session_id: uuid.UUID) -> None:
    now = datetime.now(tz=UTC)
    stmt = select(RefreshToken).where(
        RefreshToken.session_id == session_id,
        RefreshToken.revoked_at.is_(None),
    )
    for token in (await session.execute(stmt)).scalars().all():
        token.revoked_at = now


async def _create_session_with_token(
    session: AsyncSession,
    *,
    user: User,
    identity: Identity,
    ctx: RequestContext,
) -> tuple[Session, str]:
    settings = get_settings()
    now = datetime.now(tz=UTC)

    # Enforce the device/session limit by retiring the oldest active session.
    active = await _active_sessions(session, user.id)
    while len(active) >= settings.session_device_limit:
        oldest = active.pop(0)
        oldest.revoked_at = now
        oldest.revoked_reason = "device_limit"
        await _revoke_session_tokens(session, oldest.id)

    expires_at = now + timedelta(days=settings.refresh_token_ttl_days)
    sess = Session(
        user_id=user.id,
        identity_id=identity.id,
        device_hint=device_hint(ctx.user_agent),
        ip_hash=hash_ip(ctx.ip),
        city_level_location=None,
        expires_at=expires_at,
        last_seen_at=now,
    )
    session.add(sess)
    await session.flush()

    raw_refresh = generate_token()
    session.add(
        RefreshToken(
            session_id=sess.id,
            token_hash=hash_token(raw_refresh),
            expires_at=expires_at,
        )
    )
    await session.flush()
    return sess, raw_refresh


def _issue_tokens(*, user: User, sess: Session, identity: Identity, raw_refresh: str) -> AuthTokens:
    access_token, _jti, _exp = jwt_infra.issue_access_token(
        user_id=user.id,
        session_id=sess.id,
        identity_id=identity.id,
        persona=identity.persona,
        org_id=identity.org_id,
    )
    return AuthTokens(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="Bearer",
        expires_in=get_settings().access_token_ttl_minutes * 60,
    )


# --------------------------------------------------------------------------- #
# Login + lockout                                                             #
# --------------------------------------------------------------------------- #


async def _recent_failed_logins(
    session: AsyncSession, user_id: uuid.UUID, *, since: datetime
) -> int:
    stmt = select(SecurityEvent).where(
        SecurityEvent.user_id == user_id,
        SecurityEvent.event_type == ev.LOGIN_FAILED,
        SecurityEvent.created_at >= since,
    )
    return len(list((await session.execute(stmt)).scalars().all()))


async def _confirmed_totp(session: AsyncSession, user_id: uuid.UUID) -> UserTotp | None:
    """Return the user's TOTP enrolment only if it has been confirmed."""

    totp = (
        await session.execute(select(UserTotp).where(UserTotp.user_id == user_id))
    ).scalar_one_or_none()
    return totp if totp is not None and totp.is_confirmed else None


async def _finalize_login(session: AsyncSession, *, user: User, ctx: RequestContext) -> LoginResult:
    """Mint a session + tokens for a fully-authenticated user (post password and,
    when enrolled, post second factor). Records the success event + audit."""

    identity = await user_service.primary_identity(session, user.id)
    if identity is None:
        identity = await create_identity(
            session, user_id=user.id, persona=DEFAULT_PERSONA, is_primary=True
        )

    sess, raw_refresh = await _create_session_with_token(
        session, user=user, identity=identity, ctx=ctx
    )
    tokens = _issue_tokens(user=user, sess=sess, identity=identity, raw_refresh=raw_refresh)

    user.last_login_at = datetime.now(tz=UTC)
    user.login_count += 1
    await record_security_event(
        session,
        user_id=user.id,
        event_type=ev.LOGIN_SUCCESS,
        ctx=ctx,
        session_id=sess.id,
    )
    await write_audit(
        session,
        action="auth.login",
        resource_type="session",
        resource_id=sess.id,
        context=_audit_ctx(ctx, actor_id=user.id, session_id=sess.id, org_id=identity.org_id),
    )
    await session.commit()
    return LoginResult(user=user, identity=identity, tokens=tokens)


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    ctx: RequestContext,
) -> LoginResult | LoginChallenge:
    """Authenticate email + password.

    Returns a :class:`LoginResult` (tokens) for accounts without confirmed TOTP.
    For accounts WITH confirmed TOTP, password success does NOT issue tokens:
    a :class:`LoginChallenge` is returned and the client must complete
    ``/auth/login/totp`` with the second factor.
    """

    settings = get_settings()
    user = await user_service.get_by_email(session, email)

    # Uniform invalid-credentials response to avoid account enumeration.
    if user is None or not user.is_active:
        raise errors.InvalidCredentialsError()

    window_start = datetime.now(tz=UTC) - timedelta(minutes=settings.account_lockout_minutes)
    failures = await _recent_failed_logins(session, user.id, since=window_start)
    if failures >= settings.account_lockout_failures:
        raise errors.AccountLockedError(retry_after_minutes=settings.account_lockout_minutes)

    if not verify_password(password, user.password_hash):
        await record_security_event(session, user_id=user.id, event_type=ev.LOGIN_FAILED, ctx=ctx)
        await write_audit(
            session,
            action="auth.login_failed",
            resource_type="user",
            resource_id=user.id,
            context=_audit_ctx(ctx, actor_id=user.id),
        )
        await session.commit()
        raise errors.InvalidCredentialsError()

    if not user.is_email_verified:
        raise errors.EmailNotVerifiedError()

    # Second factor: a confirmed TOTP enrolment gates token issuance.
    if await _confirmed_totp(session, user.id) is not None:
        challenge_token = jwt_infra.issue_totp_challenge_token(user_id=user.id)
        await record_security_event(session, user_id=user.id, event_type=ev.TOTP_CHALLENGE, ctx=ctx)
        await write_audit(
            session,
            action="auth.totp_challenge_issued",
            resource_type="user",
            resource_id=user.id,
            context=_audit_ctx(ctx, actor_id=user.id),
        )
        await session.commit()
        return LoginChallenge(challenge_token=challenge_token)

    return await _finalize_login(session, user=user, ctx=ctx)


async def login_totp(
    session: AsyncSession,
    *,
    challenge_token: str,
    code: str,
    ctx: RequestContext,
) -> LoginResult:
    """Complete a TOTP-gated login.

    Validates the short-lived challenge token, then the TOTP code (decrypting the
    stored secret). Wrong/expired token or code yields the uniform
    invalid-credentials error (no enumeration) and accrues toward the same lockout
    window as password failures.
    """

    settings = get_settings()
    try:
        user_id = jwt_infra.decode_totp_challenge_token(challenge_token)
    except jwt_infra.InvalidTokenError as exc:
        raise errors.InvalidCredentialsError() from exc

    user = await user_service.get_by_id(session, user_id)
    totp = await _confirmed_totp(session, user_id) if user is not None else None
    if user is None or not user.is_active or totp is None:
        raise errors.InvalidCredentialsError()

    window_start = datetime.now(tz=UTC) - timedelta(minutes=settings.account_lockout_minutes)
    failures = await _recent_failed_logins(session, user.id, since=window_start)
    if failures >= settings.account_lockout_failures:
        raise errors.AccountLockedError(retry_after_minutes=settings.account_lockout_minutes)

    secret, was_plaintext = decrypt_totp_secret(totp.secret)
    if was_plaintext:
        totp.secret = encrypt_totp_secret(secret)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        await record_security_event(session, user_id=user.id, event_type=ev.LOGIN_FAILED, ctx=ctx)
        await write_audit(
            session,
            action="auth.totp_login_failed",
            resource_type="user",
            resource_id=user.id,
            context=_audit_ctx(ctx, actor_id=user.id),
        )
        await session.commit()
        raise errors.InvalidCredentialsError()

    return await _finalize_login(session, user=user, ctx=ctx)


# --------------------------------------------------------------------------- #
# Refresh (rotation + reuse detection)                                        #
# --------------------------------------------------------------------------- #


async def refresh(session: AsyncSession, *, refresh_token: str, ctx: RequestContext) -> AuthTokens:
    now = datetime.now(tz=UTC)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    # Row-lock the token under Postgres to serialise concurrent rotation; SQLite
    # (unit tests) does not support SELECT ... FOR UPDATE.
    if get_settings().database_url.startswith("postgresql"):
        stmt = stmt.with_for_update()
    token = (await session.execute(stmt)).scalar_one_or_none()
    if token is None:
        raise errors.SessionExpiredError("invalid_refresh")

    sess = (
        await session.execute(select(Session).where(Session.id == token.session_id))
    ).scalar_one_or_none()
    if sess is None:
        raise errors.SessionExpiredError("invalid_refresh")

    # Reuse detection: the presented token was already rotated/revoked.
    if token.rotated_at is not None or token.revoked_at is not None:
        replacement = None
        if token.replaced_by_id is not None:
            replacement = (
                await session.execute(
                    select(RefreshToken).where(RefreshToken.id == token.replaced_by_id)
                )
            ).scalar_one_or_none()
        # Benign concurrent double-submit of the immediately-previous token:
        # its replacement is still the current active token -> ask client to retry.
        if replacement is not None and replacement.is_active(now=now) and sess.revoked_at is None:
            raise errors.SessionExpiredError("concurrent_refresh")

        # Genuine reuse of a stale token -> revoke the whole session.
        if sess.revoked_at is None:
            sess.revoked_at = now
            sess.revoked_reason = "token_reuse"
        await _revoke_session_tokens(session, sess.id)
        await record_security_event(
            session,
            user_id=sess.user_id,
            event_type=ev.TOKEN_REUSE_DETECTED,
            ctx=ctx,
            session_id=sess.id,
        )
        await write_audit(
            session,
            action="auth.refresh_reuse_detected",
            resource_type="session",
            resource_id=sess.id,
            context=_audit_ctx(ctx, actor_id=sess.user_id, session_id=sess.id),
        )
        await session.commit()
        raise errors.SessionExpiredError("token_reuse")

    if not sess.is_active(now=now) or ensure_aware(token.expires_at) <= now:
        raise errors.SessionExpiredError("session_expired")

    user = await user_service.get_by_id(session, sess.user_id)
    identity = (
        await session.execute(select(Identity).where(Identity.id == sess.identity_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active or identity is None:
        raise errors.SessionExpiredError("session_expired")

    # Rotate: retire the presented token, mint a replacement.
    raw_refresh = generate_token()
    new_token = RefreshToken(
        session_id=sess.id,
        token_hash=hash_token(raw_refresh),
        expires_at=sess.expires_at,
    )
    session.add(new_token)
    await session.flush()
    token.rotated_at = now
    token.replaced_by_id = new_token.id
    sess.last_seen_at = now

    tokens = _issue_tokens(user=user, sess=sess, identity=identity, raw_refresh=raw_refresh)
    await write_audit(
        session,
        action="auth.refresh",
        resource_type="session",
        resource_id=sess.id,
        context=_audit_ctx(ctx, actor_id=user.id, session_id=sess.id),
    )
    await session.commit()
    return tokens


# --------------------------------------------------------------------------- #
# Logout                                                                       #
# --------------------------------------------------------------------------- #


async def logout(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    jti: uuid.UUID,
    access_expires_at: datetime,
    ctx: RequestContext,
) -> None:
    sess = (
        await session.execute(select(Session).where(Session.id == session_id))
    ).scalar_one_or_none()
    now = datetime.now(tz=UTC)
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = now
        sess.revoked_reason = "logout"
        await _revoke_session_tokens(session, sess.id)
        await record_security_event(
            session,
            user_id=sess.user_id,
            event_type=ev.LOGOUT,
            ctx=ctx,
            session_id=sess.id,
        )
        await write_audit(
            session,
            action="auth.logout",
            resource_type="session",
            resource_id=sess.id,
            context=_audit_ctx(ctx, actor_id=sess.user_id, session_id=sess.id),
        )
        await session.commit()
    await token_revocation.revoke_jti(jti, expires_at=access_expires_at)


# --------------------------------------------------------------------------- #
# Multi-identity                                                               #
# --------------------------------------------------------------------------- #


async def switch_identity(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    identity_id: uuid.UUID,
    ctx: RequestContext,
) -> AuthTokens:
    assert principal.user_id is not None
    identity = await user_service.get_identity(
        session, identity_id=identity_id, user_id=principal.user_id
    )
    if identity is None:
        raise errors.InvalidTokenError("identity_not_found")

    sess = (
        await session.execute(select(Session).where(Session.id == session_id))
    ).scalar_one_or_none()
    if sess is None or not sess.is_active(now=datetime.now(tz=UTC)):
        raise errors.SessionExpiredError("session_expired")

    user = await user_service.get_by_id(session, principal.user_id)
    assert user is not None
    sess.identity_id = identity.id

    # Rotate the session's refresh token so the browser receives a fresh httpOnly
    # cookie bound to the new identity; the prior token(s) for this session are
    # retired to preserve the single-active-token rotation invariant.
    now = datetime.now(tz=UTC)
    await _revoke_session_tokens(session, sess.id)
    raw_refresh = generate_token()
    session.add(
        RefreshToken(
            session_id=sess.id,
            token_hash=hash_token(raw_refresh),
            expires_at=sess.expires_at,
        )
    )
    sess.last_seen_at = now
    await session.flush()

    tokens = _issue_tokens(user=user, sess=sess, identity=identity, raw_refresh=raw_refresh)
    await write_audit(
        session,
        action="auth.identity_switched",
        resource_type="identity",
        resource_id=identity.id,
        context=_audit_ctx(ctx, actor_id=user.id, session_id=sess.id),
        after={"persona": identity.persona},
    )
    await session.commit()
    return tokens
