"""Events HTTP routes: public discovery, organizer management, student
registration, check-in, and university moderation (ADR-0008 §8).

Routers are HTTP-only: validate, delegate to services (which enforce RBAC + audit
+ tenant isolation + transactions), and shape the response envelope. Two routers
are exported and mounted by the module ``router``: ``events_router`` (``/events``)
and ``admin_events_router`` (``/admin/events``).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.opportunities.api.event_schemas import (
    EventApproveRequest,
    EventBulkApproveRequest,
    EventBulkRejectRequest,
    EventCreateRequest,
    EventEscalateRequest,
    EventModerationRejectRequest,
    EventUpdateRequest,
    EventVersionRequest,
)
from app.modules.opportunities.application import (
    event_moderation_service,
    event_service,
    registration_service,
)
from app.shared.permissions import GUEST, Principal
from app.shared.responses import paginated, success

events_router = APIRouter(prefix="/events")
admin_events_router = APIRouter(prefix="/admin/events")


async def _principal_or_guest(request: Request, session: AsyncSession) -> Principal:
    principal: Principal = GUEST
    if request.headers.get("authorization"):
        try:
            auth = await get_current_auth(request, session)
            principal = auth.principal
        except Exception:  # noqa: BLE001
            principal = GUEST
    return principal


# --------------------------------------------------------------------------- #
# Public discovery                                                            #
# --------------------------------------------------------------------------- #


@events_router.get("", summary="Public event discovery (RBAC-aware, visible only)")
async def list_events(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    q: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    event_format: str | None = Query(default=None, alias="format"),
) -> dict:
    principal = await _principal_or_guest(request, session)
    items, next_cursor, page_limit, total = await event_service.list_public_events(
        session,
        principal=principal,
        cursor=cursor,
        limit=limit,
        q=q,
        event_type=event_type,
        format=event_format,
    )
    body = paginated(items, next_cursor=next_cursor, limit=page_limit)
    body["page"]["total"] = total
    return body


@events_router.get("/mine", summary="Organizer-scoped list of the caller org's events")
async def list_my_events(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
    event_status: str | None = Query(default=None, alias="status"),
) -> dict:
    items, next_cursor, page_limit = await event_service.list_my_events(
        session,
        principal=auth.principal,
        status=event_status,
        cursor=cursor,
        limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@events_router.get(
    "/registrations/mine", summary="The caller's own event registrations ('My Events')"
)
async def my_registrations(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await registration_service.my_registrations(session, principal=auth.principal)
    return success(items, meta={"count": len(items)})


@events_router.get("/{event_id}", summary="Event detail (owner full / public visible / 404)")
async def get_event(
    event_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    principal = await _principal_or_guest(request, session)
    data = await event_service.get_event(session, principal=principal, event_id=event_id)
    return success(data)


# --------------------------------------------------------------------------- #
# Organizer management                                                         #
# --------------------------------------------------------------------------- #


@events_router.post("", status_code=status.HTTP_201_CREATED, summary="Create a draft event")
async def create_event(
    body: EventCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await event_service.create_event(
        session,
        principal=auth.principal,
        payload=body.model_dump(),
        ctx=auth.ctx,
    )
    return success(data)


@events_router.patch("/{event_id}", summary="Update a draft/rejected event")
async def update_event(
    event_id: uuid.UUID,
    body: EventUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await event_service.update_event(
        session,
        principal=auth.principal,
        event_id=event_id,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@events_router.post("/{event_id}/submit", summary="Submit an event for moderation")
async def submit_event(
    event_id: uuid.UUID,
    body: EventVersionRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    data = await event_service.submit_event(
        session,
        principal=auth.principal,
        event_id=event_id,
        ctx=auth.ctx,
        version=version,
    )
    return success(data)


@events_router.post("/{event_id}/cancel", summary="Cancel a published event")
async def cancel_event(
    event_id: uuid.UUID,
    body: EventVersionRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    data = await event_service.cancel_event(
        session,
        principal=auth.principal,
        event_id=event_id,
        ctx=auth.ctx,
        version=version,
    )
    return success(data)


@events_router.delete("/{event_id}", summary="Soft-delete / archive an event")
async def delete_event(
    event_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await event_service.delete_event(
        session,
        principal=auth.principal,
        event_id=event_id,
        ctx=auth.ctx,
    )
    return success({"status": "deleted"})


# --------------------------------------------------------------------------- #
# Student registration                                                         #
# --------------------------------------------------------------------------- #


@events_router.post("/{event_id}/register", summary="Register for an event")
async def register(
    event_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await registration_service.register(
        session,
        principal=auth.principal,
        event_id=event_id,
        ctx=auth.ctx,
    )
    return success(data)


@events_router.delete("/{event_id}/register", summary="Cancel my registration")
async def cancel_registration(
    event_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await registration_service.cancel_registration(
        session,
        principal=auth.principal,
        event_id=event_id,
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Check-in + attendee list (organizer / university only)                       #
# --------------------------------------------------------------------------- #


@events_router.get("/{event_id}/registrations", summary="Attendee list (organizer/university)")
async def list_attendees(
    event_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await registration_service.list_attendees(
        session,
        principal=auth.principal,
        event_id=event_id,
    )
    return success(items, meta={"count": len(items)})


@events_router.post(
    "/{event_id}/registrations/{registration_id}/check-in",
    summary="Mark a registration as attended",
)
async def check_in(
    event_id: uuid.UUID,
    registration_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await registration_service.check_in(
        session,
        principal=auth.principal,
        event_id=event_id,
        registration_id=registration_id,
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# University moderation                                                         #
# --------------------------------------------------------------------------- #


@admin_events_router.get("", summary="Event moderation queue (university only)")
async def moderation_queue(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    event_status: str | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=None),
) -> dict:
    items, total = await event_moderation_service.list_moderation_queue(
        session,
        principal=auth.principal,
        status=event_status,
        limit=limit,
    )
    return success(items, meta={"count": total})


@admin_events_router.post("/{event_id}/approve", summary="Approve + publish an event")
async def approve_event(
    event_id: uuid.UUID,
    body: EventApproveRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    version = body.version if body else None
    note = body.note if body else None
    data = await event_moderation_service.approve_event(
        session,
        principal=auth.principal,
        event_id=event_id,
        version=version,
        note=note,
        ctx=auth.ctx,
    )
    return success(data)


@admin_events_router.post("/{event_id}/reject", summary="Reject an event")
async def reject_event(
    event_id: uuid.UUID,
    body: EventModerationRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await event_moderation_service.reject_event(
        session,
        principal=auth.principal,
        event_id=event_id,
        reason=body.reason,
        reason_code=body.reason_code,
        version=body.version,
        ctx=auth.ctx,
    )
    return success(data)


@admin_events_router.post("/{event_id}/claim", summary="Claim an event for review")
async def claim_event(
    event_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await event_moderation_service.claim_event(
        session,
        principal=auth.principal,
        event_id=event_id,
        ctx=auth.ctx,
    )
    return success(data)


@admin_events_router.post(
    "/{event_id}/escalate", summary="Escalate an event to the human review queue"
)
async def escalate_event(
    event_id: uuid.UUID,
    body: EventEscalateRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    reason_code = body.reason_code if body else None
    note = body.note if body else None
    data = await event_moderation_service.escalate_event(
        session,
        principal=auth.principal,
        event_id=event_id,
        reason_code=reason_code,
        note=note,
        ctx=auth.ctx,
    )
    return success(data)


@admin_events_router.post("/bulk-approve", summary="Approve multiple events")
async def bulk_approve_events(
    body: EventBulkApproveRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    results = await event_moderation_service.bulk_approve_events(
        session,
        principal=auth.principal,
        event_ids=body.event_ids,
        ctx=auth.ctx,
    )
    return success(results)


@admin_events_router.post("/bulk-reject", summary="Reject multiple events")
async def bulk_reject_events(
    body: EventBulkRejectRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = [item.model_dump() for item in body.items]
    results = await event_moderation_service.bulk_reject_events(
        session,
        principal=auth.principal,
        items=items,
        ctx=auth.ctx,
    )
    return success(results)
