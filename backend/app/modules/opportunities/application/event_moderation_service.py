"""University event moderation: queue, approve (-> publish), reject (ADR-0008 §5).

Moderation is restricted to a platform **superadmin** or a member of a
**university** org holding ``events:moderate`` — the same org-type gate as the jobs
``moderation_service``. A partner Admin's ``*:*`` cannot self-approve because the
gate is university-only.

Approve transitions ``pending_review -> published`` (sets ``moderation_status=
approved``, ``published_at``, ``approved_by/at``); reject transitions
``pending_review -> rejected``. Both audit the transition and enqueue an outbox +
in-app notification to the organizer (no synchronous SMTP). University-created
events never appear here — they auto-publish on submit (event_service).
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
from app.modules.opportunities.api import event_presenters as presenters
from app.modules.opportunities.application.event_errors import (
    EventAlreadyClaimedError,
    EventVersionConflictError,
    IllegalEventTransitionError,
    InvalidModerationReasonError,
)
from app.modules.opportunities.domain import event_lifecycle
from app.modules.opportunities.domain.event_models import Event
from app.modules.organization.application import org_reporting_facade
from app.modules.users.application import user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AppError,
    ConflictError,
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

_RESOURCE = "events"


def _now() -> datetime:
    return datetime.now(tz=UTC)


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


async def _load_event(session: AsyncSession, event_id: uuid.UUID) -> Event | None:
    stmt = select(Event).where(Event.id == event_id, Event.deleted_at.is_(None))
    if _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _notify_organizer(
    session: AsyncSession, *, event: Event, template_key: str, locale: str,
    extra: dict | None = None,
) -> None:
    organizer = await user_service.get_by_id(session, event.created_by)
    variables: dict[str, object] = {
        "email": organizer.email if organizer else "",
        "name": organizer.full_name if organizer and organizer.full_name else "",
        "event_title": event.title,
    }
    if extra:
        variables.update(extra)
    await enqueue_notification(
        session,
        recipient_id=event.created_by,
        template_key=template_key,
        channel="email",
        locale=locale,
        variables=variables,
        dedupe_key=f"{template_key}:{event.id}:{event.version}",
    )
    notif_type = {
        "event.approved": "opportunities.event_approved",
        "event.rejected": "opportunities.event_rejected",
    }.get(template_key)
    if notif_type is not None:
        await feed_service.create_in_app(
            session,
            recipient_id=event.created_by,
            notif_type=notif_type,
            action_url=f"/partner/events/{event.id}",
            variables={
                "event_title": event.title,
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
    """List events in the moderation queue (default: ``pending_review``)."""

    await _require_university_moderator(session, principal)
    page_limit = clamp_limit(limit)
    target_status = status or event_lifecycle.PENDING_REVIEW
    stmt = (
        select(Event)
        .where(Event.deleted_at.is_(None), Event.status == target_status)
        .order_by(Event.submitted_at.asc().nulls_last(), Event.created_at.asc())
        .limit(page_limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).select_from(Event).where(
                Event.deleted_at.is_(None), Event.status == target_status
            )
        )
    ).scalar_one()
    items = [presenters.owner_event_summary(e, locale=locale) for e in rows]
    return items, total


# --------------------------------------------------------------------------- #
# Approve / reject                                                            #
# --------------------------------------------------------------------------- #


async def approve_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    version: int | None = None,
    note: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university_moderator(session, principal)
    event = await _load_event(session, event_id)
    if event is None:
        raise ResourceNotFoundError()
    if version is not None and version != event.version:
        raise EventVersionConflictError()
    if (
        event.status == event_lifecycle.PUBLISHED
        and event.moderation_status == event_lifecycle.MOD_APPROVED
    ):
        return presenters.owner_event_summary(event, locale=locale)  # idempotent
    if not event_lifecycle.can_transition("approve", event.status):
        raise IllegalEventTransitionError(event="approve")

    now = _now()
    event.status = event_lifecycle.PUBLISHED
    event.moderation_status = event_lifecycle.MOD_APPROVED
    event.moderation_note = note
    event.approved_by = principal.user_id
    event.approved_at = now
    event.published_at = now
    event.version += 1
    await session.flush()

    await write_audit(
        session, action="event.approved", resource_type="event", resource_id=event.id,
        context=_audit_ctx(principal, ctx),
        after={"status": event.status, "moderation_status": event.moderation_status,
               "org_id": str(event.org_id)},
    )
    await _notify_organizer(
        session, event=event, template_key="event.approved", locale=locale,
    )
    await session.commit()
    return presenters.owner_event_summary(event, locale=locale)


def _validate_reason_code(reason_code: str | None, *, reason: str | None) -> str:
    code = reason_code or REASON_OTHER
    if not is_valid_reason_code(code):
        raise InvalidModerationReasonError()
    if code in REASON_REQUIRES_NOTE and not (reason and reason.strip()):
        raise InvalidModerationReasonError()
    return code


async def reject_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
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
    event = await _load_event(session, event_id)
    if event is None:
        raise ResourceNotFoundError()
    if version is not None and version != event.version:
        raise EventVersionConflictError()
    if event.status == event_lifecycle.REJECTED:
        return presenters.owner_event_summary(event, locale=locale)  # idempotent
    if not event_lifecycle.can_transition("reject", event.status):
        raise IllegalEventTransitionError(event="reject")

    event.status = event_lifecycle.REJECTED
    event.moderation_status = event_lifecycle.MOD_REJECTED
    event.moderation_note = reason.strip()
    event.moderation_reason_code = code
    # Rejecting resolves any open flag; the flag timestamp no longer applies.
    event.moderation_flagged_at = None
    event.approved_by = None
    event.approved_at = None
    event.published_at = None
    event.claimed_by = None
    event.claimed_at = None
    event.version += 1
    await session.flush()

    await write_audit(
        session, action="event.rejected", resource_type="event", resource_id=event.id,
        context=_audit_ctx(principal, ctx),
        after={"status": event.status, "moderation_status": event.moderation_status,
               "reason_code": code, "org_id": str(event.org_id)},
    )
    await _notify_organizer(
        session, event=event, template_key="event.rejected", locale=locale,
        extra={"reason": reason.strip()},
    )
    await session.commit()
    return presenters.owner_event_summary(event, locale=locale)


# --------------------------------------------------------------------------- #
# Claim / assign                                                              #
# --------------------------------------------------------------------------- #


async def claim_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Claim a pending event for review (concurrency-safe conditional update)."""

    await _require_university_moderator(session, principal)
    event = await _load_event(session, event_id)
    if event is None:
        raise ResourceNotFoundError()
    if event.status != event_lifecycle.PENDING_REVIEW:
        raise IllegalEventTransitionError(event="claim")
    if event.claimed_by == principal.user_id:
        return presenters.owner_event_summary(event, locale=locale)  # idempotent
    if event.claimed_by is not None:
        raise EventAlreadyClaimedError()

    now = _now()
    result = await session.execute(
        update(Event)
        .where(
            Event.id == event_id,
            Event.claimed_by.is_(None),
            Event.version == event.version,
        )
        .values(
            claimed_by=principal.user_id, claimed_at=now, version=Event.version + 1
        )
    )
    if result.rowcount == 0:
        raise EventAlreadyClaimedError()
    await session.flush()
    await write_audit(
        session, action="event.claimed", resource_type="event", resource_id=event.id,
        context=_audit_ctx(principal, ctx),
        after={"claimed_by": str(principal.user_id), "org_id": str(event.org_id)},
    )
    await session.commit()
    await session.refresh(event)
    return presenters.owner_event_summary(event, locale=locale)


