"""Offer lifecycle: create/approve/send + candidate accept/decline (ADR-0007).

The terminal POSITIVE outcome layer on top of the shipped ADR-0004 stage engine,
ADR-0005 scorecards, and ADR-0006 interviews. One LIVE offer per application
(LIVE = ``draft | pending_approval | approved | sent``); the offer carries comp + a
response deadline + an 8-state approval/response machine (``domain/offer.py``).

Hard rules enforced HERE (service layer, never the router):

- **Approval gate (§2):** ``send`` requires ``status='approved'`` (else
  ``OfferNotApprovedError`` / 409 ``offer_not_approved``). V1 does NOT enforce
  separation-of-duties; both ``created_by`` + ``approved_by`` are recorded.
- **One LIVE offer per application (§1):** a second LIVE offer is blocked
  (``OfferExistsError`` / 409 ``offer_exists``).
- **Editable only while ``draft`` (§1):** editing after submit raises
  ``OfferNotEditableError`` / 409 ``offer_not_editable``.
- **Reveal precondition on SEND (§5):** sending an anonymous application's offer
  without an accepted reveal raises ``RevealRequiredError`` / 409 ``reveal_required``
  — the handshake stays the ONLY identity path.
- **Candidate respond (§3):** owner-only, only to a ``sent`` non-expired offer
  (else 409 ``offer_not_actionable``); idempotent; lazy-expire on read. **Accept ->
  ``applications.status='hired'``** + closes the Offer-stage ``candidate_stages`` row
  PASSED (``exit_kind='hired'``) + emits the non-blocking ``offer.accepted`` outbox
  event (career-outcome seam, NO salary) + an ``application.hired`` audit. **Decline
  -> ``declined``**; the application stays ``under_review`` (no destructive cascade).
- Partner-of-org RBAC (cross-org -> ``404`` via
  ``decision_service._load_partner_application``); optimistic ``version``; an audit
  row per write; notifications via the outbox + feed (no synchronous SMTP).

SALARY / PII: ``salary_amount`` is Fernet-encrypted at rest and decrypted only for a
recruiter or the owning student. It is NEVER in a notification/email body, the board
glance, or the ``offer.accepted`` event payload (DATA_MODEL §17). An offer carries no
student-identity field; the candidate is notified about THEIR OWN offer (leaks
nothing).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import (
    dispatch_service,
    feed_service,
    message_catalog,
)
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.application import job_read_facade
from app.modules.recruitment.api import presenters
from app.modules.recruitment.application import _shared
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    IllegalApplicationTransitionError,
    InvalidApplicationFieldError,
    OfferExistsError,
    OfferNotActionableError,
    OfferNotApprovedError,
    OfferNotEditableError,
    RevealRequiredError,
)
from app.modules.recruitment.domain import lifecycle, pipeline, timeline
from app.modules.recruitment.domain import offer as offer_domain
from app.modules.recruitment.domain.models import Application, Offer
from app.modules.recruitment.infrastructure.offer_salary_crypto import encrypt_salary
from app.modules.users.application import user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import OutboxEvent
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "offers"
_PERM_CREATE = "create"
_PERM_APPROVE = "approve"
_PERM_SEND = "send"
_PERM_WITHDRAW = "rescind"

# T-24h expiring reminder window (mirrors the interview reminder posture).
_EXPIRING_WINDOW = timedelta(hours=24)


# --------------------------------------------------------------------------- #
# Repository helpers                                                           #
# --------------------------------------------------------------------------- #


async def _live_offer_for_application(
    session: AsyncSession, *, application_id: uuid.UUID, lock: bool = False
) -> Offer | None:
    """The single LIVE offer for an application, if any (service-layer guard)."""

    stmt = select(Offer).where(
        Offer.application_id == application_id,
        Offer.status.in_(tuple(offer_domain.LIVE_STATUSES)),
    )
    if lock and _shared.use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().first()


async def _load_offer(
    session: AsyncSession, *, offer_id: uuid.UUID, lock: bool = False
) -> Offer | None:
    stmt = select(Offer).where(Offer.id == offer_id)
    if lock and _shared.use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().first()


async def _offers_for_application(
    session: AsyncSession, *, application_id: uuid.UUID
) -> list[Offer]:
    return list(
        (
            await session.execute(
                select(Offer)
                .where(Offer.application_id == application_id)
                .order_by(Offer.created_at)
            )
        ).scalars().all()
    )


async def _load_partner_offer(
    session: AsyncSession,
    *,
    principal: Principal,
    offer_id: uuid.UUID,
    permission: str,
    lock: bool = False,
):
    """Load an offer + its application for a partner action (cross-org -> 404).

    Loads the offer (missing -> 404), then loads the owning application through
    ``decision_service._load_partner_application`` (which 404s a cross-org / non-
    partner caller). The specific offer ``permission`` is then required.
    """

    from app.modules.recruitment.application import decision_service

    offer = await _load_offer(session, offer_id=offer_id, lock=lock)
    if offer is None:
        raise ResourceNotFoundError()
    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=offer.application_id
    )
    permission_checker.require(
        principal, _RESOURCE, permission, resource_org_id=app.org_id
    )
    return offer, app


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


async def _partner_view(session: AsyncSession, *, offer: Offer, locale: str) -> dict:
    return presenters.partner_offer(offer, locale=locale)


# --------------------------------------------------------------------------- #
# Create / edit draft                                                         #
# --------------------------------------------------------------------------- #


async def create_offer(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    position_title: str,
    expiry_date: datetime,
    department: str | None = None,
    start_date=None,
    salary_amount: int | None = None,
    salary_currency: str = offer_domain.DEFAULT_CURRENCY,
    salary_period: str = offer_domain.DEFAULT_PERIOD,
    benefits_summary: str | None = None,
    terms_notes: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Create the ``draft`` offer at the application's current ACTIVE stage."""

    from app.modules.recruitment.application import decision_service, stage_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _RESOURCE, _PERM_CREATE, resource_org_id=app.org_id
    )

    # An offer is only meaningful while the application is active in the pipeline.
    if app.status != lifecycle.UNDER_REVIEW:
        raise IllegalApplicationTransitionError(event="create_offer")
    active = await stage_service._active_stage(
        session, application_id=app.id, lock=True
    )
    if active is None:
        raise IllegalApplicationTransitionError(event="create_offer")

    # One LIVE offer per application (service-layer guard; PG partial-unique backstop).
    if (
        await _live_offer_for_application(
            session, application_id=app.id, lock=True
        )
        is not None
    ):
        raise OfferExistsError()

    clean_title = (position_title or "").strip()
    if not clean_title:
        raise InvalidApplicationFieldError(field="position_title")

    offer = Offer(
        application_id=app.id,
        stage_id=active.stage_id,
        org_id=app.org_id,
        position_title=clean_title,
        department=_clean_text(department),
        start_date=start_date,
        salary_amount=(
            encrypt_salary(str(salary_amount)) if salary_amount is not None else None
        ),
        salary_currency=salary_currency or offer_domain.DEFAULT_CURRENCY,
        salary_period=salary_period or offer_domain.DEFAULT_PERIOD,
        benefits_summary=_clean_text(benefits_summary),
        terms_notes=_clean_text(terms_notes),
        expiry_date=_shared.as_aware(expiry_date),
        status=offer_domain.STATUS_DRAFT,
        created_by=principal.user_id,
        version=1,
    )
    session.add(offer)
    await session.flush()

    await write_audit(
        session, action="application.offer_created", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        after={"offer_id": str(offer.id), "stage_id": str(offer.stage_id),
               "status": offer.status},
    )
    await session.commit()
    await session.refresh(offer)
    return await _partner_view(session, offer=offer, locale=locale)


