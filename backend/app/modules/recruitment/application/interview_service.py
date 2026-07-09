"""Interview scheduling + reviewer assignees (ADR-0006 §3/§4/§6).

Layered on the shipped ADR-0004 stage engine and ADR-0005 scorecards. An interview
is ONE editable-in-place scheduled round for an application at its CURRENT ACTIVE
pipeline stage, with an explicit list of assigned interviewers (PERSON mode,
``threshold_pct = 1.0`` -> all assigned must submit a scorecard).

Hard rules enforced HERE (service layer, never the router):

- **Reveal precondition (NON-NEGOTIABLE, §3):** scheduling an interview on an
  ANONYMOUS application whose reveal has not been accepted raises
  ``RevealRequiredError`` (409 ``reveal_required``). The reveal handshake stays the
  ONLY identity path; the student's consent is never silently bypassed.
- One OPEN (``scheduled``) interview per ``(application, stage)`` (409
  ``interview_exists``); a second is blocked.
- Assignees must be ACTIVE members of the job's org (else ``422``).
- ``online`` requires a ``meeting_link``; ``onsite`` requires a ``location``.
- ``meeting_link`` is Fernet-encrypted at rest and decrypted only for ATTENDEES
  (the candidate + assigned interviewers); it never reaches the board or a
  non-attendee/student surface.
- Partner-of-org RBAC (cross-org -> ``404`` via
  ``decision_service._load_partner_application``); optimistic ``version`` on
  reschedule/cancel/complete; an audit row per write; notifications via the outbox +
  feed (no synchronous SMTP).

ANONYMITY: an interview carries NO student-identity field. The candidate is notified
about THEIR OWN interview (they know their own identity, so it leaks nothing); the
reveal is what gates interviewers seeing the STUDENT's identity. The student
projection never carries assignee identities, scorecards, or the gate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import (
    dispatch_service,
    feed_service,
    message_catalog,
)
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.application import job_read_facade
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.api import presenters
from app.modules.recruitment.application import _shared
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    IllegalApplicationTransitionError,
    InterviewExistsError,
    InterviewNotActionableError,
    InterviewNotRespondableError,
    InterviewResponseConflictError,
    InvalidApplicationFieldError,
    RevealRequiredError,
)
from app.modules.recruitment.domain import interview as interview_domain
from app.modules.recruitment.domain import lifecycle, timeline
from app.modules.recruitment.domain.models import Interview, InterviewAssignee
from app.modules.recruitment.infrastructure.meeting_link_crypto import (
    encrypt_meeting_link,
)
from app.modules.users.application import user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "interviews"
_PERM_SCHEDULE = "schedule"
_PERM_ASSIGN = "assign"
_PERM_COMPLETE = "complete"
_PERM_CANCEL = "cancel"
_PERM_READ = "read"

_EVENT = "schedule_interview"

# Reminder windows (ADR-0006 §4): T-24h (candidate + assignees) and T-1h (candidate).
_WINDOW_24H = "24h"
_WINDOW_1H = "1h"
_REMINDER_WINDOWS: tuple[tuple[str, timedelta], ...] = (
    (_WINDOW_24H, timedelta(hours=24)),
    (_WINDOW_1H, timedelta(hours=1)),
)
# Assignees are reminded only at T-24h (the candidate also gets T-1h).
_ASSIGNEE_WINDOWS: frozenset[str] = frozenset({_WINDOW_24H})


# --------------------------------------------------------------------------- #
# Repository helpers                                                           #
# --------------------------------------------------------------------------- #


async def _open_interview(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    stage_id: uuid.UUID,
    lock: bool = False,
) -> Interview | None:
    """The single OPEN (``scheduled``) interview for ``(application, stage)``, if any."""

    stmt = select(Interview).where(
        Interview.application_id == application_id,
        Interview.stage_id == stage_id,
        Interview.status == interview_domain.STATUS_SCHEDULED,
    )
    if lock and _shared.use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().first()


async def open_interview_id(
    session: AsyncSession, *, application_id: uuid.UUID, stage_id: uuid.UUID
) -> uuid.UUID | None:
    """The id of the stage's OPEN interview (used to auto-link a scorecard)."""

    iv = await _open_interview(
        session, application_id=application_id, stage_id=stage_id
    )
    return iv.id if iv is not None else None


async def _assignee_ids(
    session: AsyncSession, *, interview_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        (
            await session.execute(
                select(InterviewAssignee.user_id).where(
                    InterviewAssignee.interview_id == interview_id
                )
            )
        ).scalars().all()
    )


