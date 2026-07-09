"""Job alert dispatch sweep.

Runs periodically (via scheduler/jobs.py) to find newly-published jobs that
match each student's active alert criteria and enqueue a ``job.alert_matches``
notification via the outbox. Safe to re-run (idempotent per alert per window).

Candidate jobs are constrained by the **same canonical public-visibility
predicate** used by public discovery
(:func:`opportunities.application.visibility.apply_visible_filter`) at the
STUDENT tier, so a student is never notified about a job they could not actually
discover and apply to. That predicate excludes:

- soft-deleted, non-``active``, or non-``approved`` jobs;
- unpublished jobs (``published_at`` unset);
- **past-deadline** jobs (``application_deadline`` in the past);
- restricted visibility tiers a student may not discover — in particular
  ``invitation_only`` (which requires a per-job allow-list, never a broadcast).

Matching rules (all filters are AND, each filter is optional):
  - ``keywords``: case-insensitive substring match against the job **title,
    description, requirements, and required skills** (broadened from title-only).
  - ``employment_type``: exact match against ``job.employment_type``
  - ``location_type``:  exact match against ``job.location_type``
  - ``province_code``:  location containment — JSONB ``@>`` on PostgreSQL, a
    dialect-agnostic text ``LIKE`` fallback on SQLite (mirrors
    ``job_search_service._location_contains``) so province filtering works on
    every backend, not only Postgres.

Only jobs published AFTER the alert's ``last_sent_at`` (or within the last 24 h
for never-sent alerts) are candidates.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Select, String, cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.dispatch_service import (
    enqueue_notification,
)
from app.modules.opportunities.application.visibility import apply_visible_filter
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job, JobAlert

_LOOKBACK_HOURS = 24
_BATCH_ALERTS = 200
_MAX_MATCH_ROWS = 5

# Job alerts are a student-only subscription (create is gated to persona
# ``student``), so candidate jobs are filtered at the student visibility tier.
# This deliberately EXCLUDES ``invitation_only`` (and any tier a student may not
# discover) exactly like public discovery.
_ALERT_VISIBILITY_LEVELS = lifecycle.visible_levels_for("student", is_authenticated=True)


async def sweep_job_alerts(session: AsyncSession, now: datetime) -> dict[str, int]:
    """Find new job matches for each active alert and enqueue notifications."""

    cutoff_default = now - timedelta(hours=_LOOKBACK_HOURS)
    # PostgreSQL supports JSONB containment; SQLite (tests/local) uses a text
    # ``LIKE`` fallback. Detected once per sweep, not per alert.
    use_jsonb = session.get_bind().dialect.name == "postgresql"

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
        matches = await _find_matches(
            session, alert=alert, since=cutoff, now=now, use_jsonb=use_jsonb
        )
        if not matches:
            continue

        await _notify(session, alert=alert, matches=matches, now=now)
        alert.last_sent_at = now
        enqueued += 1

    await session.commit()
    return {"alerts_swept": len(alerts), "notifications_enqueued": enqueued}


def _keyword_predicate(keywords: str):
    """Broadened keyword match: title OR description OR requirements OR skills.

    ``required_skills`` is a JSON array; cast to text so a partial keyword match
    works on every backend (same technique as ``job_search_service``).
    """

    term = f"%{keywords.strip()}%"
    return or_(
        Job.title.ilike(term),
        Job.description.ilike(term),
        Job.requirements.ilike(term),
        cast(Job.required_skills, String).ilike(term),
    )


def _province_predicate(province_code: str, *, use_jsonb: bool):
    """Backend-agnostic ``locations[].province_code`` containment predicate."""

    if use_jsonb:
        # PostgreSQL JSONB ``@>`` containment (indexable).
        needle = cast([{"province_code": province_code}], JSONB)
        return cast(Job.locations, JSONB).op("@>")(needle)
    # SQLite/local fallback (mirrors ``job_search_service._location_contains``):
    # the JSON is stored as text, so match the serialized key/value pair.
    return cast(Job.locations, String).ilike(f'%"province_code":%"{province_code}"%')


async def _find_matches(
    session: AsyncSession,
    *,
    alert: JobAlert,
    since: datetime,
    now: datetime,
    use_jsonb: bool,
) -> list[dict]:
    # Canonical public-visibility predicate (published + approved + active +
    # within-deadline + allowed tier), then the recency window and the alert's
    # own optional filters.
    stmt: Select = apply_visible_filter(
        select(Job.id, Job.title),
        levels=_ALERT_VISIBILITY_LEVELS,
        now=now,
    ).where(
        Job.published_at > since,
        Job.published_at <= now,
    )

    if alert.employment_type:
        stmt = stmt.where(Job.employment_type == alert.employment_type)

    if alert.location_type:
        stmt = stmt.where(Job.location_type == alert.location_type)

    if alert.keywords:
        stmt = stmt.where(_keyword_predicate(alert.keywords))

    if alert.province_code:
        stmt = stmt.where(_province_predicate(alert.province_code, use_jsonb=use_jsonb))

    stmt = stmt.order_by(Job.published_at.desc()).limit(_MAX_MATCH_ROWS)

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
