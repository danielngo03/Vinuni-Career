"""Messaging HTTP routes (ADR-0012 §7).

Routers are HTTP-only: validate, delegate to the services (which enforce RBAC +
rate limit + audit + tenant isolation + transactions + anonymity masking), and
shape the response envelope. No business logic here. NO WebSocket in this slice —
the unread badge is a polling endpoint mirroring the notification bell.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.messaging.api.schemas import (
    CreateThreadBody,
    MuteBody,
    ReportBody,
    SendMessageBody,
)
from app.modules.messaging.application import message_service, thread_service
from app.shared.responses import paginated, success

router = APIRouter(prefix="/messaging", tags=["messaging"])


@router.get("/threads", summary="My threads (participant), masked + unread")
async def list_threads(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, next_cursor, page_limit = await thread_service.list_mine(
        session, principal=auth.principal, cursor=cursor, limit=limit
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@router.post("/threads", status_code=status.HTTP_201_CREATED, summary="Create a thread")
async def create_thread(
    body: CreateThreadBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await thread_service.create_thread(
        session,
        principal=auth.principal,
        kind=body.kind,
        context_type=body.context_type,
        context_id=body.context_id,
        recipient_ids=body.recipient_ids,
        subject=body.subject,
        first_message=body.first_message,
        ctx=auth.ctx,
    )
    return success(data)


@router.get("/unread-count", summary="Badge sum across my non-muted threads (polling)")
async def unread_count(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    count = await message_service.unread_count(session, principal=auth.principal)
    return success({"unread_count": count})


@router.get("/threads/{thread_id}", summary="Thread detail (participant/moderator)")
async def get_thread(
    thread_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await thread_service.get_thread(session, principal=auth.principal, thread_id=thread_id)
    return success(data)


@router.get("/threads/{thread_id}/messages", summary="Messages in a thread (cursor)")
async def list_messages(
    thread_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    after: str | None = Query(default=None),
    limit: int | None = Query(default=None),
) -> dict:
    items, next_cursor, page_limit = await message_service.list_messages(
        session,
        principal=auth.principal,
        thread_id=thread_id,
        after=after,
        limit=limit,
    )
    return paginated(items, next_cursor=next_cursor, limit=page_limit)


@router.post(
    "/threads/{thread_id}/messages",
    status_code=status.HTTP_201_CREATED,
    summary="Send a message (re-check permission + rate limit + idempotent)",
)
async def send_message(
    thread_id: uuid.UUID,
    body: SendMessageBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await message_service.send_message(
        session,
        principal=auth.principal,
        thread_id=thread_id,
        body=body.body,
        reply_to_id=body.reply_to_id,
        client_dedupe_key=body.client_dedupe_key,
        ctx=auth.ctx,
    )
    return success(data)


@router.post("/threads/{thread_id}/read", summary="Set my last_read_at = now")
async def mark_read(
    thread_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await message_service.mark_read(session, principal=auth.principal, thread_id=thread_id)
    return success(data)


@router.post("/threads/{thread_id}/mute", summary="Mute/unmute a thread")
async def set_mute(
    thread_id: uuid.UUID,
    body: MuteBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await message_service.set_mute(
        session, principal=auth.principal, thread_id=thread_id, muted=body.muted
    )
    return success(data)


@router.delete(
    "/threads/{thread_id}/messages/{message_id}",
    summary="Soft-delete own (<=10min) | university any | system never",
)
async def delete_message(
    thread_id: uuid.UUID,
    message_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await message_service.delete_message(
        session,
        principal=auth.principal,
        thread_id=thread_id,
        message_id=message_id,
        ctx=auth.ctx,
    )
    return success(data)


@router.post("/threads/{thread_id}/report", summary="Report a thread to university")
async def report_thread(
    thread_id: uuid.UUID,
    body: ReportBody,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await message_service.report_thread(
        session,
        principal=auth.principal,
        thread_id=thread_id,
        reason=body.reason,
        ctx=auth.ctx,
    )
    return success(data)