async def open_interview_assignee_ids(
    session: AsyncSession, *, application_id: uuid.UUID, stage_id: uuid.UUID
) -> set[uuid.UUID]:
    """Assignee ``user_id`` set on the stage's OPEN interview (empty when none).

    The advance-gate denominator (``scorecard_service._gate_inputs``): when the stage
    has an open interview with assignees, ``required`` = this set's size.
    """

    iv = await _open_interview(
        session, application_id=application_id, stage_id=stage_id
    )
    if iv is None:
        return set()
    return set(await _assignee_ids(session, interview_id=iv.id))


async def _load_interview(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    lock: bool = False,
) -> Interview | None:
    stmt = select(Interview).where(
        Interview.id == interview_id, Interview.application_id == application_id
    )
    if lock and _shared.use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().first()


async def _active_org_member_ids(
    session: AsyncSession, *, org_id: uuid.UUID, user_ids: set[uuid.UUID]
) -> set[uuid.UUID]:
    if not user_ids:
        return set()
    return await org_reporting_facade.active_member_ids(
        session, org_id=org_id, user_ids=user_ids
    )


async def _interviews_for_application(
    session: AsyncSession, *, application_id: uuid.UUID
) -> list[Interview]:
    return list(
        (
            await session.execute(
                select(Interview)
                .where(Interview.application_id == application_id)
                .order_by(Interview.scheduled_at, Interview.created_at)
            )
        ).scalars().all()
    )


# --------------------------------------------------------------------------- #
# Validation (defensive — Pydantic guards the HTTP boundary)                   #
# --------------------------------------------------------------------------- #


def _clean_text(value: str | None) -> str | None:
    """Trim free text to a non-empty string, or ``None``."""

    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _validate_mode_payload(
    *, mode: str, location: str | None, meeting_link: str | None
) -> None:
    if mode not in interview_domain.MODES:
        raise InvalidApplicationFieldError(field="mode")
    if mode == interview_domain.MODE_ONLINE and not (meeting_link or "").strip():
        raise InvalidApplicationFieldError(field="meeting_link")
    if mode == interview_domain.MODE_ONSITE and not (location or "").strip():
        raise InvalidApplicationFieldError(field="location")


