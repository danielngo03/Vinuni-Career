"""The discovery analytics sink: ``record_event`` + the ``ingest`` orchestrator.

Ad-funded surfaces and recommendation rails call ``POST /discovery/events`` which
lands here. The event row has no free-form PII fields by construction; the service
additionally:

- validates ``event_type`` / ``target_type`` / ``source_surface`` against the
  domain vocabularies (keeping organic / recommended / sponsored / curated
  inventory tracked separately);
- retains ``placement_id`` ONLY for sponsored surfaces (organic ≠ sponsored);
- derives ``scope`` (anonymous|session|user) from the principal + discovery
  session — it is NEVER taken from the client;
- is idempotent on ``idempotency_key`` (same key → exactly one row).

``record_event`` is flush-only; ``ingest`` owns the single commit so the session
upsert, the optional signal merge, and the event insert are one transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.application import ingestion_service as analytics
from app.modules.auth.application.context import RequestContext
from app.modules.discovery.application import session_service
from app.modules.discovery.application.errors import InvalidDiscoveryEventError
from app.modules.discovery.domain import allowlist
from app.modules.discovery.domain.models import DiscoveryEvent, DiscoverySession
from app.shared.permissions import Principal


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _validate(event_type: str, source_surface: str, target_type: str) -> None:
    if event_type not in allowlist.EVENT_TYPES:
        raise InvalidDiscoveryEventError(field="event_type")
    if source_surface not in allowlist.SOURCE_SURFACES:
        raise InvalidDiscoveryEventError(field="source_surface")
    if target_type not in allowlist.TARGET_TYPES:
        raise InvalidDiscoveryEventError(field="target_type")


def _resolve_scope(
    principal: Principal | None, discovery_session: DiscoverySession | None
) -> tuple[str, uuid.UUID | None, uuid.UUID | None]:
    """Return ``(scope, session_id, user_id)`` — never trusts the client."""

    if principal is not None and principal.is_authenticated:
        sid = (
            discovery_session.id
            if discovery_session is not None and not discovery_session.opt_out
            else None
        )
        return "user", sid, principal.user_id
    if discovery_session is not None and not discovery_session.opt_out:
        return "session", discovery_session.id, None
    return "anonymous", None, None


async def record_event(
    session: AsyncSession,
    *,
    principal: Principal | None,
    discovery_session: DiscoverySession | None,
    event_type: str,
    source_surface: str,
    target_type: str,
    target_id: uuid.UUID,
    idempotency_key: str,
    placement_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> DiscoveryEvent:
    """Record one analytics event idempotently. Flush-only (caller commits).

    A repeated ``idempotency_key`` returns the already-stored row without inserting
    a second one. ``placement_id`` is kept only on sponsored surfaces; ``scope`` is
    derived server-side.
    """

    now = now or _now()
    _validate(event_type, source_surface, target_type)

    existing = (
        await session.execute(
            select(DiscoveryEvent).where(
                DiscoveryEvent.idempotency_key == idempotency_key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    # Sponsored placement reference is meaningful ONLY on sponsored inventory.
    effective_placement = (
        placement_id
        if placement_id is not None
        and allowlist.is_sponsored_surface(source_surface, target_type)
        else None
    )
    scope, session_id, user_id = _resolve_scope(principal, discovery_session)

    event = DiscoveryEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        source_surface=source_surface,
        target_type=target_type,
        target_id=target_id,
        placement_id=effective_placement,
        scope=scope,
        session_id=session_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        created_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError:
        # Concurrent insert with the same key — return the winner's row.
        return (
            await session.execute(
                select(DiscoveryEvent).where(
                    DiscoveryEvent.idempotency_key == idempotency_key
                )
            )
        ).scalar_one()

    # Ad-attribution mirror into the platform-wide analytics ledger (B-548):
    # this row already IS the ad-attribution record for the ranking/ads surface;
    # analytics_events additionally carries it under the shared cross-module
    # taxonomy (ad.impression/ad.click) so reporting never has to special-case
    # discovery_events. Only for the two attribution event types, only when a
    # sponsored placement is actually attached.
    if effective_placement is not None and event_type in ("impression", "click"):
        await analytics.record_event_safe(
            session,
            event_type=f"ad.{event_type}",
            aggregate_type="ad_placement",
            aggregate_id=effective_placement,
            actor_id=user_id,
            actor_type="student" if user_id else "guest",
            session_id=session_id,
            properties={"source_surface": source_surface, "target_type": target_type},
        )
    return event


async def ingest(
    session: AsyncSession,
    *,
    principal: Principal | None,
    cookie_id: str | None,
    payload: dict,
    ctx: RequestContext | None = None,
    now: datetime | None = None,
) -> tuple[DiscoverySession, dict]:
    """Orchestrate get-or-create session → optional signal merge → record event.

    Returns ``(discovery_session, {"recorded": True})``. Commits once. The router
    uses the returned session id to set/refresh the first-party cookie. The result
    carries NO internal data — only ``{"recorded": True}``.
    """

    now = now or _now()
    # Validate BEFORE creating a session so a bad event never spawns a row.
    _validate(
        payload["event_type"], payload["source_surface"], payload["target_type"]
    )

    discovery_session = await session_service.get_or_create(
        session,
        cookie_id=cookie_id,
        locale=payload.get("locale"),
        principal=principal,
        now=now,
    )

    signal_tags = payload.get("signal_tags")
    if isinstance(signal_tags, dict) and signal_tags:
        await session_service.record_signal(
            session, discovery_session, tags=signal_tags
        )

    await record_event(
        session,
        principal=principal,
        discovery_session=discovery_session,
        event_type=payload["event_type"],
        source_surface=payload["source_surface"],
        target_type=payload["target_type"],
        target_id=payload["target_id"],
        idempotency_key=payload["idempotency_key"],
        placement_id=payload.get("placement_id"),
        now=now,
    )
    await session.commit()
    return discovery_session, {"recorded": True}
