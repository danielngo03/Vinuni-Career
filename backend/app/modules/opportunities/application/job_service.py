"""Job posting service: partner CRUD, lifecycle transitions, public discovery.

RBAC is enforced here (not in routers) via ``PermissionChecker`` plus org-scoped
tenant isolation: a partner only ever sees / mutates its own org's jobs, and a
cross-org access attempt returns ``404`` (never ``403``) so the resource is not
enumerable. Every write records an audit row in the caller's transaction.

Public discovery (:func:`list_public_jobs` / :func:`get_job` for non-owners)
returns **only** jobs that are published and visible to the principal's tier
(``docs/BUSINESS_LOGIC.md`` §5). Hidden/unpublished jobs return ``404`` to
non-owners to prevent enumeration; counts reflect visible records only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.api import presenters, schemas
from app.modules.opportunities.application import (
    job_read_facade,
    public_read,
    saved_jobs_service,
)
from app.modules.opportunities.application.errors import (
    IllegalJobTransitionError,
    InvalidIndustryFilterError,
    InvalidJobFieldError,
    JobNotEditableError,
    JobQualityCheckFailedError,
    JobVersionConflictError,
)
from app.modules.opportunities.application.visibility import apply_visible_filter
from app.modules.opportunities.domain import jd_quality, lifecycle
from app.modules.opportunities.domain.industry_models import Industry
from app.modules.opportunities.domain.models import Job, ScreeningQuestion
from app.modules.organization.application import org_reporting_facade
from app.modules.organization.domain.catalog import slugify
from app.modules.users.application import user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.moderation import compute_due_by
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
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
        exists = (
            await session.execute(select(Job.id).where(Job.slug == candidate))
        ).first()
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


def _effective(payload: dict, existing: Job | None, field: str, default: object = None) -> object:
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

    for q in payload.get("screening_questions") or []:
        if q["q_type"] not in lifecycle.SCREENING_Q_TYPES:
            raise InvalidJobFieldError(field="screening_questions")


async def _replace_screening(
    session: AsyncSession, *, job_id: uuid.UUID, questions: list[dict]
) -> None:
    existing = (
        await session.execute(
            select(ScreeningQuestion).where(ScreeningQuestion.job_id == job_id)
        )
    ).scalars().all()
    for row in existing:
        await session.delete(row)
    await session.flush()
    for q in questions:
        session.add(
            ScreeningQuestion(
                job_id=job_id,
                question=q["question"],
                q_type=q["q_type"],
                options=q.get("options"),
                is_required=q.get("is_required", True),
                sort_order=q.get("sort_order", 0),
            )
        )
    await session.flush()


async def _load_screening(
    session: AsyncSession, *, job_id: uuid.UUID
) -> list[ScreeningQuestion]:
    return list(
        (
            await session.execute(
                select(ScreeningQuestion)
                .where(ScreeningQuestion.job_id == job_id)
                .order_by(ScreeningQuestion.sort_order, ScreeningQuestion.id)
            )
        ).scalars().all()
    )


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


# --------------------------------------------------------------------------- #
# Create / update                                                             #
# --------------------------------------------------------------------------- #


async def create_job(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "create", resource_org_id=principal.org_id
    )
    _validate_fields(payload)
    assert principal.user_id is not None

    screening = payload.pop("screening_questions", []) or []
    slug = await _unique_slug(session, payload["title"])
    job = Job(
        org_id=principal.org_id,
        posted_by=principal.user_id,
        slug=slug,
        status=lifecycle.DRAFT,
        moderation_status=lifecycle.MOD_PENDING,
        **payload,
    )
    session.add(job)
    await session.flush()
    if screening:
        await _replace_screening(session, job_id=job.id, questions=screening)

    await write_audit(
        session, action="job.created", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, ctx),
        after={"title": job.title, "status": job.status, "slug": slug},
    )
    await session.commit()
    await session.refresh(job)
    rows = await _load_screening(session, job_id=job.id)
    return presenters.owner_job_detail(job, screening=rows, locale=locale)


_UPDATABLE = {
    "title", "description", "requirements", "benefits", "employment_type",
    "location_type", "location_city", "location_country", "locations",
    "required_skills", "preferred_skills", "experience_min_years", "experience_max_years",
    "experience_mode",
    "industry_id", "degree_required", "seniority_level", "candidate_requirements",
    "salary_min", "salary_max", "salary_currency", "salary_is_disclosed", "headcount",
    "salary_mode", "salary_period", "salary_gross_net",
    "application_deadline", "visibility",
}

# Fields copied verbatim when duplicating a job (excludes runtime state fields).
_DUPLICATE_COPY = (
    "description", "requirements", "benefits", "employment_type",
    "location_type", "location_city", "location_country", "locations",
    "required_skills", "preferred_skills", "experience_min_years", "experience_max_years",
    "experience_mode",
    "industry_id", "degree_required", "seniority_level", "candidate_requirements",
    "salary_min", "salary_max", "salary_currency", "salary_is_disclosed", "headcount",
    "salary_mode", "salary_period", "salary_gross_net",
    "visibility",
)


async def duplicate_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Create a draft copy of an existing job owned by the principal's org.

    The copy gets a ``(Sao chép)`` / ``(Copy)`` suffix in the title and a
    fresh slug. Moderation state resets to pending (it is a new submission).
    Application deadline is NOT copied (likely stale). All screening questions
    are duplicated. Partner must submit the copy through the normal review flow.
    """
    source = await _load_owned_job(session, principal=principal, job_id=job_id)
    permission_checker.require(
        principal, _RESOURCE, "create", resource_org_id=source.org_id
    )
    assert principal.user_id is not None

    suffix = "(Sao chép)" if locale == "vi" else "(Copy)"
    new_title = f"{source.title} {suffix}"
    slug = await _unique_slug(session, new_title)

    copy = Job(
        org_id=source.org_id,
        posted_by=principal.user_id,
        title=new_title,
        slug=slug,
        status=lifecycle.DRAFT,
        moderation_status=lifecycle.MOD_PENDING,
        **{field: getattr(source, field) for field in _DUPLICATE_COPY},
    )
    session.add(copy)
    await session.flush()

    source_qs = await _load_screening(session, job_id=source.id)
    if source_qs:
        await _replace_screening(
            session,
            job_id=copy.id,
            questions=[
                {
                    "question": q.question,
                    "q_type": q.q_type,
                    "options": q.options,
                    "is_required": q.is_required,
                    "sort_order": q.sort_order,
                }
                for q in source_qs
            ],
        )

    await write_audit(
        session, action="job.duplicated", resource_type="job", resource_id=copy.id,
        context=_audit_ctx(principal, ctx),
        after={"title": copy.title, "source_job_id": str(source.id), "slug": slug},
    )
    await session.commit()
    await session.refresh(copy)
    rows = await _load_screening(session, job_id=copy.id)
    return presenters.owner_job_detail(copy, screening=rows, locale=locale)