async def _validate_assignees(
    session: AsyncSession, *, org_id: uuid.UUID, assignee_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Dedupe + verify every assignee is an ACTIVE member of the job's org (else 422)."""

    deduped: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for uid in assignee_ids:
        if uid not in seen:
            seen.add(uid)
            deduped.append(uid)
    members = await _active_org_member_ids(
        session, org_id=org_id, user_ids=set(deduped)
    )
    if set(deduped) - members:
        raise InvalidApplicationFieldError(field="assignee_ids")
    return deduped


# --------------------------------------------------------------------------- #
# Presentation helpers                                                         #
# --------------------------------------------------------------------------- #


async def _assignee_views(
    session: AsyncSession, *, interview_id: uuid.UUID
) -> tuple[list[dict], set[uuid.UUID]]:
    ids = await _assignee_ids(session, interview_id=interview_id)
    users = {}
    for uid in ids:
        u = await user_service.get_by_id(session, uid)
        if u is not None:
            users[uid] = u
    views = [
        {"user_id": str(uid), "name": (users[uid].full_name or "") if uid in users else ""}
        for uid in ids
    ]
    return views, set(ids)


async def _stage_evaluation_for(
    session: AsyncSession, *, application_id: uuid.UUID, stage_id: uuid.UUID
) -> dict | None:
    from app.modules.recruitment.application import scorecard_service, stage_service

    stage = await stage_service._load_stage(session, stage_id=stage_id)
    if stage is None:
        return None
    return await scorecard_service.stage_evaluation_summary(
        session, application_id=application_id, stage=stage
    )


async def _interview_view(
    session: AsyncSession,
    *,
    iv: Interview,
    principal: Principal,
    locale: str,
) -> dict:
    assignee_views, assignee_id_set = await _assignee_views(
        session, interview_id=iv.id
    )
    viewer_is_attendee = principal.user_id in assignee_id_set
    evaluation = await _stage_evaluation_for(
        session, application_id=iv.application_id, stage_id=iv.stage_id
    )
    return presenters.interview_view(
        iv,
        assignees=assignee_views,
        evaluation=evaluation,
        viewer_is_attendee=viewer_is_attendee,
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Schedule                                                                     #
# --------------------------------------------------------------------------- #


async def schedule_interview(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    mode: str,
    scheduled_at: datetime,
    assignee_ids: list[uuid.UUID],
    duration_minutes: int = 60,
    location: str | None = None,
    meeting_link: str | None = None,
    title: str | None = None,
    notes: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Schedule the candidate's interview for their CURRENT ACTIVE stage (ADR-0006 §6)."""

    from app.modules.recruitment.application import decision_service, stage_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _RESOURCE, _PERM_SCHEDULE, resource_org_id=app.org_id
    )

    # Reveal precondition (NON-NEGOTIABLE §3): an anonymous app with no accepted
    # reveal can NOT be scheduled — the handshake is the only identity path.
    if app.is_anonymous and app.reveal_approved_at is None:
        raise RevealRequiredError()

    # Only meaningful while the application is actively in the pipeline.
    if app.status != lifecycle.UNDER_REVIEW:
        raise IllegalApplicationTransitionError(event=_EVENT)
    active = await stage_service._active_stage(
        session, application_id=app.id, lock=True
    )
    if active is None:
        raise IllegalApplicationTransitionError(event=_EVENT)
    stage_id = active.stage_id

    _validate_mode_payload(mode=mode, location=location, meeting_link=meeting_link)
    clean_assignees = await _validate_assignees(
        session, org_id=app.org_id, assignee_ids=assignee_ids
    )

    # One OPEN interview per (application, stage).
    if (
        await _open_interview(
            session, application_id=app.id, stage_id=stage_id, lock=True
        )
        is not None
    ):
        raise InterviewExistsError()

    clean_link = (meeting_link or "").strip()
    iv = Interview(
        application_id=app.id,
        stage_id=stage_id,
        org_id=app.org_id,
        title=_clean_text(title),
        mode=mode,
        scheduled_at=_shared.as_aware(scheduled_at),
        duration_minutes=duration_minutes,
        location=_clean_text(location),
        meeting_link=encrypt_meeting_link(clean_link) if clean_link else None,
        status=interview_domain.STATUS_SCHEDULED,
        notes=_clean_text(notes),
        created_by=principal.user_id,
        version=1,
    )
    session.add(iv)
    await session.flush()
    for uid in clean_assignees:
        session.add(InterviewAssignee(interview_id=iv.id, user_id=uid))
    await session.flush()

    await write_audit(
        session,
        action="application.interview_scheduled",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "interview_id": str(iv.id),
            "stage_id": str(stage_id),
            "mode": mode,
            "scheduled_at": iv.scheduled_at.isoformat(),
            "assignee_count": len(clean_assignees),
        },
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.INTERVIEW_SCHEDULED,
        actor_id=principal.user_id,
        metadata={"interview_id": str(iv.id)},
    )

    await _notify_candidate(
        session,
        app=app,
        iv=iv,
        template_key="application.interview_scheduled",
        notif_type="recruitment.interview_scheduled",
        dedupe_suffix="scheduled",
    )
    await _notify_assignees_assigned(
        session, app=app, iv=iv, assignee_ids=clean_assignees
    )

    await session.commit()
    await session.refresh(iv)
    return await _interview_view(session, iv=iv, principal=principal, locale=locale)


# --------------------------------------------------------------------------- #
# Reschedule / edit                                                            #
# --------------------------------------------------------------------------- #


async def reschedule_interview(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    scheduled_at: datetime | None = None,
    mode: str | None = None,
    location: str | None = None,
    meeting_link: str | None = None,
    title: str | None = None,
    notes: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Reschedule / edit an interview in place (optimistic ``version``)."""

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _RESOURCE, _PERM_SCHEDULE, resource_org_id=app.org_id
    )

    iv = await _load_interview(
        session, application_id=app.id, interview_id=interview_id, lock=True
    )
    if iv is None:
        raise ResourceNotFoundError()
    if version is not None and version != iv.version:
        raise ApplicationVersionConflictError()
    if iv.status != interview_domain.STATUS_SCHEDULED:
        raise InterviewNotActionableError(reason="interview_not_open")

    new_mode = mode if mode is not None else iv.mode
    new_location = location if location is not None else iv.location
    # Whether a meeting link WILL exist after this edit: the provided value when
    # supplied (empty clears it), else the existing stored ciphertext. A non-empty
    # ciphertext marker validates "online has a link" without decrypting it.
    if meeting_link is not None:
        effective_link: str | None = meeting_link
    else:
        effective_link = "stored" if iv.meeting_link else None
    _validate_mode_payload(
        mode=new_mode, location=new_location, meeting_link=effective_link
    )

    iv.mode = new_mode
    iv.location = _clean_text(new_location)
    if meeting_link is not None:
        clean_link = meeting_link.strip()
        iv.meeting_link = encrypt_meeting_link(clean_link) if clean_link else None
    if scheduled_at is not None:
        iv.scheduled_at = _shared.as_aware(scheduled_at)
    if title is not None:
        iv.title = _clean_text(title)
    if notes is not None:
        iv.notes = _clean_text(notes)
    # The interview terms changed underneath the candidate — any prior
    # confirm/decline/reschedule response is now stale, so clear it and let the
    # student respond to the new time (Theme D).
    iv.candidate_response = None
    iv.candidate_responded_at = None
    iv.candidate_response_note = None
    iv.version += 1
    await session.flush()

    await write_audit(
        session,
        action="application.interview_rescheduled",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "interview_id": str(iv.id),
            "mode": iv.mode,
            "scheduled_at": iv.scheduled_at.isoformat(),
            "version": iv.version,
        },
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.INTERVIEW_RESCHEDULED,
        actor_id=principal.user_id,
        metadata={"interview_id": str(iv.id)},
    )

    await _notify_candidate(
        session,
        app=app,
        iv=iv,
        template_key="application.interview_rescheduled",
        notif_type="recruitment.interview_rescheduled",
        dedupe_suffix=f"rescheduled:{iv.version}",
    )
    await _notify_assignees_assigned(
        session,
        app=app,
        iv=iv,
        assignee_ids=await _assignee_ids(session, interview_id=iv.id),
        dedupe_suffix=f"rescheduled:{iv.version}",
    )

    await session.commit()
    await session.refresh(iv)
    return await _interview_view(session, iv=iv, principal=principal, locale=locale)


# --------------------------------------------------------------------------- #
# Assignees (PUT replace)                                                      #
# --------------------------------------------------------------------------- #


async def set_assignees(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    assignee_ids: list[uuid.UUID],
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Replace the assignee set (members of the org). Changes the gate ``required``."""

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _RESOURCE, _PERM_ASSIGN, resource_org_id=app.org_id
    )

    iv = await _load_interview(
        session, application_id=app.id, interview_id=interview_id, lock=True
    )
    if iv is None:
        raise ResourceNotFoundError()

    clean_assignees = await _validate_assignees(
        session, org_id=app.org_id, assignee_ids=assignee_ids
    )
    existing = set(await _assignee_ids(session, interview_id=iv.id))
    await session.execute(
        delete(InterviewAssignee).where(InterviewAssignee.interview_id == iv.id)
    )
    for uid in clean_assignees:
        session.add(InterviewAssignee(interview_id=iv.id, user_id=uid))
    await session.flush()

    await write_audit(
        session,
        action="application.interview_assignees_changed",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "interview_id": str(iv.id),
            "assignee_count": len(clean_assignees),
        },
    )

    newly_assigned = [uid for uid in clean_assignees if uid not in existing]
    await _notify_assignees_assigned(
        session, app=app, iv=iv, assignee_ids=newly_assigned
    )

    await session.commit()
    await session.refresh(iv)
    return await _interview_view(session, iv=iv, principal=principal, locale=locale)


