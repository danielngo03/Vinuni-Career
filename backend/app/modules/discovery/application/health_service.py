"""University/admin discovery + advertising inventory health (spec §8).

A privacy-safe operations read for the governance surface: which recommendation
rails are empty, how much sponsored inventory is live, broken/missing logos on
sponsored targets, impression/click (CTR) outliers, and policy flags. It returns
ONLY aggregates (counts, ratios) — never a user id, session id, candidate id, raw
IP, or any PII from the ``discovery_events`` ledger.

RBAC mirrors the university dashboard gate: a platform superadmin, or a member of
a **university** org holding ``jobs:moderate``. A partner Admin holds ``*:*`` but
the org-type gate keeps this surface university-only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.application import inventory_facade
from app.modules.discovery.application import ranking_service
from app.modules.discovery.domain.models import DiscoveryEvent
from app.modules.opportunities.application import public_read, ranking_read
from app.modules.organization.application import company_directory_service, org_reporting_facade
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal, permission_checker

_WINDOW_DAYS = 30
# A surface needs at least this many impressions before zero clicks is flagged.
_ZERO_CTR_MIN_IMPRESSIONS = 20


async def _require_university(session: AsyncSession, principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "jobs", "moderate"):
        raise PermissionDeniedError()
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


def _ctr_pct(impressions: int, clicks: int) -> float | None:
    if impressions <= 0:
        return None
    return round(clicks / impressions * 100, 1)


async def _event_health(session: AsyncSession, *, now: datetime) -> dict:
    since = now - timedelta(days=_WINDOW_DAYS)
    rows = (
        await session.execute(
            select(
                DiscoveryEvent.source_surface,
                DiscoveryEvent.event_type,
                func.count(DiscoveryEvent.id),
            )
            .where(DiscoveryEvent.created_at >= since)
            .group_by(DiscoveryEvent.source_surface, DiscoveryEvent.event_type)
        )
    ).all()

    by_surface: dict[str, dict[str, int]] = {}
    total_impressions = 0
    total_clicks = 0
    for surface, event_type, count in rows:
        bucket = by_surface.setdefault(surface, {"impressions": 0, "clicks": 0})
        if event_type == "impression":
            bucket["impressions"] += int(count)
            total_impressions += int(count)
        elif event_type == "click":
            bucket["clicks"] += int(count)
            total_clicks += int(count)

    surfaces = [
        {
            "surface": surface,
            "impressions": data["impressions"],
            "clicks": data["clicks"],
            "ctr_pct": _ctr_pct(data["impressions"], data["clicks"]),
        }
        for surface, data in sorted(by_surface.items())
    ]
    outliers = [
        surface
        for surface, data in sorted(by_surface.items())
        if data["impressions"] >= _ZERO_CTR_MIN_IMPRESSIONS and data["clicks"] == 0
    ]
    return {
        "window_days": _WINDOW_DAYS,
        "impressions": total_impressions,
        "clicks": total_clicks,
        "ctr_pct": _ctr_pct(total_impressions, total_clicks),
        "by_surface": surfaces,
        "zero_ctr_outliers": outliers,
    }


async def get_discovery_health(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    """Aggregate inventory + delivery health for the governance surface."""

    await _require_university(session, principal)
    now = datetime.now(tz=UTC)

    visible_jobs = await public_read.count_visible_jobs(session)
    spotlight = await company_directory_service.count_public_companies(session)
    sponsored_active = await inventory_facade.count_active_sponsored(session, now=now)
    popular = await ranking_service.popular_roles(session, locale=locale)

    rails = {
        "recommended_jobs_available": visible_jobs,
        "recent_jobs_available": visible_jobs,
        "employer_spotlight_available": spotlight,
        "popular_roles_available": len(popular),
        "sponsored_active": sponsored_active,
    }
    empty_rails = [name for name, count in rails.items() if count == 0]

    # Sponsored target integrity: missing logo + broken (now-hidden) targets.
    active_jobs = await inventory_facade.list_active_sponsored(
        session, target_type="job", now=now, limit=1000
    )
    cand_map = await ranking_read.load_candidates_by_ids(
        session,
        job_ids=[a.target_id for a in active_jobs],
        persona="guest",
        is_authenticated=False,
        locale=locale,
    )
    missing_logo = 0
    broken_target = 0
    for a in active_jobs:
        cand = cand_map.get(a.target_id)
        if cand is None:
            broken_target += 1  # active sponsored placement whose job is now hidden
        elif not cand.has_logo:
            missing_logo += 1

    policy_flags: list[dict] = []
    if broken_target > 0:
        policy_flags.append(
            {"code": "sponsored_target_unavailable", "count": broken_target}
        )
    if missing_logo > 0:
        policy_flags.append({"code": "sponsored_missing_logo", "count": missing_logo})

    events = await _event_health(session, now=now)
    if events["zero_ctr_outliers"]:
        policy_flags.append(
            {"code": "zero_ctr_surface", "count": len(events["zero_ctr_outliers"])}
        )

    return {
        "rails": rails,
        "empty_rails": empty_rails,
        "sponsored": {
            "active_count": sponsored_active,
            "active_job_count": len(active_jobs),
            "missing_logo_count": missing_logo,
            "broken_target_count": broken_target,
        },
        "events": events,
        "policy_flags": policy_flags,
    }
