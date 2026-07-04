"""Event registration, waitlist, check-in, and the scheduler sweeps (ADR-0008 §2/§3).

Capacity is enforced atomically: the count-check + insert runs under an event-row
``SELECT ... FOR UPDATE`` (Postgres; dialect-guarded). The authoritative capacity
check is the live ``COUNT(status='confirmed')`` under the lock; the partial unique
index ``uq_event_reg_active`` is the duplicate safety net. SQLite tests rely on the
service-layer single-writer guard.

Waitlist promotion is **inline on cancel** (same locked transaction, FIFO head)
with a scheduler ``waitlist_backfill`` safety net — one promote routine, called
both ways. V1 events are free, so there is no payment hold; promotion is immediate
and permanent.

PII discipline (§3): audit ``after`` snapshots and logs carry only ``user_id`` +
``registration_id`` + ``status`` — never email or full name. The attendee email is
exposed **only** in the owning-organizer projection, never to other roles, never
publicly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.analytics.application import ingestion_service as analytics
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import dispatch_service, feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.api import event_presenters as presenters
from app.modules.opportunities.application.event_errors import (
    EventNotOpenError,
    IllegalEventTransitionError,
    NotRegisteredError,
    RegistrationClosedError,
    RegistrationNotOpenError,
)
from app.modules.opportunities.domain import event_lifecycle, lifecycle
from app.modules.opportunities.domain.event_models import Event, EventRegistration
from app.modules.users.application import user_read_facade, user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "events"

# Grace window after an event ends before remaining confirmeds become no-shows.
_NO_SHOW_GRACE = timedelta(hours=2)
# Reminder lead times (T-24h + T-1h — two independent, separately-deduped ticks).
_REMINDER_WINDOW = timedelta(hours=24)
_REMINDER_WINDOW_SOON = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _as_aware(value: datetime | None) -> datetime | None:
    """SQLite reads timestamps back naive; coerce to UTC-aware for comparisons."""

    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _load_event_locked(
    session: AsyncSession, event_id: uuid.UUID
) -> Event | None:
    stmt = select(Event).where(Event.id == event_id, Event.deleted_at.is_(None))
    if _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def _confirmed_count(session: AsyncSession, event_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == event_id,
                EventRegistration.status == event_lifecycle.REG_CONFIRMED,
            )
        )
    ).scalar_one()


async def _active_registration(
    session: AsyncSession, *, event_id: uuid.UUID, user_id: uuid.UUID
) -> EventRegistration | None:
    """The caller's non-cancelled registration for an event, if any."""

    return (
        await session.execute(
            select(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == user_id,
                EventRegistration.status != event_lifecycle.REG_CANCELLED,
            )
        )
    ).scalars().first()


async def _waitlist_position(
    session: AsyncSession, *, reg: EventRegistration
) -> int:
    """1-based FIFO position of a waitlisted registration.

    Computed by ranking within the ordered waitlist (column-to-column ordering in
    SQL) rather than a bound-param timestamp comparison — the latter is unreliable
    on SQLite, which stores ``func.now()`` at second precision while ORM-bound
    datetimes carry microseconds. ``id`` breaks ties for same-second rows.
    """

    ids = list(
        (
            await session.execute(
                select(EventRegistration.id)
                .where(
                    EventRegistration.event_id == reg.event_id,
                    EventRegistration.status == event_lifecycle.REG_WAITLISTED,
                )
                .order_by(
                    EventRegistration.created_at.asc(), EventRegistration.id.asc()
                )
            )
        ).scalars().all()
    )
    try:
        return ids.index(reg.id) + 1
    except ValueError:
        return 1


# --------------------------------------------------------------------------- #
# Validation                                                                  #
# --------------------------------------------------------------------------- #


