"""Shared job-service helpers: validation, ownership, visibility, audit context.

Extracted from the former monolithic ``job_service`` so that the write, read,
and search services can share a single source of truth for slug generation,
field/mode validation, ownership loading, moderation checks, and public
visibility predicates without importing each other (avoids cycles).

RBAC is enforced in the calling services (not here); this module holds the
pure/loader helpers those services depend on. Behaviour is byte-for-byte
identical to the pre-split ``job_service`` implementation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.opportunities.api import schemas
from app.modules.opportunities.application.errors import (
    InvalidJobFieldError,
)
from app.modules.opportunities.application.visibility import apply_visible_filter
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade
from app.modules.organization.domain.catalog import slugify
from app.shared.audit import AuditContext
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "jobs"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


async def _unique_slug(session: AsyncSession, title: str) -> str:
    base = slugify(title)[:280] or "job"
    candidate = base
    suffix = 1
    while True:
        exists = (await session.execute(select(Job.id).where(Job.slug == candidate))).first()
        if exists is None:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


def _normalize_locations(payload: dict) -> None:
    """Sync multi-location array with legacy single-location fields.

    If `locations` is provided, the first item in the list is authoritative for
    the legacy `location_type / location_city / location_country` fields so that
    all downstream read paths that only look at those fields stay correct.
    """
    locs = payload.get("locations")
    if not locs:
        return
    primary = locs[0]
    payload["location_type"] = primary.get("type", payload.get("location_type", "onsite"))
    payload["location_city"] = primary.get("city") or payload.get("location_city")
    payload["location_country"] = primary.get("country", "Vietnam")


_SALARY_MODE_FIELDS = ("salary_mode", "salary_min", "salary_max", "salary_is_disclosed")
_EXPERIENCE_MODE_FIELDS = ("experience_mode", "experience_min_years", "experience_max_years")


def _effective(payload: dict, existing: Job | None, field: str, default: Any = None) -> Any:
    if field in payload:
        return payload[field]
    if existing is not None:
        return getattr(existing, field)
    return default


def _validate_salary_and_experience_modes(payload: dict, *, existing: Job | None) -> None:
    """Enforce salary_mode/experience_mode consistency against the *effective*
    (post-merge) row state, and make ``salary_mode`` authoritative over any
    client-sent ``salary_is_disclosed`` flag.

    On create, ``existing`` is ``None`` so "effective" == the create payload
    (already fully validated once by the Pydantic schema; this re-validation is
    cheap and keeps a single source of truth). On update (PATCH), ``payload``
    may only carry a subset of the salary/experience fields — the rest come
    from ``existing`` — so this is the only place the *complete* combination is
    actually checked.
    """

    if any(f in payload for f in _SALARY_MODE_FIELDS):
        salary_mode = _effective(payload, existing, "salary_mode")
        salary_min = _effective(payload, existing, "salary_min")
        salary_max = _effective(payload, existing, "salary_max")
        salary_is_disclosed = _effective(payload, existing, "salary_is_disclosed", False)
        try:
            _mode, disclosed = schemas.validate_salary_mode(
                salary_mode=salary_mode,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_is_disclosed=salary_is_disclosed,
            )
        except ValueError as exc:
            raise InvalidJobFieldError(field="salary_mode") from exc
        if salary_mode is not None:
            # Mode is authoritative: always persist the mode-derived disclosed
            # flag, never a client-sent value that could contradict it.
            payload["salary_is_disclosed"] = bool(disclosed)

    if any(f in payload for f in _EXPERIENCE_MODE_FIELDS):
        experience_mode = _effective(payload, existing, "experience_mode")
        experience_min = _effective(payload, existing, "experience_min_years")
        experience_max = _effective(payload, existing, "experience_max_years")
        try:
            schemas.validate_experience_mode(
                experience_mode=experience_mode,
                experience_min_years=experience_min,
                experience_max_years=experience_max,
            )
        except ValueError as exc:
            raise InvalidJobFieldError(field="experience_mode") from exc


def _validate_fields(payload: dict, *, existing: Job | None = None) -> None:
    _normalize_locations(payload)
    if payload.get("candidate_requirements") is None and "candidate_requirements" in payload:
        payload["candidate_requirements"] = {}
    et = payload.get("employment_type")
    if et is not None and et not in lifecycle.EMPLOYMENT_TYPES:
        raise InvalidJobFieldError(field="employment_type")
    lt = payload.get("location_type")
    if lt is not None and lt not in lifecycle.LOCATION_TYPES:
        raise InvalidJobFieldError(field="location_type")
    vis = payload.get("visibility")
    if vis is not None and vis not in lifecycle.VISIBILITY_LEVELS:
        raise InvalidJobFieldError(field="visibility")
    seniority = payload.get("seniority_level")
    if seniority is not None and seniority not in lifecycle.SENIORITY_LEVELS:
        raise InvalidJobFieldError(field="seniority_level")

    smin, smax = payload.get("salary_min"), payload.get("salary_max")
    if smin is not None and smax is not None and smin > smax:
        raise InvalidJobFieldError(field="salary_max")
    emin, emax = payload.get("experience_min_years"), payload.get("experience_max_years")
    if emin is not None and emax is not None and emin > emax:
        raise InvalidJobFieldError(field="experience_max_years")

    _validate_salary_and_experience_modes(payload, existing=existing)


# --------------------------------------------------------------------------- #
# Loading / ownership                                                         #
# --------------------------------------------------------------------------- #


async def _load_owned_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID, lock: bool = False
) -> Job:
    """Load a non-deleted job that ``principal`` owns; else ``404``.

    Cross-org access is indistinguishable from a missing resource (tenant
    isolation + enumeration hiding).
    """

    stmt = select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and job.org_id != principal.org_id:
        raise ResourceNotFoundError()
    return job


async def _can_moderate(session: AsyncSession, principal: Principal) -> bool:
    """True if ``principal`` is a platform superadmin or a university moderator.

    Mirrors ``moderation_service._require_university_moderator`` without raising,
    so reads (e.g. full job detail while ``pending_review``) can branch on it.
    """

    if principal.is_superadmin:
        return True
    if not permission_checker.can(principal, _RESOURCE, "moderate"):
        return False
    if principal.org_id is None:
        return False
    return await org_reporting_facade.is_university_org(session, principal.org_id)


def _is_publicly_visible(job: Job, *, now: datetime) -> bool:
    if job.deleted_at is not None:
        return False
    if job.status != lifecycle.ACTIVE or job.moderation_status != lifecycle.MOD_APPROVED:
        return False
    if job.published_at is None:
        return False
    if job.application_deadline is not None and job.application_deadline <= now:
        return False
    if job.visibility == lifecycle.INVITATION_ONLY:
        return False  # requires a per-job allow-list (later phase)
    return True


def _jsonable(value: object) -> object:
    """Best-effort JSON-safe coercion for audit diff values (UUID/datetime/etc)."""

    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    return value


def _public_filter(stmt: Select, *, principal: Principal, now: datetime) -> Select:
    """Tier-aware public visibility predicate (shared single source).

    Wraps :func:`visibility.apply_visible_filter` with the principal's allowed
    tiers so the discovery list, the directory ``active_job_count`` subquery, and
    the marketplace facade can never drift apart.
    """

    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    return apply_visible_filter(stmt, levels=levels, now=now)