async def update_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Edit a job's content.

    Amendment policy (B-552, ``docs/BUSINESS_LOGIC.md``): ``draft``/``rejected``
    jobs are fully editable, exactly as before. A **published** (``active``)
    job may also be amended, but the field being changed decides the effect:

    - ``lifecycle.FREE_AMEND_FIELDS`` (deadline, headcount, visibility,
      benefits) apply immediately — the job stays ``active``/public.
    - ``lifecycle.REMODERATION_FIELDS`` (title, description, requirements,
      compensation, location, candidate requirements, ...) pull the job back
      into moderation (``active -> pending_review``) because the previously
      approved content no longer matches what would be live; the partner must
      be re-approved before the amended content is public again.
    - Screening questions are locked once ``active`` (existing applications'
      ``screening_answers`` reference the question set by id/order) —
      attempting to change them raises ``JobNotEditableError``.

    Any other status (``pending_review``, ``closed``, ``expired``) stays
    edit-locked, as before. Every amendment is audited with an old/new value
    diff (not just the changed field names) so support/compliance can review
    exactly what changed post-publication.
    """

    job = await _load_owned_job(session, principal=principal, job_id=job_id, lock=True)
    permission_checker.require(
        principal, _RESOURCE, "update", resource_org_id=job.org_id
    )
    if job.status not in lifecycle.EDITABLE_STATES:
        raise JobNotEditableError()

    expected_version = payload.pop("version", None)
    if expected_version is not None and expected_version != job.version:
        raise JobVersionConflictError()

    screening = payload.pop("screening_questions", None)
    was_active = job.status == lifecycle.ACTIVE
    if was_active and screening is not None:
        raise JobNotEditableError(reason="screening_locked_after_publish")

    _validate_fields(payload, existing=job)

    before: dict[str, object] = {}
    after: dict[str, object] = {}
    changed: dict[str, object] = {}
    requires_remoderation = False
    for field in _UPDATABLE:
        if field in payload:
            old_value = getattr(job, field)
            new_value = payload[field]
            if old_value == new_value:
                continue
            before[field] = _jsonable(old_value)
            after[field] = _jsonable(new_value)
            setattr(job, field, new_value)
            changed[field] = True
            if was_active and field in lifecycle.REMODERATION_FIELDS:
                requires_remoderation = True
    if screening is not None:
        await _replace_screening(session, job_id=job.id, questions=screening)
        changed["screening_questions"] = True
    if changed:
        job.version += 1
    await session.flush()

    audit_after: dict[str, object] = {"fields": sorted(changed.keys())}
    if before or after:
        audit_after["diff"] = {"before": before, "after": after}

    if was_active and requires_remoderation:
        if not lifecycle.can_transition("amend", job.status):
            raise IllegalJobTransitionError(event="amend")
        now = _now()
        job.status = lifecycle.PENDING_REVIEW
        job.moderation_status = lifecycle.MOD_PENDING
        job.moderation_note = None
        job.moderation_reason_code = None
        job.claimed_by = None
        job.claimed_at = None
        job.submitted_at = now
        job.due_by = compute_due_by(now, sla_hours=get_settings().job_moderation_sla_hours)
        audit_after["status"] = job.status
        audit_after["reason"] = "content_amendment_requires_remoderation"
        await session.flush()

    await write_audit(
        session, action="job.updated", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, ctx),
        before={"fields": sorted(before.keys())} if before else None,
        after=audit_after,
    )
    await session.commit()
    await session.refresh(job)
    rows = await _load_screening(session, job_id=job.id)
    return presenters.owner_job_detail(job, screening=rows, locale=locale)


def _jsonable(value: object) -> object:
    """Best-effort JSON-safe coercion for audit diff values (UUID/datetime/etc)."""

    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    return value


# --------------------------------------------------------------------------- #
# Lifecycle transitions (partner-controlled)                                  #
# --------------------------------------------------------------------------- #


async def _transition(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    event: str,
    action_permission: str,
    ctx: RequestContext,
    version: int | None,
    locale: str,
) -> dict:
    job = await _load_owned_job(session, principal=principal, job_id=job_id, lock=True)
    permission_checker.require(
        principal, _RESOURCE, action_permission, resource_org_id=job.org_id
    )
    if version is not None and version != job.version:
        raise JobVersionConflictError()
    if not lifecycle.can_transition(event, job.status):
        raise IllegalJobTransitionError(event=event)

    now = _now()
    job.status = lifecycle.target_state(event)
    # NOTE: "submit" is handled by the dedicated :func:`submit_job` (JD
    # quality-check gate, B-552) rather than this generic helper; only
    # "close"/"reopen" route through here.
    if event == "close":
        job.closed_at = now
    elif event == "reopen":
        if job.moderation_status != lifecycle.MOD_APPROVED:
            raise IllegalJobTransitionError(event=event)
        if job.application_deadline is not None and job.application_deadline <= now:
            raise IllegalJobTransitionError(event=event)
        job.closed_at = None
        if job.published_at is None:
            job.published_at = now
    job.version += 1
    await session.flush()

    await write_audit(
        session, action=f"job.{event}", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, ctx),
        after={"status": job.status},
    )
    await session.commit()
    await session.refresh(job)
    rows = await _load_screening(session, job_id=job.id)
    return presenters.owner_job_detail(job, screening=rows, locale=locale)


async def check_jd_quality(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Preview the deterministic JD quality-check rubric without submitting.

    Lets a partner see exactly what :func:`submit_job` will (dis)allow before
    they actually submit — same rubric, same result shape, read-only.
    """

    job = await _load_owned_job(session, principal=principal, job_id=job_id)
    permission_checker.require(
        principal, _RESOURCE, "read", resource_org_id=job.org_id
    )
    rows = await _load_screening(session, job_id=job.id)
    issues = jd_quality.evaluate(job, screening=rows)
    return {
        "passed": not jd_quality.has_blocking(issues),
        "issues": [i.as_dict(locale=locale) for i in issues],
    }


