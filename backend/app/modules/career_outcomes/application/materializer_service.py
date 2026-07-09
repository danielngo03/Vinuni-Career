"""Career-outcomes materializer — the deferred ``offer.accepted`` consumer.

ADR-0007 left the career-outcome seam as a NON-blocking outbox event with no
consumer. This module is that consumer and the **first drainer of the generic
``outbox_events`` table** (the notification outbox has its own drainer in
``notifications.dispatch_service``).

:func:`materialize_career_outcomes` claims unprocessed ``offer.accepted`` events
(``published_at IS NULL``), creates one ``career_outcome_record`` per event at
``trust_level=4`` / ``source='system_estimate'``, and marks the event processed by
stamping ``published_at``. It is idempotent two ways:

1. The claim filters on ``published_at IS NULL`` — a processed event is never
   re-seen on a later sweep.
2. ``career_outcome_records.source_event_id`` is UNIQUE and the materializer
   skips an event whose record already exists — so even an at-least-once redelivery
   (e.g. a crash between insert and the ``published_at`` commit) cannot duplicate.

It consumes ONLY the event payload — no recruitment ORM import, no student PII, no
salary (the payload carries none). On PostgreSQL the claim uses ``FOR UPDATE SKIP
LOCKED`` so concurrent drainers never double-process; the clause is dialect-guarded
and inert on SQLite.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.career_outcomes.domain.models import (
    OUTCOME_HIRED,
    SOURCE_SYSTEM_ESTIMATE,
    TRUST_LEVEL_ESTIMATED,
    CareerOutcomeRecord,
)
from app.shared.models import OutboxEvent

logger = logging.getLogger(__name__)

EVENT_TYPE = "offer.accepted"


def _parse_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _parse_date(value: object) -> datetime | None:
    # start_date is serialized as an ISO date string in the payload (or null).
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def materialize_career_outcomes(
    session: AsyncSession,
    now: datetime | None = None,
    *,
    limit: int = 100,
) -> dict[str, int]:
    """Drain unprocessed ``offer.accepted`` events into career-outcome records.

    Returns a per-disposition count: ``materialized`` (new record created),
    ``deduped`` (record already existed — skipped but event still marked), and
    ``invalid`` (payload missing required ids — marked processed, not retried).
    """

    now = now or datetime.now(tz=UTC)
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.event_type == EVENT_TYPE,
            OutboxEvent.published_at.is_(None),
        )
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    # Prod-readiness for the multi-worker path; inert on the SQLite unit DB.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    events = list((await session.execute(stmt)).scalars().all())

    counts = {"materialized": 0, "deduped": 0, "invalid": 0}
    for event in events:
        payload = event.payload or {}
        application_id = _parse_uuid(payload.get("application_id"))
        offer_id = _parse_uuid(payload.get("offer_id"))
        org_id = _parse_uuid(payload.get("org_id"))
        employer_org_id = _parse_uuid(payload.get("employer_org_id")) or org_id

        if application_id is None or offer_id is None or org_id is None:
            # Structurally unusable event — mark processed so it never blocks the
            # sweep, and log PII-safe (ids only) for follow-up.
            event.published_at = now
            counts["invalid"] += 1
            logger.warning("career_outcomes.invalid_event", extra={"event_id": str(event.id)})
            continue

        existing = (
            await session.execute(
                select(CareerOutcomeRecord.id).where(
                    CareerOutcomeRecord.source_event_id == event.id
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            position_title = payload.get("position_title")
            start = _parse_date(payload.get("start_date"))
            session.add(
                CareerOutcomeRecord(
                    application_id=application_id,
                    offer_id=offer_id,
                    org_id=org_id,
                    employer_org_id=employer_org_id,
                    position_title=(position_title if isinstance(position_title, str) else None),
                    start_date=start.date() if start is not None else None,
                    outcome_type=OUTCOME_HIRED,
                    trust_level=TRUST_LEVEL_ESTIMATED,
                    source=SOURCE_SYSTEM_ESTIMATE,
                    source_event_id=event.id,
                    recorded_at=now,
                )
            )
            counts["materialized"] += 1
        else:
            counts["deduped"] += 1

        event.published_at = now

    await session.flush()
    return counts
