"""Write + read path for ``partner_job_metrics_daily`` / dimensions (spec
"Recruiting Intelligence Read Models" §``partner_job_metrics_daily``).

:func:`record_job_metric_event` is the single call any module makes to log one
funnel event for a job (impression / detail_view / cta_click / apply_start /
applications_submitted / save_click / share_click). It is BEST-EFFORT and
isolated in its own savepoint: a metrics-write failure never poisons or aborts
the caller's own transaction (mirrors the ``discovery.event_service`` idempotent-
insert pattern, but for an incrementing counter row instead of an append row).

Coarse dimensions:

- ``device_class`` — derived from the request's user-agent via
  :func:`coarse_device_class` (desktop|mobile|tablet|unknown). Never the raw UA.
- ``student_tier`` — the acting principal's persona (student|alumni|guest) when
  known. There is no separate "subscription tier" concept for students yet
  (`docs/DATA_MODEL.md` has no such column) — persona is the closest coarse,
  non-PII tier signal available today; a real tier field is a documented open
  question for `system-architect`/`product-owner-system-planner`.
- ``major_group`` / ``year_group`` — best-effort buckets derived from the
  student's OWN confirmed preferences via the existing
  ``student_profiles.preferences_facade`` (never a raw free-text major or exact
  graduation year). ``None`` when the student has no profile.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.application import inventory_facade
from app.modules.analytics.domain.partner_read_models import (
    PartnerJobMetricDaily,
    PartnerJobMetricDimensionDaily,
)
from app.modules.advertising.domain.lifecycle import TARGET_JOB
from app.modules.student_profiles.application import preferences_facade
from app.shared.hashing import device_hint

logger = logging.getLogger(__name__)

# Funnel event -> daily counter column(s) it increments.
_FUNNEL_EVENTS: dict[str, str] = {
    "impression": "impressions",
    "detail_view": "detail_views",
    "cta_click": "cta_clicks",
    "apply_start": "apply_starts",
    "applications_submitted": "applications_submitted",
    "save_click": "save_clicks",
    "share_click": "share_clicks",
}

SOURCE_VALUES: frozenset[str] = frozenset(
    {"organic", "search", "recommendation", "sponsored", "invitation", "direct"}
)
_SOURCE_COLUMN = {s: f"src_{s}" for s in SOURCE_VALUES}

DIMENSION_TYPES: frozenset[str] = frozenset(
    {"device_class", "student_tier", "major_group", "year_group"}
)
DEVICE_CLASSES: frozenset[str] = frozenset({"desktop", "mobile", "tablet", "unknown"})
STUDENT_TIERS: frozenset[str] = frozenset({"student", "alumni", "guest"})


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _today() -> date:
    return _now().date()


def coarse_device_class(user_agent: str | None) -> str:
    """Map a user-agent to a coarse device class only — never store the raw UA.

    Reuses :func:`app.shared.hashing.device_hint` (``"<browser>_<platform>"``)
    and keeps only the platform half, so callers never even have the browser
    name in memory next to a metrics row.
    """

    hint = device_hint(user_agent)
    platform = hint.rsplit("_", 1)[-1]
    return platform if platform in DEVICE_CLASSES else "unknown"


def student_tier_for_persona(persona: str | None) -> str | None:
    if persona in ("student", "alumni"):
        return persona
    return None


_MAJOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "computer_science": ("computer science", "software", "information technology", "data science", "ai", "cs"),
    "engineering": ("engineering", "mechanical", "electrical", "civil"),
    "business": ("business", "economics", "finance", "management", "marketing", "accounting"),
    "design": ("design", "art", "media", "communication"),
    "health_sciences": ("health", "biology", "medicine", "nursing", "pharma"),
    "social_sciences": ("social", "psychology", "education", "law", "political"),
}


def _major_group(major: str | None) -> str | None:
    if not major:
        return None
    low = major.lower()
    for group, keywords in _MAJOR_KEYWORDS.items():
        if any(k in low for k in keywords):
            return group
    return "other"


def _year_group(graduation_year: int | None, *, as_of: date | None = None) -> str | None:
    if graduation_year is None:
        return None
    as_of = as_of or _today()
    delta = graduation_year - as_of.year
    if delta <= 0:
        return "graduating_or_alumni"
    if delta == 1:
        return "senior"
    if delta == 2:
        return "junior"
    if delta == 3:
        return "sophomore"
    return "freshman_or_earlier"


async def coarse_academic_dims(
    session: AsyncSession, *, user_id: uuid.UUID | None
) -> tuple[str | None, str | None]:
    """Best-effort ``(major_group, year_group)`` for a student principal.

    ``None, None`` for guests, non-students, or students with no profile yet —
    callers must treat this as "unknown", never fabricate a bucket.
    """

    if user_id is None:
        return None, None
    prefs = await preferences_facade.get_ranking_preferences(session, user_id=user_id)
    if prefs is None:
        return None, None
    return _major_group(prefs.field), _year_group(prefs.graduation_year)


async def default_source_for_job(
    session: AsyncSession, *, job_id: uuid.UUID, now: datetime | None = None
) -> str:
    """``"sponsored"`` if the job carries a currently-live sponsored placement,
    else the honest ``"organic"`` default. Callers with a stronger signal
    (search results page, a recommendation rail, an invitation link) should pass
    their own ``source`` instead of relying on this default.
    """

    try:
        is_sponsored = await inventory_facade.is_target_sponsored_now(
            session, target_type=TARGET_JOB, target_id=job_id, now=now
        )
    except Exception:  # noqa: BLE001 — attribution is best-effort
        return "organic"
    return "sponsored" if is_sponsored else "organic"


def _dialect_insert(session: AsyncSession):
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    return pg_insert if dialect == "postgresql" else sqlite_insert


async def _upsert_daily_row(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    metric_date: date,
    counter_increments: dict[str, int],
) -> None:
    if not counter_increments:
        return
    insert = _dialect_insert(session)
    values = {
        "org_id": org_id,
        "job_id": job_id,
        "metric_date": metric_date,
        **counter_increments,
    }
    stmt = insert(PartnerJobMetricDaily).values(**values)
    tbl = PartnerJobMetricDaily.__table__
    set_ = {col: tbl.c[col] + amount for col, amount in counter_increments.items()}
    stmt = stmt.on_conflict_do_update(
        index_elements=["job_id", "metric_date"], set_=set_
    )
    await session.execute(stmt)


async def _upsert_dimension_row(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    metric_date: date,
    dimension_type: str,
    dimension_value: str,
) -> None:
    insert = _dialect_insert(session)
    values = {
        "org_id": org_id,
        "job_id": job_id,
        "metric_date": metric_date,
        "dimension_type": dimension_type,
        "dimension_value": dimension_value,
        "event_count": 1,
    }
    stmt = insert(PartnerJobMetricDimensionDaily).values(**values)
    tbl = PartnerJobMetricDimensionDaily.__table__
    stmt = stmt.on_conflict_do_update(
        index_elements=["job_id", "metric_date", "dimension_type", "dimension_value"],
        set_={"event_count": tbl.c.event_count + 1},
    )
    await session.execute(stmt)


async def record_job_metric_event(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    event_type: str,
    source: str = "organic",
    device_class: str | None = None,
    student_tier: str | None = None,
    major_group: str | None = None,
    year_group: str | None = None,
    metric_date: date | None = None,
) -> None:
    """Record one job-engagement event into the daily read model. Best-effort.

    Any failure (bad dialect, constraint edge case, transient DB error) is
    logged and swallowed in its own savepoint — this must never break the
    primary write (job view / save / apply) it is instrumenting.
    """

    if event_type not in _FUNNEL_EVENTS:
        logger.warning("partner_job_metrics.unknown_event_type", extra={"event_type": event_type})
        return

    counter_increments = {_FUNNEL_EVENTS[event_type]: 1}
    src = source if source in SOURCE_VALUES else "organic"
    counter_increments[_SOURCE_COLUMN[src]] = 1
    day = metric_date or _today()

    dims: list[tuple[str, str]] = []
    if device_class and device_class in DEVICE_CLASSES:
        dims.append(("device_class", device_class))
    if student_tier and student_tier in STUDENT_TIERS:
        dims.append(("student_tier", student_tier))
    if major_group:
        dims.append(("major_group", major_group))
    if year_group:
        dims.append(("year_group", year_group))

    try:
        async with session.begin_nested():
            await _upsert_daily_row(
                session, org_id=org_id, job_id=job_id, metric_date=day,
                counter_increments=counter_increments,
            )
            for dim_type, dim_value in dims:
                await _upsert_dimension_row(
                    session, org_id=org_id, job_id=job_id, metric_date=day,
                    dimension_type=dim_type, dimension_value=dim_value,
                )
    except Exception:  # noqa: BLE001 — telemetry is best-effort at these sites
        logger.warning(
            "partner_job_metrics.record_failed",
            extra={"event_type": event_type, "job_id": str(job_id)},
        )


# --------------------------------------------------------------------------- #
# Reads (partner dashboard v2)                                                #
# --------------------------------------------------------------------------- #


async def has_any_metrics(session: AsyncSession, *, org_id: uuid.UUID) -> bool:
    row = (
        await session.execute(
            select(PartnerJobMetricDaily.id)
            .where(PartnerJobMetricDaily.org_id == org_id)
            .limit(1)
        )
    ).first()
    return row is not None


async def job_performance_for_org(
    session: AsyncSession, *, org_id: uuid.UUID, since_days: int = 30, limit: int = 10
) -> list[dict]:
    """Per-job totals over the trailing window, newest-activity-first.

    Returns an empty list (never fabricated zero rows) when no metrics exist yet
    for this org — the caller (``partner_ops_dashboard``) is responsible for the
    honest "using application counts only" fallback copy.
    """

    cutoff = _today()
    from datetime import timedelta

    since = cutoff - timedelta(days=since_days)
    rows = (
        await session.execute(
            select(
                PartnerJobMetricDaily.job_id,
                func.sum(PartnerJobMetricDaily.impressions).label("impressions"),
                func.sum(PartnerJobMetricDaily.detail_views).label("detail_views"),
                func.sum(PartnerJobMetricDaily.cta_clicks).label("cta_clicks"),
                func.sum(PartnerJobMetricDaily.apply_starts).label("apply_starts"),
                func.sum(PartnerJobMetricDaily.applications_submitted).label("applications_submitted"),
                func.sum(PartnerJobMetricDaily.save_clicks).label("save_clicks"),
                func.sum(PartnerJobMetricDaily.share_clicks).label("share_clicks"),
                func.sum(PartnerJobMetricDaily.src_organic).label("src_organic"),
                func.sum(PartnerJobMetricDaily.src_search).label("src_search"),
                func.sum(PartnerJobMetricDaily.src_recommendation).label("src_recommendation"),
                func.sum(PartnerJobMetricDaily.src_sponsored).label("src_sponsored"),
                func.sum(PartnerJobMetricDaily.src_invitation).label("src_invitation"),
                func.sum(PartnerJobMetricDaily.src_direct).label("src_direct"),
            )
            .where(
                PartnerJobMetricDaily.org_id == org_id,
                PartnerJobMetricDaily.metric_date >= since,
            )
            .group_by(PartnerJobMetricDaily.job_id)
            .order_by(func.sum(PartnerJobMetricDaily.detail_views).desc())
            .limit(max(limit, 1))
        )
    ).all()

    out: list[dict] = []
    for r in rows:
        applications = r.applications_submitted or 0
        views = r.detail_views or 0
        conversion = round((applications / views) * 100, 1) if views else None
        out.append({
            "job_id": str(r.job_id),
            "impressions": r.impressions or 0,
            "detail_views": views,
            "cta_clicks": r.cta_clicks or 0,
            "apply_starts": r.apply_starts or 0,
            "applications_submitted": applications,
            "save_clicks": r.save_clicks or 0,
            "share_clicks": r.share_clicks or 0,
            "conversion_rate_pct": conversion,
            "source_mix": {
                "organic": r.src_organic or 0,
                "search": r.src_search or 0,
                "recommendation": r.src_recommendation or 0,
                "sponsored": r.src_sponsored or 0,
                "invitation": r.src_invitation or 0,
                "direct": r.src_direct or 0,
            },
        })
    return out


async def org_metrics_summary(
    session: AsyncSession, *, org_id: uuid.UUID, since_days: int = 30
) -> dict | None:
    """Org-wide totals + conversion for the trailing window, or ``None`` if the
    projection has no rows yet for this org (honest "no data yet" trigger)."""

    perf = await job_performance_for_org(session, org_id=org_id, since_days=since_days, limit=10_000)
    if not perf:
        return None
    totals = {
        "impressions": sum(p["impressions"] for p in perf),
        "detail_views": sum(p["detail_views"] for p in perf),
        "cta_clicks": sum(p["cta_clicks"] for p in perf),
        "apply_starts": sum(p["apply_starts"] for p in perf),
        "applications_submitted": sum(p["applications_submitted"] for p in perf),
        "save_clicks": sum(p["save_clicks"] for p in perf),
        "share_clicks": sum(p["share_clicks"] for p in perf),
    }
    views = totals["detail_views"]
    totals["conversion_rate_pct"] = (
        round((totals["applications_submitted"] / views) * 100, 1) if views else None
    )
    return totals
