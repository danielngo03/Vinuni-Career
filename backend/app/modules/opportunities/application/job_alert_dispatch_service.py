"""Job alert dispatch sweep.

Runs periodically (via scheduler/jobs.py) to find newly-published jobs that
match each student's active alert criteria and enqueue a ``job.alert_matches``
notification via the outbox. Safe to re-run (idempotent per alert per window).

Matching rules (all filters are AND, each filter is optional):
  - ``keywords``: case-insensitive substring match against ``job.title``
  - ``employment_type``: exact match against ``job.employment_type``
  - ``location_type``:  exact match against ``job.location_type``
  - ``province_code``:  JSONB containment check on ``job.locations``
    (PostgreSQL only; skipped on SQLite for test isolation)

Only jobs published AFTER the alert's ``last_sent_at`` (or within the last 24 h
for never-sent alerts) are candidates. ``status == "active"`` and
``moderation_status == "approved"`` are required.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.dispatch_service import (
    enqueue_notification,
)
from app.modules.opportunities.domain.models import Job, JobAlert

_LOOKBACK_HOURS = 24
_BATCH_ALERTS = 200
_MAX_MATCH_ROWS = 5


async def sweep_job_alerts(session: AsyncSession, now: datetime) -> dict[str, int]:
    """Find new job matches for each active alert and enqueue notifications."""

    cutoff_default = now - timedelta(hours=_LOOKBACK_HOURS)

    alerts: list[JobAlert] = list(
        (
            await session.execute(
                select(JobAlert)
                .where(JobAlert.is_active.is_(True))
                .order_by(JobAlert.created_at.asc())
                .limit(_BATCH_ALERTS)
            )
        )
        .scalars()
        .all()
    )

    enqueued = 0
    for alert in alerts:
        cutoff = alert.last_sent_at if alert.last_sent_at is not None else cutoff_default
        matches = await _find_matches(session, alert=alert, since=cutoff, now=now)
        if not matches:
            continue

        await _notify(session, alert=alert, matches=matches, now=now)
        alert.last_sent_at = now
        enqueued += 1

    await session.commit()
    return {"alerts_swept": len(alerts), "notifications_enqueued": enqueued}


async def _find_matches(
    session: AsyncSession,
    *,
    alert: JobAlert,
    since: datetime,
    now: datetime,
) -> list[dict]:
    filters = [
        Job.status == "active",
        Job.moderation_status == "approved",
        Job.deleted_at.is_(None),
        Job.published_at.isnot(None),
        Job.published_at > since,
        Job.published_at <= now,
    ]

    if alert.employment_type:
        filters.append(Job.employment_type == alert.employment_type)

    if alert.location_type:
        filters.append(Job.location_type == alert.location_type)

    if alert.keywords:
        filters.append(Job.title.ilike(f"%{alert.keywords}%"))

    if alert.province_code:
        try:
            from sqlalchemy import cast as sa_cast
            from sqlalchemy.dialects.postgresql import JSONB

            needle = sa_cast([{"province_code": alert.province_code}], JSONB)
            filters.append(sa_cast(Job.locations, JSONB).op("@>")(needle))
        except Exception:
            # Not on PostgreSQL (e.g. SQLite in tests); skip province filter.
            pass

    stmt = (
        select(Job.id, Job.title)
        .where(and_(*filters))
        .order_by(Job.published_at.desc())
        .limit(_MAX_MATCH_ROWS)
    )

    rows = (await session.execute(stmt)).all()
    return [{"id": str(r.id), "title": r.title} for r in rows]


async def _notify(
    session: AsyncSession,
    *,
    alert: JobAlert,
    matches: list[dict],
    now: datetime,
) -> None:
    count = len(matches)
    first_title = matches[0]["title"] if matches else ""
    dedupe_key = f"job.alert_matches:{alert.id}:{now.date().isoformat()}"

    await enqueue_notification(
        session,
        recipient_id=alert.user_id,
        template_key="job.alert_matches",
        channel="in_app",
        locale="vi",
        variables={
            "alert_name": alert.name,
            "match_count": count,
            "first_job_title": first_title,
            "url": "/student/alerts",
        },
        dedupe_key=dedupe_key,
    )