async def update_draft(
    session: AsyncSession,
    *,
    principal: Principal,
    offer_id: uuid.UUID,
    position_title: str | None = None,
    department: str | None = None,
    start_date=None,
    salary_amount: int | None = None,
    salary_currency: str | None = None,
    salary_period: str | None = None,
    benefits_summary: str | None = None,
    terms_notes: str | None = None,
    expiry_date: datetime | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Edit comp/terms/expiry in place — ONLY while ``draft`` (§1)."""

    offer, app = await _load_partner_offer(
        session, principal=principal, offer_id=offer_id,
        permission=_PERM_CREATE, lock=True,
    )
    if version is not None and version != offer.version:
        raise ApplicationVersionConflictError()
    if offer.status not in offer_domain.EDITABLE_STATUSES:
        raise OfferNotEditableError()

    if position_title is not None:
        clean_title = position_title.strip()
        if not clean_title:
            raise InvalidApplicationFieldError(field="position_title")
        offer.position_title = clean_title
    if department is not None:
        offer.department = _clean_text(department)
    if start_date is not None:
        offer.start_date = start_date
    if salary_amount is not None:
        offer.salary_amount = encrypt_salary(str(salary_amount))
    if salary_currency is not None:
        offer.salary_currency = salary_currency
    if salary_period is not None:
        offer.salary_period = salary_period
    if benefits_summary is not None:
        offer.benefits_summary = _clean_text(benefits_summary)
    if terms_notes is not None:
        offer.terms_notes = _clean_text(terms_notes)
    if expiry_date is not None:
        offer.expiry_date = _shared.as_aware(expiry_date)
    offer.version += 1
    await session.flush()

    await write_audit(
        session, action="application.offer_updated", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        after={"offer_id": str(offer.id), "version": offer.version},
    )
    await session.commit()
    await session.refresh(offer)
    return await _partner_view(session, offer=offer, locale=locale)


# --------------------------------------------------------------------------- #
# Approval flow: submit / approve / reject-back                               #
# --------------------------------------------------------------------------- #


async def submit_offer(
    session: AsyncSession,
    *,
    principal: Principal,
    offer_id: uuid.UUID,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """``draft -> pending_approval`` (freezes content for approval)."""

    offer, app = await _load_partner_offer(
        session, principal=principal, offer_id=offer_id,
        permission=_PERM_CREATE, lock=True,
    )
    if version is not None and version != offer.version:
        raise ApplicationVersionConflictError()
    if not offer_domain.can_transition(offer_domain.EVENT_SUBMIT, offer.status):
        raise IllegalApplicationTransitionError(event="submit_offer")

    offer.status = offer_domain.transition_target(offer_domain.EVENT_SUBMIT)
    offer.version += 1
    await session.flush()

    await write_audit(
        session, action="application.offer_submitted", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        after={"offer_id": str(offer.id), "status": offer.status},
    )
    await session.commit()
    await session.refresh(offer)
    return await _partner_view(session, offer=offer, locale=locale)


async def approve_offer(
    session: AsyncSession,
    *,
    principal: Principal,
    offer_id: uuid.UUID,
    decision: str,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """``pending_approval -> approved`` (approve) or ``-> draft`` (reject-back)."""

    if decision not in offer_domain.APPROVE_DECISIONS:
        raise InvalidApplicationFieldError(field="decision")

    offer, app = await _load_partner_offer(
        session, principal=principal, offer_id=offer_id,
        permission=_PERM_APPROVE, lock=True,
    )
    if version is not None and version != offer.version:
        raise ApplicationVersionConflictError()

    if decision == offer_domain.APPROVE_DECISION:
        if not offer_domain.can_transition(offer_domain.EVENT_APPROVE, offer.status):
            raise IllegalApplicationTransitionError(event="approve_offer")
        offer.status = offer_domain.transition_target(offer_domain.EVENT_APPROVE)
        offer.approved_by = principal.user_id
        offer.approved_at = _shared.now()
        action = "application.offer_approved"
    else:  # reject-back to draft
        if not offer_domain.can_transition(offer_domain.EVENT_REJECT, offer.status):
            raise IllegalApplicationTransitionError(event="approve_offer")
        offer.status = offer_domain.transition_target(offer_domain.EVENT_REJECT)
        action = "application.offer_rejected_back"
    offer.version += 1
    await session.flush()

    await write_audit(
        session, action=action, resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        after={"offer_id": str(offer.id), "status": offer.status,
               "decision": decision},
    )
    await session.commit()
    await session.refresh(offer)
    return await _partner_view(session, offer=offer, locale=locale)


# --------------------------------------------------------------------------- #
# Send (reveal precondition) / rescind                                        #
# --------------------------------------------------------------------------- #


async def send_offer(
    session: AsyncSession,
    *,
    principal: Principal,
    offer_id: uuid.UUID,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """``approved -> sent`` (the approval gate + reveal precondition; §2/§5)."""

    offer, app = await _load_partner_offer(
        session, principal=principal, offer_id=offer_id,
        permission=_PERM_SEND, lock=True,
    )
    if version is not None and version != offer.version:
        raise ApplicationVersionConflictError()

    # The structural approval gate: send requires status='approved'.
    if offer.status != offer_domain.STATUS_APPROVED:
        raise OfferNotApprovedError()
    # Reveal precondition (§5): an anonymous app with no accepted reveal can NOT have
    # an offer sent — the handshake is the only identity path.
    if app.is_anonymous and app.reveal_approved_at is None:
        raise RevealRequiredError()

    offer.status = offer_domain.transition_target(offer_domain.EVENT_SEND)
    offer.sent_at = _shared.now()
    offer.version += 1
    await session.flush()

    await write_audit(
        session, action="application.offer_sent", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        after={"offer_id": str(offer.id), "status": offer.status},
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.OFFER_SENT,
        actor_id=principal.user_id,
        metadata={"offer_id": str(offer.id)},
    )
    await _notify_candidate(
        session, app=app, offer=offer,
        template_key="application.offer_received",
        notif_type="recruitment.offer_received",
        dedupe_suffix="sent",
    )
    await session.commit()
    await session.refresh(offer)
    return await _partner_view(session, offer=offer, locale=locale)


async def rescind_offer(
    session: AsyncSession,
    *,
    principal: Principal,
    offer_id: uuid.UUID,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """``{draft,pending_approval,approved,sent} -> rescinded`` (partner withdraw)."""

    offer, app = await _load_partner_offer(
        session, principal=principal, offer_id=offer_id,
        permission=_PERM_WITHDRAW, lock=True,
    )
    if version is not None and version != offer.version:
        raise ApplicationVersionConflictError()
    if not offer_domain.can_transition(offer_domain.EVENT_RESCIND, offer.status):
        raise OfferNotActionableError(reason="offer_not_actionable")

    was_sent = offer.status == offer_domain.STATUS_SENT
    offer.status = offer_domain.transition_target(offer_domain.EVENT_RESCIND)
    offer.version += 1
    await session.flush()

    await write_audit(
        session, action="application.offer_rescinded", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        after={"offer_id": str(offer.id), "status": offer.status,
               "was_sent": was_sent},
    )
    # Timeline (like the notification) only matters once the offer reached the
    # candidate — a rescinded DRAFT/pending/approved offer was never student-visible.
    if was_sent:
        await timeline.record_timeline_event(
            session,
            application_id=app.id,
            event_type=timeline.OFFER_RESCINDED,
            actor_id=principal.user_id,
            metadata={"offer_id": str(offer.id)},
        )
    # Notify the candidate ONLY if the offer had already reached them (was sent).
    if was_sent:
        await _notify_candidate(
            session, app=app, offer=offer,
            template_key="application.offer_rescinded",
            notif_type="recruitment.offer_rescinded",
            dedupe_suffix="rescinded",
        )
    await session.commit()
    await session.refresh(offer)
    return await _partner_view(session, offer=offer, locale=locale)


# --------------------------------------------------------------------------- #
# Candidate respond: accept / decline                                         #
# --------------------------------------------------------------------------- #


async def respond_offer(
    session: AsyncSession,
    *,
    principal: Principal,
    offer_id: uuid.UUID,
    decision: str,
    notes: str | None = None,
    idempotency_key: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """The candidate accepts/declines a SENT offer (§3). Owner-only, idempotent."""

    offer = await _load_offer(session, offer_id=offer_id, lock=True)
    if offer is None:
        raise ResourceNotFoundError()
    app = await _shared.load_application(
        session, application_id=offer.application_id, lock=True
    )
    # Owner-only: a non-owner is indistinguishable from missing (404, never 403).
    if principal.user_id is None or app.applicant_id != principal.user_id:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _shared.RESOURCE, "update")

    if decision not in offer_domain.RESPOND_DECISIONS:
        raise InvalidApplicationFieldError(field="decision")

    now = _shared.now()

    # Lazy-expire: a stale sent offer past its deadline is flipped to expired and is
    # never acted on (§3). Re-raise as not-actionable.
    if (
        offer.status == offer_domain.STATUS_SENT
        and _shared.as_aware(offer.expiry_date) <= now
    ):
        offer.status = offer_domain.STATUS_EXPIRED
        await session.flush()
        await session.commit()
        raise OfferNotActionableError(reason="offer_not_actionable")

    # Idempotent replay: re-responding with the SAME decision on an already-answered
    # offer is a no-op (no duplicate hired / placement / notification).
    if (
        decision == offer_domain.RESPOND_ACCEPTED
        and offer.status == offer_domain.STATUS_ACCEPTED
    ) or (
        decision == offer_domain.RESPOND_DECLINED
        and offer.status == offer_domain.STATUS_DECLINED
    ):
        return presenters.student_offer(offer, locale=locale)

    if offer.status != offer_domain.STATUS_SENT:
        raise OfferNotActionableError(reason="offer_not_actionable")

    if decision == offer_domain.RESPOND_ACCEPTED:
        return await _accept(session, offer=offer, app=app, principal=principal,
                             now=now, ctx=ctx, locale=locale)
    return await _decline(session, offer=offer, app=app, principal=principal,
                         notes=notes, now=now, ctx=ctx, locale=locale)


async def _accept(
    session: AsyncSession, *, offer: Offer, app, principal: Principal,
    now: datetime, ctx: RequestContext, locale: str,
) -> dict:
    """Accept: offer -> accepted; application -> hired; close stage row; career seam."""

    from app.modules.recruitment.application import stage_service

    offer.status = offer_domain.STATUS_ACCEPTED
    offer.student_response_at = now
    offer.version += 1

    # Terminal positive outcome on the coarse status (§4). hired is terminal/inactive.
    app.status = lifecycle.HIRED
    app.last_status_at = now
    app.version += 1

    # Close the open Offer-stage candidate_stages row PASSED with exit_kind='hired'
    # (no new stage row — Offer is the last stage). No-op when no active row exists.
    active = await stage_service._active_stage(
        session, application_id=app.id, lock=True
    )
    if active is not None:
        active.status = pipeline.STAGE_PASSED
        active.exit_kind = pipeline.EXIT_HIRED
        active.exited_at = now
    await session.flush()

    # Career-outcome seam (trust_level=4): a NON-blocking outbox domain event the
    # career-outcomes materializer consumes idempotently. NO salary in the payload.
    session.add(
        OutboxEvent(
            aggregate_type="application",
            aggregate_id=app.id,
            event_type="offer.accepted",
            payload={
                "application_id": str(app.id),
                "offer_id": str(offer.id),
                "org_id": str(app.org_id),
                "employer_org_id": str(app.org_id),
                "position_title": offer.position_title,
                "start_date": offer.start_date.isoformat() if offer.start_date else None,
            },
            actor_id=principal.user_id,
        )
    )
    await session.flush()

    await write_audit(
        session, action="application.hired", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        after={"offer_id": str(offer.id), "status": app.status},
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.OFFER_ACCEPTED,
        actor_id=principal.user_id,
        metadata={"offer_id": str(offer.id)},
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.HIRED,
        actor_id=principal.user_id,
        metadata={"offer_id": str(offer.id)},
    )
    # Partner-internal feed: candidate hired (position + start date; NO salary).
    await _notify_partner(
        session, offer=offer, app=app,
        notif_type="recruitment.offer_accepted",
        recipient_id=offer.created_by,
    )
    await session.commit()
    await session.refresh(offer)
    return presenters.student_offer(offer, locale=locale)


async def _decline(
    session: AsyncSession, *, offer: Offer, app, principal: Principal,
    notes: str | None, now: datetime, ctx: RequestContext, locale: str,
) -> dict:
    """Decline: offer -> declined; the application stays under_review (no cascade)."""

    offer.status = offer_domain.STATUS_DECLINED
    offer.student_response_at = now
    offer.decline_reason = _clean_text(notes)
    offer.version += 1
    await session.flush()

    await write_audit(
        session, action="application.offer_declined", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        # decline_reason is partner-internal — recorded in audit metadata only.
        after={"offer_id": str(offer.id), "status": offer.status},
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.OFFER_DECLINED,
        actor_id=principal.user_id,
        metadata={"offer_id": str(offer.id)},
    )
    await _notify_partner(
        session, offer=offer, app=app,
        notif_type="recruitment.offer_declined",
        recipient_id=offer.created_by,
    )
    await session.commit()
    await session.refresh(offer)
    return presenters.student_offer(offer, locale=locale)


# --------------------------------------------------------------------------- #
# Reads (partner list / student list+detail / projection blocks)              #
# --------------------------------------------------------------------------- #


async def list_offers_partner(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Partner-internal list of an application's offers (oldest first; full comp)."""

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _RESOURCE, _PERM_CREATE, resource_org_id=app.org_id
    )
    rows = await _offers_for_application(session, application_id=app.id)
    return {
        "application_id": str(app.id),
        "offers": [presenters.partner_offer(o, locale=locale) for o in rows],
    }