# --------------------------------------------------------------------------- #
# Bulk approve / reject                                                       #
# --------------------------------------------------------------------------- #


async def bulk_approve_events(
    session: AsyncSession,
    *,
    principal: Principal,
    event_ids: list[uuid.UUID],
    ctx: RequestContext,
    locale: str = "vi",
) -> list[dict]:
    results: list[dict] = []
    for event_id in event_ids:
        try:
            data = await approve_event(
                session, principal=principal, event_id=event_id, ctx=ctx,
                locale=locale,
            )
            results.append({"id": str(event_id), "success": True, "event": data})
        except AppError as exc:
            await session.rollback()
            results.append(
                {
                    "id": str(event_id),
                    "success": False,
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )
    return results


async def bulk_reject_events(
    session: AsyncSession,
    *,
    principal: Principal,
    items: list[dict],
    ctx: RequestContext,
    locale: str = "vi",
) -> list[dict]:
    results: list[dict] = []
    for item in items:
        event_id = item["id"]
        try:
            data = await reject_event(
                session,
                principal=principal,
                event_id=event_id,
                reason=item.get("reason", ""),
                reason_code=item.get("reason_code"),
                ctx=ctx,
                locale=locale,
            )
            results.append({"id": str(event_id), "success": True, "event": data})
        except AppError as exc:
            await session.rollback()
            results.append(
                {
                    "id": str(event_id),
                    "success": False,
                    "error_code": exc.code,
                    "message": exc.message,
                }
            )
    return results


# --------------------------------------------------------------------------- #
# Escalation -> human review queue                                            #
# --------------------------------------------------------------------------- #


async def escalate_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    reason_code: str | None = None,
    note: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_university_moderator(session, principal)
    code = _validate_reason_code(reason_code, reason=note)
    event = await _load_event(session, event_id)
    if event is None:
        raise ResourceNotFoundError()

    event.moderation_status = event_lifecycle.MOD_FLAGGED
    if note and note.strip():
        event.moderation_note = note.strip()
    event.moderation_reason_code = code
    # Anchor the AI human-review-queue SLA on when the flag was raised.
    event.moderation_flagged_at = _now()
    event.version += 1
    await session.flush()

    await write_audit(
        session, action="event.escalated", resource_type="event",
        resource_id=event.id, context=_audit_ctx(principal, ctx),
        after={"moderation_status": event.moderation_status, "reason_code": code,
               "org_id": str(event.org_id)},
    )

    from app.modules.moderation.application import review_queue_service

    await review_queue_service.enqueue(
        session,
        source=review_queue_service.SOURCE_MODERATOR_ESCALATION,
        resource_type="event",
        resource_id=event.id,
        org_id=event.org_id,
        severity="high",
        findings={
            "reason_code": code,
            "note": (note or "").strip(),
            "escalated_by": str(principal.user_id),
        },
    )
    await session.commit()
    await session.refresh(event)
    return presenters.owner_event_summary(event, locale=locale)


# --------------------------------------------------------------------------- #
# AI human-review queue: human final say over an AI/rule flag (B-579)          #
# --------------------------------------------------------------------------- #


def _cleared_moderation_status(status: str) -> str:
    """The ``moderation_status`` an event returns to when a human clears its flag.

    Mirrors the jobs helper: a ``published`` event returns to ``approved``, a
    ``rejected`` event to ``rejected``, and anything still in a review posture to
    ``pending``.
    """

    if status == event_lifecycle.PUBLISHED:
        return event_lifecycle.MOD_APPROVED
    if status == event_lifecycle.REJECTED:
        return event_lifecycle.MOD_REJECTED
    return event_lifecycle.MOD_PENDING


async def uphold_flag_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    reason: str,
    reason_code: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Human UPHOLDS an AI/rule flag on an event -> reject it (final say).

    Reuses the existing ``reject_event`` transition; records a dedicated
    ``event.flag_upheld`` audit capturing the prior flag reason first.
    """

    await _require_university_moderator(session, principal)
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"reason": "reason_required"})
    event = await _load_event(session, event_id)
    if event is None:
        raise ResourceNotFoundError()
    if event.moderation_status != event_lifecycle.MOD_FLAGGED:
        raise ConflictError(details={"reason": "not_flagged"})
    if not event_lifecycle.can_transition("reject", event.status):
        raise IllegalEventTransitionError(event="reject")

    prior_reason = event.moderation_reason_code
    code = _validate_reason_code(reason_code or prior_reason, reason=reason)
    await write_audit(
        session, action="event.flag_upheld", resource_type="event",
        resource_id=event.id, context=_audit_ctx(principal, ctx),
        before={"moderation_status": event_lifecycle.MOD_FLAGGED,
                "flag_reason_code": prior_reason},
        after={"decision": "uphold", "resulting_status": event_lifecycle.REJECTED,
               "reason_code": code, "human_reason": reason.strip()[:500],
               "org_id": str(event.org_id)},
    )
    return await reject_event(
        session, principal=principal, event_id=event_id, reason=reason,
        reason_code=code, ctx=ctx, locale=locale,
    )


async def clear_flag_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    reason: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Human DISMISSES an AI/rule flag on an event -> clear it (false positive).

    Returns the event to the moderation posture implied by its current status
    without changing ``status``. Audited (``event.flag_cleared``). Idempotent.
    """

    await _require_university_moderator(session, principal)
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"reason": "reason_required"})
    event = await _load_event(session, event_id)
    if event is None:
        raise ResourceNotFoundError()
    if event.moderation_status != event_lifecycle.MOD_FLAGGED:
        return presenters.owner_event_summary(event, locale=locale)  # idempotent

    prior_reason = event.moderation_reason_code
    new_status = _cleared_moderation_status(event.status)
    event.moderation_status = new_status
    event.moderation_reason_code = None
    event.moderation_flagged_at = None
    event.moderation_note = None
    event.version += 1
    await session.flush()

    await write_audit(
        session, action="event.flag_cleared", resource_type="event",
        resource_id=event.id, context=_audit_ctx(principal, ctx),
        before={"moderation_status": event_lifecycle.MOD_FLAGGED,
                "flag_reason_code": prior_reason},
        after={"decision": "dismiss", "moderation_status": new_status,
               "human_reason": reason.strip()[:500], "org_id": str(event.org_id)},
    )
    await session.commit()
    await session.refresh(event)
    return presenters.owner_event_summary(event, locale=locale)
