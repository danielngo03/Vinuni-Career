"""Cooldown + rolling-hour rate limiting for enumeration-sensitive auth flows.

Keyed by ``(scope, sha256(normalized_email))`` — never by user id — so the
same throttle behaviour applies identically whether or not the email maps to
a real account (``docs/SECURITY_PRIVACY.md``, ``docs/EDGE_CASES_FAILURE_MODES.md``).
Callers must invoke :func:`check_and_touch_throttle` BEFORE any account lookup
so anti-enumeration holds by construction.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application import errors
from app.modules.auth.domain.models import AuthThrottle, ensure_aware
from app.modules.users.application.user_service import normalize_email

_ROLLING_WINDOW = timedelta(hours=1)


def _key_hash(email: str) -> str:
    normalized = normalize_email(email)
    return hashlib.sha256(normalized.encode()).hexdigest()


async def check_and_touch_throttle(session: AsyncSession, *, scope: str, email: str) -> None:
    """Raise :class:`errors.RateLimitedError` if ``scope``+``email`` is
    cooling down or has exceeded the rolling-hour cap; otherwise record this
    attempt and return normally.

    Must run as the FIRST thing in the caller (before any DB lookup keyed by
    the email/user) so the 429 fires identically for known and unknown emails.
    """

    settings = get_settings()
    now = datetime.now(tz=UTC)
    key_hash = _key_hash(email)

    stmt = select(AuthThrottle).where(
        AuthThrottle.scope == scope, AuthThrottle.key_hash == key_hash
    )
    row = (await session.execute(stmt)).scalar_one_or_none()

    if row is None:
        session.add(
            AuthThrottle(
                scope=scope,
                key_hash=key_hash,
                window_started_at=now,
                attempt_count=1,
                last_attempt_at=now,
            )
        )
        await session.flush()
        return

    last_attempt = ensure_aware(row.last_attempt_at)
    elapsed = (now - last_attempt).total_seconds()
    if elapsed < settings.auth_resend_cooldown_seconds:
        retry_after = int(settings.auth_resend_cooldown_seconds - elapsed) or 1
        raise errors.RateLimitedError(reason="resend_cooldown", retry_after_seconds=retry_after)

    window_started = ensure_aware(row.window_started_at)
    if now - window_started > _ROLLING_WINDOW:
        row.window_started_at = now
        row.attempt_count = 0
        window_started = now

    if row.attempt_count >= settings.auth_email_request_rate_limit_per_hour:
        retry_after = int((window_started + _ROLLING_WINDOW - now).total_seconds())
        raise errors.RateLimitedError(
            reason="rate_limited", retry_after_seconds=max(retry_after, 1)
        )

    row.attempt_count += 1
    row.last_attempt_at = now
    await session.flush()
