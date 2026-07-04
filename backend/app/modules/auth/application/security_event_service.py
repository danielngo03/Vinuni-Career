"""Recording and listing user-facing security events.

Security events store privacy-safe metadata only: a coarse ``device_hint`` and an
``ip_hash`` — never the raw IP or raw user-agent (``docs/SECURITY_PRIVACY.md``).
``city_level_location`` is left ``NULL`` while ``GEOIP_ENABLED=false`` locally.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.auth.domain.models import SecurityEvent
from app.shared.hashing import device_hint, hash_ip


async def record_security_event(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    event_type: str,
    ctx: RequestContext | None = None,
    session_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> SecurityEvent:
    ctx = ctx or RequestContext()
    event = SecurityEvent(
        user_id=user_id,
        event_type=event_type,
        session_id=session_id,
        device_hint=device_hint(ctx.user_agent),
        ip_hash=hash_ip(ctx.ip),
        city_level_location=None,  # GEOIP disabled locally
        event_metadata=metadata or {},
    )
    session.add(event)
    await session.flush()
    return event


async def list_security_events(
    session: AsyncSession, *, user_id: uuid.UUID, limit: int = 20
) -> list[SecurityEvent]:
    stmt = (
        select(SecurityEvent)
        .where(SecurityEvent.user_id == user_id)
        .order_by(SecurityEvent.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
