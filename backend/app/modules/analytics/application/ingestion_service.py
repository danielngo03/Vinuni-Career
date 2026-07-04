"""The single write path for ``analytics_events`` (B-548).

Any module may call :func:`record_event` to append a product-analytics fact.
This is flush-only (mirrors ``discovery.event_service.record_event``) — the
caller's own transaction owns the commit, so an analytics write never becomes
its own point of failure independent of the business write it describes.

An unknown ``event_type``/``aggregate_type``/``actor_type`` is a programmer
error, not a runtime one: it raises immediately in dev/test (loud, cheap to
fix) — this module is called only from trusted server-side code, never from a
public request body, so there is no untrusted-input path to harden against.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.domain import taxonomy
from app.modules.analytics.domain.models import AnalyticsEvent

logger = logging.getLogger(__name__)


class InvalidAnalyticsEventError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    actor_type: str | None = None,
    session_id: uuid.UUID | None = None,
    properties: dict | None = None,
    occurred_at: datetime | None = None,
) -> AnalyticsEvent:
    if event_type not in taxonomy.EVENT_TYPES:
        raise InvalidAnalyticsEventError(f"unknown event_type: {event_type!r}")
    if aggregate_type not in taxonomy.AGGREGATE_TYPES:
        raise InvalidAnalyticsEventError(f"unknown aggregate_type: {aggregate_type!r}")
    if actor_type is not None and actor_type not in taxonomy.ACTOR_TYPES:
        raise InvalidAnalyticsEventError(f"unknown actor_type: {actor_type!r}")

    event = AnalyticsEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_id=actor_id,
        actor_type=actor_type,
        session_id=session_id,
        properties=taxonomy.sanitize_properties(properties),
        occurred_at=occurred_at or _now(),
    )
    session.add(event)
    await session.flush()
    return event


async def record_event_safe(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    actor_type: str | None = None,
    session_id: uuid.UUID | None = None,
    properties: dict | None = None,
) -> None:
    """Best-effort variant for call sites where analytics must never break the
    primary write (e.g. a notification-dispatch sweep). Logs and swallows.
    """

    try:
        await record_event(
            session,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            actor_id=actor_id,
            actor_type=actor_type,
            session_id=session_id,
            properties=properties,
        )
    except Exception:  # noqa: BLE001 — analytics is best-effort at these sites
        logger.warning("analytics.record_event_failed", extra={"event_type": event_type})