def _assert_registrable(event: Event, *, principal: Principal, now: datetime) -> None:
    """Raise the right coded error if the event cannot be registered for."""

    if event.status in (
        event_lifecycle.DRAFT,
        event_lifecycle.PENDING_REVIEW,
        event_lifecycle.REJECTED,
    ):
        raise ResourceNotFoundError()  # never publicly enumerable
    if event.status in (event_lifecycle.CANCELLED, event_lifecycle.COMPLETED):
        raise EventNotOpenError()
    if (
        event.moderation_status != event_lifecycle.MOD_APPROVED
        or event.published_at is None
    ):
        raise ResourceNotFoundError()

    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    if (
        event.visibility == event_lifecycle.INVITATION_ONLY
        or event.visibility not in levels
    ):
        raise ResourceNotFoundError()

    starts_at = _as_aware(event.starts_at)
    if event_lifecycle.registration_not_yet_open(
        now=now, registration_opens_at=_as_aware(event.registration_opens_at)
    ):
        raise RegistrationNotOpenError()
    assert starts_at is not None
    if event_lifecycle.registration_window_closed(
        now=now,
        registration_closes_at=_as_aware(event.registration_closes_at),
        starts_at=starts_at,
    ):
        raise RegistrationClosedError()


# --------------------------------------------------------------------------- #
# Notifications                                                               #
# --------------------------------------------------------------------------- #


def _venue_or_format(event: Event, *, locale: str) -> str:
    if event.format == "online":
        return event_lifecycle.format_label("online", locale=locale)
    return event.venue_name or event_lifecycle.format_label(event.format, locale=locale)