# --------------------------------------------------------------------------- #
# Cancel / complete                                                            #
# --------------------------------------------------------------------------- #


async def cancel_interview(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """``status -> cancelled`` (frees the open slot). Notifies the candidate."""

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _RESOURCE, _PERM_CANCEL, resource_org_id=app.org_id
    )

    iv = await _load_interview(
        session, application_id=app.id, interview_id=interview_id, lock=True
    )
    if iv is None:
        raise ResourceNotFoundError()
    if version is not None and version != iv.version:
        raise ApplicationVersionConflictError()
    if iv.status != interview_domain.STATUS_SCHEDULED:
        raise InterviewNotActionableError(reason="interview_not_open")

    iv.status = interview_domain.STATUS_CANCELLED
    iv.version += 1
    await session.flush()

    await write_audit(
        session,
        action="application.interview_cancelled",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"interview_id": str(iv.id), "version": iv.version},
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.INTERVIEW_CANCELLED,
        actor_id=principal.user_id,
        metadata={"interview_id": str(iv.id)},
    )
    await _notify_candidate(
        session,
        app=app,
        iv=iv,
        template_key="application.interview_cancelled",
        notif_type="recruitment.interview_cancelled",
        dedupe_suffix=f"cancelled:{iv.version}",
    )

    await session.commit()
    await session.refresh(iv)
    return await _interview_view(session, iv=iv, principal=principal, locale=locale)


