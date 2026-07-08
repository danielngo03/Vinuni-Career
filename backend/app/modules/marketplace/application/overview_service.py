"""Read-only marketplace overview aggregator.

Composes the public homepage strip (``docs/SCREEN_SPECS.md`` §1.1) by calling
**only** the ``opportunities`` and ``organization`` public facades — it owns no
models, runs no migration, and never imports another module's ORM.

Honesty rules baked in:

- ``metrics`` is ``None`` (not faked) if any metric query raises, so the homepage
  hides the live aggregate strip instead of showing wrong numbers.
- ``jobs_trend`` (the 4th metric ``new_jobs_30d`` + its 30-day sparkline
  ``series`` + ``delta_pct``) is computed from real ``published_at`` timestamps
  via the **same** visibility predicate as ``active_jobs`` (so it can never
  drift). It is ``None`` (not faked) if its query raises — the other three
  metrics still return, never a 500. ``delta_pct`` is ``None`` when there is not
  enough history (no prior-period jobs) to compute an honest percentage; the
  ``series`` is still returned so the sparkline renders without a trend arrow.
- ``sponsored_jobs`` / ``featured_jobs`` come from the real ``is_sponsored`` /
  ``is_featured`` flags; when none exist the arrays are empty (sections hide) —
  never fabricated inventory.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.application import inventory_facade
from app.modules.discovery.application import frequency_cap, ranking_service
from app.modules.opportunities.application import (
    event_public_read,
    public_read,
    ranking_read,
)
from app.modules.organization.application import company_directory_service
from app.shared.permissions import GUEST, Principal

_SPONSORED_CAP = 3
_FEATURED_CAP = 3
_RECENT_CAP = 6
_SPOTLIGHT_CAP = 4
_UPCOMING_EVENTS_CAP = 6
_SPONSORED_EVENTS_CAP = 3
_FEATURED_EVENTS_CAP = 3
_RECOMMENDED_CAP = 6
_RECOMMENDED_EVENTS_CAP = 4
_POPULAR_ROLES_CAP = 8

# Static, honest trust content (NOT metrics). The frontend localizes each key; no
# fabricated numbers are ever attached here (spec §2/§6 trust modules).
_TRUST_MODULES: list[dict] = [
    {"key": "verified_by_vinuni"},
    {"key": "career_support"},
    {"key": "employer_quality"},
    {"key": "data_privacy"},
]

# Trailing window for the job-growth sparkline + delta. ``new_jobs_30d`` and the
# delta both derive from this single constant so the contract length is explicit.
_TREND_DAYS = 30


async def _metrics(session: AsyncSession) -> dict | None:
    """Live aggregate counts, or ``None`` if they cannot be computed."""

    try:
        active_jobs = await public_read.count_visible_jobs(session)
        companies = await company_directory_service.count_public_companies(session)
        open_for_applications = await public_read.count_open_for_applications(session)
    except Exception:  # noqa: BLE001 — strip is hidden on any failure, never faked
        return None
    return {
        "active_jobs": active_jobs,
        "companies": companies,
        "open_for_applications": open_for_applications,
    }


def _percent_change(current: int, prior: int) -> float | None:
    """Percent change of ``current`` vs the prior equivalent period.

    Returns ``None`` (never ``0`` or a fabricated number) when the prior period
    has no jobs — there is then no honest baseline to compute growth against, so
    the frontend hides the trend arrow.
    """

    if prior <= 0:
        return None
    return round((current - prior) / prior * 100, 1)


async def _jobs_trend(session: AsyncSession) -> dict | None:
    """Real 30-day job-growth trend, or ``None`` if it cannot be computed.

    Single grouped aggregate over the trailing 60 UTC days (current 30-day
    window + the prior 30 for the delta), zero-filled into a fixed-length
    ``series``. No per-row Python loop over the table — only the bounded window
    is read, grouped in SQL.
    """

    try:
        today = datetime.now(tz=UTC).date()
        window_start = today - timedelta(days=_TREND_DAYS - 1)  # 30 buckets incl. today
        prior_start = window_start - timedelta(days=_TREND_DAYS)
        fetch_start = datetime(
            prior_start.year, prior_start.month, prior_start.day, tzinfo=UTC
        )
        fetch_end = (
            datetime(today.year, today.month, today.day, tzinfo=UTC)
            + timedelta(days=1)
        )
        per_day = await public_read.published_per_day(
            session, start=fetch_start, end=fetch_end
        )
    except Exception:  # noqa: BLE001 — trend hidden on failure; metrics unaffected
        return None

    series: list[dict] = []
    current_total = 0
    for offset in range(_TREND_DAYS):
        day = window_start + timedelta(days=offset)
        count = per_day.get(day.isoformat(), 0)
        series.append({"date": day.isoformat(), "count": count})
        current_total += count

    # Prior equivalent period: the 30 days immediately before the window.
    window_key = window_start.isoformat()
    prior_key = prior_start.isoformat()
    prior_total = sum(
        n for day_key, n in per_day.items() if prior_key <= day_key < window_key
    )

    return {
        "new_jobs_30d": current_total,
        "series": series,
        "delta_pct": _percent_change(current_total, prior_total),
    }


# Primary public banner slots, in hero->rail order (spec §4/§5 V1 scope).
_BANNER_SLOTS = ("homepage_hero", "right_rail")


def _uuid_list(values: object, *, limit: int = 12) -> list[uuid.UUID]:
    """Parse first-party coarse signal IDs defensively."""

    if not isinstance(values, list):
        return []
    parsed: list[uuid.UUID] = []
    for value in values[:limit]:
        try:
            parsed.append(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return parsed


def _string_list(values: object, *, limit: int = 12) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values[:limit] if str(value).strip()]


async def _sponsored_banners(
    session: AsyncSession,
    *,
    locale: str,
    discovery_session_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[dict | None, dict | None]:
    """Resolve (hero_campaign, sponsored_banner) for the two primary slots.

    Each slot prefers a REAL active placement: the hero is the top live sponsored
    placement, the right-rail is the next (no duplication). Each banner carries
    the polished disclosure keyed by the placement's ``disclosure_class``, the
    eligibility-filtered job summary (a placement whose target is now hidden is
    dropped — never a broken banner), and — when one has been uploaded + approved
    — the slot CREATIVE (``image_url`` is the public serve route, never a storage
    key). When no partner placement fills a slot, a VinUni-curated fallback is
    used (labelled curated, NEVER paid) if one is configured; otherwise the slot
    is hidden. ``sponsored_disclosure`` is kept for backward compatibility.
    """

    try:
        capped = await frequency_cap.over_capped_placements(
            session, session_id=discovery_session_id, user_id=user_id
        )
        active = await inventory_facade.list_active_sponsored(
            session, target_type="job", limit=4, exclude_placement_ids=capped
        )
        cand_map = {}
        if active:
            cand_map = await ranking_read.load_candidates_by_ids(
                session,
                job_ids=[a.target_id for a in active],
                persona="guest",
                is_authenticated=False,
                locale=locale,
            )
        # Eligible placements only (target still visible).
        eligible = [a for a in active if cand_map.get(a.target_id) is not None]

        banners: list[dict | None] = []
        for idx, slot in enumerate(_BANNER_SLOTS):
            if idx < len(eligible):
                a = eligible[idx]
                creative = await inventory_facade.approved_creative_for_slot(
                    session, placement_id=a.placement_id, slot=slot, locale=locale
                )
                banners.append(
                    {
                        "placement_id": str(a.placement_id),
                        "slot": slot,
                        "source": "partner",
                        "target_type": "job",
                        "job": cand_map[a.target_id].summary,
                        "creative": creative,
                        "disclosure": inventory_facade.disclosure(
                            disclosure_class=a.disclosure_class, locale=locale
                        ),
                        # Backward-compat key (older consumers read this).
                        "sponsored_disclosure": inventory_facade.disclosure(
                            disclosure_class=a.disclosure_class, locale=locale
                        ),
                    }
                )
            else:
                banners.append(
                    inventory_facade.curated_fallback(slot, locale=locale)
                )
    except Exception:  # noqa: BLE001 — a sponsored-read failure hides the banner, never 500s
        return None, None
    return banners[0], banners[1]


async def _recommended_events(
    session: AsyncSession, *, session_tags: dict | None, locale: str
) -> list[dict]:
    """Upcoming events tagged with an honest ``source`` + reason codes."""

    event_ids = _uuid_list((session_tags or {}).get("event_ids"))
    if event_ids:
        related = await event_public_read.list_related_summaries(
            session,
            seed_event_ids=event_ids,
            limit=_RECOMMENDED_EVENTS_CAP,
            locale=locale,
        )
        if related:
            return [
                {
                    **row,
                    "source": "recommended",
                    "reason_codes": [{"code": "similar_role"}],
                }
                for row in related
            ]

    rows = await event_public_read.list_upcoming_summaries(
        session, limit=_RECOMMENDED_EVENTS_CAP, locale=locale
    )
    return [
        {**row, "source": "recent", "reason_codes": [{"code": "recent"}]}
        for row in rows
    ]


async def _recommended_companies(
    session: AsyncSession, *, session_tags: dict | None
) -> list[dict]:
    """Public companies ranked from company/industry session signals."""

    tags = session_tags or {}
    return await company_directory_service.list_recommended_companies(
        session,
        seed_company_ids=_uuid_list(tags.get("company_ids")),
        industries=_string_list(tags.get("industries")),
        limit=_SPOTLIGHT_CAP,
    )


async def get_overview(
    session: AsyncSession,
    *,
    locale: str = "vi",
    principal: Principal | None = None,
    session_tags: dict | None = None,
    discovery_session_id: uuid.UUID | None = None,
) -> dict:
    """Aggregate the public marketplace homepage payload.

    ``principal`` defaults to a guest; ``session_tags`` are the resolved
    first-party ``discovery_session`` coarse signals (or ``None``) used to
    personalize the ``recommended_jobs`` rail honestly. ``discovery_session_id``
    keys sponsored hero/rail frequency capping (see ``frequency_cap``).
    """

    principal = principal or GUEST
    metrics = await _metrics(session)
    jobs_trend = await _jobs_trend(session)
    sponsored = await public_read.list_sponsored_summaries(
        session, limit=_SPONSORED_CAP, locale=locale
    )
    featured = await public_read.list_featured_summaries(
        session, limit=_FEATURED_CAP, locale=locale
    )
    recent = await public_read.list_recent_summaries(
        session, limit=_RECENT_CAP, locale=locale
    )
    spotlight = await company_directory_service.list_spotlight_companies(
        session, limit=_SPOTLIGHT_CAP
    )
    # Events strip (ADR-0008 §4) — real, hide-if-empty: each array is empty when
    # nothing qualifies, so the homepage hides the section (no fabricated teaser).
    # Sourced ONLY through the events public-read facade (no event ORM here).
    upcoming_events = await event_public_read.list_upcoming_summaries(
        session, limit=_UPCOMING_EVENTS_CAP, locale=locale
    )
    sponsored_events = await event_public_read.list_sponsored_summaries(
        session, limit=_SPONSORED_EVENTS_CAP, locale=locale
    )
    featured_events = await event_public_read.list_featured_summaries(
        session, limit=_FEATURED_EVENTS_CAP, locale=locale
    )

    # --- Recommendation / sponsored delivery rails (spec §6/§8) ------------- #
    # The recommended rail uses the ranker (guest session signals or honest
    # recent/popular fallback). Sponsored inventory is delivered in its OWN
    # hero/banner/sponsored rails (with_sponsored=False here) so it is never
    # mixed into — and can never reorder — the organic recommended rail.
    try:
        recommended = await ranking_service.recommend_jobs(
            session,
            principal=principal,
            cookie_tags=session_tags,
            limit=_RECOMMENDED_CAP,
            locale=locale,
            with_sponsored=False,
        )
    except Exception:  # noqa: BLE001 — a ranker failure hides the rail, never 500s
        recommended = {"source": "recent", "personalized": False, "items": []}

    recommended_events = await _recommended_events(
        session, session_tags=session_tags, locale=locale
    )
    recommended_companies = await _recommended_companies(
        session, session_tags=session_tags
    )
    hero_campaign, sponsored_banner = await _sponsored_banners(
        session,
        locale=locale,
        discovery_session_id=discovery_session_id,
        user_id=principal.user_id if principal.is_authenticated else None,
    )
    employer_spotlight = await company_directory_service.list_spotlight_companies(
        session, limit=_SPOTLIGHT_CAP
    )
    try:
        popular_roles = await ranking_service.popular_roles(
            session, limit=_POPULAR_ROLES_CAP, locale=locale
        )
    except Exception:  # noqa: BLE001 — hide the rail on failure, never fabricate
        popular_roles = []

    return {
        "metrics": metrics,
        "jobs_trend": jobs_trend,
        # Existing rails (kept for backward compatibility).
        "sponsored_jobs": sponsored,
        "featured_jobs": featured,
        "recent_jobs": recent,
        "spotlight_companies": spotlight,
        "upcoming_events": upcoming_events,
        "sponsored_events": sponsored_events,
        "featured_events": featured_events,
        # Spec §8 explicit rails.
        "hero_campaign": hero_campaign,
        "recommended_jobs": recommended,
        "recommended_events": recommended_events,
        "recommended_companies": recommended_companies,
        "sponsored_banner": sponsored_banner,
        "employer_spotlight": employer_spotlight,
        "popular_roles": popular_roles,
        "trust_modules": _TRUST_MODULES,
    }
