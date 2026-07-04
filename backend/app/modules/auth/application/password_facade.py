"""Password verify/hash + related-session-revoke facade for `account`'s
change-password use case.

Wraps ``auth.infrastructure.passwords`` (hash/verify) and the ``Session`` rows
that must be revoked on a password change, so ``account_service`` no longer
imports ``auth.infrastructure``/``auth.domain.models`` directly
(`docs/ARCHITECTURE.md` Sec 8). Hashing algorithm and revoke semantics
(revoke every OTHER active session, keep the current one signed in) are
unchanged from the previous inline code — structural move only
(`docs/SECURITY_PRIVACY.md`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.auth_service import _revoke_session_tokens
from app.modules.auth.domain.models import Session
from app.modules.auth.infrastructure.passwords import hash_password, verify_password


def verify_password_matches(plain_password: str, password_hash: str | None) -> bool:
    return verify_password(plain_password, password_hash)


def hash_new_password(plain_password: str) -> str:
    return hash_password(plain_password)


async def revoke_other_sessions(
    session: AsyncSession, *, user_id: uuid.UUID, keep_session_id: uuid.UUID
) -> None:
    """Revoke every OTHER active session for ``user_id``; keep
    ``keep_session_id`` signed in (password-change semantics)."""

    now = datetime.now(tz=UTC)
    others = (
        await session.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.id != keep_session_id,
                Session.revoked_at.is_(None),
            )
        )
    ).scalars().all()
    for other_session in others:
        other_session.revoked_at = now
        other_session.revoked_reason = "password_change"
        await _revoke_session_tokens(session, other_session.id)