async def submit_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID,
    ctx: RequestContext, version: int | None = None, locale: str = "vi",
) -> dict:
    """Submit a ``draft``/``rejected`` job for university moderation.

    Blocked by the deterministic JD quality-check rubric (B-552,
    ``domain.jd_quality``) whenever any finding is ``blocking`` severity —
    the partner must fix the listed issue(s) and resubmit. ``advisory``
    findings never block; they ride along in the response
    (``quality_check.issues``) and in the audit trail as non-blocking
    warnings the partner chose to submit with.

    This is deterministic/rule-based, not an AI call — the separate AI
    bias-check (``jd_ai_service.check_bias``) remains an independent,
    advisory-only feature.
    """

    job = await _load_owned_job(session, principal=principal, job_id=job_id, lock=True)
    permission_checker.require(
        principal, _RESOURCE, "submit", resource_org_id=job.org_id
    )
    if version is not None and version != job.version:
        raise JobVersionConflictError()
    if not lifecycle.can_transition("submit", job.status):
        raise IllegalJobTransitionError(event="submit")

    screening_rows = await _load_screening(session, job_id=job.id)
    issues = jd_quality.evaluate(job, screening=screening_rows)
    if jd_quality.has_blocking(issues):
        raise JobQualityCheckFailedError(
            issues=[i.as_dict(locale=locale) for i in issues]
        )

    now = _now()
    job.status = lifecycle.PENDING_REVIEW
    job.submitted_at = now
    job.due_by = compute_due_by(now, sla_hours=get_settings().job_moderation_sla_hours)
    # A previously-rejected job re-enters moderation fresh.
    job.moderation_status = lifecycle.MOD_PENDING
    job.moderation_note = None
    job.moderation_reason_code = None
    job.claimed_by = None
    job.claimed_at = None
    job.version += 1
    await session.flush()

    warnings = [i.as_dict(locale=locale) for i in issues if i.severity == jd_quality.ADVISORY]
    await write_audit(
        session, action="job.submit", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, ctx),
        after={"status": job.status, "quality_warnings": warnings},
    )
    await session.commit()
    await session.refresh(job)
    rows = await _load_screening(session, job_id=job.id)
    result = presenters.owner_job_detail(job, screening=rows, locale=locale)
    result["quality_check"] = {"passed": True, "issues": [i.as_dict(locale=locale) for i in issues]}
    return result


