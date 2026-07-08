"""Job write + lifecycle service: partner CRUD, transitions, deadline sweep.

RBAC is enforced here (not in routers) via ``PermissionChecker`` plus org-scoped
tenant isolation: a partner only ever mutates its own org's jobs, and a
cross-org access attempt returns ``404`` (never ``403``) so the resource is not
enumerable. Every write records an audit row in the caller's transaction.

Extracted verbatim from the former monolithic ``job_service``; behaviour is
byte-for-byte identical. Shared helpers live in
:mod:`app.modules.opportunities.application.job_common`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.api import presenters
from app.modules.opportunities.application.errors import (
    IllegalJobTransitionError,
    JobNotEditableError,
    JobQualityCheckFailedError,
    JobVersionConflictError,
)
from app.modules.opportunities.application.job_common import (
    _RESOURCE,
    _audit_ctx,
    _jsonable,
    _load_owned_job,
    _now,
    _unique_slug,
    _validate_fields,
)
from app.modules.opportunities.domain import jd_quality, lifecycle
from app.modules.opportunities.domain.language_detection import resolve_original_language
from app.modules.opportunities.domain.models import Job
from app.modules.users.application import user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.moderation import compute_due_by
from app.shared.permissions import Principal, permission_checker

# Sentinel: "the caller did not send this key at all" (vs. sent it as null).
_UNSET: object = object()


async def _invalidate_job_fit_cache(job_id: uuid.UUID) -> None:
    """Best-effort Redis invalidation of cached fit scores for a job.

    Called after a job's content or visibility changes (update, approve,
    close, reopen).  Failures are silently swallowed — the 4 h TTL is the
    fallback and a failed invalidation never blocks the write response.
    """
    try:
        import redis.asyncio as aioredis

        from app.ai.cv.fit_cache import invalidate_job
        from app.core.config import get_settings

        client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            await invalidate_job(client, job_id=job_id)
        finally:
            await client.aclose()
    except Exception:
        pass

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
    # Resolve the JD's ORIGINAL language (client hint from AI extraction /
    # manual selection, else zero-cost heuristic over the JD text). Stored as a
    # concrete language so the student "translate this JD" affordance works —
    # never trust an unresolved/"mixed" client value.
    lang_hint = payload.pop("language_code", None)
    _validate_fields(payload)
    assert principal.user_id is not None

    language_code = resolve_original_language(
        hint=lang_hint,
        text=" ".join(
            part for part in (payload.get("description"), payload.get("requirements"))
            if part
        ),
    )

    slug = await _unique_slug(session, payload["title"])
    job = Job(
        org_id=principal.org_id,
        posted_by=principal.user_id,
        slug=slug,
        status=lifecycle.DRAFT,
        moderation_status=lifecycle.MOD_PENDING,
        language_code=language_code,
        **payload,
    )
    session.add(job)
    await session.flush()

    await write_audit(
        session, action="job.created", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, ctx),
        after={"title": job.title, "status": job.status, "slug": slug},
    )
    await session.commit()
    await session.refresh(job)
    return presenters.owner_job_detail(job, locale=locale)


_UPDATABLE = {
    "title", "description", "requirements", "benefits", "employment_type",
    "location_type", "location_city", "location_country", "locations",
    "required_skills", "preferred_skills", "experience_min_years", "experience_max_years",
    "experience_mode",
    "industry_id", "degree_required", "seniority_level", "candidate_requirements",
    "salary_min", "salary_max", "salary_currency", "salary_is_disclosed", "headcount",
    "salary_mode", "salary_period", "salary_gross_net",
    "application_deadline", "visibility", "cv_language_required",
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
    "visibility", "cv_language_required",
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
    Application deadline is NOT copied (likely stale). Partner must submit the
    copy through the normal review flow.
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

    await write_audit(
        session, action="job.duplicated", resource_type="job", resource_id=copy.id,
        context=_audit_ctx(principal, ctx),
        after={"title": copy.title, "source_job_id": str(source.id), "slug": slug},
    )
    await session.commit()
    await session.refresh(copy)
    return presenters.owner_job_detail(copy, locale=locale)


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

    # Original language is derived, not a raw client field — resolve it below.
    lang_hint = payload.pop("language_code", _UNSET)

    was_active = job.status == lifecycle.ACTIVE

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

    # Re-resolve the stored original language when the partner sent a language
    # hint OR edited the JD text (so a rewrite from VN to EN re-detects). Never
    # writes "mixed"/"unknown". Leaves it untouched when neither changed.
    if lang_hint is not _UNSET or "description" in payload or "requirements" in payload:
        hint = None if lang_hint is _UNSET else lang_hint
        new_lang = resolve_original_language(
            hint=hint,
            text=" ".join(part for part in (job.description, job.requirements) if part),
        )
        if new_lang != job.language_code:
            before["language_code"] = job.language_code
            after["language_code"] = new_lang
            job.language_code = new_lang
            changed["language_code"] = True

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
    # Invalidate cached fit scores when job requirements change so students see
    # fresh scores on next page load.  Best-effort; TTL is the fallback.
    if changed:
        await _invalidate_job_fit_cache(job.id)
    return presenters.owner_job_detail(job, locale=locale)


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
    # A status change (close/reopen) makes cached scores stale for all users.
    await _invalidate_job_fit_cache(job.id)
    return presenters.owner_job_detail(job, locale=locale)


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
    issues = jd_quality.evaluate(job)
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

    issues = jd_quality.evaluate(job)
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
    result = presenters.owner_job_detail(job, locale=locale)
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
