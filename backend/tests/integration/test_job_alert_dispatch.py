"""Integration tests for the job alert dispatch sweep."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.template_seed import ensure_default_templates
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.opportunities.application.job_alert_dispatch_service import (
    sweep_job_alerts,
)
from app.modules.opportunities.domain.models import Job, JobAlert


def _now() -> datetime:
    return datetime.now(UTC)


def _make_job(
    session: AsyncSession,
    *,
    title: str,
    employment_type: str = "full_time",
    location_type: str = "onsite",
    published_minutes_ago: int = 10,
    status: str = "active",
    moderation_status: str = "approved",
) -> Job:
    now = _now()
    job = Job(
        org_id=uuid.uuid4(),
        posted_by=uuid.uuid4(),
        title=title,
        slug=f"slug-{uuid.uuid4().hex[:8]}",
        description="Test job",
        employment_type=employment_type,
        location_type=location_type,
        status=status,
        moderation_status=moderation_status,
        published_at=now - timedelta(minutes=published_minutes_ago),
        created_at=now - timedelta(minutes=published_minutes_ago + 1),
    )
    session.add(job)
    return job


def _make_alert(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str = "Test Alert",
    keywords: str | None = None,
    employment_type: str | None = None,
    location_type: str | None = None,
    last_sent_at: datetime | None = None,
) -> JobAlert:
    alert = JobAlert(
        user_id=user_id,
        name=name,
        keywords=keywords,
        employment_type=employment_type,
        location_type=location_type,
        is_active=True,
        last_sent_at=last_sent_at,
    )
    session.add(alert)
    return alert


@pytest.mark.asyncio
async def test_sweep_matches_keyword_alert(db_session: AsyncSession) -> None:
    await ensure_default_templates(db_session)
    user_id = uuid.uuid4()
    _make_job(db_session, title="Python Backend Engineer", published_minutes_ago=5)
    _make_alert(db_session, user_id=user_id, keywords="python")
    await db_session.flush()

    now = _now()
    result = await sweep_job_alerts(db_session, now=now)

    assert result["notifications_enqueued"] == 1
    outbox = (await db_session.execute(select(NotificationOutbox))).scalars().all()
    assert len(outbox) == 1
    assert outbox[0].template_key == "job.alert_matches"
    assert outbox[0].recipient_id == user_id


@pytest.mark.asyncio
async def test_sweep_no_match_for_different_keyword(db_session: AsyncSession) -> None:
    await ensure_default_templates(db_session)
    user_id = uuid.uuid4()
    _make_job(db_session, title="Marketing Specialist", published_minutes_ago=5)
    _make_alert(db_session, user_id=user_id, keywords="python")
    await db_session.flush()

    result = await sweep_job_alerts(db_session, now=_now())
    assert result["notifications_enqueued"] == 0


@pytest.mark.asyncio
async def test_sweep_respects_last_sent_at_cutoff(db_session: AsyncSession) -> None:
    await ensure_default_templates(db_session)
    user_id = uuid.uuid4()
    now = _now()
    # Job published 5 minutes ago, alert last_sent 3 minutes ago → before the job.
    _make_job(db_session, title="Python Dev", published_minutes_ago=5)
    _make_alert(
        db_session,
        user_id=user_id,
        keywords="python",
        last_sent_at=now - timedelta(minutes=3),
    )
    await db_session.flush()

    result = await sweep_job_alerts(db_session, now=now)
    assert result["notifications_enqueued"] == 0


@pytest.mark.asyncio
async def test_sweep_skips_non_active_jobs(db_session: AsyncSession) -> None:
    await ensure_default_templates(db_session)
    user_id = uuid.uuid4()
    _make_job(db_session, title="Python Dev", status="closed", published_minutes_ago=5)
    _make_alert(db_session, user_id=user_id, keywords="python")
    await db_session.flush()

    result = await sweep_job_alerts(db_session, now=_now())
    assert result["notifications_enqueued"] == 0


@pytest.mark.asyncio
async def test_sweep_skips_unapproved_jobs(db_session: AsyncSession) -> None:
    await ensure_default_templates(db_session)
    user_id = uuid.uuid4()
    _make_job(
        db_session,
        title="Python Dev",
        moderation_status="pending",
        published_minutes_ago=5,
    )
    _make_alert(db_session, user_id=user_id, keywords="python")
    await db_session.flush()

    result = await sweep_job_alerts(db_session, now=_now())
    assert result["notifications_enqueued"] == 0


@pytest.mark.asyncio
async def test_sweep_updates_last_sent_at(db_session: AsyncSession) -> None:
    await ensure_default_templates(db_session)
    user_id = uuid.uuid4()
    _make_job(db_session, title="Python Dev", published_minutes_ago=5)
    alert = _make_alert(db_session, user_id=user_id, keywords="python")
    await db_session.flush()
    alert_id = alert.id

    now = _now()
    await sweep_job_alerts(db_session, now=now)

    refreshed = await db_session.get(JobAlert, alert_id)
    assert refreshed is not None
    assert refreshed.last_sent_at is not None


@pytest.mark.asyncio
async def test_sweep_deduplicates_same_day(db_session: AsyncSession) -> None:
    await ensure_default_templates(db_session)
    user_id = uuid.uuid4()
    _make_job(db_session, title="Python Dev", published_minutes_ago=5)
    _make_alert(db_session, user_id=user_id, keywords="python")
    await db_session.flush()

    now = _now()
    r1 = await sweep_job_alerts(db_session, now=now)
    r2 = await sweep_job_alerts(db_session, now=now)

    # Second sweep: last_sent_at is now == now, so no new jobs after that.
    assert r1["notifications_enqueued"] == 1
    assert r2["notifications_enqueued"] == 0


@pytest.mark.asyncio
async def test_sweep_filters_by_employment_type(db_session: AsyncSession) -> None:
    await ensure_default_templates(db_session)
    user_id = uuid.uuid4()
    _make_job(
        db_session,
        title="Intern Dev",
        employment_type="internship",
        published_minutes_ago=5,
    )
    _make_alert(db_session, user_id=user_id, employment_type="full_time")
    await db_session.flush()

    result = await sweep_job_alerts(db_session, now=_now())
    assert result["notifications_enqueued"] == 0
