"""Analytics event contract (B-548): the ingestion service + sponsored-slot
frequency cap (owned by ``discovery.frequency_cap``, applied by the ranker and
the marketplace overview via ``advertising.inventory_facade``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.analytics.application import ingestion_service
from app.modules.analytics.application.ingestion_service import (
    InvalidAnalyticsEventError,
)
from app.modules.analytics.domain.models import AnalyticsEvent
from app.modules.discovery.application import frequency_cap
from app.modules.discovery.domain.models import DiscoveryEvent
from sqlalchemy import func, select


async def test_record_event_persists_sanitized_row(db_session) -> None:
    job_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    event = await ingestion_service.record_event(
        db_session,
        event_type="job.applied",
        aggregate_type="job",
        aggregate_id=job_id,
        actor_id=actor_id,
        actor_type="student",
        properties={"email": "leak@example.com", "org_id": "abc"},
    )
    await db_session.commit()

    row = (
        await db_session.execute(select(AnalyticsEvent).where(AnalyticsEvent.id == event.id))
    ).scalar_one()
    assert row.event_type == "job.applied"
    assert row.aggregate_id == job_id
    assert row.actor_id == actor_id
    # PII-shaped key stripped even though the caller passed it.
    assert "email" not in row.properties
    assert row.properties == {"org_id": "abc"}


async def test_record_event_rejects_unknown_event_type(db_session) -> None:
    try:
        await ingestion_service.record_event(
            db_session,
            event_type="not.a.real.event",
            aggregate_type="job",
            aggregate_id=uuid.uuid4(),
        )
        raise AssertionError("expected InvalidAnalyticsEventError")
    except InvalidAnalyticsEventError:
        pass


async def test_record_event_safe_never_raises(db_session) -> None:
    # Unknown event_type would normally raise — record_event_safe swallows it.
    await ingestion_service.record_event_safe(
        db_session,
        event_type="not.a.real.event",
        aggregate_type="job",
        aggregate_id=uuid.uuid4(),
    )
    count = (
        await db_session.execute(select(func.count()).select_from(AnalyticsEvent))
    ).scalar_one()
    assert count == 0


async def test_record_event_safe_savepoint_isolates_db_failure(db_session) -> None:
    """A DB-level flush failure inside best-effort analytics must NOT poison the
    caller's transaction. Regression for the AI chat turn 500: a failed
    ``ai.tool.called`` insert previously aborted the asyncpg transaction, so the
    subsequent tool-result persist raised ``PendingRollbackError``. The savepoint
    (``begin_nested``) must roll back only the failed analytics insert.
    """
    from unittest.mock import patch

    seeded = await ingestion_service.record_event(
        db_session,
        event_type="ai.tool.called",
        aggregate_type="ai_tool",
        aggregate_id=uuid.uuid4(),
        actor_type="student",
        properties={"tool": "match_cv_to_jobs", "ok": True},
    )
    # Force a primary-key collision inside record_event_safe → IntegrityError on
    # flush (a real DB failure, not a pre-flush validation error).
    with patch.object(ingestion_service.uuid, "uuid4", return_value=seeded.id):
        await ingestion_service.record_event_safe(
            db_session,
            event_type="ai.tool.called",
            aggregate_type="ai_tool",
            aggregate_id=uuid.uuid4(),
            actor_type="student",
            properties={"tool": "explain_job_fit", "ok": True},
        )

    # Outer transaction must still be usable after the swallowed failure...
    await db_session.execute(select(1))
    # ...and a fresh legitimate analytics write still succeeds.
    ok = await ingestion_service.record_event(
        db_session,
        event_type="ai.tool.called",
        aggregate_type="ai_tool",
        aggregate_id=uuid.uuid4(),
        actor_type="student",
        properties={"tool": "compare_jobs", "ok": True},
    )
    assert ok.id is not None and ok.id != seeded.id


async def test_frequency_cap_excludes_placement_after_threshold(db_session) -> None:
    session_id = uuid.uuid4()
    placement_id = uuid.uuid4()
    now = datetime.now(tz=UTC)

    for _ in range(frequency_cap.DEFAULT_CAP):
        db_session.add(
            DiscoveryEvent(
                id=uuid.uuid4(),
                event_type="impression",
                source_surface="homepage_sponsored",
                target_type="job",
                target_id=uuid.uuid4(),
                placement_id=placement_id,
                scope="session",
                session_id=session_id,
                idempotency_key=str(uuid.uuid4()),
                created_at=now,
            )
        )
    await db_session.commit()

    capped = await frequency_cap.over_capped_placements(
        db_session, session_id=session_id, user_id=None, now=now
    )
    assert placement_id in capped


async def test_frequency_cap_ignores_impressions_outside_window(db_session) -> None:
    session_id = uuid.uuid4()
    placement_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    old = now - timedelta(hours=25)

    for _ in range(frequency_cap.DEFAULT_CAP):
        db_session.add(
            DiscoveryEvent(
                id=uuid.uuid4(),
                event_type="impression",
                source_surface="homepage_sponsored",
                target_type="job",
                target_id=uuid.uuid4(),
                placement_id=placement_id,
                scope="session",
                session_id=session_id,
                idempotency_key=str(uuid.uuid4()),
                created_at=old,
            )
        )
    await db_session.commit()

    capped = await frequency_cap.over_capped_placements(
        db_session, session_id=session_id, user_id=None, now=now
    )
    assert capped == set()


async def test_frequency_cap_anonymous_viewer_is_never_capped(db_session) -> None:
    capped = await frequency_cap.over_capped_placements(db_session, session_id=None, user_id=None)
    assert capped == set()
