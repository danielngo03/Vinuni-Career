"""University job moderation: queue, approve (-> publish), reject.

Moderation is restricted to a platform **superadmin** or a member of a
**university** org holding ``jobs:moderate`` — exactly mirroring the
partner-approval gate (``partner_registration_service._require_university_actor``,
ADR-0002 §4.1/§5.2). A partner Admin holds ``*:*`` which would otherwise match
``jobs:moderate``; the org-type gate keeps the moderation surface university-only
so partners can never approve their own jobs.

Approve transitions ``pending_review -> active`` and publishes the job (sets
``moderation_status=approved``, ``published_at``); reject transitions
``pending_review -> rejected``. Both audit the transition and enqueue an
outbox notification to the posting partner (no synchronous SMTP).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.api import presenters
from app.modules.opportunities.application.errors import (
    IllegalJobTransitionError,
    InvalidModerationReasonError,
    JobAlreadyClaimedError,
    JobVersionConflictError,
)
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade
from app.modules.users.application import user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AppError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.moderation import (
    REASON_OTHER,
    REASON_REQUIRES_NOTE,
    is_valid_reason_code,
)
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "jobs"


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _invalidate_job_fit_cache(job_id: uuid.UUID) -> None:
    """Best-effort Redis invalidation of cached fit scores for a job.

    Called after a job's visibility changes (approve, reject).  Failures are
    silently swallowed — the 4 h TTL is the fallback and a failed invalidation
    never blocks the write response.
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


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


async def _require_university_moderator(
    session: AsyncSession, principal: Principal
) -> None:
    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, "moderate")
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


async def _load_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    stmt = select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
    if _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


def _audit_ctx(principal: Principal, job: Job, ctx: RequestContext) -> AuditContext:
    # actor_org_id is the moderator's org; resource org is captured in the snapshot.
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _notify_partner(
    session: AsyncSession, *, job: Job, template_key: str, locale: str,
    extra: dict | None = None,
) -> None:
    poster = await user_service.get_by_id(session, job.posted_by)
    variables: dict[str, object] = {
        "email": poster.email if poster else "",
        "name": poster.full_name if poster and poster.full_name else "",
        "job_title": job.title,
    }
    if extra:
        variables.update(extra)
    await enqueue_notification(
        session,
        recipient_id=job.posted_by,
        template_key=template_key,
        channel="email",
        locale=locale,
        variables=variables,
        dedupe_key=f"{template_key}:{job.id}:{job.version}",
    )
    # In-app feed row for the posting partner (same transaction as the outbox).
    notif_type = {
        "job.approved": "opportunities.job_approved",
        "job.rejected": "opportunities.job_rejected",
    }.get(template_key)
    if notif_type is not None:
        await feed_service.create_in_app(
            session,
            recipient_id=job.posted_by,
            notif_type=notif_type,
            action_url=f"/partner/jobs/{job.id}",
            variables={
                "job_title": job.title,
                "reason": (extra or {}).get("reason", ""),
            },
            locale=locale,
        )


# --------------------------------------------------------------------------- #
# Queue                                                                       #
# --------------------------------------------------------------------------- #


async def list_moderation_queue(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], int]:
    """List jobs in the moderation queue (default: ``pending_review``)."""

    await _require_university_moderator(session, principal)
    page_limit = clamp_limit(limit)
    target_status = status or lifecycle.PENDING_REVIEW
    stmt = (
        select(Job)
        .where(Job.deleted_at.is_(None), Job.status == target_status)
        .order_by(Job.submitted_at.asc().nulls_last(), Job.created_at.asc())
        .limit(page_limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).select_from(Job).where(
                Job.deleted_at.is_(None), Job.status == target_status
            )
        )
    ).scalar_one()
    items = [presenters.owner_job_summary(j, locale=locale) for j in rows]
    return items, total


# --------------------------------------------------------------------------- #
# Approve / reject                                                            #
# --------------------------------------------------------------------------- #