async def list_offers_student(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> list[dict]:
    """The student's OWN offers — only ``sent``+terminal states are ever visible."""

    if principal.user_id is None:
        raise ResourceNotFoundError()
    rows = list(
        (
            await session.execute(
                select(Offer)
                .join(Application, Offer.application_id == Application.id)
                .where(
                    Application.applicant_id == principal.user_id,
                    Offer.status.in_(tuple(offer_domain.STUDENT_VISIBLE_STATUSES)),
                )
                .order_by(Offer.created_at.desc())
            )
        ).scalars().all()
    )
    return [presenters.student_offer(o, locale=locale) for o in rows]


async def get_offer_student(
    session: AsyncSession,
    *,
    principal: Principal,
    offer_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """The owning student's OWN offer detail (full comp). Non-owner -> 404."""

    offer = await _load_offer(session, offer_id=offer_id)
    if offer is None:
        raise ResourceNotFoundError()
    app = await _shared.load_application(session, application_id=offer.application_id)
    if principal.user_id is None or app.applicant_id != principal.user_id:
        raise ResourceNotFoundError()
    # A draft/pending/approved offer is partner-internal — invisible to the student.
    if offer.status not in offer_domain.STUDENT_VISIBLE_STATUSES:
        raise ResourceNotFoundError()
    return presenters.student_offer(offer, locale=locale)


async def student_offer_block(
    session: AsyncSession, *, application_id: uuid.UUID, locale: str = "vi"
) -> dict | None:
    """The candidate's OWN offer summary card for their application detail.

    Surfaced ONLY for a ``sent``+terminal offer (never a draft/pending/approved one,
    never partner internals). ``None`` when there is no student-visible offer.
    """

    offer = (
        await session.execute(
            select(Offer)
            .where(
                Offer.application_id == application_id,
                Offer.status.in_(tuple(offer_domain.STUDENT_VISIBLE_STATUSES)),
            )
            .order_by(Offer.created_at.desc())
        )
    ).scalars().first()
    if offer is None:
        return None
    return presenters.student_offer_card(offer, locale=locale)


async def student_offer_blocks(
    session: AsyncSession,
    *,
    application_ids: list[uuid.UUID],
    locale: str = "vi",
) -> dict[uuid.UUID, dict]:
    """Batch the latest student-visible offer card per application (no N+1).

    ONE query keyed by ``application_id`` (mirrors ``student_offer_block`` but for a
    page of applications) so the applications LIST attaches the SAME identity-safe
    offer card the detail path uses without a per-row query. Latest ``created_at``
    wins per application; only ``sent``+terminal offers are ever included. Empty in
    -> empty out.
    """

    if not application_ids:
        return {}
    rows = (
        await session.execute(
            select(Offer)
            .where(
                Offer.application_id.in_(set(application_ids)),
                Offer.status.in_(tuple(offer_domain.STUDENT_VISIBLE_STATUSES)),
            )
            .order_by(Offer.created_at.desc())
        )
    ).scalars().all()
    blocks: dict[uuid.UUID, dict] = {}
    for offer in rows:
        # First row per application is the latest (ordered by created_at desc).
        blocks.setdefault(
            offer.application_id, presenters.student_offer_card(offer, locale=locale)
        )
    return blocks


async def count_actionable_offers_for_student(
    session: AsyncSession, *, user_id: uuid.UUID
) -> int:
    """Number of LIVE offers awaiting the student's response.

    An offer is actionable only while ``sent`` and not past its ``expiry_date``
    (the lazy-expire sweep flips overdue ones to ``expired``; this count is honest
    even before the sweep runs). Drives the dashboard "respond to offer" todo.
    """

    now = _shared.now()
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(Offer)
                .join(Application, Offer.application_id == Application.id)
                .where(
                    Application.applicant_id == user_id,
                    Application.deleted_at.is_(None),
                    Offer.status == offer_domain.STATUS_SENT,
                    or_(
                        Offer.expiry_date.is_(None),
                        Offer.expiry_date > now,
                    ),
                )
            )
        ).scalar_one()
    )