async def complete_interview(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    outcome: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """``status -> completed | no_show``. Partner-internal (no candidate notice)."""

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _RESOURCE, _PERM_COMPLETE, resource_org_id=app.org_id
    )

    if outcome not in interview_domain.COMPLETE_OUTCOMES:
        raise InvalidApplicationFieldError(field="outcome")

    iv = await _load_interview(
        session, application_id=app.id, interview_id=interview_id, lock=True
    )
    if iv is None:
        raise ResourceNotFoundError()
    if version is not None and version != iv.version:
        raise ApplicationVersionConflictError()
    if iv.status != interview_domain.STATUS_SCHEDULED:
        raise InterviewNotActionableError(reason="interview_not_open")

    iv.status = outcome
    iv.version += 1
    await session.flush()

    action = (
        "application.interview_completed"
        if outcome == interview_domain.STATUS_COMPLETED
        else "application.interview_no_show"
    )
    await write_audit(
        session,
        action=action,
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"interview_id": str(iv.id), "outcome": outcome, "version": iv.version},
    )
    if outcome == interview_domain.STATUS_COMPLETED:
        await timeline.record_timeline_event(
            session,
            application_id=app.id,
            event_type=timeline.INTERVIEW_COMPLETED,
            actor_id=principal.user_id,
            metadata={"interview_id": str(iv.id)},
        )

    await session.commit()
    await session.refresh(iv)
    return await _interview_view(session, iv=iv, principal=principal, locale=locale)


# --------------------------------------------------------------------------- #
# List (partner)                                                               #
# --------------------------------------------------------------------------- #


async def list_interviews(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Partner-internal list of the application's interviews (newest stage first)."""

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _RESOURCE, _PERM_READ, resource_org_id=app.org_id
    )

    rows = await _interviews_for_application(session, application_id=app.id)
    items = [
        await _interview_view(session, iv=iv, principal=principal, locale=locale)
        for iv in rows
    ]
    return {"application_id": str(app.id), "interviews": items}


async def student_interview_block(
    session: AsyncSession, *, application_id: uuid.UUID, locale: str = "vi"
) -> dict | None:
    """The candidate's OWN upcoming interview card (identity-safe) or ``None``.

    Surfaced ONLY on the applicant's own application detail. Carries no assignee
    identities, scorecards, or gate — just the student's own date/mode/location-link.
    """

    iv = (
        await session.execute(
            select(Interview)
            .where(
                Interview.application_id == application_id,
                Interview.status == interview_domain.STATUS_SCHEDULED,
            )
            .order_by(Interview.scheduled_at)
        )
    ).scalars().first()
    if iv is None:
        return None
    return presenters.student_interview_card(iv, locale=locale)


async def student_interview_blocks(
    session: AsyncSession,
    *,
    application_ids: list[uuid.UUID],
    locale: str = "vi",
) -> dict[uuid.UUID, dict]:
    """Batch the earliest ``scheduled`` interview card per application (no N+1).

    ONE query keyed by ``application_id`` (mirrors ``apply_service._latest_reveals_for``)
    so the applications LIST can attach the SAME identity-safe upcoming-interview
    card the detail path uses without a per-row query. Earliest ``scheduled_at``
    wins per application. Empty in -> empty out.
    """

    if not application_ids:
        return {}
    rows = (
        await session.execute(
            select(Interview)
            .where(
                Interview.application_id.in_(set(application_ids)),
                Interview.status == interview_domain.STATUS_SCHEDULED,
            )
            .order_by(Interview.scheduled_at)
        )
    ).scalars().all()
    blocks: dict[uuid.UUID, dict] = {}
    for iv in rows:
        # First row per application is the earliest (ordered by scheduled_at).
        blocks.setdefault(
            iv.application_id, presenters.student_interview_card(iv, locale=locale)
        )
    return blocks


# --------------------------------------------------------------------------- #
# Candidate respond (student confirms / declines / requests reschedule)        #
# --------------------------------------------------------------------------- #

# response state -> the truthful STUDENT-facing timeline event it appends.
_RESPONSE_TIMELINE_EVENTS: dict[str, str] = {
    interview_domain.CANDIDATE_RESPONSE_CONFIRMED: timeline.INTERVIEW_CONFIRMED,
    interview_domain.CANDIDATE_RESPONSE_DECLINED: (
        timeline.INTERVIEW_DECLINED_BY_CANDIDATE
    ),
    interview_domain.CANDIDATE_RESPONSE_RESCHEDULE: (
        timeline.INTERVIEW_RESCHEDULE_REQUESTED
    ),
}