async def close_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID,
    ctx: RequestContext, version: int | None = None, locale: str = "vi",
) -> dict:
    return await _transition(
        session, principal=principal, job_id=job_id, event="close",
        action_permission="publish", ctx=ctx, version=version, locale=locale,
    )


async def reopen_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID,
    ctx: RequestContext, version: int | None = None, locale: str = "vi",
) -> dict:
    return await _transition(
        session, principal=principal, job_id=job_id, event="reopen",
        action_permission="publish", ctx=ctx, version=version, locale=locale,
    )


async def delete_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID,
    ctx: RequestContext, locale: str = "vi",
) -> None:
    job = await _load_owned_job(session, principal=principal, job_id=job_id, lock=True)
    permission_checker.require(
        principal, _RESOURCE, "delete", resource_org_id=job.org_id
    )
    if job.status not in lifecycle.DELETABLE_STATES:
        raise JobNotEditableError()
    job.deleted_at = _now()
    job.version += 1
    await session.flush()
    await write_audit(
        session, action="job.deleted", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, ctx),
        before={"status": job.status},
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Scheduler: deadline auto-close sweep                                         #
# --------------------------------------------------------------------------- #


async def _notify_partner_auto_closed(
    session: AsyncSession, *, job: Job, locale: str
) -> None:
    """Notify the posting partner that a job auto-closed at its deadline.

    Deduped on ``job.auto_closed:{job_id}`` (outbox) and the natural in-app key so
    a re-tick never double-notifies (belt-and-braces with the ``status='active'``
    claim gate that already excludes a now-closed job).
    """

    poster = await user_service.get_by_id(session, job.posted_by)
    await enqueue_notification(
        session,
        recipient_id=job.posted_by,
        template_key="job.auto_closed",
        channel="email",
        locale=locale,
        variables={
            "email": poster.email if poster else "",
            "name": poster.full_name if poster and poster.full_name else "",
            "job_title": job.title,
        },
        dedupe_key=f"job.auto_closed:{job.id}",
    )
    await feed_service.create_in_app(
        session,
        recipient_id=job.posted_by,
        notif_type="opportunities.job_auto_closed",
        action_url=f"/partner/jobs/{job.id}",
        variables={"job_title": job.title},
        locale=locale,
    )


