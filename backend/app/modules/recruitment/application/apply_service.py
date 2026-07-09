"""Apply flow: submit, list (student), detail, withdraw, partner views, CV download.

RBAC is enforced here (not in routers):

- A student applies only as itself (``applications:create``); the snapshot owner is
  always the acting user.
- A partner sees applications only for its own org's jobs (``applications:read`` +
  ``org_id`` match); a cross-org access is indistinguishable from missing (``404``).
- An anonymous applicant's identity is redacted in partner views until a reveal
  request is accepted; the watermarked partner CV download is likewise blocked
  until reveal for anonymous applications.

Every write is audited in the caller's transaction; the immutable CV snapshot is
created via the documents facade (never reimplemented); the partner notification
is enqueued on the outbox (no synchronous SMTP).
"""

from __future__ import annotations

import copy
import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.application import ingestion_service as analytics
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import snapshot_service
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
from app.modules.recruitment.domain.models import Application, ApplicationRevealRequest
from app.modules.users.application import user_service
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
        is_anonymous=bool(payload.get("is_anonymous", False)),
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

    # Anonymous applications carry a redacted snapshot COPY for the partner-side
    # pre-reveal preview (``docs/BUSINESS_LOGIC.md`` §4.2 / ``docs/SECURITY_PRIVACY.md``).
    # The ORIGINAL ``snapshot_json`` stays immutable and un-redacted so an accepted
    # reveal still exposes the true identity; only this copy is served pre-reveal.
    # Guarded on ``redacted_json is None`` so an idempotent apply-replay (the
    # snapshot already existed) never rebuilds/overwrites it.
    if app.is_anonymous and snapshot.redacted_json is None:
        snapshot.redacted_json = _redact_snapshot(snapshot.snapshot_json or {})

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
            "is_anonymous": app.is_anonymous,
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
    except Exception:  # noqa: BLE001 — telemetry must never break apply submission
        pass


# --------------------------------------------------------------------------- #
# Anonymous-apply CV snapshot redaction (B-603)                                #
# --------------------------------------------------------------------------- #
#
# The immutable snapshot mirrors the CV content model (``documents`` module):
#   - a ``header`` section, ``content_json`` = {name, headline, email, phone,
#     location, links:[{label,url}]} — DIRECTLY identifying,
#   - entry sections, ``content_json`` = {entries:[{heading, subheading, timeframe,
#     location, note, highlights[]}]},
#   - skills/languages, ``content_json`` = {items:[{name, level}]},
#   - text sections, ``content_json`` = {text} / {items:[{text}]}.
# Uploaded-CV snapshots use {title, source_type, document_id, sections:[{title,
# content_json:{items}}]} (no header section; the ingestion path already drops the
# contact block).
#
# For an anonymous application the partner's PRE-REVEAL view must not leak the
# student's identity, yet must keep the evaluable professional content. We drop the
# header contact block and scrub email/phone patterns that can appear inside free
# text — while preserving skills, experience headings/bullets, and education.

_ANON_NAME = "[Ẩn danh]"
# Inline redaction mark for a scrubbed email/phone pattern. Carries no ``@`` and no
# digit run, which makes the scrub idempotent (a re-run finds nothing new).
_PII_MARK = "[đã ẩn]"

# Header/contact fields that identify the applicant — removed entirely.
_HEADER_CONTACT_FIELDS = ("name", "email", "phone", "location", "links")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,}")
# A phone-like run: optional leading ``+``/``(``, a digit, then 8-14 more chars from
# {digit, space, ., -, (, )}, ending on a digit. The digit-count validator below
# (9..15) keeps year ranges ("2020 - 2023" = 8 digits), month/year ranges broken by
# ``/``, and GPAs intact — only genuine phone numbers are scrubbed.
_PHONE_CANDIDATE_RE = re.compile(r"\+?\(?\d[\d\s().\-]{7,}\d")


def _scrub_pii_text(value: str) -> str:
    """Replace email + phone-number patterns in one string with a redaction mark.

    Deterministic (pure regex) and idempotent (the mark contains no ``@`` and no
    9+ digit run, so re-scrubbing already-scrubbed text is a no-op).
    """

    scrubbed = _EMAIL_RE.sub(_PII_MARK, value)

    def _phone_repl(match: re.Match[str]) -> str:
        digits = sum(ch.isdigit() for ch in match.group(0))
        return _PII_MARK if 9 <= digits <= 15 else match.group(0)

    return _PHONE_CANDIDATE_RE.sub(_phone_repl, scrubbed)


