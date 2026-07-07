"""Internal org read facade for cross-module reporting/permission/embed surfaces.

Other modules (e.g. ``career_outcomes`` university reporting, ``opportunities`` /
``recruitment`` / ``dashboards`` / ``messaging`` / ``advertising`` / ``billing`` /
``ai_settings`` / ``discovery`` / ``reviews`` / ``documents`` / ``users``) resolve
org shape by id through this seam instead of importing the ``Organization`` ORM,
so the module boundary holds (`docs/ARCHITECTURE.md`: communicate through
interfaces/read models).

Three shapes are exposed, from narrowest to widest:

- :func:`org_type_for` / :func:`is_university_org` — the single field the
  ubiquitous "acting principal's org must be a university" permission gate needs.
- :func:`display_name_for` / :func:`display_names_for` — the non-sensitive name
  used in list/detail projections and notification copy.
- :func:`summary_for` / :func:`summaries_for` — the small public-safe
  :class:`OrgSummary` embedded in job/event cards (mirrors
  ``organization.api.public_presenters.company_block``); never exposes raw
  ``logo_path``, ``status``, ``subscription_tier``, or RBAC/settings internals.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.organization.domain.models import (
    Membership,
    MembershipDepartment,
    Organization,
)

_FALLBACK = "VinUni Career"
_UNIVERSITY = "university"


async def display_names_for(
    session: AsyncSession, org_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Batch-resolve ``{org_id: display_name}`` for the given ids.

    Missing ids are simply absent from the result; callers fall back as needed.
    One query regardless of how many ids are requested.
    """

    ids = {i for i in org_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Organization.id, Organization.display_name).where(
                Organization.id.in_(ids)
            )
        )
    ).all()
    return {row.id: (row.display_name or _FALLBACK) for row in rows}


async def display_name_for(
    session: AsyncSession, org_id: uuid.UUID | None
) -> str | None:
    """Single-org display name lookup, or ``None`` if missing/``org_id`` is ``None``."""

    if org_id is None:
        return None
    return (
        await session.execute(
            select(Organization.display_name).where(Organization.id == org_id)
        )
    ).scalar_one_or_none()


async def org_type_for(session: AsyncSession, org_id: uuid.UUID | None) -> str | None:
    """The raw ``org_type`` (``partner`` | ``university``), or ``None`` if missing."""

    if org_id is None:
        return None
    return (
        await session.execute(
            select(Organization.org_type).where(Organization.id == org_id)
        )
    ).scalar_one_or_none()


async def is_university_org(session: AsyncSession, org_id: uuid.UUID | None) -> bool:
    """``True`` iff ``org_id`` resolves to a ``university``-type org.

    The shared shape of the "caller must be acting from a university org" RBAC
    gate repeated across moderation/reporting services platform-wide.
    """

    return await org_type_for(session, org_id) == _UNIVERSITY


async def trust_snapshot_for(
    session: AsyncSession, org_id: uuid.UUID | None
) -> dict | None:
    """Fraud-signal-relevant trust facts for one org, or ``None`` if missing.

    Returns ``{"created_at": datetime, "is_verified": bool}`` only — the
    minimal projection the moderation fraud scanner needs, never the full row.
    """

    if org_id is None:
        return None
    row = (
        await session.execute(
            select(Organization.created_at, Organization.is_verified).where(
                Organization.id == org_id
            )
        )
    ).first()
    if row is None:
        return None
    return {"created_at": row.created_at, "is_verified": bool(row.is_verified)}


@dataclass(frozen=True)
class OrgSummary:
    """Public-safe embedded-company shape (mirrors ``public_presenters.company_block``
    plus the handful of extra fields job-fit/ranking/detail read models need)."""

    id: uuid.UUID
    slug: str
    display_name: str
    org_type: str
    is_verified: bool
    has_logo: bool
    logo_url: str | None
    trust_level: str | None = None
    industry: str | None = None
    company_size: str | None = None
    headquarters_city: str | None = None
    website_url: str | None = None
    description: str | None = None
    founded_year: int | None = None
    verified_at: datetime | None = None
    rating: dict | None = None


def _to_summary(org: Organization, *, rating: dict | None = None) -> OrgSummary:
    logo_url = None
    if org.logo_path:
        base = get_settings().app_url.rstrip("/")
        logo_url = f"{base}/api/v1/companies/{org.slug}/logo?v={org.version}"
    return OrgSummary(
        id=org.id,
        slug=org.slug,
        display_name=org.display_name,
        org_type=org.org_type,
        is_verified=org.is_verified,
        has_logo=bool(org.logo_path),
        logo_url=logo_url,
        trust_level=org.trust_level,
        industry=org.industry,
        company_size=org.company_size,
        headquarters_city=org.headquarters_city,
        website_url=org.website_url,
        description=org.description,
        founded_year=org.founded_year,
        verified_at=org.verified_at,
        rating=rating,
    )


