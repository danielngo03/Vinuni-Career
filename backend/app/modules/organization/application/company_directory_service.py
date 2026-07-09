"""Public company directory (unauthenticated career-marketplace surface).

Only **partner** orgs that are **active** and not soft-deleted are ever exposed;
university orgs and pending/suspended partners are invisible (and a direct slug
lookup for them returns ``404`` — indistinguishable from missing, no enumeration).
Projections come exclusively from :mod:`public_presenters`, so no internal field
(status of pending/suspended orgs, subscription tier, settings, RBAC, tax/contact
data, storage paths) can leak.

``active_job_count`` and the per-company ``active_jobs`` list come from the
``opportunities`` public-read facade — this module never imports the ``Job`` ORM
or re-derives the visibility predicate, so the directory cannot drift from the
public jobs list.
"""

from __future__ import annotations

import uuid

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.application import public_read
from app.modules.organization.api import public_presenters
from app.modules.organization.domain.models import Organization
from app.shared.exceptions import ResourceNotFoundError
from app.shared.pagination import clamp_limit, decode_cursor, encode_cursor

# Cap of open roles embedded in a company profile.
_MAX_ACTIVE_JOBS = 20

_PARTNER = "partner"
_ACTIVE = "active"


def _base_query():
    """Select only publicly listable companies (active partners, not deleted)."""

    return select(Organization).where(
        Organization.org_type == _PARTNER,
        Organization.status == _ACTIVE,
        Organization.deleted_at.is_(None),
    )


def _decode_offset(cursor: str | None) -> int:
    decoded = decode_cursor(cursor)
    if decoded is None:
        return 0
    try:
        offset = int(decoded["offset"])
    except (KeyError, TypeError, ValueError):
        return 0
    return max(offset, 0)