def _scrub_deep(value: object) -> object:
    """Recursively scrub PII patterns from every string in a nested structure.

    Non-string leaves (skill ``level`` ints, ``is_visible`` bools, ids) are returned
    untouched, so evaluable structured data (skills 0-100, experience entries,
    education) survives intact.
    """

    if isinstance(value, str):
        return _scrub_pii_text(value)
    if isinstance(value, list):
        return [_scrub_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub_deep(v) for k, v in value.items()}
    return value


def _redact_header_content(content: dict) -> dict:
    """Strip the identifying contact block from a CV header ``content_json``.

    Drops name/email/phone/location/links and re-labels the name as ``[Ẩn danh]``
    so the header still renders anonymously; keeps the professional ``headline``
    (pattern-scrubbed) because it carries positioning, not identity.
    """

    redacted = {key: value for key, value in content.items() if key not in _HEADER_CONTACT_FIELDS}
    redacted = {key: _scrub_deep(value) for key, value in redacted.items()}
    redacted["name"] = _ANON_NAME
    return redacted


def _redact_snapshot(snapshot_json: dict) -> dict:
    """Build the anonymous partner-preview COPY of an immutable CV snapshot.

    Removes identifying PII (header contact + inline email/phone patterns) while
    PRESERVING evaluable content (skills, experience headings/bullets, education).
    Deep-copies its input so the ORIGINAL immutable ``snapshot_json`` is never
    mutated — the reveal flow keeps serving the un-redacted original. Pure,
    deterministic, and idempotent (redacting the output again yields the same JSON).
    """

    redacted = copy.deepcopy(dict(snapshot_json))
    # The top-level title can carry the applicant's name — an uploaded CV's title is
    # ``document.original_name`` (e.g. "Nguyen Van A - CV.pdf"), and a builder title
    # may include the person's name. Replace it with the anonymous label.
    redacted["title"] = _ANON_NAME
    sections = redacted.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            content = section.get("content_json")
            if not isinstance(content, dict):
                continue
            if section.get("section_type") == "header":
                section["content_json"] = _redact_header_content(content)
            else:
                section["content_json"] = _scrub_deep(content)
    redacted["redacted"] = True
    return redacted


async def _notify_partner_received(
    session: AsyncSession, *, app: Application, job: job_read_facade.JobRef, locale: str
) -> None:
    poster = await user_service.get_by_id(session, job.posted_by)
    if poster is None:
        return
    applicant_label = "Ứng viên ẩn danh" if app.is_anonymous else "một ứng viên"
    if locale == "en":
        applicant_label = "an anonymous candidate" if app.is_anonymous else "a candidate"
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
    # In-app feed row for the posting partner. Uses the anonymous applicant handle
    # only — never the student's name/email — for anonymous applications.
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


def _effective_reveal_status(req: ApplicationRevealRequest) -> str:
    """A still-``pending`` request past its 72h expiry reads as ``expired``.

    Read path only — never mutates the row (lazy expiry is committed by
    ``reveal_service.respond_reveal``); this just keeps the applicant view from
    offering an accept/decline panel for a request that can no longer be acted on.
    """

    if req.status == lifecycle.REVEAL_PENDING and _shared.as_aware(req.expires_at) <= _shared.now():
        return lifecycle.REVEAL_EXPIRED
    return req.status


