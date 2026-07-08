"""Process-wide realtime singletons + the publish helper the services call.

Kept tiny and dependency-light so it can be imported from ``message_service`` without a
cycle. Channels: ``user:{id}`` (a participant's personal socket) and ``org:{id}`` (the
shared org inbox). Events are lightweight signals only (``{type, thread_id}``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.messaging.application.realtime.bus import build_bus
from app.modules.messaging.application.realtime.connection_manager import (
    ConnectionManager,
)
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import (
    MessageThreadParticipant,
    MessageThreadParty,
)

connection_manager = ConnectionManager()
_bus = build_bus(get_settings().messaging_redis_url)
_bus.set_dispatcher(connection_manager.dispatch_local)


def user_channel(user_id: uuid.UUID) -> str:
    return f"user:{user_id}"


def org_channel(org_id: uuid.UUID) -> str:
    return f"org:{org_id}"


async def startup_bus() -> None:
    await _bus.start()


async def shutdown_bus() -> None:
    await _bus.stop()


async def channels_for_thread(
    session: AsyncSession,
    *,
    thread_id: uuid.UUID,
    exclude_user_id: uuid.UUID | None = None,
) -> list[str]:
    """Every channel that should receive a signal about ``thread_id``.

    Participant users (student threads, initiating staff) + org parties (shared inbox).
    """

    channels: set[str] = set()
    participants = (
        (
            await session.execute(
                select(MessageThreadParticipant.user_id).where(
                    MessageThreadParticipant.thread_id == thread_id,
                    MessageThreadParticipant.removed_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for uid in participants:
        if exclude_user_id is not None and uid == exclude_user_id:
            continue
        channels.add(user_channel(uid))
    org_ids = (
        (
            await session.execute(
                select(MessageThreadParty.org_id).where(
                    MessageThreadParty.thread_id == thread_id,
                    MessageThreadParty.party_kind == rules.PARTY_ORG,
                    MessageThreadParty.org_id.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for oid in org_ids:
        channels.add(org_channel(oid))
    return list(channels)


async def publish_signal(channels: list[str], event: dict) -> None:
    """Publish a lightweight event to each channel (best-effort; never raises)."""

    if not get_settings().messaging_realtime_enabled:
        return
    for ch in channels:
        try:
            await _bus.publish(ch, event)
        except Exception:  # noqa: BLE001 - realtime is best-effort, never breaks a write
            continue
