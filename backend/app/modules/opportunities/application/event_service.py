"""Event service: organizer CRUD, lifecycle transitions, public discovery (ADR-0008).

RBAC is enforced here (not in routers) via ``PermissionChecker`` plus org-scoped
tenant isolation: an organizer only ever sees / mutates its own org's events, and
a cross-org access attempt returns ``404`` (never ``403``) so the resource is not
enumerable. Every write records an audit row in the caller's transaction.

Public discovery (:func:`list_public_events` / :func:`get_event` for non-owners)
returns **only** events that are published, approved, visible to the principal's
tier, and not past their end time. Hidden/unpublished events return ``404`` to
non-owners to prevent enumeration.

University auto-approve (§5): a ``university``-type org's ``submit`` transitions
``draft/rejected -> published`` directly; a partner-org submit goes to
``pending_review``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.api import event_presenters as presenters
from app.modules.opportunities.application import event_public_read
from app.modules.opportunities.application.event_errors import (
    EventNotEditableError,
    EventVersionConflictError,
    IllegalEventTransitionError,
    InvalidEventFieldError,
)
from app.modules.opportunities.application.event_visibility import apply_visible_filter
from app.modules.opportunities.domain import event_lifecycle, lifecycle
from app.modules.opportunities.domain.event_models import Event, EventRegistration
from app.modules.organization.application import org_reporting_facade
from app.modules.organization.domain.catalog import slugify
from app.modules.users.application import user_service
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.moderation import compute_due_by
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "events"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _as_aware(value: datetime | None) -> datetime | None:
    """SQLite reads timestamps back naive; coerce to UTC-aware for comparisons."""

    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


async def _org_type(session: AsyncSession, org_id: uuid.UUID) -> str | None:
    return await org_reporting_facade.org_type_for(session, org_id)


async def _unique_slug(session: AsyncSession, title: str) -> str:
    base = slugify(title)[:560] or "event"
    candidate = base
    suffix = 1
    while True:
        exists = (await session.execute(select(Event.id).where(Event.slug == candidate))).first()
        if exists is None:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


def _validate_fields(payload: dict, *, partial: bool) -> None:
    et = payload.get("event_type")
    if et is not None and et not in event_lifecycle.EVENT_TYPES:
        raise InvalidEventFieldError(field="event_type")
    fmt = payload.get("format")
    if fmt is not None and fmt not in event_lifecycle.FORMATS:
        raise InvalidEventFieldError(field="format")
    vis = payload.get("visibility")
    if vis is not None and vis not in event_lifecycle.VISIBILITY_LEVELS:
        raise InvalidEventFieldError(field="visibility")

    cap = payload.get("capacity")
    if cap is not None and cap < 1:
        raise InvalidEventFieldError(field="capacity")

    starts_at = payload.get("starts_at")
    ends_at = payload.get("ends_at")
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise InvalidEventFieldError(field="ends_at")

    opens = payload.get("registration_opens_at")
    closes = payload.get("registration_closes_at")
    if opens is not None and closes is not None and closes <= opens:
        raise InvalidEventFieldError(field="registration_closes_at")
    # A registration deadline after the event starts is meaningless.
    if closes is not None and starts_at is not None and closes > starts_at:
        raise InvalidEventFieldError(field="registration_closes_at")


# --------------------------------------------------------------------------- #
# Loading / ownership                                                         #
# --------------------------------------------------------------------------- #


async def _load_owned_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    lock: bool = False,
) -> Event:
    """Load a non-deleted event that ``principal`` owns; else ``404``."""

    stmt = select(Event).where(Event.id == event_id, Event.deleted_at.is_(None))
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    event = (await session.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and event.org_id != principal.org_id:
        raise ResourceNotFoundError()
    return event


async def _can_moderate(session: AsyncSession, principal: Principal) -> bool:
    """True if ``principal`` is a platform superadmin or a university moderator."""

    if principal.is_superadmin:
        return True
    if not permission_checker.can(principal, _RESOURCE, "moderate"):
        return False
    if principal.org_id is None:
        return False
    return await _org_type(session, principal.org_id) == "university"


def _is_publicly_visible(event: Event, *, now: datetime) -> bool:
    if event.deleted_at is not None:
        return False
    if (
        event.status != event_lifecycle.PUBLISHED
        or event.moderation_status != event_lifecycle.MOD_APPROVED
    ):
        return False
    if event.published_at is None:
        return False
    ends_at = _as_aware(event.ends_at)
    if ends_at is not None and ends_at <= now:
        return False
    if event.visibility == event_lifecycle.INVITATION_ONLY:
        return False  # requires a per-event allow-list (later phase)
    return True


# --------------------------------------------------------------------------- #
# Create / update                                                             #
# --------------------------------------------------------------------------- #

_UPDATABLE = {
    "title",
    "description",
    "event_type",
    "format",
    "cover_image_path",
    "venue_name",
    "venue_address",
    "starts_at",
    "ends_at",
    "timezone",
    "registration_opens_at",
    "registration_closes_at",
    "capacity",
    "visibility",
    "tags",
}


async def create_event(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "create", resource_org_id=principal.org_id)
    _validate_fields(payload, partial=False)
    assert principal.user_id is not None

    slug = await _unique_slug(session, payload["title"])
    event = Event(
        org_id=principal.org_id,
        created_by=principal.user_id,
        slug=slug,
        status=event_lifecycle.DRAFT,
        moderation_status=event_lifecycle.MOD_PENDING,
        **payload,
    )
    session.add(event)
    await session.flush()

    await write_audit(
        session,
        action="event.created",
        resource_type="event",
        resource_id=event.id,
        context=_audit_ctx(principal, ctx),
        after={"title": event.title, "status": event.status, "slug": slug},
    )
    await session.commit()
    await session.refresh(event)
    return presenters.owner_event_detail(event, locale=locale)


async def update_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    event = await _load_owned_event(session, principal=principal, event_id=event_id, lock=True)
    permission_checker.require(principal, _RESOURCE, "update", resource_org_id=event.org_id)
    if event.status not in event_lifecycle.EDITABLE_STATES:
        raise EventNotEditableError()

    expected_version = payload.pop("version", None)
    if expected_version is not None and expected_version != event.version:
        raise EventVersionConflictError()

    # Validate the resulting record (merge incoming over current for time checks).
    merged = {
        "event_type": payload.get("event_type", event.event_type),
        "format": payload.get("format", event.format),
        "visibility": payload.get("visibility", event.visibility),
        "capacity": payload.get("capacity", event.capacity),
        "starts_at": payload.get("starts_at", event.starts_at),
        "ends_at": payload.get("ends_at", event.ends_at),
        "registration_opens_at": payload.get("registration_opens_at", event.registration_opens_at),
        "registration_closes_at": payload.get(
            "registration_closes_at", event.registration_closes_at
        ),
    }
    _validate_fields(merged, partial=True)

    changed: dict[str, object] = {}
    for field in _UPDATABLE:
        if field in payload:
            setattr(event, field, payload[field])
            changed[field] = True
    if changed:
        event.version += 1
    await session.flush()

    await write_audit(
        session,
        action="event.updated",
        resource_type="event",
        resource_id=event.id,
        context=_audit_ctx(principal, ctx),
        after={"fields": sorted(changed.keys())},
    )
    await session.commit()
    await session.refresh(event)
    return presenters.owner_event_detail(event, locale=locale)


# --------------------------------------------------------------------------- #
# Lifecycle transitions (organizer-controlled)                                #
# --------------------------------------------------------------------------- #


async def submit_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    ctx: RequestContext,
    version: int | None = None,
    locale: str = "vi",
) -> dict:
    """Submit for moderation — partner -> ``pending_review``; university -> ``published``.

    University-created events are auto-approved (PRD §14.9); they go live
    immediately with ``moderation_status=approved`` and ``published_at`` set.
    """

    event = await _load_owned_event(session, principal=principal, event_id=event_id, lock=True)
    permission_checker.require(principal, _RESOURCE, "submit", resource_org_id=event.org_id)
    if version is not None and version != event.version:
        raise EventVersionConflictError()
    if not event_lifecycle.can_transition("submit", event.status):
        raise IllegalEventTransitionError(event="submit")

    now = _now()
    event.submitted_at = now
    event.due_by = compute_due_by(now, sla_hours=get_settings().event_moderation_sla_hours)
    org_type = await _org_type(session, event.org_id)
    auto_approve = org_type == "university"

    if auto_approve:
        event.status = event_lifecycle.PUBLISHED
        event.moderation_status = event_lifecycle.MOD_APPROVED
        event.moderation_note = None
        event.moderation_reason_code = None
        event.approved_by = principal.user_id
        event.approved_at = now
        event.published_at = now
        action = "event.published"
    else:
        event.status = event_lifecycle.PENDING_REVIEW
        event.moderation_status = event_lifecycle.MOD_PENDING
        event.moderation_note = None
        event.moderation_reason_code = None
        action = "event.submit"
    event.claimed_by = None
    event.claimed_at = None
    event.version += 1
    await session.flush()

    await write_audit(
        session,
        action=action,
        resource_type="event",
        resource_id=event.id,
        context=_audit_ctx(principal, ctx),
        after={"status": event.status, "moderation_status": event.moderation_status},
    )
    await session.commit()
    await session.refresh(event)
    return presenters.owner_event_detail(event, locale=locale)


async def cancel_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    ctx: RequestContext,
    version: int | None = None,
    locale: str = "vi",
) -> dict:
    """Cancel a published event and notify every confirmed/waitlisted registrant."""

    event = await _load_owned_event(session, principal=principal, event_id=event_id, lock=True)
    permission_checker.require(principal, _RESOURCE, "manage", resource_org_id=event.org_id)
    if version is not None and version != event.version:
        raise EventVersionConflictError()
    if not event_lifecycle.can_transition("cancel", event.status):
        raise IllegalEventTransitionError(event="cancel")

    now = _now()
    event.status = event_lifecycle.CANCELLED
    event.cancelled_at = now
    event.version += 1
    await session.flush()

    await write_audit(
        session,
        action="event.cancel",
        resource_type="event",
        resource_id=event.id,
        context=_audit_ctx(principal, ctx),
        after={"status": event.status},
    )
    await _notify_registrants_cancelled(session, event=event, locale=locale)
    await session.commit()
    await session.refresh(event)
    return presenters.owner_event_detail(event, locale=locale)


async def _notify_registrants_cancelled(
    session: AsyncSession, *, event: Event, locale: str
) -> None:
    """Fan-out a neutral cancellation notice to confirmed + waitlisted registrants.

    PII-safe: bodies use only event title + the recipient's own name; no other
    attendee's identity appears. Deduped per ``(event, user)``.
    """

    regs = list(
        (
            await session.execute(
                select(EventRegistration).where(
                    EventRegistration.event_id == event.id,
                    EventRegistration.status.in_(
                        [event_lifecycle.REG_CONFIRMED, event_lifecycle.REG_WAITLISTED]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    for reg in regs:
        user = await user_service.get_by_id(session, reg.user_id)
        await enqueue_notification(
            session,
            recipient_id=reg.user_id,
            template_key="event.cancelled",
            channel="email",
            locale=locale,
            variables={
                "email": user.email if user else "",
                "name": user.full_name if user and user.full_name else "",
                "event_title": event.title,
            },
            dedupe_key=f"event.cancelled:{event.id}:{reg.user_id}",
        )
        await feed_service.create_in_app(
            session,
            recipient_id=reg.user_id,
            notif_type="opportunities.event_cancelled",
            action_url=f"/events/{event.id}",
            variables={"event_title": event.title},
            locale=locale,
        )


async def delete_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> None:
    event = await _load_owned_event(session, principal=principal, event_id=event_id, lock=True)
    permission_checker.require(principal, _RESOURCE, "manage", resource_org_id=event.org_id)
    if event.status not in event_lifecycle.DELETABLE_STATES:
        raise EventNotEditableError()
    event.deleted_at = _now()
    event.version += 1
    await session.flush()
    await write_audit(
        session,
        action="event.deleted",
        resource_type="event",
        resource_id=event.id,
        context=_audit_ctx(principal, ctx),
        before={"status": event.status},
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Reads                                                                       #
# --------------------------------------------------------------------------- #


async def get_event(
    session: AsyncSession,
    *,
    principal: Principal,
    event_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Owner -> full detail; non-owner -> public detail iff visible, else ``404``."""

    event = (
        await session.execute(select(Event).where(Event.id == event_id, Event.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if event is None:
        raise ResourceNotFoundError()

    is_owner = principal.is_superadmin or (
        principal.org_id is not None and principal.org_id == event.org_id
    )
    if is_owner and permission_checker.can(
        principal, _RESOURCE, "read", resource_org_id=event.org_id
    ):
        return presenters.owner_event_detail(event, locale=locale)

    # University moderators (and superadmins) may view full detail in any status.
    if await _can_moderate(session, principal):
        return presenters.owner_event_detail(event, locale=locale)

    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    if not _is_publicly_visible(event, now=_now()) or event.visibility not in levels:
        raise ResourceNotFoundError()
    org = await org_reporting_facade.summary_for(session, event.org_id)
    return presenters.public_event_detail(event, company=org, locale=locale)


async def get_registrable_event(
    session: AsyncSession, *, principal: Principal, event_id: uuid.UUID
) -> Event:
    """Return the :class:`Event` ORM iff ``principal`` may register for it.

    Visible to the persona's tier + published/approved/upcoming. Anything else
    returns ``404`` (enumeration hiding), consistent with :func:`get_event`.
    """

    event = (
        await session.execute(select(Event).where(Event.id == event_id, Event.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if event is None:
        raise ResourceNotFoundError()
    now = _now()
    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    if not _is_publicly_visible(event, now=now) or event.visibility not in levels:
        raise ResourceNotFoundError()
    return event


def _public_filter(stmt: Select, *, principal: Principal, now: datetime) -> Select:
    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    return apply_visible_filter(stmt, levels=levels, now=now)


def _apply_search_filters(
    stmt: Select, *, q: str | None, event_type: str | None, format: str | None
) -> Select:
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Event.title.ilike(term),
                func.cast(Event.tags, String).ilike(term),
            )
        )
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if format:
        stmt = stmt.where(Event.format == format)
    return stmt


async def list_public_events(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    q: str | None = None,
    event_type: str | None = None,
    format: str | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int, int]:
    """Cursor-paginated public discovery list. Returns (items, next, limit, total).

    Ordered by soonest ``starts_at`` (upcoming first) — past events are excluded by
    the visibility predicate.
    """

    now = _now()
    page_limit = clamp_limit(limit)

    def _filtered(base: Select) -> Select:
        return _apply_search_filters(
            _public_filter(base, principal=principal, now=now),
            q=q,
            event_type=event_type,
            format=format,
        )

    total = (await session.execute(_filtered(select(func.count()).select_from(Event)))).scalar_one()

    stmt = _filtered(select(Event))
    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_starts = datetime.fromisoformat(decoded["starts_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                Event.starts_at > anchor_starts,
                (Event.starts_at == anchor_starts) & (Event.id > anchor_id),
            )
        )
    stmt = stmt.order_by(Event.starts_at.asc(), Event.id.asc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda e: {
            "starts_at": e.starts_at.isoformat(),
            "id": str(e.id),
        },
    )
    items = await event_public_read.enrich_summaries(session, page.items, locale=locale)
    return items, page.next_cursor, page.limit, total


async def list_my_events(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    """Organizer-scoped list of the caller org's own events (all statuses)."""

    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=principal.org_id)
    page_limit = clamp_limit(limit)
    stmt = select(Event).where(Event.org_id == principal.org_id, Event.deleted_at.is_(None))
    if status is not None:
        stmt = stmt.where(Event.status == status)

    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_created = datetime.fromisoformat(decoded["created_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                Event.created_at < anchor_created,
                (Event.created_at == anchor_created) & (Event.id < anchor_id),
            )
        )
    stmt = stmt.order_by(Event.created_at.desc(), Event.id.desc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda e: {
            "created_at": e.created_at.isoformat(),
            "id": str(e.id),
        },
    )
    items = [presenters.owner_event_summary(e, locale=locale) for e in page.items]
    return items, page.next_cursor, page.limit