async def _latest_reveal_for(
    session: AsyncSession, *, application_id: uuid.UUID
) -> ApplicationRevealRequest | None:
    """The most recent reveal request on an application (at most one per org)."""

    return (
        (
            await session.execute(
                select(ApplicationRevealRequest)
                .where(ApplicationRevealRequest.application_id == application_id)
                .order_by(ApplicationRevealRequest.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


async def _latest_reveals_for(
    session: AsyncSession, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ApplicationRevealRequest]:
    """Batch the latest reveal request per application id (avoids N+1)."""

    if not application_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(ApplicationRevealRequest)
                .where(ApplicationRevealRequest.application_id.in_(set(application_ids)))
                .order_by(ApplicationRevealRequest.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[uuid.UUID, ApplicationRevealRequest] = {}
    for req in rows:
        latest.setdefault(req.application_id, req)
    return latest


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
    reveals = await _latest_reveals_for(session, [a.id for a in page.items])
    hiring_org_ids = [a.org_id for a in page.items if a.org_id is not None]
    reveal_org_ids = [r.requester_org_id for r in reveals.values()]
    org_names = await _org_display_names(session, hiring_org_ids + reveal_org_ids)
    items = []
    for a in page.items:
        req = reveals.get(a.id)
        items.append(
            presenters.applicant_application(
                a,
                job_title=titles.get(a.job_id),
                company_name=org_names.get(a.org_id) if a.org_id else None,
                reveal=req,
                reveal_status=_effective_reveal_status(req) if req else None,
                reveal_company_name=(org_names.get(req.requester_org_id) if req else None),
                locale=locale,
            )
        )
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
        req = await _latest_reveal_for(session, application_id=app.id)
        company = (
            await _shared.org_display_name(session, req.requester_org_id)
            if req is not None
            else None
        )

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
            reveal=req,
            reveal_status=_effective_reveal_status(req) if req else None,
            reveal_company_name=company,
            timeline_events=timeline_events,
            next_action=next_action,
            messages_pointer=messages_pointer,
            locale=locale,
        )
        view["upcoming_interview"] = upcoming_interview
        view["offer"] = offer_card
        return view

    if _is_partner_of(principal, app):
        view = await _partner_view(session, app=app, principal=principal, locale=locale)
        # Attach the (anonymity-safe) pipeline position so the partner detail can
        # render the candidate's current stage. Lazy import avoids a cycle.
        from app.modules.recruitment.application import stage_service

        view["pipeline"] = await stage_service._pipeline_block(session, app=app)
        await _record_candidate_access(
            session,
            app=app,
            principal=principal,
            event_type="application_opened",
        )
        if app.reveal_approved_at is not None and _can_view_identity(principal, app):
            await _record_candidate_access(
                session,
                app=app,
                principal=principal,
                event_type="identity_revealed_viewed",
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


async def _reveal_status_for(
    session: AsyncSession, *, application_id: uuid.UUID, org_id: uuid.UUID
) -> str | None:
    return (
        await session.execute(
            select(ApplicationRevealRequest.status).where(
                ApplicationRevealRequest.application_id == application_id,
                ApplicationRevealRequest.requester_org_id == org_id,
            )
        )
    ).scalar_one_or_none()


def _can_view_identity(principal: Principal, app: Application) -> bool:
    """Whether ``principal`` may see this applicant's real identity.

    A non-anonymous applicant chose to apply openly, so identity is visible to any
    partner-of-org (base ``applications:read``). An ANONYMOUS applicant whose
    reveal was accepted is only unmasked for a member additionally holding
    ``candidate_identity:view_revealed_identity``; without it the partner keeps the
    redacted view even post-reveal (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md``). The
    Admin wildcard (``*:*``) passes.
    """

    if not app.is_anonymous:
        return True
    if app.reveal_approved_at is None:
        return False
    return permission_checker.can(
        principal, "candidate_identity", "view_revealed_identity", resource_org_id=app.org_id
    )


async def _partner_view(
    session: AsyncSession, *, app: Application, principal: Principal, locale: str
) -> dict:
    authorized = _can_view_identity(principal, app)
    user = None
    if authorized:
        user = await user_service.get_by_id(session, app.applicant_id)
    reveal_status = await _reveal_status_for(session, application_id=app.id, org_id=app.org_id)
    assignee = await _assignee_block(session, app=app)
    return presenters.partner_application(
        app,
        user=user,
        reveal_status=reveal_status,
        identity_authorized=authorized,
        assignee=assignee,
        locale=locale,
    )


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
    is required. Anonymous applicants are redacted until reveal is accepted.

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

    items: list[dict] = []
    for a in page.items:
        items.append(await _partner_view(session, app=a, principal=principal, locale=locale))
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

    Applicant -> unwatermarked (owner). Authorized partner -> watermarked, but only
    once an anonymous applicant's reveal has been accepted (PDF view is unavailable
    until then per ``docs/BUSINESS_LOGIC.md`` §4.2). Anyone else -> ``404``.
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
    # Downloading a candidate's CV is a sensitive-identity action gated on the
    # dedicated ``candidate_identity:download_cv`` capability (additive to the base
    # partner-of-org ``applications:read``) so CV export can be granted narrowly to
    # a subset of the team and every use is audited
    # (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md`` candidate_identity row).
    permission_checker.require(
        principal, "candidate_identity", "download_cv", resource_org_id=app.org_id
    )

    # Anonymous + not yet revealed -> PDF download blocked.
    if app.is_anonymous and app.reveal_approved_at is None:
        raise ResourceNotFoundError()

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