async def partner_offer_block(
    session: AsyncSession, *, application_id: uuid.UUID, locale: str = "vi"
) -> dict | None:
    """The partner-only board/detail offer glance (NO salary). ``None`` when none.

    Prefers the LIVE offer; falls back to the most recent terminal one so a board
    card still reflects an accepted/declined outcome.
    """

    offer = await _live_offer_for_application(session, application_id=application_id)
    if offer is None:
        offer = (
            await session.execute(
                select(Offer)
                .where(Offer.application_id == application_id)
                .order_by(Offer.created_at.desc())
            )
        ).scalars().first()
    if offer is None:
        return None
    return presenters.offer_board_block(offer, locale=locale)


# --------------------------------------------------------------------------- #
# Notifications                                                                #
# --------------------------------------------------------------------------- #


async def _job_title(session: AsyncSession, *, job_id: uuid.UUID) -> str:
    title = await job_read_facade.get_job_title(session, job_id)
    return title or ""


def _expiry_label(offer: Offer) -> str:
    return _shared.as_aware(offer.expiry_date).strftime("%Y-%m-%d %H:%M UTC")


async def _company_name(session: AsyncSession, *, org_id: uuid.UUID) -> str:
    return await _shared.org_display_name(session, org_id)


async def _notify_candidate(
    session: AsyncSession,
    *,
    app,
    offer: Offer,
    template_key: str,
    notif_type: str,
    dedupe_suffix: str,
) -> None:
    """Identity-safe candidate notice (outbox email + in-app feed). NO salary.

    The candidate opens the platform to view comp — no salary figure ever reaches a
    notification/email body (DATA_MODEL §17).
    """

    student = await user_service.get_by_id(session, app.applicant_id)
    if student is None:
        return
    locale = message_catalog.normalize_locale(
        getattr(student, "preferred_language", None)
    )
    job_title = await _job_title(session, job_id=app.job_id)
    company = await _company_name(session, org_id=app.org_id)
    variables: dict[str, object] = {
        "email": student.email,
        "name": student.full_name or "",
        "job_title": job_title,
        "position_title": offer.position_title,
        "company_name": company,
        "expiry_date": _expiry_label(offer),
    }
    await enqueue_notification(
        session,
        recipient_id=app.applicant_id,
        template_key=template_key,
        channel="email",
        locale=locale,
        variables=variables,
        dedupe_key=f"{notif_type}:{offer.id}:{dedupe_suffix}",
    )
    await feed_service.create_in_app(
        session,
        recipient_id=app.applicant_id,
        notif_type=notif_type,
        action_url=f"/student/applications/{app.id}?offer={offer.id}&n={dedupe_suffix}",
        variables={
            "job_title": job_title,
            "position_title": offer.position_title,
            "company_name": company,
            "expiry_date": _expiry_label(offer),
        },
        locale=locale,
    )


