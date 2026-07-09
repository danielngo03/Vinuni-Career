"""Superadmin platform analytics read model — P6.

Three aggregate-only, privacy-safe read functions for the Platform Admin Console:

- ``kpis``   — top-line totals (students, partner_members, university_staff,
               jobs, applications, events).
- ``funnel`` — application funnel stage counts + conversion rates derived from
               ``AnalyticsEvent`` within a rolling ``range_days`` window.
- ``growth`` — per-day trends: signups, applications, active_users; gap-filled.

All three are wrapped in :func:`safe` from the dashboard helpers so a single
failing sub-query never crashes the endpoint.  RBAC is enforced by the router
(``require_superadmin``), not here.

Privacy contract:
- NO per-user rows, NO actor_id rows, NO PII in output.
- Only aggregate counts, conversion ratios, and date-bucketed series.
- ``properties`` is never surfaced; only event counts are returned.
- Date bucketing is done in Python (not via PG-specific ``date_trunc``) so
  SQLite test runs remain valid.

Cohort retention is OUT OF SCOPE for this slice (deferred).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.domain.models import AnalyticsEvent
from app.modules.analytics.domain.taxonomy import EVENT_TYPES
from app.modules.dashboards.application._common import safe
from app.modules.opportunities.application import job_read_facade
from app.modules.recruitment.application import dashboard_read as recruitment_read
from app.modules.users.application import user_read_facade
from app.modules.users.domain.models import User

# ---------------------------------------------------------------------------
# Taxonomy constants (used via string — avoids hardcoding)
# ---------------------------------------------------------------------------

_JOB_VIEWED: str = "job.viewed"
_JOB_APPLIED: str = "job.applied"
_APP_SUBMITTED: str = "application.submitted"
_APP_STATUS_CHANGED: str = "application.status_changed"

assert _JOB_VIEWED in EVENT_TYPES
assert _JOB_APPLIED in EVENT_TYPES
assert _APP_SUBMITTED in EVENT_TYPES
assert _APP_STATUS_CHANGED in EVENT_TYPES

# Funnel stage order — every status name we inspect in properties["status"].
_STATUS_STAGES: list[str] = [
    "under_review",
    "interview",
    "offer",
    "hired",
    "rejected",
]

# Full funnel stage order (for output, preserving stable key names).
_FUNNEL_STAGES: list[str] = [
    "job_views",
    "job_applies",
    "applications_submitted",
    "under_review",
    "interview",
    "offer",
    "hired",
    "rejected",
]


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------


async def kpis(session: AsyncSession) -> dict[str, Any]:
    """Top-line platform totals — superadmin KPI cards.

    Returns::

        {
          "students": int,
          "partner_members": int,
          "university_staff": int,
          "jobs": int,
          "applications": int,
          "events": int,
        }

    Every sub-query is ``safe``-wrapped; a failing sub-query returns 0.
    """

    students: int = await safe(
        session,
        lambda: user_read_facade.count_identities_by_persona(session, "student"),
        fallback=0,
    )
    partner_members: int = await safe(
        session,
        lambda: user_read_facade.count_identities_by_persona(session, "partner_member"),
        fallback=0,
    )
    university_staff: int = await safe(
        session,
        lambda: user_read_facade.count_identities_by_persona(session, "university_staff"),
        fallback=0,
    )
    jobs: int = await safe(
        session,
        lambda: job_read_facade.count_all_jobs(session),
        fallback=0,
    )
    applications: int = await safe(
        session,
        lambda: recruitment_read.count_all_applications(session),
        fallback=0,
    )
    events: int = await safe(
        session,
        lambda: job_read_facade.count_published_events(session),
        fallback=0,
    )

    return {
        "students": students,
        "partner_members": partner_members,
        "university_staff": university_staff,
        "jobs": jobs,
        "applications": applications,
        "events": events,
    }


# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------


def _safe_rate(numerator: int, denominator: int) -> float:
    """Conversion rate as a 0-1 float; 0.0 if denominator is zero."""

    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


async def _funnel_raw(session: AsyncSession, *, since: datetime) -> dict[str, int]:
    """Fetch raw stage counts from AnalyticsEvent; no PII exposed."""

    # ---- event-type stage counts (job.viewed, job.applied, application.submitted)
    event_type_counts: dict[str, int] = {}
    for et in (_JOB_VIEWED, _JOB_APPLIED, _APP_SUBMITTED):
        count_val = (
            await session.execute(
                select(func.count())
                .select_from(AnalyticsEvent)
                .where(
                    AnalyticsEvent.event_type == et,
                    AnalyticsEvent.occurred_at >= since,
                )
            )
        ).scalar_one()
        event_type_counts[et] = count_val

    # ---- application.status_changed — split by properties["status"]
    # We load only event_type and properties within the window; no actor_id selected.
    status_rows = (
        (
            await session.execute(
                select(AnalyticsEvent.properties).where(
                    AnalyticsEvent.event_type == _APP_STATUS_CHANGED,
                    AnalyticsEvent.occurred_at >= since,
                )
            )
        )
        .scalars()
        .all()
    )

    status_counts: dict[str, int] = defaultdict(int)
    for props in status_rows:
        if isinstance(props, dict):
            status_val = props.get("status")
            if isinstance(status_val, str) and status_val in _STATUS_STAGES:
                status_counts[status_val] += 1

    return {
        "job_views": event_type_counts.get(_JOB_VIEWED, 0),
        "job_applies": event_type_counts.get(_JOB_APPLIED, 0),
        "applications_submitted": event_type_counts.get(_APP_SUBMITTED, 0),
        **{stage: status_counts.get(stage, 0) for stage in _STATUS_STAGES},
    }


async def funnel(session: AsyncSession, *, range_days: int) -> dict[str, Any]:
    """Application funnel for the rolling ``range_days`` window.

    Returns::

        {
          "range_days": int,
          "stages": [
            {
              "stage": "job_views",
              "count": int,
              "conversion_from_previous": float  # 0-1; null for first stage
            },
            ...
          ]
        }

    Conversion rate is count / previous_stage_count (0.0 when previous is 0).
    No per-user rows; no PII; no actor_id in output.
    """

    range_days = max(1, range_days)
    since = datetime.now(tz=UTC) - timedelta(days=range_days)

    raw: dict[str, int] = await safe(
        session,
        lambda: _funnel_raw(session, since=since),
        fallback=dict.fromkeys(_FUNNEL_STAGES, 0),
    )

    stages = []
    prev_count: int | None = None
    for stage_name in _FUNNEL_STAGES:
        count = raw.get(stage_name, 0)
        conversion: float | None = None if prev_count is None else _safe_rate(count, prev_count)
        stages.append(
            {
                "stage": stage_name,
                "count": count,
                "conversion_from_previous": conversion,
            }
        )
        prev_count = count

    return {
        "range_days": range_days,
        "stages": stages,
    }


# ---------------------------------------------------------------------------
# Growth
# ---------------------------------------------------------------------------


async def _growth_raw(
    session: AsyncSession,
    *,
    since: datetime,
    range_days: int,
) -> dict[str, Any]:
    """Fetch per-day series for the growth endpoint.

    Date bucketing is done in Python (iterate rows by occurred_at.date()) so
    we remain cross-DB safe (SQLite + PostgreSQL). No PG-only functions.
    """

    # ---- Build the gap-filled day spine (most recent last) -----------------
    today = datetime.now(tz=UTC).date()
    day_spine: list[date] = [today - timedelta(days=d) for d in range(range_days - 1, -1, -1)]

    # ---- Signups: users.created_at in window --------------------------------
    signup_rows = (
        (
            await session.execute(
                select(User.created_at).where(User.created_at >= since, User.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    )

    signups_by_day: dict[date, int] = defaultdict(int)
    for created_at in signup_rows:
        day_key = created_at.date() if hasattr(created_at, "date") else created_at
        signups_by_day[day_key] += 1

    # ---- Applications submitted per day -------------------------------------
    app_rows = (
        (
            await session.execute(
                select(AnalyticsEvent.occurred_at).where(
                    AnalyticsEvent.event_type == _APP_SUBMITTED,
                    AnalyticsEvent.occurred_at >= since,
                )
            )
        )
        .scalars()
        .all()
    )

    apps_by_day: dict[date, int] = defaultdict(int)
    for occurred_at in app_rows:
        day_key = occurred_at.date() if hasattr(occurred_at, "date") else occurred_at
        apps_by_day[day_key] += 1

    # ---- Active users (distinct actor_id per day) ---------------------------
    # We select only actor_id + occurred_at; no other PII. Counting distinct
    # actor_ids per day is done in Python to stay cross-DB safe.
    active_rows = (
        await session.execute(
            select(AnalyticsEvent.actor_id, AnalyticsEvent.occurred_at).where(
                AnalyticsEvent.actor_id.isnot(None),
                AnalyticsEvent.occurred_at >= since,
            )
        )
    ).all()

    # actor_id per day (use a set per day)
    actors_by_day: dict[date, set] = defaultdict(set)
    for actor_id, occurred_at in active_rows:
        day_key = occurred_at.date() if hasattr(occurred_at, "date") else occurred_at
        actors_by_day[day_key].add(actor_id)

    # ---- Compose the gap-filled series -------------------------------------
    series = []
    for day in day_spine:
        series.append(
            {
                "day": day.isoformat(),
                "signups": signups_by_day.get(day, 0),
                "applications": apps_by_day.get(day, 0),
                "active_users": len(actors_by_day.get(day, set())),
            }
        )

    return {"series": series}


async def growth(session: AsyncSession, *, range_days: int) -> dict[str, Any]:
    """Per-day growth trends for the rolling ``range_days`` window.

    Returns::

        {
          "range_days": int,
          "series": [
            {
              "day": "YYYY-MM-DD",
              "signups": int,
              "applications": int,
              "active_users": int
            },
            ...
          ]
        }

    One row per day in the window, ascending by date, gap-filled with zeros.
    No per-user rows; actor_ids are counted server-side but never returned.
    Cohort retention is deferred.
    """

    range_days = max(1, range_days)
    since = datetime.now(tz=UTC) - timedelta(days=range_days)

    empty_series: list[dict] = [
        {
            "day": (datetime.now(tz=UTC).date() - timedelta(days=d)).isoformat(),
            "signups": 0,
            "applications": 0,
            "active_users": 0,
        }
        for d in range(range_days - 1, -1, -1)
    ]

    result: dict[str, Any] = await safe(
        session,
        lambda: _growth_raw(session, since=since, range_days=range_days),
        fallback={"series": empty_series},
    )

    return {
        "range_days": range_days,
        **result,
    }