async def approve_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    version: int | None = None,
    note: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university_moderator(session, principal)
    job = await _load_job(session, job_id)
    if job is None:
        raise ResourceNotFoundError()
    if version is not None and version != job.version:
        raise JobVersionConflictError()
    if job.status == lifecycle.ACTIVE and job.moderation_status == lifecycle.MOD_APPROVED:
        return presenters.owner_job_summary(job, locale=locale)  # idempotent
    if not lifecycle.can_transition("approve", job.status):
        raise IllegalJobTransitionError(event="approve")

    now = _now()
    job.status = lifecycle.ACTIVE
    job.moderation_status = lifecycle.MOD_APPROVED
    job.moderation_note = note
    job.approved_by = principal.user_id
    job.approved_at = now
    job.published_at = now
    job.version += 1
    await session.flush()

    await write_audit(
        session, action="job.approved", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, job, ctx),
        after={"status": job.status, "moderation_status": job.moderation_status,
               "org_id": str(job.org_id)},
    )
    await _notify_partner(
        session, job=job, template_key="job.approved", locale=locale,
        extra={"action_url": _job_url(job, locale=locale)},
    )
    await session.commit()
    # A newly published job may have been scored before it was visible; invalidate
    # any stale cached scores so students get fresh results on next page load.
    await _invalidate_job_fit_cache(job.id)
    return presenters.owner_job_summary(job, locale=locale)


def _validate_reason_code(reason_code: str | None, *, reason: str | None) -> str:
    """Validate + resolve the structured reason code (defaults to ``other``).

    Kept backward compatible with the original free-text-only ``reason``: a
    caller that omits ``reason_code`` gets ``other`` and the free-text ``reason``
    still carries the full explanation.
    """

    code = reason_code or REASON_OTHER
    if not is_valid_reason_code(code):
        raise InvalidModerationReasonError()
    if code in REASON_REQUIRES_NOTE and not (reason and reason.strip()):
        raise InvalidModerationReasonError()
    return code


async def reject_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    reason: str,
    reason_code: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university_moderator(session, principal)
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"reason": "reason_required"})
    code = _validate_reason_code(reason_code, reason=reason)
    job = await _load_job(session, job_id)
    if job is None:
        raise ResourceNotFoundError()
    if version is not None and version != job.version:
        raise JobVersionConflictError()
    if job.status == lifecycle.REJECTED:
        return presenters.owner_job_summary(job, locale=locale)  # idempotent
    if not lifecycle.can_transition("reject", job.status):
        raise IllegalJobTransitionError(event="reject")

    job.status = lifecycle.REJECTED
    job.moderation_status = lifecycle.MOD_REJECTED
    job.moderation_note = reason.strip()
    job.moderation_reason_code = code
    job.approved_by = None
    job.approved_at = None
    job.published_at = None
    job.claimed_by = None
    job.claimed_at = None
    job.version += 1
    await session.flush()

    await write_audit(
        session, action="job.rejected", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, job, ctx),
        after={"status": job.status, "moderation_status": job.moderation_status,
               "reason_code": code, "org_id": str(job.org_id)},
    )
    await _notify_partner(
        session, job=job, template_key="job.rejected", locale=locale,
        extra={"reason": reason.strip()},
    )
    await session.commit()
    return presenters.owner_job_summary(job, locale=locale)


def _job_url(job: Job, *, locale: str) -> str:
    base = get_settings().frontend_url.rstrip("/")
    return f"{base}/{locale}/jobs/{job.slug}"


# --------------------------------------------------------------------------- #
# Claim / assign                                                              #
# --------------------------------------------------------------------------- #


