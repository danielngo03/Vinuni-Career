"""Job search/discovery service: industry scope, filters, public + owner lists.

Public discovery (:func:`list_public_jobs`) returns **only** jobs that are
published and visible to the principal's tier (``docs/BUSINESS_LOGIC.md`` §5);
``total`` reflects visible+matching records only. Logged-in students/alumni get
a per-job CV fit summary attached.

Extracted verbatim from the former monolithic ``job_service``; behaviour is
byte-for-byte identical. Shared helpers live in
:mod:`app.modules.opportunities.application.job_common`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import Select, String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import job_fit as cv_job_fit
from app.ai.cv import skill_translation
from app.core.config import get_settings
from app.modules.documents.application import cv_ranking_facade
from app.modules.opportunities.api import presenters
from app.modules.opportunities.application import (
    public_read,
    saved_jobs_service,
)
from app.modules.opportunities.application.errors import (
    InvalidIndustryFilterError,
)
from app.modules.opportunities.application.job_common import (
    _RESOURCE,
    _now,
    _public_filter,
)
from app.modules.opportunities.domain.industry_models import Industry
from app.modules.opportunities.domain.models import Job
from app.shared.exceptions import ResourceNotFoundError
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal, permission_checker


async def resolve_industry_scope(
    session: AsyncSession,
    *,
    industry_group_id: uuid.UUID | None,
    industry_id: uuid.UUID | None,
    specialization_id: uuid.UUID | None,
) -> list[uuid.UUID] | None:
    """Resolve the canonical deepest-scope industry filter to a job-matching id set.

    Public discovery query contract (``docs/API_CONTRACTS.md``): exactly one of
    the three params may be given at a time. Returns ``None`` when none are
    given (no industry filter applied). Only 3 taxonomy levels exist (0/1/2),
    so descendant expansion never needs more than 2 extra hops (children +
    grandchildren) — no recursive CTE required.

    - ``industry_group_id`` (level 0): node + all level-1/level-2 descendants.
    - ``industry_id`` (level 1): node + its level-2 children.
    - ``specialization_id`` (level 2): exact node only (no expansion).
    """

    provided = [
        (value, param, level)
        for value, param, level in (
            (industry_group_id, "industry_group_id", 0),
            (industry_id, "industry_id", 1),
            (specialization_id, "specialization_id", 2),
        )
        if value is not None
    ]
    if not provided:
        return None
    if len(provided) > 1:
        raise InvalidIndustryFilterError(reason="multiple_scope")

    value, param, level = provided[0]
    node = (
        await session.execute(select(Industry).where(Industry.id == value))
    ).scalar_one_or_none()
    if node is None or not node.is_active:
        raise InvalidIndustryFilterError(reason="not_found", param=param)
    if node.level != level:
        raise InvalidIndustryFilterError(reason="level_mismatch", param=param)

    if level == 2:
        return [node.id]

    children = list(
        (
            await session.execute(
                select(Industry.id).where(
                    Industry.parent_id == node.id, Industry.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    ids = [node.id, *children]
    if level == 0 and children:
        grandchildren = list(
            (
                await session.execute(
                    select(Industry.id).where(
                        Industry.parent_id.in_(children), Industry.is_active.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        ids.extend(grandchildren)
    return ids


def _apply_search_filters(
    stmt: Select,
    *,
    q: str | None,
    employment_type: str | None,
    location_type: str | None,
    location_types: str | None = None,
    province_code: str | None = None,
    ward_code: str | None = None,
    province_codes: str | None = None,
    ward_codes: str | None = None,
    # Deprecated free-text industry search — kept for backward compat. The
    # canonical `industry_ids` (resolved from industry_group_id/industry_id/
    # specialization_id via `resolve_industry_scope`) takes precedence over
    # this when provided.
    industry_terms: str | None = None,
    industry_ids: list[uuid.UUID] | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    experience_min_years: int | None = None,
    experience_max_years: int | None = None,
    posted_within_days: int | None = None,
    use_jsonb: bool = True,
) -> Select:
    """Apply optional marketplace search/filters to a public job query."""

    if industry_ids is not None:
        stmt = stmt.where(Job.industry_id.in_(industry_ids))
    if q:
        term = f"%{q.strip()}%"
        # ``required_skills`` is JSON; cast to text for a partial keyword match.
        stmt = stmt.where(
            or_(
                Job.title.ilike(term),
                func.cast(Job.required_skills, String).ilike(term),
            )
        )
    if employment_type:
        stmt = stmt.where(Job.employment_type == employment_type)
    if location_type:
        stmt = stmt.where(Job.location_type == location_type)
    location_type_values = _split_codes(location_types)
    if location_type_values:
        stmt = stmt.where(Job.location_type.in_(location_type_values))
    if province_code:
        stmt = _location_contains(stmt, "province_code", province_code, use_jsonb)
    if ward_code:
        stmt = _location_contains(stmt, "ward_code", ward_code, use_jsonb)
    province_values = _split_codes(province_codes)
    if province_values:
        stmt = _location_contains_any(stmt, "province_code", province_values, use_jsonb)
    ward_values = _split_codes(ward_codes)
    if ward_values:
        stmt = _location_contains_any(stmt, "ward_code", ward_values, use_jsonb)
    industry_values = _split_codes(industry_terms)
    if industry_values:
        clauses = []
        for value in industry_values:
            term = f"%{value}%"
            clauses.extend(
                [
                    Job.title.ilike(term),
                    Job.description.ilike(term),
                    Job.requirements.ilike(term),
                    func.cast(Job.required_skills, String).ilike(term),
                    func.cast(Job.preferred_skills, String).ilike(term),
                ]
            )
        stmt = stmt.where(or_(*clauses))
    if salary_min is not None:
        stmt = stmt.where(
            Job.salary_is_disclosed.is_(True),
            or_(Job.salary_max.is_(None), Job.salary_max >= salary_min),
        )
    if salary_max is not None:
        stmt = stmt.where(
            Job.salary_is_disclosed.is_(True),
            or_(Job.salary_min.is_(None), Job.salary_min <= salary_max),
        )
    if experience_min_years is not None:
        stmt = stmt.where(
            or_(
                Job.experience_max_years.is_(None),
                Job.experience_max_years >= experience_min_years,
            )
        )
    if experience_max_years is not None:
        stmt = stmt.where(
            or_(
                Job.experience_min_years.is_(None),
                Job.experience_min_years <= experience_max_years,
            )
        )
    if posted_within_days is not None:
        cutoff = _now() - timedelta(days=posted_within_days)
        stmt = stmt.where(Job.published_at >= cutoff)
    return stmt


def _split_codes(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _location_contains(stmt: Select, field: str, value: str, use_jsonb: bool) -> Select:
    if use_jsonb:
        # PostgreSQL JSONB @> containment: match any location item with field=value.
        needle = cast([{field: value}], JSONB)
        return stmt.where(cast(Job.locations, JSONB).op("@>")(needle))
    # SQLite test/local fallback. The production path above remains JSONB-indexable.
    return stmt.where(cast(Job.locations, String).ilike(f'%"{field}":%"{value}"%'))


def _location_contains_any(stmt: Select, field: str, values: list[str], use_jsonb: bool) -> Select:
    clauses = []
    for value in values:
        if use_jsonb:
            needle = cast([{field: value}], JSONB)
            clauses.append(cast(Job.locations, JSONB).op("@>")(needle))
        else:
            clauses.append(cast(Job.locations, String).ilike(f'%"{field}":%"{value}"%'))
    return stmt.where(or_(*clauses))


def _public_sort_order(sort: str | None) -> list:
    """Return deterministic sort clauses for public page-based discovery."""

    match sort:
        case "salary_high":
            return [
                Job.salary_is_disclosed.desc(),
                Job.salary_max.desc().nullslast(),
                Job.salary_min.desc().nullslast(),
                Job.published_at.desc(),
                Job.id.desc(),
            ]
        case "salary_low":
            return [
                Job.salary_is_disclosed.desc(),
                Job.salary_min.asc().nullslast(),
                Job.salary_max.asc().nullslast(),
                Job.published_at.desc(),
                Job.id.desc(),
            ]
        case "deadline_soon":
            return [
                Job.application_deadline.asc().nullslast(),
                Job.published_at.desc(),
                Job.id.desc(),
            ]
        case "featured":
            return [
                Job.is_featured.desc(),
                Job.is_sponsored.desc(),
                Job.published_at.desc(),
                Job.id.desc(),
            ]
        case "newest":
            return [Job.published_at.desc(), Job.id.desc()]
        case _:
            return [
                Job.is_featured.desc(),
                Job.is_sponsored.desc(),
                Job.published_at.desc(),
                Job.id.desc(),
            ]


def _fit_tier(score: int | None) -> str:
    if score is None:
        return "no_cv"
    if score >= 85:
        return "strong"
    if score >= 70:
        return "good"
    if score >= 50:
        return "possible"
    return "weak"


def _job_fit_projection(job: Job) -> dict:
    """Requirements projection for discovery-card fit scoring.

    MUST stay field-for-field aligned with ``job_fit_read.load_job_for_fit`` (the
    detail/store path) and ``job_fit_batch_service._job_projection`` so the
    discovery card's score / recommended_cv / gaps are identical to the detail and
    batch paths. In particular it carries ``cv_language_required`` (drives the "CV
    language preferred" soft gap) and the internal ``version`` stamp — omitting
    either made discovery diverge from the store-backed paths.
    """
    jd_text = " ".join(
        part for part in (job.title, job.description, job.requirements, job.benefits) if part
    )
    return {
        "id": str(job.id),
        # Internal content-version stamp for the persisted fit store (never surfaced).
        "version": job.version,
        "title": job.title,
        "description": job.description,
        "requirements": job.requirements,
        "benefits": job.benefits,
        "required_skills": list(job.required_skills or []),
        "preferred_skills": list(job.preferred_skills or []),
        "employment_type": job.employment_type,
        "experience_min_years": job.experience_min_years,
        "experience_max_years": job.experience_max_years,
        "experience_mode": job.experience_mode,
        "degree_required": job.degree_required,
        "seniority_level": job.seniority_level,
        "candidate_requirements": dict(job.candidate_requirements or {}),
        "location_type": job.location_type,
        "location_city": job.location_city,
        "location_country": job.location_country,
        "locations": list(job.locations or []),
        "cv_language_required": getattr(job, "cv_language_required", "any") or "any",
        "jd_text": jd_text,
    }


def _empty_student_fit() -> dict:
    return {
        "score": None,
        "tier": "no_cv",
        "recommended_cv_id": None,
        "recommended_cv_title": None,
        "matched_skills": [],
        "gap_count": 0,
        "signal": "no_cv",
        "bands": None,
    }


async def _attach_student_fit(
    session: AsyncSession,
    *,
    principal: Principal,
    jobs: list[Job],
    items: list[dict],
) -> list[dict]:
    """Attach per-job CV fit summary for logged-in students/alumni."""

    if not principal.is_authenticated or principal.persona not in {"student", "alumni"}:
        return items
    try:
        cv_inputs = await cv_ranking_facade.build_cv_inputs(session, principal=principal)
    except Exception:
        return items

    by_id = {str(job.id): job for job in jobs}
    for item in items:
        job = by_id.get(str(item.get("id") or ""))
        if job is None:
            continue
        if not cv_inputs:
            item["student_fit"] = _empty_student_fit()
            continue
        job_dict = _job_fit_projection(job)
        # Cross-lingual (VN↔EN) matching: translate every JD/CV skill term to
        # canonical English and append the English forms before scoring. Gated on
        # AI availability + best-effort (offline / error -> inputs unchanged ->
        # pure lexical). This discovery path recomputes per request (no persisted
        # store), but the in-process + DB translation cache keeps unique terms warm
        # across cards, so steady-state translation cost is ~0.
        # Discovery recomputes per request and does NOT persist to the store, so a
        # degraded (translation-failed) result simply retries on the next request —
        # no provisional caching needed here.
        # CACHE-ONLY: the discovery list scores every visible job per request. A
        # synchronous model translation per job would stall the list for tens of
        # seconds, so we use only already-warm translations here; uncached terms
        # fall back to pure lexical. The single-job detail path warms the cache.
        aug_job, aug_cv_inputs, _aug_complete = await skill_translation.english_augment(
            job_dict, cv_inputs, allow_model_calls=False
        )
        outcome = cv_job_fit.evaluate(
            aug_job,
            aug_cv_inputs,
            stale_days=get_settings().cv_stale_after_days,
        )
        best = outcome.results[0] if outcome.results else None
        item["student_fit"] = {
            "score": best.score if best else None,
            "tier": _fit_tier(best.score if best else None),
            "recommended_cv_id": outcome.recommended_cv_id,
            "recommended_cv_title": best.title if best else None,
            "matched_skills": list(best.matched_skills[:5]) if best else [],
            "gap_count": len(best.gaps) if best else 0,
            "signal": outcome.signal if best else "no_cv",
            "bands": best.bands.as_dict() if best else None,
            "cv_scores": [
                {
                    "cv_id": fit.cv_id,
                    "title": fit.title,
                    "score": fit.score,
                    "tier": _fit_tier(fit.score),
                    "bands": fit.bands.as_dict(),
                    "matched_skills": list(fit.matched_skills[:5]),
                    "gap_count": len(fit.gaps),
                    "stale": fit.stale,
                    "recommended": fit.cv_id == outcome.recommended_cv_id,
                }
                for fit in outcome.results
            ],
        }
    return items


async def list_public_jobs(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    page: int | None = None,
    limit: int | None = None,
    q: str | None = None,
    employment_type: str | None = None,
    location_type: str | None = None,
    location_types: str | None = None,
    province_code: str | None = None,
    ward_code: str | None = None,
    province_codes: str | None = None,
    ward_codes: str | None = None,
    industry_terms: str | None = None,
    industry_group_id: uuid.UUID | None = None,
    industry_id: uuid.UUID | None = None,
    specialization_id: uuid.UUID | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    experience_min_years: int | None = None,
    experience_max_years: int | None = None,
    posted_within_days: int | None = None,
    sort: str | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int, int]:
    """Public discovery list. Returns (items, next, limit, total).

    ``total`` reflects only records visible to the principal's tier *and* matching
    the optional location and job-type filters.
    """

    now = _now()
    page_limit = clamp_limit(limit)
    bind = session.get_bind()
    use_jsonb = bind.dialect.name == "postgresql"

    industry_ids = await resolve_industry_scope(
        session,
        industry_group_id=industry_group_id,
        industry_id=industry_id,
        specialization_id=specialization_id,
    )

    def _filtered(base: Select) -> Select:
        return _apply_search_filters(
            _public_filter(base, principal=principal, now=now),
            q=q,
            employment_type=employment_type,
            location_type=location_type,
            location_types=location_types,
            province_code=province_code,
            ward_code=ward_code,
            province_codes=province_codes,
            ward_codes=ward_codes,
            industry_terms=industry_terms,
            industry_ids=industry_ids,
            salary_min=salary_min,
            salary_max=salary_max,
            experience_min_years=experience_min_years,
            experience_max_years=experience_max_years,
            posted_within_days=posted_within_days,
            use_jsonb=use_jsonb,
        )

    total = (await session.execute(_filtered(select(func.count()).select_from(Job)))).scalar_one()

    stmt = _filtered(select(Job))
    if page is not None:
        offset = max(page - 1, 0) * page_limit
        stmt = stmt.order_by(*_public_sort_order(sort))
        stmt = stmt.offset(offset).limit(page_limit)
        rows = list((await session.execute(stmt)).scalars().all())
        saved_ids = await saved_jobs_service.get_saved_ids(session, principal=principal)
        items = await public_read.enrich_summaries(
            session, rows, locale=locale, saved_ids=saved_ids
        )
        items = await _attach_student_fit(session, principal=principal, jobs=rows, items=items)
        return items, None, page_limit, total

    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_published = datetime.fromisoformat(decoded["published_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                Job.published_at < anchor_published,
                (Job.published_at == anchor_published) & (Job.id < anchor_id),
            )
        )
    stmt = stmt.order_by(Job.published_at.desc(), Job.id.desc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    cursor_page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda j: {
            "published_at": j.published_at.isoformat(),
            "id": str(j.id),
        },
    )
    saved_ids = await saved_jobs_service.get_saved_ids(session, principal=principal)
    items = await public_read.enrich_summaries(
        session, cursor_page.items, locale=locale, saved_ids=saved_ids
    )
    items = await _attach_student_fit(
        session, principal=principal, jobs=cursor_page.items, items=items
    )
    return items, cursor_page.next_cursor, cursor_page.limit, total


async def list_my_jobs(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    """Partner-scoped list of the caller org's own jobs (all statuses)."""

    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=principal.org_id)
    page_limit = clamp_limit(limit)
    stmt = select(Job).where(Job.org_id == principal.org_id, Job.deleted_at.is_(None))
    if status is not None:
        stmt = stmt.where(Job.status == status)

    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_created = datetime.fromisoformat(decoded["created_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                Job.created_at < anchor_created,
                (Job.created_at == anchor_created) & (Job.id < anchor_id),
            )
        )
    stmt = stmt.order_by(Job.created_at.desc(), Job.id.desc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda j: {
            "created_at": j.created_at.isoformat(),
            "id": str(j.id),
        },
    )

    # Live recruiting funnel counts (unreviewed / in-pipeline) per job — TWO batched
    # grouped queries for the whole page (no per-job N+1). Read through the
    # recruitment facade so this module never imports the Application ORM (lazy
    # import keeps the opportunities <-> recruitment boundary acyclic).
    from app.modules.recruitment.application import job_application_stats_facade
    from app.modules.users.application import user_read_facade

    stats = await job_application_stats_facade.application_stats_for_jobs(
        session, [j.id for j in page.items]
    )
    # Owner (poster) display names — ONE batched users-facade lookup for the page.
    owner_names = await user_read_facade.get_full_names(
        session, [j.posted_by for j in page.items]
    )

    empty_stats = job_application_stats_facade.JobAppStats()
    items = [
        presenters.owner_job_summary(
            j,
            locale=locale,
            unreviewed_count=stats.get(j.id, empty_stats).unreviewed,
            in_pipeline_count=stats.get(j.id, empty_stats).in_pipeline,
            owner_name=owner_names.get(j.posted_by),
        )
        for j in page.items
    ]
    return items, page.next_cursor, page.limit