async def respond_to_interview(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    interview_id: uuid.UUID,
    action: str,
    note: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """The candidate confirms / declines / requests-reschedule of THEIR interview.

    Owner-only (a non-owner is indistinguishable from missing -> ``404``, never
    ``403``, mirroring offer respond). Idempotent (the SAME response again is a
    no-op success); a CONFLICTING response is a ``409``; a non-``scheduled`` or past
    interview is a ``409``. Records the student-owned response on the row + an audit
    row + a truthful student-facing timeline event, and notifies the partner side
    (masked, PII-safe). Never mutates the partner-owned interview ``status``.
    """

    # Load the interview scoped to (application, interview); a mismatch is 404.
    iv = await _load_interview(
        session, application_id=application_id, interview_id=interview_id, lock=True
    )
    if iv is None:
        raise ResourceNotFoundError()
    app = await _shared.load_application(
        session, application_id=iv.application_id, lock=True
    )
    # Owner-only: only the applicant may respond to their own interview.
    if principal.user_id is None or app.applicant_id != principal.user_id:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _shared.RESOURCE, "update")

    if action not in interview_domain.CANDIDATE_ACTIONS:
        raise InvalidApplicationFieldError(field="action")
    target = interview_domain.CANDIDATE_ACTION_TO_RESPONSE[action]

    # Idempotent replay: the SAME response again is a no-op success (safe even after
    # the interview has passed — the outcome the caller wanted already holds). A
    # stale version on such a replay is NOT an error (mirrors withdraw).
    if iv.candidate_response == target:
        return presenters.student_interview_card(iv, locale=locale)

    if version is not None and version != iv.version:
        raise ApplicationVersionConflictError()

    # Respondable only while a future ``scheduled`` interview (cancelled/completed/
    # no_show/past -> a clear, actionable 409).
    if (
        iv.status != interview_domain.STATUS_SCHEDULED
        or _shared.as_aware(iv.scheduled_at) <= _shared.now()
    ):
        raise InterviewNotRespondableError()

    # First-response-wins: a DIFFERENT already-recorded response is a conflict.
    if iv.candidate_response is not None:
        raise InterviewResponseConflictError(current_response=iv.candidate_response)

    now = _shared.now()
    iv.candidate_response = target
    iv.candidate_responded_at = now
    iv.candidate_response_note = _clean_text(note)
    iv.version += 1
    await session.flush()

    await write_audit(
        session,
        action="application.interview_candidate_responded",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "interview_id": str(iv.id),
            "candidate_response": target,
            "version": iv.version,
        },
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=_RESPONSE_TIMELINE_EVENTS[target],
        actor_id=principal.user_id,
        # The student's OWN note is fine on their own timeline metadata (never
        # surfaced to the student projection, which drops metadata entirely).
        metadata={"interview_id": str(iv.id)},
    )
    await _notify_partner_candidate_response(session, app=app, iv=iv, response=target)

    await session.commit()
    await session.refresh(iv)
    return presenters.student_interview_card(iv, locale=locale)


# --------------------------------------------------------------------------- #
# Notifications                                                                #
# --------------------------------------------------------------------------- #


def _location_or_link(iv: Interview, *, locale: str) -> str:
    from app.modules.recruitment.infrastructure.meeting_link_crypto import (
        decrypt_meeting_link,
    )

    if iv.mode == interview_domain.MODE_ONLINE:
        return decrypt_meeting_link(iv.meeting_link) or ""
    if iv.mode == interview_domain.MODE_ONSITE:
        return iv.location or ""
    return (
        "Nhà tuyển dụng sẽ gọi cho bạn."
        if locale == "vi"
        else "The company will call you."
    )


def _scheduled_label(iv: Interview) -> str:
    return _shared.as_aware(iv.scheduled_at).strftime("%Y-%m-%d %H:%M UTC")


async def _job_title(session: AsyncSession, *, job_id: uuid.UUID) -> str:
    title = await job_read_facade.get_job_title(session, job_id)
    return title or ""


async def _notify_candidate(
    session: AsyncSession,
    *,
    app,
    iv: Interview,
    template_key: str,
    notif_type: str,
    dedupe_suffix: str,
) -> None:
    """Identity-safe candidate notice (outbox email + in-app feed) about THEIR own
    interview. Carries date/time/mode + their own location-or-link; NEVER assignee
    identities (PRD §7.6)."""

    student = await user_service.get_by_id(session, app.applicant_id)
    if student is None:
        return
    locale = message_catalog.normalize_locale(
        getattr(student, "preferred_language", None)
    )
    job_title = await _job_title(session, job_id=app.job_id)
    mode_label = interview_domain.MODE_LABELS[iv.mode].get(
        locale, interview_domain.MODE_LABELS[iv.mode]["vi"]
    )
    variables: dict[str, object] = {
        "email": student.email,
        "name": student.full_name or "",
        "job_title": job_title,
        "scheduled_at": _scheduled_label(iv),
        "mode_label": mode_label,
        "location_or_link": _location_or_link(iv, locale=locale),
    }
    await enqueue_notification(
        session,
        recipient_id=app.applicant_id,
        template_key=template_key,
        channel="email",
        locale=locale,
        variables=variables,
        dedupe_key=f"{notif_type}:{iv.id}:{dedupe_suffix}",
    )
    await feed_service.create_in_app(
        session,
        recipient_id=app.applicant_id,
        notif_type=notif_type,
        action_url=f"/student/applications/{app.id}?interview={iv.id}&n={dedupe_suffix}",
        variables={
            "job_title": job_title,
            "scheduled_at": _scheduled_label(iv),
            "mode_label": mode_label,
        },
        locale=locale,
    )


