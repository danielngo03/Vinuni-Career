"""Auth-owned session read/revoke facade for `account`'s device-list settings UI.

`account` needs session rows to render "your devices" and to support remote
logout, but session semantics (active-window definition, revoke reason,
refresh-token teardown) belong to `auth`. This is the seam `account` calls
instead of importing `auth.domain.models.Session` directly
(`docs/ARCHITECTURE.md` Sec 8). The query shape, active-window filter, and
revoke side effects (retiring the session's refresh tokens via
``auth_service._revoke_session_tokens``) are unchanged from the previous
inline code in ``account_service.py`` — this is a structural move only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.auth_service import _revoke_session_tokens
from app.modules.auth.domain.models import Session


@dataclass(frozen=True)
class SessionInfo:
    """Privacy-safe session shape: device hint + city-level location only,
    never raw IP, raw user-agent, or refresh tokens."""

    id: uuid.UUID
    device_hint: str
    city_level_location: str | None
    created_at: datetime | None
    last_seen_at: datetime | None


def _to_info(row: Session) -> SessionInfo:
    return SessionInfo(
        id=row.id,
        device_hint=row.device_hint or "unknown",
        city_level_location=row.city_level_location,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
    )


async def list_active_sessions(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[SessionInfo]:
    now = datetime.now(tz=UTC)
    stmt = (
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.expires_at > now,
        )
        .order_by(Session.last_seen_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_info(row) for row in rows]


@dataclass(frozen=True)
class SessionRevocation:
    session_id: uuid.UUID
    newly_revoked: bool


async def revoke_session(
    session: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID
) -> SessionRevocation | None:
    """Revoke ``session_id`` if it belongs to ``user_id``.

    Returns ``None`` if no such session exists for this user (caller raises
    not-found). ``newly_revoked`` is ``False`` when the session was already
    revoked — the caller only records a security event/audit on a fresh revoke,
    matching the previous inline behaviour.
    """

    target = (
        await session.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user_id)
        )
    ).scalar_one_or_none()
    if target is None:
        return None
    newly_revoked = target.revoked_at is None
    if newly_revoked:
        target.revoked_at = datetime.now(tz=UTC)
        target.revoked_reason = "remote_logout"
        await _revoke_session_tokens(session, target.id)
    return SessionRevocation(session_id=target.id, newly_revoked=newly_revoked)
