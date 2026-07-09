"""Apply flow: submit, list (student), detail, withdraw, partner views, CV download.

RBAC is enforced here (not in routers):

- A student applies only as itself (``applications:create``); the snapshot owner is
  always the acting user.
- A partner sees applications only for its own org's jobs (``applications:read`` +
  ``org_id`` match); a cross-org access is indistinguishable from missing (``404``).
- An application ALWAYS carries and exposes the applicant's real identity to any
  partner member who passes the base ``applications:read`` gate (owner decision
  2026-07-10 — the anonymous-apply + identity-reveal handshake was removed). The
  CV preview / download is still additionally gated on ``candidate_identity``
  (``view_cv`` / ``download_cv``), the partner download is watermarked, and every
  sensitive candidate access (application open, CV view/download) is audited.

Every write is audited in the caller's transaction; the immutable CV snapshot is
created via the documents facade (never reimplemented); the partner notification
is enqueued on the outbox (no synchronous SMTP).
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.application import ingestion_service as analytics
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import application_fit_service, snapshot_service
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.application import job_read_facade, job_service
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.api import presenters
from app.modules.recruitment.application import _shared, access
from app.modules.recruitment.application.errors import (
    ApplicationNotWithdrawableError,
    ApplicationVersionConflictError,
    DuplicateApplicationError,
)
from app.modules.recruitment.domain import lifecycle, timeline
from app.modules.recruitment.domain.models import Application
from app.modules.student_profiles.application import avatar_facade
from app.modules.users.application import user_read_facade, user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


# --------------------------------------------------------------------------- #
# Submit                                                                      #
# --------------------------------------------------------------------------- #


async def _existing_by_idempotency(
    session: AsyncSession, *, applicant_id: uuid.UUID, idempotency_key: str
) -> Application | None:
    return (
        await session.execute(
            select(Application).where(
                Application.applicant_id == applicant_id,
                Application.idempotency_key == idempotency_key,
                Application.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _active_duplicate(
    session: AsyncSession, *, job_id: uuid.UUID, applicant_id: uuid.UUID
) -> Application | None:
    return (
        await session.execute(
            select(Application).where(
                Application.job_id == job_id,
                Application.applicant_id == applicant_id,
                Application.deleted_at.is_(None),
                Application.status.in_(tuple(lifecycle.ACTIVE_STATUSES)),
            )
        )
    ).scalar_one_or_none()


async def apply_to_job(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None

    job_id = _shared.to_uuid(payload["job_id"])
    if job_id is None:
        raise ResourceNotFoundError()
    idempotency_key = payload.get("idempotency_key")

    # Submit idempotency: replay returns the already-created application.
    if idempotency_key:
        prior = await _existing_by_idempotency(
            session, applicant_id=principal.user_id, idempotency_key=idempotency_key
        )
        if prior is not None:
            return presenters.applicant_application(prior, locale=locale)

    # Job must be open + visible to this applicant (else 404).
    job = await job_service.get_applyable_job_ref(session, principal=principal, job_id=job_id)

    # One active application per (job, applicant).
    existing = await _active_duplicate(session, job_id=job.id, applicant_id=principal.user_id)
    if existing is not None:
        raise DuplicateApplicationError(application_id=existing.id, status=existing.status)

    app = Application(
        job_id=job.id,
        applicant_id=principal.user_id,
        org_id=job.org_id,
        status=lifecycle.SUBMITTED,
        cover_letter=payload.get("cover_letter"),
        screening_answers=payload.get("screening_answers") or {},
        idempotency_key=idempotency_key,
    )
    session.add(app)
    # B-593: two requests with DIFFERENT idempotency keys can both clear the
    # in-transaction ``_active_duplicate`` pre-check above and then race to INSERT.
    # The Postgres partial unique index ``uq_applications_active`` (one active row
    # per ``(job, applicant)``) rejects the loser's insert with an ``IntegrityError``.
    # Translate that into the SAME clean ``409`` the sequential-duplicate path
    # returns — never a raw ``500``. The DB index still guarantees no corruption.
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        winner = await _active_duplicate(session, job_id=job.id, applicant_id=principal.user_id)
        if winner is not None:
            raise DuplicateApplicationError(application_id=winner.id, status=winner.status) from exc
        raise DuplicateApplicationError() from exc

    # Immutable CV snapshot via the documents facade (atomic with this txn).
    snapshot = await snapshot_service.create_application_cv_snapshot(
        session,
        owner_id=principal.user_id,
        cv_selection=payload["cv_selection"],
        application_id=app.id,
        idempotency_key=(f"{idempotency_key}:cv" if idempotency_key else None),
        ctx=ctx,
        commit=False,
    )
    app.snapshot_id = snapshot.id

    await job_read_facade.increment_application_count(session, job.id)
    await session.flush()

    await write_audit(
        session,
        action="application.created",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "job_id": str(app.job_id),
            "org_id": str(app.org_id),
            "snapshot_id": str(app.snapshot_id),
        },
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.SUBMITTED,
        actor_id=principal.user_id,
    )
    await analytics.record_event_safe(
        session,
        event_type="application.submitted",
        aggregate_type="application",
        aggregate_id=app.id,
        actor_id=principal.user_id,
        actor_type="student",
        properties={"job_id": str(job.id), "org_id": str(job.org_id)},
    )
    await _notify_partner_received(session, app=app, job=job, locale=locale)
    await _record_apply_metrics(session, job=job, principal=principal)

    await session.commit()
    await session.refresh(app)
    return presenters.applicant_application(app, job_title=job.title, locale=locale)


async def _record_apply_metrics(session: AsyncSession, *, job, principal: Principal) -> None:
    """Best-effort ``apply_start``/``applications_submitted`` hooks into
    ``partner_job_metrics_daily`` (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`).

    The current apply flow is single-step (no separate "start application" call
    before submit), so both counters are incremented together at submit time —
    documented simplification; a real multi-step apply-intent event is a later
    refinement once the frontend adds one.
    """

    try:
        from app.modules.analytics.application import partner_job_metrics_service as metrics

        source = await metrics.default_source_for_job(session, job_id=job.id)
        student_tier = metrics.student_tier_for_persona(principal.persona)
        major_group, year_group = await metrics.coarse_academic_dims(
            session, user_id=principal.user_id
        )
        for event_type in ("apply_start", "applications_submitted"):
            await metrics.record_job_metric_event(
                session,
                org_id=job.org_id,
                job_id=job.id,
                event_type=event_type,
                source=source,
                student_tier=student_tier,
                major_group=major_group,
                year_group=year_group,
            )
        await _record_ad_apply_attribution(session, job=job, principal=principal)
    except Exception:  # noqa: BLE001 — telemetry must never break apply submission
        pass


async def _record_ad_apply_attribution(
    session: AsyncSession, *, job, principal: Principal
) -> None:
    """Emit ``ad.apply_start`` when this apply is attributable to a live placement.

    Closes the ad funnel (impression -> click -> apply_start) so campaign
    performance can report apply attribution. Best-effort and non-breaking: if the
    job carries no currently-live sponsored placement there is nothing to
    attribute and we simply return.
    """

    from app.modules.advertising.application import inventory_facade
    from app.modules.advertising.domain.lifecycle import TARGET_JOB

    placement_id = await inventory_facade.active_placement_id_for_target(
        session, target_type=TARGET_JOB, target_id=job.id
    )
    if placement_id is None:
        return
    await analytics.record_event_safe(
        session,
        event_type="ad.apply_start",
        aggregate_type="ad_placement",
        aggregate_id=placement_id,
        actor_id=principal.user_id,
        actor_type="student",
        properties={"target_type": "job"},
    )


async def _notify_partner_received(
    session: AsyncSession, *, app: Application, job: job_read_facade.JobRef, locale: str
) -> None:
    poster = await user_service.get_by_id(session, job.posted_by)
    if poster is None:
        return
    applicant_label = "một ứng viên" if locale != "en" else "a candidate"
    await enqueue_notification(
        session,
        recipient_id=job.posted_by,
        template_key="application.received",
        channel="email",
        locale=locale,
        variables={
            "email": poster.email,
            "name": poster.full_name or "",
            "job_title": job.title,
            "applicant_label": applicant_label,
        },
        dedupe_key=f"application.received:{app.id}",
    )
    # In-app feed row for the posting partner (neutral "a candidate" label; the
    # applicant's real identity lives on the application detail behind RBAC).
    await feed_service.create_in_app(
        session,
        recipient_id=job.posted_by,
        notif_type="recruitment.application_received",
        action_url=f"/partner/applications/{app.id}",
        variables={"job_title": job.title, "applicant_label": applicant_label},
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Student reads                                                               #
# --------------------------------------------------------------------------- #


async def list_my_applications(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None
    page_limit = clamp_limit(limit)

    stmt = select(Application).where(
        Application.applicant_id == principal.user_id,
        Application.deleted_at.is_(None),
    )
    decoded = decode_cursor(cursor)
    if decoded is not None:
        from datetime import datetime

        anchor_created = datetime.fromisoformat(decoded["created_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                Application.created_at < anchor_created,
                (Application.created_at == anchor_created) & (Application.id < anchor_id),
            )
        )
    stmt = stmt.order_by(Application.created_at.desc(), Application.id.desc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda a: {
            "created_at": a.created_at.isoformat(),
            "id": str(a.id),
        },
    )
    titles = await _job_titles(session, [a.job_id for a in page.items])
    org_names = await _org_display_names(
        session, [a.org_id for a in page.items if a.org_id is not None]
    )
    items = [
        presenters.applicant_application(
            a,
            job_title=titles.get(a.job_id),
            company_name=org_names.get(a.org_id) if a.org_id else None,
            locale=locale,
        )
        for a in page.items
    ]
    return items, page.next_cursor, page.limit


async def _org_display_names(
    session: AsyncSession, org_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    return await org_reporting_facade.display_names_for(session, org_ids)


async def _job_titles(session: AsyncSession, job_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    return await job_read_facade.get_job_titles(session, job_ids)


def _is_partner_of(principal: Principal, app: Application) -> bool:
    if principal.is_superadmin:
        return True
    if principal.org_id is None or principal.org_id != app.org_id:
        return False
    return permission_checker.can(principal, _RESOURCE, "read", resource_org_id=app.org_id)


async def get_application(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Applicant -> own full view; authorized partner -> partner view; else 404."""

    app = await _shared.load_application(session, application_id=application_id)

    if principal.user_id is not None and app.applicant_id == principal.user_id:
        titles = await _job_titles(session, [app.job_id])

        # The student's OWN upcoming interview card (identity-safe: date/mode/
        # location-or-link only — NEVER assignee identities, scorecards, or the
        # gate). Lazy import avoids an apply_service <-> interview_service cycle.
        from app.modules.recruitment.application import interview_service

        upcoming_interview = await interview_service.student_interview_block(
            session, application_id=app.id, locale=locale
        )
        # The student's OWN offer summary card (identity-safe: position / their own
        # comp / start / deadline — NEVER partner internals, never a draft/pending
        # offer). Surfaced only for a sent+terminal offer (ADR-0007 §8).
        from app.modules.recruitment.application import offer_service
        from app.modules.recruitment.application.messaging_pointer import (
            application_messages_pointer,
        )
        from app.modules.recruitment.domain import offer as offer_domain

        offer_card = await offer_service.student_offer_block(
            session, application_id=app.id, locale=locale
        )
        timeline_events = await timeline.list_timeline_for_student(
            session, application_id=app.id, locale=locale
        )
        next_action = timeline.derive_next_action(
            status=app.status,
            has_upcoming_interview=upcoming_interview is not None,
            has_actionable_offer=(
                offer_card is not None and offer_card.get("status") == offer_domain.STATUS_SENT
            ),
        )
        pointer = await application_messages_pointer(
            session,
            application_id=app.id,
            viewer_id=principal.user_id,
            org_id=app.org_id,
        )
        messages_pointer = (
            {"thread_id": str(pointer.thread_id), "unread_count": pointer.unread_count}
            if pointer is not None
            else None
        )

        view = presenters.applicant_application(
            app,
            job_title=titles.get(app.job_id),
            timeline_events=timeline_events,
            next_action=next_action,
            messages_pointer=messages_pointer,
            locale=locale,
        )
        view["upcoming_interview"] = upcoming_interview
        view["offer"] = offer_card
        return view

    if _is_partner_of(principal, app):
        view = await _partner_view(
            session, app=app, principal=principal, locale=locale, include_detail=True
        )
        # Attach the pipeline position so the partner detail can render the
        # candidate's current stage. Lazy import avoids a cycle.
        from app.modules.recruitment.application import stage_service

        view["pipeline"] = await stage_service._pipeline_block(session, app=app)
        await _record_candidate_access(
            session,
            app=app,
            principal=principal,
            event_type="application_opened",
        )
        return view

    raise ResourceNotFoundError()


# --------------------------------------------------------------------------- #
# Withdraw                                                                    #
# --------------------------------------------------------------------------- #


async def _decrement_job_application_count(session: AsyncSession, *, job_id: uuid.UUID) -> None:
    """Decrement the denormalized ``jobs.application_count`` by one, floored at 0.

    Loads the job row the same way ``apply_to_job`` mutates it (the live ORM row),
    taking a row lock on Postgres so a concurrent apply/withdraw cannot interleave
    a lost update. The counter is never driven negative.
    """

    await job_read_facade.decrement_application_count(
        session, job_id, lock=_shared.use_for_update()
    )


async def withdraw_application(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    version: int | None = None,
    reason: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    app = await _shared.load_application(session, application_id=application_id, lock=True)
    # Only the applicant may withdraw; others cannot even tell it exists.
    if principal.user_id is None or app.applicant_id != principal.user_id:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "update")

    # Idempotent: already withdrawn -> return current state, no error (retry-safe;
    # a stale version on a replay is NOT an error either — the outcome is already
    # the one the caller wanted).
    if app.status == lifecycle.WITHDRAWN:
        return presenters.applicant_application(app, locale=locale)
    if version is not None and version != app.version:
        raise ApplicationVersionConflictError()
    if app.status not in lifecycle.WITHDRAWABLE_STATES:
        raise ApplicationNotWithdrawableError()

    clean_reason = (reason or "").strip() or None

    # Real submitted/under_review -> withdrawn transition (we are here only because
    # the idempotent re-withdraw early-returned above). The student is RETRACTING a
    # received application, so the denormalized, partner-visible job counter is
    # decremented in THIS transaction, mirroring the increment in ``apply_to_job``.
    #
    # Counter semantics decision: ``jobs.application_count`` = "applications
    # received". A withdraw is the student pulling back a submission -> decrement. A
    # rejection (``decision_service``) is a partner decision on a genuinely received
    # application -> it KEEPS counting (no decrement on reject). ``docs/DATA_MODEL.md``
    # line 736 defines the field only as a "denormalized counter" and does NOT scope
    # it to active applications; the active-only metric lives in a separate projection
    # field (``proj_student_dashboard.active_applications``, line 1321). The decrement
    # below is guarded by the real state change above, so an idempotent re-withdraw
    # never double-decrements and the counter cannot drift down.
    await _decrement_job_application_count(session, job_id=app.job_id)

    app.status = lifecycle.WITHDRAWN
    app.last_status_at = _shared.now()
    app.version += 1
    await session.flush()

    audit_after: dict = {"status": app.status}
    if clean_reason:
        audit_after["reason"] = clean_reason
    await write_audit(
        session,
        action="application.withdrawn",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after=audit_after,
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.WITHDRAWN,
        actor_id=principal.user_id,
        # The student's OWN free-text reason — fine to keep on their own timeline
        # (never surfaced to another student or the partner via this event).
        metadata={"reason": clean_reason} if clean_reason else None,
    )
    await session.commit()
    await session.refresh(app)
    return presenters.applicant_application(app, locale=locale)


# --------------------------------------------------------------------------- #
# Partner views                                                               #
# --------------------------------------------------------------------------- #


async def _applicant_block_for(session: AsyncSession, *, app: Application) -> dict:
    """The applicant's real identity block for a single application.

    An application always exposes the applicant's real identity to a partner who
    passed the base ``applications:read`` gate (owner decision 2026-07-10). Loads
    the user's contact (name/email) + safe avatar URL through the users /
    student-profile facades so recruitment never imports those ORMs directly.
    """

    user = await user_service.get_by_id(session, app.applicant_id)
    avatars = await avatar_facade.avatar_urls_for(session, [app.applicant_id])
    return presenters.applicant_block(app, user=user, avatar_url=avatars.get(app.applicant_id))


async def _cv_block_for(
    session: AsyncSession, *, app: Application, principal: Principal
) -> dict | None:
    """Watermarked inline CV view/download block for the partner detail.

    Gated on ``candidate_identity:view_cv`` (the CV-preview capability, additive to
    the base ``applications:read``) so CV access can be granted narrowly; a member
    without it sees the candidate but not the CV embed (``cv: null``). Returns
    ``None`` when the application carries no snapshot / nothing renderable.
    """

    if app.snapshot_id is None:
        return None
    if not permission_checker.can(
        principal, "candidate_identity", "view_cv", resource_org_id=app.org_id
    ):
        return None
    org_name = await _shared.org_display_name(session, app.org_id)
    watermark = f"VinUni Career • {org_name}"
    return await snapshot_service.build_partner_cv_view(
        session,
        snapshot_id=app.snapshot_id,
        actor_id=principal.user_id,
        watermark_text=watermark,
    )


async def _fit_block_for(session: AsyncSession, *, app: Application, locale: str) -> dict | None:
    """User-safe CV-JD fit ``{score, band, reasons}`` for the partner detail.

    Deterministic reuse of the shared CV-fit engine on the application's IMMUTABLE
    snapshot vs the job it was submitted to; ``None`` when not computable. Never
    exposes provider/model/token/latency/raw confidence/embedding internals.
    """

    if app.snapshot_id is None:
        return None
    return await application_fit_service.application_snapshot_fit(
        session,
        snapshot_id=app.snapshot_id,
        job_id=app.job_id,
        locale=locale,
    )


async def _partner_view(
    session: AsyncSession,
    *,
    app: Application,
    principal: Principal,
    locale: str,
    stage: dict | None = None,
    applicant: dict | None = None,
    include_detail: bool = False,
) -> dict:
    if applicant is None:
        applicant = await _applicant_block_for(session, app=app)
    assignee = await _assignee_block(session, app=app)
    cv = None
    fit = None
    if include_detail:
        cv = await _cv_block_for(session, app=app, principal=principal)
        fit = await _fit_block_for(session, app=app, locale=locale)
    return presenters.partner_application(
        app,
        applicant=applicant,
        cv=cv,
        fit=fit,
        assignee=assignee,
        stage=stage,
        locale=locale,
    )


async def _current_stages_for(
    session: AsyncSession, *, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict]:
    """Batch-resolve ``{application_id: {stage_id, stage_name}}`` for a LIST page.

    ONE join over the ACTIVE ``candidate_stages`` rows + their ``pipeline_stages``
    name — independent of page size (no per-application fetch). Applications still
    pre-pipeline (``submitted``, no ACTIVE row) are simply absent → ``stage`` is
    ``None`` on their card. Stage metadata only; never any student identity.
    """

    from app.modules.recruitment.domain import pipeline
    from app.modules.recruitment.domain.models import CandidateStage, PipelineStage

    if not application_ids:
        return {}
    rows = (
        await session.execute(
            select(
                CandidateStage.application_id,
                PipelineStage.id,
                PipelineStage.name,
            )
            .join(PipelineStage, PipelineStage.id == CandidateStage.stage_id)
            .where(
                CandidateStage.application_id.in_(set(application_ids)),
                CandidateStage.status == pipeline.STAGE_ACTIVE,
            )
        )
    ).all()
    return {
        app_id: {"stage_id": str(stage_id), "stage_name": name}
        for app_id, stage_id, name in rows
    }


async def _assignee_block(session: AsyncSession, *, app: Application) -> dict | None:
    """Resolve the assigned recruiter (candidate owner) into a display block.

    ``None`` when unassigned or the membership no longer resolves (e.g. removed).
    Reads through the org facade so the recruitment module never imports the
    ``Membership`` ORM directly.
    """

    if app.assigned_to_membership_id is None:
        return None
    brief = await org_reporting_facade.member_brief(
        session, org_id=app.org_id, membership_id=app.assigned_to_membership_id
    )
    if brief is None:
        return None
    return {
        "membership_id": str(brief.membership_id),
        "user_id": str(brief.user_id),
        "display_name": brief.display_name,
    }


async def _assignee_filter_clause(
    session: AsyncSession, *, principal: Principal, assignee: str | None
):
    """Translate the ``assignee`` filter token into a SQL clause (or ``None``).

    ``"me"`` resolves the caller's own membership; ``"unassigned"`` matches the
    NULL owner; anything else is parsed as a membership id. An unresolvable token
    yields an always-false clause so the page is empty rather than unfiltered.
    """

    if not assignee:
        return None
    if assignee == "unassigned":
        return Application.assigned_to_membership_id.is_(None)
    if assignee == "me":
        if principal.org_id is None or principal.user_id is None:
            return Application.id.is_(None)  # no membership -> match nothing
        mid = await org_reporting_facade.membership_id_for_user_in_org(
            session, org_id=principal.org_id, user_id=principal.user_id
        )
        if mid is None:
            return Application.id.is_(None)
        return Application.assigned_to_membership_id == mid
    try:
        return Application.assigned_to_membership_id == uuid.UUID(assignee)
    except (ValueError, AttributeError, TypeError):
        return Application.id.is_(None)


async def list_job_applications(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    cursor: str | None = None,
    limit: int | None = None,
    status: str | None = None,
    assignee: str | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    """Partner-scoped list of applications to one of the caller org's jobs.

    The job must belong to the caller's org (else ``404``); ``applications:read``
    is required. Each row carries the applicant's real identity block (never
    masked); the CV embed + fit are DETAIL-only enrichments (not on the list).

    Team filters (all optional, composable):

    - ``status`` — one application status (``submitted``/``under_review``/…).
    - ``assignee`` — candidate owner: ``"me"`` (the caller's own membership),
      ``"unassigned"``, or a specific membership id. An unknown/cross-org
      membership id simply yields an empty page (never a tenant leak).
    """

    job = await job_read_facade.get_job_ref(session, job_id)
    if job is None:
        raise ResourceNotFoundError()
    # Tenant isolation: a cross-org job is indistinguishable from missing.
    if not principal.is_superadmin and (principal.org_id is None or principal.org_id != job.org_id):
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=job.org_id)

    page_limit = clamp_limit(limit)
    stmt = select(Application).where(Application.job_id == job.id, Application.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Application.status == status)
    assignee_clause = await _assignee_filter_clause(session, principal=principal, assignee=assignee)
    if assignee_clause is not None:
        stmt = stmt.where(assignee_clause)
    decoded = decode_cursor(cursor)
    if decoded is not None:
        from datetime import datetime

        anchor_applied = datetime.fromisoformat(decoded["applied_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                Application.applied_at < anchor_applied,
                (Application.applied_at == anchor_applied) & (Application.id < anchor_id),
            )
        )
    stmt = stmt.order_by(Application.applied_at.desc(), Application.id.desc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda a: {
            "applied_at": a.applied_at.isoformat(),
            "id": str(a.id),
        },
    )

    # Current pipeline stage per row — ONE batched join (independent of page size).
    stages = await _current_stages_for(
        session, application_ids=[a.id for a in page.items]
    )
    # Applicant identity per row — TWO batched facade lookups (contacts + avatars)
    # for the whole page, independent of page size (no per-row user fetch).
    applicant_ids = [a.applicant_id for a in page.items]
    contacts = await user_read_facade.get_user_contacts(session, applicant_ids)
    avatars = await avatar_facade.avatar_urls_for(session, applicant_ids)
    items: list[dict] = []
    for a in page.items:
        applicant = presenters.applicant_block(
            a, user=contacts.get(a.applicant_id), avatar_url=avatars.get(a.applicant_id)
        )
        items.append(
            await _partner_view(
                session,
                app=a,
                principal=principal,
                locale=locale,
                stage=stages.get(a.id),
                applicant=applicant,
            )
        )
    return items, page.next_cursor, page.limit


# --------------------------------------------------------------------------- #
# CV download (owner unwatermarked / partner watermarked)                      #
# --------------------------------------------------------------------------- #


async def get_application_cv_download(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Return a signed snapshot download URL.

    Applicant -> unwatermarked (owner). Authorized partner -> watermarked. Anyone
    else -> ``404``. The partner path is gated on ``candidate_identity:download_cv``
    and every download is audited (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md``).
    """

    app = await _shared.load_application(session, application_id=application_id)
    if app.snapshot_id is None:
        raise ResourceNotFoundError()

    # Applicant self-download (unwatermarked) goes straight through the facade.
    if principal.user_id is not None and app.applicant_id == principal.user_id:
        return await snapshot_service.get_snapshot_download(
            session, principal=principal, snapshot_id=app.snapshot_id
        )

    if not _is_partner_of(principal, app):
        raise ResourceNotFoundError()
    # Downloading a candidate's CV is a sensitive action gated on the dedicated
    # ``candidate_identity:download_cv`` capability (additive to the base
    # partner-of-org ``applications:read``) so CV export can be granted narrowly to
    # a subset of the team and every use is audited
    # (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md`` candidate_identity row).
    permission_checker.require(
        principal, "candidate_identity", "download_cv", resource_org_id=app.org_id
    )

    org_name = await _shared.org_display_name(session, app.org_id)
    watermark = f"VinUni Career • {org_name}"
    await _record_candidate_access(
        session,
        app=app,
        principal=principal,
        event_type="cv_downloaded",
    )
    with access.authorized_download(
        snapshot_id=app.snapshot_id,
        user_id=principal.user_id,
        watermark_text=watermark,
    ):
        return await snapshot_service.get_snapshot_download(
            session, principal=principal, snapshot_id=app.snapshot_id
        )


async def _record_candidate_access(
    session: AsyncSession,
    *,
    app: Application,
    principal: Principal,
    event_type: str,
) -> None:
    """Best-effort hook into ``partner_candidate_access_events``
    (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`). Instrumentation only — never raises,
    never changes the caller's authorization/business outcome."""

    try:
        from app.modules.analytics.application import partner_candidate_access_service as access_log

        await access_log.record_access_event(
            session,
            org_id=app.org_id,
            actor_id=principal.user_id,
            application_id=app.id,
            job_id=app.job_id,
            candidate_id=app.applicant_id,
            event_type=event_type,
        )
        # Both call sites (``get_application`` / ``get_application_cv_download``)
        # are otherwise pure reads (no commit) — this write must commit explicitly
        # or the session close at the end of the request would silently discard it.
        await session.commit()
    except Exception:  # noqa: BLE001 — audit instrumentation must never break the read/download
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