async def _notify_registration(
    session: AsyncSession,
    *,
    event: Event,
    user_id: uuid.UUID,
    template_key: str,
    notif_type: str,
    locale: str,
    extra: dict | None = None,
) -> None:
    user = await user_service.get_by_id(session, user_id)
    variables: dict[str, object] = {
        "email": user.email if user else "",
        "name": user.full_name if user and user.full_name else "",
        "event_title": event.title,
        "starts_at": event.starts_at.isoformat() if event.starts_at else "",
        "venue_or_format": _venue_or_format(event, locale=locale),
    }
    if extra:
        variables.update(extra)
    await enqueue_notification(
        session,
        recipient_id=user_id,
        template_key=template_key,
        channel="email",
        locale=locale,
        variables=variables,
        dedupe_key=extra.get("dedupe_key") if extra else None,
    )
    feed_vars: dict[str, object] = {"event_title": event.title}
    if extra and "waitlist_position" in extra:
        feed_vars["waitlist_position"] = extra["waitlist_position"]
    await feed_service.create_in_app(
        session,
        recipient_id=user_id,
        notif_type=notif_type,
        action_url=f"/events/{event.id}",
        variables=feed_vars,
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Register                                                                    #
# --------------------------------------------------------------------------- #


async def register(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Register the caller for an event (-> confirmed | waitlisted).

    Guests get ``401`` (login required). Idempotent for an existing active
    registration. Capacity is enforced under an event-row lock with the live
    confirmed-count check; a full event waitlists FIFO.
    """

    # Guest -> 401 (AuthRequiredError); authenticated-but-forbidden -> 403.
    permission_checker.require(principal, _RESOURCE, "register")
    assert principal.user_id is not None
    user_id = principal.user_id

    event = await _load_event_locked(session, event_id)
    if event is None:
        raise ResourceNotFoundError()
    now = _now()
    _assert_registrable(event, principal=principal, now=now)

    existing = await _active_registration(
        session, event_id=event_id, user_id=user_id
    )
    if existing is not None:
        # Idempotent: return the current registration state unchanged.
        position = (
            await _waitlist_position(session, reg=existing)
            if existing.status == event_lifecycle.REG_WAITLISTED
            else None
        )
        await session.commit()
        return presenters.my_registration(
            existing, event=event, waitlist_position=position, locale=locale
        )

    if event.capacity is None:
        status = event_lifecycle.REG_CONFIRMED
    else:
        confirmed_n = await _confirmed_count(session, event_id)
        status = (
            event_lifecycle.REG_CONFIRMED
            if confirmed_n < event.capacity
            else event_lifecycle.REG_WAITLISTED
        )

    # Set ``created_at`` explicitly (microsecond precision) so FIFO waitlist
    # ordering is deterministic on both Postgres and SQLite (whose ``func.now()``
    # only has second precision, which would otherwise tie same-second rows).
    reg = EventRegistration(
        event_id=event_id, user_id=user_id, status=status, created_at=now
    )
    session.add(reg)
    await session.flush()

    if status == event_lifecycle.REG_CONFIRMED:
        event.registration_count += 1
    event.version += 1
    await session.flush()

    await write_audit(
        session, action="event.registered", resource_type="event_registration",
        resource_id=reg.id, context=_audit_ctx(principal, ctx),
        after={"event_id": str(event_id), "user_id": str(user_id), "status": status},
    )
    await analytics.record_event_safe(
        session,
        event_type="event.registered",
        aggregate_type="event_registration",
        aggregate_id=reg.id,
        actor_id=user_id,
        actor_type="student",
        properties={"event_id": str(event_id), "status": status},
    )

    position = None
    if status == event_lifecycle.REG_CONFIRMED:
        await _notify_registration(
            session, event=event, user_id=user_id,
            template_key="event.registration_confirmed",
            notif_type="opportunities.event_registration_confirmed", locale=locale,
        )
    else:
        position = await _waitlist_position(session, reg=reg)
        await _notify_registration(
            session, event=event, user_id=user_id,
            template_key="event.registration_waitlisted",
            notif_type="opportunities.event_waitlisted", locale=locale,
            extra={"waitlist_position": position},
        )

    await session.commit()
    await session.refresh(reg)
    return presenters.my_registration(
        reg, event=event, waitlist_position=position, locale=locale
    )


# --------------------------------------------------------------------------- #
# Cancel + inline waitlist promotion                                          #
# --------------------------------------------------------------------------- #


async def _promote_head(
    session: AsyncSession, *, event: Event, locale: str
) -> EventRegistration | None:
    """Promote the FIFO waitlist head to confirmed (single source of truth)."""

    stmt = (
        select(EventRegistration)
        .where(
            EventRegistration.event_id == event.id,
            EventRegistration.status == event_lifecycle.REG_WAITLISTED,
        )
        .order_by(EventRegistration.created_at.asc(), EventRegistration.id.asc())
        .limit(1)
    )
    if _use_for_update():
        stmt = stmt.with_for_update(skip_locked=True)
    head = (await session.execute(stmt)).scalars().first()
    if head is None:
        return None

    head.status = event_lifecycle.REG_CONFIRMED
    head.version += 1
    event.registration_count += 1
    await session.flush()

    await write_audit(
        session, action="event.waitlist_promoted",
        resource_type="event_registration", resource_id=head.id,
        context=AuditContext(actor_org_id=event.org_id),
        after={"event_id": str(event.id), "user_id": str(head.user_id),
               "status": head.status},
    )
    await _notify_registration(
        session, event=event, user_id=head.user_id,
        template_key="event.waitlist_promoted",
        notif_type="opportunities.event_waitlist_promoted", locale=locale,
    )
    return head


async def cancel_registration(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Cancel the caller's registration; inline-promote the waitlist head if freed."""

    permission_checker.require(principal, _RESOURCE, "register")
    assert principal.user_id is not None
    user_id = principal.user_id

    event = await _load_event_locked(session, event_id)
    if event is None:
        raise ResourceNotFoundError()

    reg = (
        await session.execute(
            select(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == user_id,
                EventRegistration.status.in_(
                    [event_lifecycle.REG_CONFIRMED, event_lifecycle.REG_WAITLISTED]
                ),
            )
        )
    ).scalars().first()
    if reg is None:
        raise NotRegisteredError()

    was_confirmed = reg.status == event_lifecycle.REG_CONFIRMED
    reg.status = event_lifecycle.REG_CANCELLED
    reg.cancelled_at = _now()
    reg.version += 1
    if was_confirmed and event.registration_count > 0:
        event.registration_count -= 1
    event.version += 1
    await session.flush()

    await write_audit(
        session, action="event.registration_cancelled",
        resource_type="event_registration", resource_id=reg.id,
        context=_audit_ctx(principal, ctx),
        after={"event_id": str(event_id), "user_id": str(user_id),
               "status": reg.status},
    )

    # A freed confirmed seat lets the FIFO head in (capacitied events only).
    if (
        was_confirmed
        and event.capacity is not None
        and event.status == event_lifecycle.PUBLISHED
    ):
        await _promote_head(session, event=event, locale=locale)

    await session.commit()
    return {"status": "cancelled", "registration_id": str(reg.id)}


# --------------------------------------------------------------------------- #
# Check-in + attendee list (organizer / university only)                      #
# --------------------------------------------------------------------------- #


async def _load_event_for_staff(
    session: AsyncSession, *, principal: Principal, event_id: uuid.UUID
) -> tuple[Event, bool]:
    """Load an event for a staff action; return (event, is_owning_organizer).

    Authorization (§3): the owning org's members with ``events:manage`` run their
    own door; university staff with ``events:moderate`` (or a superadmin) may also
    act. Cross-org access by a non-moderator is ``404`` (enumeration hiding).
    """

    event = (
        await session.execute(
            select(Event).where(Event.id == event_id, Event.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if event is None:
        raise ResourceNotFoundError()

    is_moderator = principal.is_superadmin or (
        permission_checker.can(principal, _RESOURCE, "moderate")
        and principal.org_id is not None
        and await _is_university(session, principal.org_id)
    )
    if principal.org_id is not None and principal.org_id == event.org_id:
        permission_checker.require(
            principal, _RESOURCE, "manage", resource_org_id=event.org_id
        )
        return event, True
    if is_moderator:
        return event, False
    raise ResourceNotFoundError()


async def _is_university(session: AsyncSession, org_id: uuid.UUID) -> bool:
    from app.modules.organization.application import org_reporting_facade

    return await org_reporting_facade.is_university_org(session, org_id)


async def check_in(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Mark a confirmed registration ``attended``. Idempotent; organizer/university."""

    event, _is_organizer = await _load_event_for_staff(
        session, principal=principal, event_id=event_id
    )
    reg = (
        await session.execute(
            select(EventRegistration).where(
                EventRegistration.id == registration_id,
                EventRegistration.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if reg is None:
        raise ResourceNotFoundError()

    if reg.status == event_lifecycle.REG_ATTENDED:
        return {"status": "attended", "registration_id": str(reg.id)}  # idempotent
    if reg.status != event_lifecycle.REG_CONFIRMED:
        raise IllegalEventTransitionError(event="check_in")

    reg.status = event_lifecycle.REG_ATTENDED
    reg.check_in_at = _now()
    reg.check_in_by = principal.user_id
    reg.version += 1
    await session.flush()

    await write_audit(
        session, action="event.checked_in", resource_type="event_registration",
        resource_id=reg.id, context=_audit_ctx(principal, ctx),
        after={"event_id": str(event_id), "user_id": str(reg.user_id),
               "status": reg.status},
    )
    await analytics.record_event_safe(
        session,
        event_type="event.checked_in",
        aggregate_type="event_registration",
        aggregate_id=reg.id,
        actor_id=reg.user_id,
        actor_type="student",
        properties={"event_id": str(event_id)},
    )
    await session.commit()
    return {"status": "attended", "registration_id": str(reg.id)}


async def list_attendees(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    locale: str = "vi",
) -> list[dict]:
    """Attendee list (organizer/university only). Email only in the organizer view."""

    event, is_organizer = await _load_event_for_staff(
        session, principal=principal, event_id=event_id
    )
    rows = list(
        (
            await session.execute(
                select(EventRegistration)
                .where(
                    EventRegistration.event_id == event_id,
                    EventRegistration.status != event_lifecycle.REG_CANCELLED,
                )
                .order_by(EventRegistration.created_at.asc())
            )
        ).scalars().all()
    )
    user_ids = {r.user_id for r in rows}
    users = await user_read_facade.get_user_contacts(session, user_ids)

    out: list[dict] = []
    for r in rows:
        user = users.get(r.user_id)
        out.append(
            presenters.attendee_row(
                r,
                display_name=user.full_name if user else None,
                email=user.email if user else None,
                include_email=is_organizer,
                locale=locale,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Student "My Events"                                                         #
# --------------------------------------------------------------------------- #


async def my_registrations(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> list[dict]:
    """The caller's own registrations (active states), newest event first."""

    permission_checker.require(principal, _RESOURCE, "register")
    assert principal.user_id is not None
    rows = list(
        (
            await session.execute(
                select(EventRegistration)
                .where(
                    EventRegistration.user_id == principal.user_id,
                    EventRegistration.status != event_lifecycle.REG_CANCELLED,
                )
                .order_by(EventRegistration.created_at.desc())
            )
        ).scalars().all()
    )
    event_ids = {r.event_id for r in rows}
    events: dict[uuid.UUID, Event] = {}
    if event_ids:
        erows = (
            await session.execute(select(Event).where(Event.id.in_(event_ids)))
        ).scalars().all()
        events = {e.id: e for e in erows}

    out: list[dict] = []
    for r in rows:
        event = events.get(r.event_id)
        if event is None or event.deleted_at is not None:
            continue
        position = (
            await _waitlist_position(session, reg=r)
            if r.status == event_lifecycle.REG_WAITLISTED
            else None
        )
        out.append(
            presenters.my_registration(
                r, event=event, waitlist_position=position, locale=locale
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Scheduler sweeps (flush-only; the scheduler owns the commit)                #
# --------------------------------------------------------------------------- #


async def sweep_auto_complete(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Auto-complete published events whose ``ends_at`` has passed."""

    now = now or _now()
    rows = list(
        (
            await session.execute(
                select(Event).where(
                    Event.deleted_at.is_(None),
                    Event.status == event_lifecycle.PUBLISHED,
                    Event.ends_at < now,
                )
            )
        ).scalars().all()
    )
    for event in rows:
        event.status = event_lifecycle.COMPLETED
        event.version += 1
        await write_audit(
            session, action="event.auto_completed", resource_type="event",
            resource_id=event.id, context=AuditContext(actor_org_id=event.org_id),
            after={"status": event.status},
        )
    await session.flush()
    return {"completed": len(rows)}


async def sweep_no_show(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Flip remaining confirmed registrations of ended events to ``no_show``."""

    now = now or _now()
    cutoff = now - _NO_SHOW_GRACE
    rows = list(
        (
            await session.execute(
                select(EventRegistration)
                .join(Event, Event.id == EventRegistration.event_id)
                .where(
                    Event.deleted_at.is_(None),
                    Event.ends_at < cutoff,
                    Event.status.in_(
                        [event_lifecycle.COMPLETED, event_lifecycle.PUBLISHED]
                    ),
                    EventRegistration.status == event_lifecycle.REG_CONFIRMED,
                )
            )
        ).scalars().all()
    )
    for reg in rows:
        reg.status = event_lifecycle.REG_NO_SHOW
        reg.version += 1
        await write_audit(
            session, action="event.no_show", resource_type="event_registration",
            resource_id=reg.id, context=AuditContext(),
            after={"event_id": str(reg.event_id), "user_id": str(reg.user_id),
                   "status": reg.status},
        )
    await session.flush()
    return {"no_show": len(rows)}


async def sweep_waitlist_backfill(
    session: AsyncSession, *, now: datetime | None = None, locale: str = "vi"
) -> dict[str, int]:
    """Promote FIFO waitlist heads for any under-capacity published event."""

    now = now or _now()
    events = list(
        (
            await session.execute(
                select(Event).where(
                    Event.deleted_at.is_(None),
                    Event.status == event_lifecycle.PUBLISHED,
                    Event.capacity.isnot(None),
                    Event.ends_at > now,
                )
            )
        ).scalars().all()
    )
    promoted = 0
    for event in events:
        assert event.capacity is not None
        while True:
            confirmed_n = await _confirmed_count(session, event.id)
            if confirmed_n >= event.capacity:
                break
            head = await _promote_head(session, event=event, locale=locale)
            if head is None:
                break
            promoted += 1
    await session.flush()
    return {"promoted": promoted}


async def sweep_reminders(
    session: AsyncSession, *, now: datetime | None = None, locale: str = "vi"
) -> dict[str, int]:
    """Enqueue a T-24h reminder per confirmed registrant (idempotent, deduped)."""

    now = now or _now()
    window_end = now + _REMINDER_WINDOW
    rows = list(
        (
            await session.execute(
                select(EventRegistration, Event)
                .join(Event, Event.id == EventRegistration.event_id)
                .where(
                    Event.deleted_at.is_(None),
                    Event.status == event_lifecycle.PUBLISHED,
                    Event.starts_at > now,
                    Event.starts_at <= window_end,
                    EventRegistration.status == event_lifecycle.REG_CONFIRMED,
                )
            )
        ).all()
    )
    sent = 0
    for reg, event in rows:
        dedupe_key = f"event.reminder:{event.id}:{reg.user_id}"
        if await _outbox_dedupe_exists(session, dedupe_key=dedupe_key):
            continue  # a previous tick already enqueued this reminder
        await _notify_registration(
            session, event=event, user_id=reg.user_id,
            template_key="event.reminder",
            notif_type="opportunities.event_reminder", locale=locale,
            extra={"dedupe_key": dedupe_key},
        )
        sent += 1
    await session.flush()
    return {"reminders": sent}


async def sweep_reminders_soon(
    session: AsyncSession, *, now: datetime | None = None, locale: str = "vi"
) -> dict[str, int]:
    """Enqueue a T-1h reminder per confirmed registrant (idempotent, deduped).

    Independent tick from :func:`sweep_reminders` (T-24h) — its own dedupe key
    (``event.reminder_soon`` vs ``event.reminder``) so a registrant who confirms
    inside the T-24h window still gets exactly one of each, never a duplicate.
    """

    now = now or _now()
    window_end = now + _REMINDER_WINDOW_SOON
    rows = list(
        (
            await session.execute(
                select(EventRegistration, Event)
                .join(Event, Event.id == EventRegistration.event_id)
                .where(
                    Event.deleted_at.is_(None),
                    Event.status == event_lifecycle.PUBLISHED,
                    Event.starts_at > now,
                    Event.starts_at <= window_end,
                    EventRegistration.status == event_lifecycle.REG_CONFIRMED,
                )
            )
        ).all()
    )
    sent = 0
    for reg, event in rows:
        dedupe_key = f"event.reminder_soon:{event.id}:{reg.user_id}"
        if await _outbox_dedupe_exists(session, dedupe_key=dedupe_key):
            continue  # a previous tick already enqueued this reminder
        await _notify_registration(
            session, event=event, user_id=reg.user_id,
            template_key="event.reminder_soon",
            notif_type="opportunities.event_reminder_soon", locale=locale,
            extra={"dedupe_key": dedupe_key},
        )
        sent += 1
    await session.flush()
    return {"reminders_soon": sent}


async def _outbox_dedupe_exists(
    session: AsyncSession, *, dedupe_key: str
) -> bool:
    return await dispatch_service.dedupe_exists(session, dedupe_key=dedupe_key)