async def _notify_assignees_assigned(
    session: AsyncSession,
    *,
    app,
    iv: Interview,
    assignee_ids: list[uuid.UUID],
    dedupe_suffix: str = "assigned",
) -> None:
    """Partner-internal feed (+ email opt-in) to newly-assigned interviewers."""

    if not assignee_ids:
        return
    job_title = await _job_title(session, job_id=app.job_id)
    for uid in assignee_ids:
        member = await user_service.get_by_id(session, uid)
        if member is None:
            continue
        locale = message_catalog.normalize_locale(
            getattr(member, "preferred_language", None)
        )
        mode_label = interview_domain.MODE_LABELS[iv.mode].get(
            locale, interview_domain.MODE_LABELS[iv.mode]["vi"]
        )
        await enqueue_notification(
            session,
            recipient_id=uid,
            template_key="application.interview_assigned",
            channel="email",
            locale=locale,
            variables={
                "email": member.email,
                "name": member.full_name or "",
                "job_title": job_title,
                "scheduled_at": _scheduled_label(iv),
                "mode_label": mode_label,
            },
            dedupe_key=f"recruitment.interview_assigned:{iv.id}:{uid}:{dedupe_suffix}",
        )
        await feed_service.create_in_app(
            session,
            recipient_id=uid,
            notif_type="recruitment.interview_assigned",
            action_url=(
                f"/partner/applications/{app.id}?interview={iv.id}&n={dedupe_suffix}"
            ),
            variables={
                "job_title": job_title,
                "scheduled_at": _scheduled_label(iv),
                "mode_label": mode_label,
            },
            locale=locale,
        )


async def _notify_partner_candidate_response(
    session: AsyncSession, *, app, iv: Interview, response: str
) -> None:
    """Notify the partner side that the candidate responded (masked, PII-safe).

    Recipients: the interview's scheduler (``created_by``) + its assignees (deduped)
    — the people who need to know the candidate confirmed / declined / asked to
    reschedule. Outbox email + in-app feed, mirroring ``_notify_assignees_assigned``.
    Carries ONLY the localized response verb + job/time/mode — never the student's
    identity (they responded to their OWN interview, so nothing new is revealed to
    them; the partner learns only that "the candidate" responded). Deduped per
    ``(interview, response, version, recipient)`` so a post-reschedule re-response
    (version bumped) notifies again while a true retry does not.
    """

    recipients: set[uuid.UUID] = set()
    if iv.created_by is not None:
        recipients.add(iv.created_by)
    for uid in await _assignee_ids(session, interview_id=iv.id):
        recipients.add(uid)
    if not recipients:
        return
    job_title = await _job_title(session, job_id=app.job_id)
    for uid in recipients:
        member = await user_service.get_by_id(session, uid)
        if member is None:
            continue
        locale = message_catalog.normalize_locale(
            getattr(member, "preferred_language", None)
        )
        mode_label = interview_domain.MODE_LABELS[iv.mode].get(
            locale, interview_domain.MODE_LABELS[iv.mode]["vi"]
        )
        response_label = interview_domain.candidate_response_verb(
            response, locale=locale
        )
        await enqueue_notification(
            session,
            recipient_id=uid,
            template_key="application.interview_candidate_responded",
            channel="email",
            locale=locale,
            variables={
                "email": member.email,
                "name": member.full_name or "",
                "job_title": job_title,
                "response_label": response_label,
                "scheduled_at": _scheduled_label(iv),
                "mode_label": mode_label,
            },
            dedupe_key=(
                f"recruitment.interview_candidate_responded:{iv.id}:{response}"
                f":{iv.version}:{uid}"
            ),
        )
        await feed_service.create_in_app(
            session,
            recipient_id=uid,
            notif_type="recruitment.interview_candidate_responded",
            action_url=(
                f"/partner/applications/{app.id}?interview={iv.id}"
                f"&r={response}&v={iv.version}"
            ),
            variables={
                "job_title": job_title,
                "response_label": response_label,
                "scheduled_at": _scheduled_label(iv),
                "mode_label": mode_label,
            },
            locale=locale,
        )


# --------------------------------------------------------------------------- #
# Reminder sweep (ADR-0003 scheduler job; ADR-0006 §4)                          #
# --------------------------------------------------------------------------- #


async def _outbox_dedupe_exists(session: AsyncSession, *, dedupe_key: str) -> bool:
    return await dispatch_service.dedupe_exists(session, dedupe_key=dedupe_key)