async def summary_for(
    session: AsyncSession, org_id: uuid.UUID | None
) -> OrgSummary | None:
    """Single-org public-safe summary, or ``None`` if missing/``org_id`` is ``None``."""

    if org_id is None:
        return None
    org = (
        await session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        return None
    from app.modules.reviews.application import company_rating_facade

    ratings = await company_rating_facade.ratings_for(session, [org.id])
    return _to_summary(org, rating=ratings.get(org.id))


async def summaries_for(
    session: AsyncSession, org_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, OrgSummary]:
    """Batch-resolve ``{org_id: OrgSummary}`` for the given ids."""

    ids = {i for i in org_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(select(Organization).where(Organization.id.in_(ids)))
    ).scalars().all()
    from app.modules.reviews.application import company_rating_facade

    ratings = await company_rating_facade.ratings_for(session, ids)
    return {org.id: _to_summary(org, rating=ratings.get(org.id)) for org in rows}


async def active_member_ids(
    session: AsyncSession, *, org_id: uuid.UUID, user_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    """The subset of ``user_ids`` that are ACTIVE members of ``org_id``."""

    ids = {i for i in user_ids if i is not None}
    if not ids:
        return set()
    rows = (
        await session.execute(
            select(Membership.user_id).where(
                Membership.org_id == org_id,
                Membership.user_id.in_(ids),
                Membership.status == "active",
            )
        )
    ).scalars().all()
    return set(rows)


async def search_orgs(
    session: AsyncSession, *, q: str | None, page: int = 1, page_size: int = 30
) -> dict:
    """Staff org lookup (platform-support console): name/slug search, admin-safe
    fields only (verification/suspension/package state — never raw RBAC/settings
    internals). Mirrors ``users.admin_users_service.list_platform_users`` shape.
    """

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    stmt = select(Organization)
    if q:
        q_like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Organization.display_name).like(q_like),
                func.lower(Organization.slug).like(q_like),
            )
        )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one() or 0

    stmt = stmt.order_by(Organization.created_at.desc()).offset(offset).limit(page_size)
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        {
            "id": str(org.id),
            "slug": org.slug,
            "display_name": org.display_name,
            "org_type": org.org_type,
            "status": org.status,
            "is_verified": org.is_verified,
            "trust_level": org.trust_level,
            "subscription_tier": org.subscription_tier,
            "created_at": org.created_at.isoformat() if org.created_at else None,
        }
        for org in rows
    ]
    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


def company_block(summary: OrgSummary | None) -> dict | None:
    """Tiny employer block embedded in a public job/event row; ``None`` if no org.

    Mirrors ``organization.api.public_presenters.company_block`` but takes the
    cross-module-safe :class:`OrgSummary` DTO instead of the ``Organization`` ORM.
    """

    if summary is None:
        return None
    return {
        "slug": summary.slug,
        "display_name": summary.display_name,
        "logo_url": summary.logo_url,
        "is_verified": summary.is_verified,
        "rating": summary.rating,
    }


async def department_ids_for_membership(
    session: AsyncSession, *, membership_id: uuid.UUID
) -> list[uuid.UUID]:
    """Department ids a membership belongs to (no ``MembershipDepartment`` export)."""

    rows = (
        await session.execute(
            select(MembershipDepartment.department_id).where(
                MembershipDepartment.membership_id == membership_id
            )
        )
    ).scalars().all()
    return list(rows)


async def department_ids_for_user_in_org(
    session: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID
) -> set[uuid.UUID]:
    """Department ids the user's active membership in ``org_id`` belongs to.

    Empty set if the user has no active membership in the org or no department
    assignment.
    """

    membership_id = (
        await session.execute(
            select(Membership.id).where(
                Membership.user_id == user_id, Membership.org_id == org_id
            )
        )
    ).scalar_one_or_none()
    if membership_id is None:
        return set()
    return set(await department_ids_for_membership(session, membership_id=membership_id))


async def primary_department_names_for_users(
    session: AsyncSession, *, org_id: uuid.UUID, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Best-effort ``user_id -> primary department name`` within one org.

    "Primary" is the alphabetically-first department the user's membership sits
    in — a deterministic single label for the operations workload-by-department
    roll-up (a moderator may belong to several departments). Users with no
    department are simply absent from the map (the caller buckets them as
    unassigned). One bounded join over the moderator set, not per user.
    """

    ids = [uid for uid in user_ids if uid is not None]
    if not ids:
        return {}

    from app.modules.organization.domain.models import Department  # local: avoid cycle

    rows = (
        await session.execute(
            select(Membership.user_id, Department.name)
            .join(MembershipDepartment, MembershipDepartment.membership_id == Membership.id)
            .join(Department, Department.id == MembershipDepartment.department_id)
            .where(Membership.org_id == org_id, Membership.user_id.in_(ids))
            .order_by(Membership.user_id, Department.name.asc())
        )
    ).all()

    primary: dict[uuid.UUID, str] = {}
    for user_id, dept_name in rows:
        # First row per user wins (ordered by name asc) -> alphabetical primary.
        if user_id not in primary:
            primary[user_id] = dept_name
    return primary
