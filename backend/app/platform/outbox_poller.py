"""
Outbox poller — background asyncio task.

Polls ``outbox_events`` for unpublished rows and dispatches each event
to the in-process event bus. In production this would be replaced by
a Temporal workflow worker that picks up from the same table.

Guarantees:
- At-least-once delivery (retry_count capped at 5 before marking failed).
- Rows are marked published=True atomically after successful dispatch.
- Failures are logged and retried up to 5 times before being abandoned.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.platform.database.models.outbox import OutboxEvent
from app.platform.database.session import SessionLocal
from app.shared.events import DomainEvent, get_event_bus

logger = logging.getLogger(__name__)

MAX_RETRY = 5
POLL_INTERVAL_SECONDS = 2
BATCH_SIZE = 50


async def _dispatch_one(db: Session, row: OutboxEvent) -> None:
    try:
        payload = json.loads(row.payload)
        metadata = json.loads(row.metadata_json or "{}")
        event = DomainEvent(
            event_type=row.event_type,
            aggregate_id=row.aggregate_id,
            aggregate_type=row.aggregate_type,
            occurred_at=row.occurred_at,
            metadata={**metadata, **payload},
        )
        await get_event_bus().publish(event)
        row.published_at = datetime.now(UTC)
        db.commit()
        logger.debug("outbox dispatched: %s / %s", row.event_type, row.aggregate_id)
    except Exception as exc:  # noqa: BLE001
        row.retry_count += 1
        row.last_error = str(exc)[:500]
        db.commit()
        logger.warning(
            "outbox dispatch failed (retry %d): %s — %s",
            row.retry_count,
            row.event_type,
            exc,
        )


async def outbox_poller_loop() -> None:
    """Run forever; meant to be started as an asyncio background task."""
    logger.info("Outbox poller started (poll_interval=%ds)", POLL_INTERVAL_SECONDS)
    while True:
        try:
            with SessionLocal() as db:
                rows = db.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.published_at.is_(None),
                        OutboxEvent.retry_count < MAX_RETRY,
                    )
                    .order_by(OutboxEvent.occurred_at.asc())
                    .limit(BATCH_SIZE)
                ).all()
                for row in rows:
                    await _dispatch_one(db, row)
        except Exception as exc:  # noqa: BLE001
            logger.error("outbox poller error: %s", exc)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