async def sweep_due_reminders(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Enqueue T-24h / T-1h interview reminders for due ``scheduled`` interviews.

    Called by the ADR-0003 scheduler (``interview.reminder_sweep``). IDEMPOTENT:
    each reminder is gated on a per-``(interview, window[, user])`` outbox
    ``dedupe_key`` (``interview.reminder:{id}:{window}``) so re-running enqueues
    nothing new. Flush-only — the scheduler owns the commit (mirrors
    ``reveal_service.sweep_expired``).
    """

    now = _shared.as_aware(now) if now is not None else _shared.now()
    horizon = now + _REMINDER_WINDOWS[0][1]  # widest window (24h)
    rows = list(
        (
            await session.execute(
                select(Interview).where(
                    Interview.status == interview_domain.STATUS_SCHEDULED,
                    Interview.scheduled_at > now,
                    Interview.scheduled_at <= horizon,
                )
            )
        ).scalars().all()
    )

    enqueued = 0
    for iv in rows:
        sched = _shared.as_aware(iv.scheduled_at)
        for window, delta in _REMINDER_WINDOWS:
            # The window is "open" once now has reached scheduled_at - delta.
            if sched - delta > now:
                continue
            enqueued += await _enqueue_reminder_for_window(
                session, iv=iv, window=window
            )
    return {"reminders": enqueued}


async def _enqueue_reminder_for_window(
    session: AsyncSession, *, iv: Interview, window: str
) -> int:
    count = 0
    app = await _shared.load_application(session, application_id=iv.application_id)

    # Candidate reminder (email + feed), deduped per (interview, window).
    cand_key = f"interview.reminder:{iv.id}:{window}"
    if not await _outbox_dedupe_exists(session, dedupe_key=cand_key):
        student = await user_service.get_by_id(session, app.applicant_id)
        if student is not None:
            locale = message_catalog.normalize_locale(
                getattr(student, "preferred_language", None)
            )
            job_title = await _job_title(session, job_id=app.job_id)
            mode_label = interview_domain.MODE_LABELS[iv.mode].get(
                locale, interview_domain.MODE_LABELS[iv.mode]["vi"]
            )
            await enqueue_notification(
                session,
                recipient_id=app.applicant_id,
                template_key="application.interview_reminder",
                channel="email",
                locale=locale,
                variables={
                    "email": student.email,
                    "name": student.full_name or "",
                    "job_title": job_title,
                    "scheduled_at": _scheduled_label(iv),
                    "mode_label": mode_label,
                    "location_or_link": _location_or_link(iv, locale=locale),
                },
                dedupe_key=cand_key,
            )
            await feed_service.create_in_app(
                session,
                recipient_id=app.applicant_id,
                notif_type="recruitment.interview_reminder",
                action_url=(
                    f"/student/applications/{app.id}?interview={iv.id}&w={window}"
                ),
                variables={
                    "job_title": job_title,
                    "scheduled_at": _scheduled_label(iv),
                    "mode_label": mode_label,
                },
                locale=locale,
            )
            count += 1

    # Assignee reminders (in-app feed) only at T-24h.
    if window in _ASSIGNEE_WINDOWS:
        job_title = await _job_title(session, job_id=app.job_id)
        for uid in await _assignee_ids(session, interview_id=iv.id):
            a_key = f"interview.reminder.assignee:{iv.id}:{window}:{uid}"
            if await _outbox_dedupe_exists(session, dedupe_key=a_key):
                continue
            member = await user_service.get_by_id(session, uid)
            if member is None:
                continue
            locale = message_catalog.normalize_locale(
                getattr(member, "preferred_language", None)
            )
            mode_label = interview_domain.MODE_LABELS[iv.mode].get(
                locale, interview_domain.MODE_LABELS[iv.mode]["vi"]
            )
            # An outbox marker row carries the dedupe so re-runs are idempotent even
            # though the assignee channel is in-app (feed dedupe is action_url-based).
            await enqueue_notification(
                session,
                recipient_id=uid,
                template_key="application.interview_assigned",
                channel="email",
                locale=locale,
                variables={
                    "email": member.email,
                    "name": member.full_name or "",
                    "job_title": job_title,
                    "scheduled_at": _scheduled_label(iv),
                    "mode_label": mode_label,
                },
                dedupe_key=a_key,
            )
            await feed_service.create_in_app(
                session,
                recipient_id=uid,
                notif_type="recruitment.interview_reminder_assignee",
                action_url=(
                    f"/partner/applications/{app.id}?interview={iv.id}&w={window}"
                ),
                variables={
                    "job_title": job_title,
                    "scheduled_at": _scheduled_label(iv),
                    "mode_label": mode_label,
                },
                locale=locale,
            )
            count += 1

    await session.flush()
    return count