async def sweep_deadline_closures(
    session: AsyncSession, *, now: datetime | None = None, locale: str = "vi"
) -> dict[str, int]:
    """Auto-close every active job whose application deadline has passed.

    ``status='active' AND application_deadline IS NOT NULL AND deadline <= now`` ->
    the existing ``active -> closed`` transition (``docs/BUSINESS_LOGIC.md`` §2.2;
    ADR-0003 §2). Each close is audited (``job.auto_closed``) and notifies the
    posting partner (deduped). Status-gated + idempotent: a re-tick excludes the
    now-closed job, so it never re-closes or re-notifies. Flush-only — the
    scheduler job owns the commit.
    """

    now = now or _now()
    rows = list(
        (
            await session.execute(
                select(Job).where(
                    Job.deleted_at.is_(None),
                    Job.status == lifecycle.ACTIVE,
                    Job.application_deadline.isnot(None),
                    Job.application_deadline <= now,
                )
            )
        ).scalars().all()
    )
    for job in rows:
        job.status = lifecycle.CLOSED
        job.closed_at = now
        job.version += 1
        await write_audit(
            session,
            action="job.auto_closed",
            resource_type="job",
            resource_id=job.id,
            context=AuditContext(actor_org_id=job.org_id),
            after={"status": job.status, "reason": "deadline_passed"},
        )
        await _notify_partner_auto_closed(session, job=job, locale=locale)
    await session.flush()
    return {"closed": len(rows)}


# --------------------------------------------------------------------------- #
# Reads                                                                       #
# --------------------------------------------------------------------------- #


