"""Analytics event contract (B-548): the ingestion service + sponsored-slot
frequency cap (owned by ``discovery.frequency_cap``, applied by the ranker and
the marketplace overview via ``advertising.inventory_facade``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.modules.analytics.application import ingestion_service
from app.modules.analytics.application.ingestion_service import (
    InvalidAnalyticsEventError,
)
from app.modules.analytics.domain.models import AnalyticsEvent
from app.modules.discovery.application import frequency_cap
from app.modules.discovery.domain.models import DiscoveryEvent


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
        await db_session.execute(
            select(AnalyticsEvent).where(AnalyticsEvent.id == event.id)
        )
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
        assert False, "expected InvalidAnalyticsEventError"
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
    capped = await frequency_cap.over_capped_placements(
        db_session, session_id=None, user_id=None
    )
    assert capped == set()