async def list_companies(
    session: AsyncSession,
    *,
    q: str | None = None,
    industry: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> tuple[list[dict], str | None, int, int]:
    """Offset-paginated directory page. Returns (items, next_cursor, limit, total).

    Ordering: verified first, then most open roles, then name. ``active_job_count``
    is computed in the same query via a correlated subquery from the opportunities
    facade (no N+1).
    """

    page_limit = clamp_limit(limit)
    offset = _decode_offset(cursor)

    count_col = public_read.visible_job_count_subquery(Organization.id)

    filters = []
    if q and q.strip():
        term = f"%{q.strip()}%"
        filters.append(
            or_(
                Organization.display_name.ilike(term),
                Organization.industry.ilike(term),
            )
        )
    if industry and industry.strip():
        filters.append(Organization.industry == industry.strip())

    total = (
        await session.execute(_base_query().with_only_columns(func.count()).where(*filters))
    ).scalar_one()

    stmt = (
        _base_query()
        .add_columns(count_col.label("active_job_count"))
        .where(*filters)
        .order_by(
            desc(Organization.is_verified),
            desc("active_job_count"),
            asc(Organization.display_name),
        )
        .offset(offset)
        .limit(page_limit + 1)
    )
    raw_rows = (await session.execute(stmt)).all()
    rows: list[tuple[Organization, int]] = [(org, int(count or 0)) for org, count in raw_rows]

    has_more = len(rows) > page_limit
    page_rows = rows[:page_limit]

    # Batch-fetch ratings so the directory can show aggregate star scores.
    # One query for the whole page (no N+1).
    from app.modules.reviews.application import company_rating_facade  # lazy import

    org_ids = [org.id for org, _ in page_rows]
    ratings = await company_rating_facade.ratings_for(session, org_ids) if org_ids else {}

    items = [
        public_presenters.directory_summary(
            org,
            active_job_count=count or 0,
            rating=ratings.get(org.id),
        )
        for org, count in page_rows
    ]
    next_cursor = encode_cursor({"offset": offset + page_limit}) if has_more else None
    return items, next_cursor, page_limit, total


async def get_listable_org_by_slug(session: AsyncSession, *, slug: str) -> Organization | None:
    """Return the org for ``slug`` iff it is publicly listable, else ``None``.

    Single source of the public-visibility predicate so logo delivery, the
    company profile, and the directory cannot drift (a suspended/pending/
    university org is never resolvable here).
    """

    return (
        await session.execute(_base_query().where(Organization.slug == slug))
    ).scalar_one_or_none()


async def get_company(session: AsyncSession, *, slug: str, locale: str = "vi") -> dict:
    """Public company profile by slug, or ``404`` if not a listable partner."""

    org = await get_listable_org_by_slug(session, slug=slug)
    if org is None:
        raise ResourceNotFoundError()

    active_jobs = await public_read.list_public_job_summaries_for_org(
        session, org_id=org.id, limit=_MAX_ACTIVE_JOBS, locale=locale
    )
    count_col = public_read.visible_job_count_subquery(Organization.id)
    active_job_count = (
        await session.execute(select(count_col).where(Organization.id == org.id))
    ).scalar_one()

    # Company review aggregate via the reviews facade (read model only — no live
    # JOIN over reviews on this guest surface, and no reviews ORM imported here).
    from app.modules.reviews.application import company_rating_facade

    ratings = await company_rating_facade.ratings_for(session, [org.id])

    return public_presenters.company_detail(
        org,
        active_job_count=active_job_count or 0,
        active_jobs=active_jobs,
        rating=ratings.get(org.id),
    )


async def list_spotlight_companies(session: AsyncSession, *, limit: int) -> list[dict]:
    """Verified-first companies for the marketplace spotlight rail."""

    count_col = public_read.visible_job_count_subquery(Organization.id)
    stmt = (
        _base_query()
        .add_columns(count_col.label("active_job_count"))
        .order_by(
            desc(Organization.is_verified),
            desc("active_job_count"),
            asc(Organization.display_name),
        )
        .limit(max(limit, 0))
    )
    raw_rows = (await session.execute(stmt)).all()
    rows: list[tuple[Organization, int]] = [(org, int(count or 0)) for org, count in raw_rows]
    return [
        public_presenters.directory_summary(org, active_job_count=count or 0) for org, count in rows
    ]


async def list_recommended_companies(
    session: AsyncSession,
    *,
    seed_company_ids: list[uuid.UUID],
    industries: list[str] | None = None,
    limit: int,
) -> list[dict]:
    """Public companies ranked from coarse session signals.

    Uses only public company metadata: recently viewed company IDs and industry
    interests. If no session signal is available, this degrades to the normal
    verified/open-role ordering rather than fabricating personalization.
    """

    page_limit = max(limit, 0)
    if page_limit == 0:
        return []

    count_col = public_read.visible_job_count_subquery(Organization.id)
    normalized_industries = {
        value.strip().lower()
        for value in (industries or [])
        if isinstance(value, str) and value.strip()
    }

    seed_industries: set[str] = set()
    if seed_company_ids:
        seed_rows = list(
            (await session.execute(_base_query().where(Organization.id.in_(seed_company_ids))))
            .scalars()
            .all()
        )
        seed_industries = {
            org.industry.strip().lower()
            for org in seed_rows
            if org.industry and org.industry.strip()
        }

    interest_industries = seed_industries | normalized_industries
    stmt = (
        _base_query()
        .add_columns(count_col.label("active_job_count"))
        .order_by(
            desc(Organization.is_verified),
            desc("active_job_count"),
            asc(Organization.display_name),
        )
        .limit(max(page_limit * 4, 12))
    )
    raw_rows = (await session.execute(stmt)).all()
    rows: list[tuple[Organization, int]] = [(org, int(count or 0)) for org, count in raw_rows]

    def score(row: tuple[Organization, int]) -> tuple[int, int, str]:
        org, count = row
        industry = org.industry.strip().lower() if org.industry else ""
        value = 0
        if org.id in seed_company_ids:
            value += 5
        if industry and industry in interest_industries:
            value += 4
        if org.is_verified:
            value += 2
        value += min(count or 0, 3)
        return (-value, -(count or 0), org.display_name.lower())

    ranked = sorted(rows, key=score)[:page_limit]
    return [
        public_presenters.directory_summary(org, active_job_count=count or 0)
        for org, count in ranked
    ]


async def count_public_companies(session: AsyncSession) -> int:
    """Number of publicly listable partner companies."""

    return (await session.execute(_base_query().with_only_columns(func.count()))).scalar_one()