async def get_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID,
    locale: str = "vi", user_agent: str | None = None, source: str | None = None,
) -> dict:
    """Owner -> full detail; non-owner -> public detail iff visible, else ``404``.

    ``user_agent``/``source`` are optional, best-effort telemetry inputs for the
    ``partner_job_metrics_daily`` read model (spec §"Recruiting Intelligence Read
    Models") — only recorded on the genuine public detail-view branch below, and
    never on the owner/moderator branches (a partner viewing their own job, or a
    university moderator reviewing it, is not a candidate engagement signal).
    """

    job = (
        await session.execute(
            select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError()

    is_owner = principal.is_superadmin or (
        principal.org_id is not None and principal.org_id == job.org_id
    )
    if is_owner and permission_checker.can(
        principal, _RESOURCE, "read", resource_org_id=job.org_id
    ):
        rows = await _load_screening(session, job_id=job.id)
        return presenters.owner_job_detail(job, screening=rows, locale=locale)

    # University moderators (and superadmins) may view the full detail of any job
    # in any status — including ``pending_review`` in the moderation queue — so
    # they can review before approving/rejecting.
    if await _can_moderate(session, principal):
        rows = await _load_screening(session, job_id=job.id)
        return presenters.owner_job_detail(job, screening=rows, locale=locale)

    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    if not _is_publicly_visible(job, now=_now()) or job.visibility not in levels:
        raise ResourceNotFoundError()
    # Applicants/guests get the screening *question definitions* (not answers) so
    # they can complete the application; owner-only fields stay withheld.
    rows = await _load_screening(session, job_id=job.id)
    org = await org_reporting_facade.summary_for(session, job.org_id)
    saved_ids = await saved_jobs_service.get_saved_ids(session, principal=principal)
    await _record_detail_view_metric(
        session, job=job, principal=principal, user_agent=user_agent, source=source
    )
    return presenters.public_job_detail(
        job, screening=rows, company=org, locale=locale,
        is_saved=job.id in saved_ids,
    )


async def _record_detail_view_metric(
    session: AsyncSession, *, job: Job, principal: Principal,
    user_agent: str | None, source: str | None,
) -> None:
    """Best-effort ``detail_view`` hook into ``partner_job_metrics_daily``.

    Lazy-imported to avoid a module-load cycle (``analytics`` -> ``advertising``
    -> ... never needs to import back into ``opportunities``, but importing it
    at module scope here is unnecessary weight on every ``opportunities`` import).
    """

    try:
        from app.modules.analytics.application import partner_job_metrics_service as metrics

        effective_source = source or await metrics.default_source_for_job(
            session, job_id=job.id
        )
        student_tier = metrics.student_tier_for_persona(principal.persona)
        major_group, year_group = await metrics.coarse_academic_dims(
            session, user_id=principal.user_id
        )
        await metrics.record_job_metric_event(
            session,
            org_id=job.org_id,
            job_id=job.id,
            event_type="detail_view",
            source=effective_source,
            device_class=metrics.coarse_device_class(user_agent),
            student_tier=student_tier,
            major_group=major_group,
            year_group=year_group,
        )
        # ``get_job`` is otherwise a pure read (no commit) — this is the one write
        # in the request, so it must commit explicitly or the session close would
        # silently discard it.
        await session.commit()
    except Exception:  # noqa: BLE001 — telemetry must never break job detail reads
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass


_PREVIEW_PERSONAS = {
    "guest": {"persona": "guest", "is_authenticated": False},
    "student": {"persona": "student", "is_authenticated": True},
}


async def preview_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    as_persona: str,
    locale: str = "vi",
) -> dict:
    """Owner-only pre-publish preview: "what would guest/student see?"

    Lets a partner (holding ``jobs:read``) check exactly what the public
    marketplace card/detail will render — sponsored-label rules, hidden
    owner-only fields (moderation notes/status/poster), and the persona's
    visibility-tier gate — **before** actually publishing. Reuses the same
    :func:`app.modules.opportunities.api.presenters.public_job_detail`
    projection the real public/student ``get_job`` path renders, so the
    preview can never drift from the live surface.

    Does not require the job to already be ``active``/approved — a partner
    previews a draft exactly as it will look *once* published.
    """

    job = await _load_owned_job(session, principal=principal, job_id=job_id)
    permission_checker.require(
        principal, _RESOURCE, "read", resource_org_id=job.org_id
    )
    spec = _PREVIEW_PERSONAS.get(as_persona)
    if spec is None:
        raise InvalidJobFieldError(field="as")

    levels = lifecycle.visible_levels_for(
        spec["persona"], is_authenticated=spec["is_authenticated"]
    )
    is_invitation_only = job.visibility == lifecycle.INVITATION_ONLY
    would_be_visible = job.visibility in levels and not is_invitation_only

    rows = await _load_screening(session, job_id=job.id)
    org = await org_reporting_facade.summary_for(session, job.org_id)
    detail = presenters.public_job_detail(
        job, screening=rows, company=org, locale=locale, is_saved=False,
    )
    hidden_reason = None
    if not would_be_visible:
        hidden_reason = "invitation_only" if is_invitation_only else "visibility_tier"

    return {
        "as": as_persona,
        "would_be_visible": would_be_visible,
        "hidden_reason": hidden_reason,
        "preview": detail,
    }


async def get_applyable_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID
) -> Job:
    """Return the :class:`Job` ORM iff ``principal`` may apply to it.

    Public interface for the ``recruitment`` module: a job is applyable when it is
    published + approved + within its deadline AND visible to the applicant's
    tier. Anything else (missing, draft, closed, expired, deadline passed,
    invisible to the tier) returns ``404`` — indistinguishable from a missing
    resource (enumeration hiding), consistent with :func:`get_job`.
    """

    job = (
        await session.execute(
            select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError()
    now = _now()
    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    if not _is_publicly_visible(job, now=now) or job.visibility not in levels:
        raise ResourceNotFoundError()
    return job


async def get_applyable_job_ref(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID
) -> job_read_facade.JobRef:
    """Cross-module-safe DTO variant of :func:`get_applyable_job` for ``recruitment``."""

    job = await get_applyable_job(session, principal=principal, job_id=job_id)
    return job_read_facade.to_ref(job)


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
        ).scalars().all()
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
            ).scalars().all()
        )
        ids.extend(grandchildren)
    return ids


def _apply_search_filters(
    stmt: Select,
    *,
    q: str | None,
    employment_type: str | None,
    location_type: str | None,
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


def _location_contains_any(
    stmt: Select, field: str, values: list[str], use_jsonb: bool
) -> Select:
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

    total = (
        await session.execute(_filtered(select(func.count()).select_from(Job)))
    ).scalar_one()

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
    permission_checker.require(
        principal, _RESOURCE, "read", resource_org_id=principal.org_id
    )
    page_limit = clamp_limit(limit)
    stmt = select(Job).where(
        Job.org_id == principal.org_id, Job.deleted_at.is_(None)
    )
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
    items = [presenters.owner_job_summary(j, locale=locale) for j in page.items]
    return items, page.next_cursor, page.limit
