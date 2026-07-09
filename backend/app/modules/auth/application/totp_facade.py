"""TOTP enrolment facade for `account`'s two-factor settings UI.

Wraps ``UserTotp`` rows and ``auth.infrastructure.totp_crypto`` so
``account_service`` no longer imports ``auth.domain.models``/
``auth.infrastructure`` directly (`docs/ARCHITECTURE.md` Sec 8). Secret
generation, at-rest encryption, legacy-plaintext re-encryption-on-read, and the
enrol/confirm/disable state machine are unchanged from the previous inline
code — structural move only (`docs/SECURITY_PRIVACY.md`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain.models import UserTotp
from app.modules.auth.infrastructure.totp_crypto import (
    decrypt_totp_secret,
    encrypt_totp_secret,
)


async def _get_totp(session: AsyncSession, user_id: uuid.UUID) -> UserTotp | None:
    return (
        await session.execute(select(UserTotp).where(UserTotp.user_id == user_id))
    ).scalar_one_or_none()


def _decrypt_secret(totp: UserTotp) -> str:
    """Return the plaintext base32 secret, re-encrypting in place if the stored
    value is a legacy plaintext row (dev-migration tolerance)."""

    secret, was_plaintext = decrypt_totp_secret(totp.secret)
    if was_plaintext:
        totp.secret = encrypt_totp_secret(secret)
    return secret


@dataclass(frozen=True)
class TotpSetup:
    secret: str
    otpauth_uri: str


async def begin_setup(
    session: AsyncSession, *, user_id: uuid.UUID, account_email: str, issuer_name: str
) -> TotpSetup:
    secret = pyotp.random_base32()
    ciphertext = encrypt_totp_secret(secret)
    existing = await _get_totp(session, user_id)
    if existing is None:
        session.add(UserTotp(user_id=user_id, secret=ciphertext))
    else:
        existing.secret = ciphertext
        existing.confirmed_at = None
    await session.flush()

    otpauth_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=account_email, issuer_name=issuer_name
    )
    return TotpSetup(secret=secret, otpauth_uri=otpauth_uri)


@dataclass(frozen=True)
class TotpOutcome:
    ok: bool
    reason: str | None = None


async def confirm_setup(session: AsyncSession, *, user_id: uuid.UUID, code: str) -> TotpOutcome:
    """Verify ``code`` against the pending secret and mark it confirmed.

    ``reason`` mirrors the previous inline error details exactly
    (``totp_not_initialised`` / ``totp_invalid_code``) so the caller can raise
    the same user-facing validation error unchanged.
    """

    totp = await _get_totp(session, user_id)
    if totp is None:
        return TotpOutcome(ok=False, reason="totp_not_initialised")
    if not pyotp.TOTP(_decrypt_secret(totp)).verify(code, valid_window=1):
        return TotpOutcome(ok=False, reason="totp_invalid_code")

    totp.confirmed_at = datetime.now(tz=UTC)
    return TotpOutcome(ok=True)


async def disable(session: AsyncSession, *, user_id: uuid.UUID, code: str) -> TotpOutcome:
    """Verify ``code`` and delete the confirmed enrolment.

    ``reason`` mirrors the previous inline error details exactly
    (``totp_not_enabled`` / ``totp_invalid_code``).
    """

    totp = await _get_totp(session, user_id)
    if totp is None or not totp.is_confirmed:
        return TotpOutcome(ok=False, reason="totp_not_enabled")
    if not pyotp.TOTP(_decrypt_secret(totp)).verify(code, valid_window=1):
        return TotpOutcome(ok=False, reason="totp_invalid_code")

    await session.delete(totp)
    return TotpOutcome(ok=True)