async def _notify_partner(
    session: AsyncSession,
    *,
    offer: Offer,
    app,
    notif_type: str,
    recipient_id: uuid.UUID,
) -> None:
    """Partner-internal in-app feed (candidate hired / declined). NO salary."""

    member = await user_service.get_by_id(session, recipient_id)
    if member is None:
        return
    locale = message_catalog.normalize_locale(
        getattr(member, "preferred_language", None)
    )
    job_title = await _job_title(session, job_id=app.job_id)
    await feed_service.create_in_app(
        session,
        recipient_id=recipient_id,
        notif_type=notif_type,
        action_url=f"/partner/applications/{app.id}?offer={offer.id}",
        variables={
            "job_title": job_title,
            "position_title": offer.position_title,
            # Partner-internal; the candidate's reason is shown to the partner only.
            "decline_reason": offer.decline_reason or "",
        },
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Expiry sweep (ADR-0003 scheduler job; ADR-0007 §6)                           #
# --------------------------------------------------------------------------- #


async def _outbox_dedupe_exists(session: AsyncSession, *, dedupe_key: str) -> bool:
    return await dispatch_service.dedupe_exists(session, dedupe_key=dedupe_key)


async def sweep_offers(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Lazy-expire sweep + the T-24h expiring reminder (ADR-0007 §6).

    Finds ``sent`` offers: flips those past ``expiry_date`` to ``expired`` (notifying
    candidate + partner) and enqueues the T-24h ``offer_expiring`` reminder for those
    entering the window. IDEMPOTENT — once flipped the row is no longer ``sent`` so a
    re-run finds no work; the expiring reminder is deduped on the per-offer outbox
    ``dedupe_key``. Flush-only — the scheduler owns the commit (mirrors
    ``interview_service.sweep_due_reminders`` / ``reveal_service.sweep_expired``).
    """

    now = _shared.as_aware(now) if now is not None else _shared.now()
    horizon = now + _EXPIRING_WINDOW
    rows = list(
        (
            await session.execute(
                select(Offer).where(Offer.status == offer_domain.STATUS_SENT)
            )
        ).scalars().all()
    )

    expired = 0
    expiring = 0
    for offer in rows:
        exp = _shared.as_aware(offer.expiry_date)
        if exp <= now:
            offer.status = offer_domain.STATUS_EXPIRED
            await session.flush()
            await _enqueue_expired(session, offer=offer)
            expired += 1
        elif exp <= horizon:
            if await _enqueue_expiring(session, offer=offer):
                expiring += 1
    await session.flush()
    return {"expired": expired, "expiring": expiring}


async def _enqueue_expired(session: AsyncSession, *, offer: Offer) -> None:
    app = await _shared.load_application(session, application_id=offer.application_id)
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.OFFER_EXPIRED,
        metadata={"offer_id": str(offer.id)},
    )
    await _notify_candidate(
        session, app=app, offer=offer,
        template_key="application.offer_expired",
        notif_type="recruitment.offer_expired",
        dedupe_suffix="expired",
    )
    # Partner feed: the offer lapsed without a response.
    await _notify_partner(
        session, offer=offer, app=app,
        notif_type="recruitment.offer_expired",
        recipient_id=offer.created_by,
    )


async def _enqueue_expiring(session: AsyncSession, *, offer: Offer) -> bool:
    dedupe_key = f"recruitment.offer_expiring:{offer.id}:expiring"
    if await _outbox_dedupe_exists(session, dedupe_key=dedupe_key):
        return False
    app = await _shared.load_application(session, application_id=offer.application_id)
    await _notify_candidate(
        session, app=app, offer=offer,
        template_key="application.offer_expiring",
        notif_type="recruitment.offer_expiring",
        dedupe_suffix="expiring",
    )
    return True