async def claim_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Claim a pending job for review (concurrency-safe conditional update).

    Uses a single ``UPDATE ... WHERE claimed_by IS NULL`` so two moderators
    racing to claim the same job cannot both win, regardless of DB engine/
    row-locking support (works identically on Postgres and the SQLite test
    path). Already claimed by someone else -> 409 conflict; already claimed by
    the caller -> idempotent no-op.
    """

    await _require_university_moderator(session, principal)
    job = await _load_job(session, job_id)
    if job is None:
        raise ResourceNotFoundError()
    if job.status != lifecycle.PENDING_REVIEW:
        raise IllegalJobTransitionError(event="claim")
    if job.claimed_by == principal.user_id:
        return presenters.owner_job_summary(job, locale=locale)  # idempotent
    if job.claimed_by is not None:
        raise JobAlreadyClaimedError()

    now = _now()
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.claimed_by.is_(None), Job.version == job.version)
        .values(claimed_by=principal.user_id, claimed_at=now, version=Job.version + 1)
    )
    if result.rowcount == 0:
        # Lost the race between load and update.
        raise JobAlreadyClaimedError()
    await session.flush()
    await write_audit(
        session, action="job.claimed", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, job, ctx),
        after={"claimed_by": str(principal.user_id), "org_id": str(job.org_id)},
    )
    await session.commit()
    await session.refresh(job)
    return presenters.owner_job_summary(job, locale=locale)


# --------------------------------------------------------------------------- #
# Bulk approve / reject                                                       #
# --------------------------------------------------------------------------- #


async def bulk_approve_jobs(
    session: AsyncSession,
    *,
    principal: Principal,
    job_ids: list[uuid.UUID],
    ctx: RequestContext,
    locale: str = "vi",
) -> list[dict]:
    """Approve each job independently; partial success is reported per item."""

    results: list[dict] = []
    for job_id in job_ids:
        try:
            data = await approve_job(
                session, principal=principal, job_id=job_id, ctx=ctx, locale=locale,
            )
            results.append({"id": str(job_id), "success": True, "job": data})
        except AppError as exc:
            await session.rollback()
            results.append(
                {
                    "id": str(job_id),
                    "success": False,
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )
    return results


async def bulk_reject_jobs(
    session: AsyncSession,
    *,
    principal: Principal,
    items: list[dict],
    ctx: RequestContext,
    locale: str = "vi",
) -> list[dict]:
    """Reject each job independently; ``items`` is ``[{id, reason, reason_code?}]``."""

    results: list[dict] = []
    for item in items:
        job_id = item["id"]
        try:
            data = await reject_job(
                session,
                principal=principal,
                job_id=job_id,
                reason=item.get("reason", ""),
                reason_code=item.get("reason_code"),
                ctx=ctx,
                locale=locale,
            )
            results.append({"id": str(job_id), "success": True, "job": data})
        except AppError as exc:
            await session.rollback()
            results.append(
                {
                    "id": str(job_id),
                    "success": False,
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )
    return results


# --------------------------------------------------------------------------- #
# Escalation -> human review queue                                            #
# --------------------------------------------------------------------------- #


async def escalate_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    reason_code: str | None = None,
    note: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Flag a job and create/refresh a row in the shared human review queue.

    Communicates with ``app.modules.moderation`` through its application-layer
    ``review_queue_service`` (a sibling-module application import is allowed by
    the module-boundary rule; only sibling domain/infrastructure reaches are
    forbidden — see ``jd_ai_service._escalate_if_needed`` for the same pattern).
    """

    await _require_university_moderator(session, principal)
    code = _validate_reason_code(reason_code, reason=note)
    job = await _load_job(session, job_id)
    if job is None:
        raise ResourceNotFoundError()

    job.moderation_status = lifecycle.MOD_FLAGGED
    if note and note.strip():
        job.moderation_note = note.strip()
    job.moderation_reason_code = code
    job.version += 1
    await session.flush()

    await write_audit(
        session, action="job.escalated", resource_type="job", resource_id=job.id,
        context=_audit_ctx(principal, job, ctx),
        after={"moderation_status": job.moderation_status, "reason_code": code,
               "org_id": str(job.org_id)},
    )

    from app.modules.moderation.application import review_queue_service

    await review_queue_service.enqueue(
        session,
        source=review_queue_service.SOURCE_MODERATOR_ESCALATION,
        resource_type="job",
        resource_id=job.id,
        org_id=job.org_id,
        severity="high",
        findings={
            "reason_code": code,
            "note": (note or "").strip(),
            "escalated_by": str(principal.user_id),
        },
    )
    await session.commit()
    await session.refresh(job)
    return presenters.owner_job_summary(job, locale=locale)
