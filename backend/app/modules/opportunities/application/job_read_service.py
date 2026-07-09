"""Job read/detail service: owner + public detail, preview, applyable lookups.

Public discovery (:func:`get_job` for non-owners) returns **only** jobs that are
published and visible to the principal's tier (``docs/BUSINESS_LOGIC.md`` §5).
Hidden/unpublished jobs return ``404`` to non-owners to prevent enumeration.

Extracted verbatim from the former monolithic ``job_service``; behaviour is
byte-for-byte identical. Shared helpers live in
:mod:`app.modules.opportunities.application.job_common`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.api import presenters
from app.modules.opportunities.application import (
    job_read_facade,
    saved_jobs_service,
)
from app.modules.opportunities.application.errors import (
    InvalidJobFieldError,
)
from app.modules.opportunities.application.job_common import (
    _RESOURCE,
    _can_moderate,
    _is_publicly_visible,
    _load_owned_job,
    _now,
)
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

# --------------------------------------------------------------------------- #
# Reads                                                                       #
# --------------------------------------------------------------------------- #


async def get_job(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    locale: str = "vi",
    user_agent: str | None = None,
    source: str | None = None,
) -> dict:
    """Owner -> full detail; non-owner -> public detail iff visible, else ``404``.

    ``user_agent``/``source`` are optional, best-effort telemetry inputs for the
    ``partner_job_metrics_daily`` read model (spec §"Recruiting Intelligence Read
    Models") — only recorded on the genuine public detail-view branch below, and
    never on the owner/moderator branches (a partner viewing their own job, or a
    university moderator reviewing it, is not a candidate engagement signal).
    """

    job = (
        await session.execute(select(Job).where(Job.id == job_id, Job.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError()

    is_owner = principal.is_superadmin or (
        principal.org_id is not None and principal.org_id == job.org_id
    )
    if is_owner and permission_checker.can(
        principal, _RESOURCE, "read", resource_org_id=job.org_id
    ):
        return presenters.owner_job_detail(job, locale=locale)

    # University moderators (and superadmins) may view the full detail of any job
    # in any status — including ``pending_review`` in the moderation queue — so
    # they can review before approving/rejecting.
    if await _can_moderate(session, principal):
        return presenters.owner_job_detail(job, locale=locale)

    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    if not _is_publicly_visible(job, now=_now()) or job.visibility not in levels:
        raise ResourceNotFoundError()
    org = await org_reporting_facade.summary_for(session, job.org_id)
    saved_ids = await saved_jobs_service.get_saved_ids(session, principal=principal)
    await _record_detail_view_metric(
        session, job=job, principal=principal, user_agent=user_agent, source=source
    )
    return presenters.public_job_detail(
        job,
        company=org,
        locale=locale,
        is_saved=job.id in saved_ids,
    )


async def _record_detail_view_metric(
    session: AsyncSession,
    *,
    job: Job,
    principal: Principal,
    user_agent: str | None,
    source: str | None,
) -> None:
    """Best-effort ``detail_view`` hook into ``partner_job_metrics_daily``.

    Lazy-imported to avoid a module-load cycle (``analytics`` -> ``advertising``
    -> ... never needs to import back into ``opportunities``, but importing it
    at module scope here is unnecessary weight on every ``opportunities`` import).
    """

    try:
        from app.modules.analytics.application import partner_job_metrics_service as metrics

        effective_source = source or await metrics.default_source_for_job(session, job_id=job.id)
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
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=job.org_id)
    spec = _PREVIEW_PERSONAS.get(as_persona)
    if spec is None:
        raise InvalidJobFieldError(field="as")

    persona = str(spec["persona"])
    is_authenticated = bool(spec["is_authenticated"])
    levels = lifecycle.visible_levels_for(persona, is_authenticated=is_authenticated)
    is_invitation_only = job.visibility == lifecycle.INVITATION_ONLY
    would_be_visible = job.visibility in levels and not is_invitation_only

    org = await org_reporting_facade.summary_for(session, job.org_id)
    detail = presenters.public_job_detail(
        job,
        company=org,
        locale=locale,
        is_saved=False,
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
        await session.execute(select(Job).where(Job.id == job_id, Job.deleted_at.is_(None)))
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
