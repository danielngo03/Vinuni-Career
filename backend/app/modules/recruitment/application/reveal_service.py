"""Anonymous-apply reveal handshake (``docs/BUSINESS_LOGIC.md`` §4.3).

A partner reviewing an anonymous application may send ONE reveal request (reason
>= 20 chars) per application. The applicant student accepts or declines within
72h; on accept the partner may see the identity and download the watermarked CV.
Both sides are audited and notified via the outbox.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.recruitment.api import presenters
from app.modules.recruitment.application import _shared
from app.modules.recruitment.application.errors import (
    InvalidApplicationFieldError,
    RevealNotAvailableError,
)
from app.modules.recruitment.domain import lifecycle, timeline
from app.modules.recruitment.domain.models import Application, ApplicationRevealRequest
from app.modules.users.application import user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE
_MIN_REASON = 20


async def _pending_request(
    session: AsyncSession, *, application_id: uuid.UUID
) -> ApplicationRevealRequest | None:
    return (
        (
            await session.execute(
                select(ApplicationRevealRequest)
                .where(
                    ApplicationRevealRequest.application_id == application_id,
                    ApplicationRevealRequest.status == lifecycle.REVEAL_PENDING,
                )
                .order_by(ApplicationRevealRequest.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


async def _existing_for_org(
    session: AsyncSession, *, application_id: uuid.UUID, org_id: uuid.UUID
) -> ApplicationRevealRequest | None:
    return (
        await session.execute(
            select(ApplicationRevealRequest).where(
                ApplicationRevealRequest.application_id == application_id,
                ApplicationRevealRequest.requester_org_id == org_id,
            )
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Partner: request                                                            #
# --------------------------------------------------------------------------- #


async def request_reveal(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    reason: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    app = await _shared.load_application(session, application_id=application_id, lock=True)
    # Partner-of-org scope (cross-org indistinguishable from missing).
    if not principal.is_superadmin and (principal.org_id is None or principal.org_id != app.org_id):
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=app.org_id)
    # Sensitive candidate-identity access: sending a reveal request is gated on the
    # dedicated ``candidate_identity:request_reveal`` capability (additive to the
    # base partner-of-org ``applications:read``), so a recruiter role can review
    # applications without holding the power to unmask anonymous candidates
    # (``docs/PARTNER_RBAC_ANALYTICS_SPEC.md`` candidate_identity row). The Admin
    # wildcard (``*:*``) still passes.
    permission_checker.require(
        principal, "candidate_identity", "request_reveal", resource_org_id=app.org_id
    )
    assert principal.user_id is not None

    if not app.is_anonymous:
        raise RevealNotAvailableError(reason="not_anonymous")
    if app.status == lifecycle.WITHDRAWN:
        raise RevealNotAvailableError(reason="application_withdrawn")
    if app.reveal_approved_at is not None:
        raise RevealNotAvailableError(reason="already_revealed")
    if not reason or len(reason.strip()) < _MIN_REASON:
        raise InvalidApplicationFieldError(field="reason")

    org_id = principal.org_id if principal.org_id is not None else app.org_id
    existing = await _existing_for_org(session, application_id=app.id, org_id=org_id)
    if existing is not None and existing.status == lifecycle.REVEAL_PENDING:
        return presenters.reveal_request(existing, locale=locale)  # idempotent in-flight
    if existing is not None and existing.status not in (
        lifecycle.REVEAL_EXPIRED,
        lifecycle.REVEAL_DECLINED,
    ):
        # ACCEPTED is already handled by the ``reveal_approved_at`` guard above; any
        # other non-reusable state is an in-flight duplicate.
        raise RevealNotAvailableError(reason="already_requested")

    if existing is not None:
        # The org's prior request lapsed (``expired`` via the sweep) or was
        # ``declined`` — allow a fresh request. The ``uq_reveal_app_org`` constraint
        # forbids a second row per (application, org), so the lapsed row is re-armed
        # in place: new reason, new requester, new 72h TTL, cleared response. This
        # restores the documented "partner may re-request after expiry" rule
        # (ADR-0003 §2) that a stale pending row previously blocked forever.
        req = existing
        req.reason = reason.strip()
        req.requester_id = principal.user_id
        req.status = lifecycle.REVEAL_PENDING
        req.expires_at = _shared.now() + timedelta(hours=lifecycle.REVEAL_TTL_HOURS)
        req.responded_at = None
    else:
        req = ApplicationRevealRequest(
            application_id=app.id,
            requester_id=principal.user_id,
            requester_org_id=org_id,
            reason=reason.strip(),
            status=lifecycle.REVEAL_PENDING,
            expires_at=_shared.now() + timedelta(hours=lifecycle.REVEAL_TTL_HOURS),
        )
        session.add(req)
    await session.flush()

    await write_audit(
        session,
        action="application.reveal_requested",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"reveal_request_id": str(req.id), "org_id": str(org_id)},
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.REVEAL_REQUESTED,
        actor_id=principal.user_id,
        metadata={"reveal_request_id": str(req.id)},
    )
    await _notify_student_requested(session, app=app, org_id=org_id, locale=locale)
    await _record_reveal_requested_access(session, app=app, principal=principal, org_id=org_id)

    await session.commit()
    await session.refresh(req)
    return presenters.reveal_request(req, locale=locale)


async def _record_reveal_requested_access(
    session: AsyncSession,
    *,
    app: Application,
    principal: Principal,
    org_id: uuid.UUID,
) -> None:
    """Best-effort hook into ``partner_candidate_access_events``
    (`docs/PARTNER_RBAC_ANALYTICS_SPEC.md`). Instrumentation only."""

    try:
        from app.modules.analytics.application import partner_candidate_access_service as access_log

        await access_log.record_access_event(
            session,
            org_id=org_id,
            actor_id=principal.user_id,
            application_id=app.id,
            job_id=app.job_id,
            candidate_id=app.applicant_id,
            event_type="identity_reveal_requested",
        )
    except Exception:  # noqa: BLE001 — audit instrumentation must never break the reveal flow
        pass


async def _notify_student_requested(
    session: AsyncSession, *, app: Application, org_id: uuid.UUID, locale: str
) -> None:
    student = await user_service.get_by_id(session, app.applicant_id)
    if student is None:
        return
    company_name = await _shared.org_display_name(session, org_id)
    await enqueue_notification(
        session,
        recipient_id=app.applicant_id,
        template_key="application.reveal_requested",
        channel="email",
        locale=locale,
        variables={
            "email": student.email,
            "name": student.full_name or "",
            "company_name": company_name,
        },
        dedupe_key=f"application.reveal_requested:{app.id}:{org_id}",
    )
    # In-app feed row for the student (same transaction as the outbox enqueue).
    await feed_service.create_in_app(
        session,
        recipient_id=app.applicant_id,
        notif_type="recruitment.reveal_requested",
        action_url=f"/student/applications/{app.id}",
        variables={"company_name": company_name},
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Student: respond                                                            #
# --------------------------------------------------------------------------- #


async def respond_reveal(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    decision: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    app = await _shared.load_application(session, application_id=application_id, lock=True)
    if principal.user_id is None or app.applicant_id != principal.user_id:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "update")

    if decision not in (lifecycle.REVEAL_ACCEPTED, lifecycle.REVEAL_DECLINED):
        raise InvalidApplicationFieldError(field="decision")

    req = await _pending_request(session, application_id=app.id)
    if req is None:
        raise RevealNotAvailableError(reason="no_pending_request")

    now = _shared.now()
    if _shared.as_aware(req.expires_at) <= now:
        req.status = lifecycle.REVEAL_EXPIRED
        req.responded_at = now
        await session.flush()
        await session.commit()
        raise RevealNotAvailableError(reason="expired")

    req.status = decision
    req.responded_at = now
    if decision == lifecycle.REVEAL_ACCEPTED:
        app.reveal_approved_by = principal.user_id
        app.reveal_approved_at = now
        app.version += 1
    await session.flush()

    await write_audit(
        session,
        action="application.reveal_responded",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"reveal_request_id": str(req.id), "decision": decision},
    )
    if decision == lifecycle.REVEAL_ACCEPTED:
        await timeline.record_timeline_event(
            session,
            application_id=app.id,
            event_type=timeline.REVEAL_APPROVED,
            actor_id=principal.user_id,
            metadata={"reveal_request_id": str(req.id)},
        )
    await _notify_partner_responded(session, req=req, app=app, decision=decision, locale=locale)

    await session.commit()
    await session.refresh(req)
    return presenters.reveal_request(req, locale=locale)


# --------------------------------------------------------------------------- #
# Scheduler: expiry sweep                                                      #
# --------------------------------------------------------------------------- #


async def sweep_expired(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Transition every overdue ``pending`` reveal request to ``expired``.

    Called by the periodic scheduler (ADR-0003 §2). Idempotent and status-gated:
    only ``pending`` rows past ``expires_at`` are touched, so re-running finds no
    work. Flush-only — the scheduler job owns the commit. After the sweep retires a
    stale row, :func:`request_reveal` can re-arm it (re-request after expiry).
    """

    now = now or _shared.now()
    rows = list(
        (
            await session.execute(
                select(ApplicationRevealRequest).where(
                    ApplicationRevealRequest.status == lifecycle.REVEAL_PENDING,
                    ApplicationRevealRequest.expires_at <= now,
                )
            )
        )
        .scalars()
        .all()
    )
    for req in rows:
        req.status = lifecycle.REVEAL_EXPIRED
        req.responded_at = now
    await session.flush()
    return {"expired": len(rows)}


async def _notify_partner_responded(
    session: AsyncSession,
    *,
    req: ApplicationRevealRequest,
    app: Application,
    decision: str,
    locale: str,
) -> None:
    partner = await user_service.get_by_id(session, req.requester_id)
    if partner is None:
        return
    decision_label = lifecycle.reveal_label(decision, locale=locale)
    await enqueue_notification(
        session,
        recipient_id=req.requester_id,
        template_key="application.reveal_responded",
        channel="email",
        locale=locale,
        variables={
            "email": partner.email,
            "name": partner.full_name or "",
            "decision_label": decision_label,
        },
        dedupe_key=f"application.reveal_responded:{req.id}",
    )
    # In-app feed row for the partner who requested the reveal.
    await feed_service.create_in_app(
        session,
        recipient_id=req.requester_id,
        notif_type="recruitment.reveal_responded",
        action_url=f"/partner/applications/{app.id}",
        variables={"decision_label": decision_label},
        locale=locale,
    )
