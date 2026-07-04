"""AI assistant HTTP router.

Endpoints:
  POST   /ai/chat/sessions                               Create a new chat session
  GET    /ai/chat/sessions                               List the caller's sessions (non-archived)
  GET    /ai/chat/sessions/{id}/messages                 List messages in a session
  POST   /ai/chat/sessions/{id}/messages                 Send a message (runs LLM + tools)
  GET    /ai/chat/sessions/{id}/messages/stream          Stream a message response via SSE
  POST   /ai/chat/sessions/{id}/messages/{msg_id}/confirm  Confirm a pending tool_call message
  DELETE /ai/chat/sessions/{id}                          Archive a session

RBAC: all endpoints require authentication. Students and partners can use the
assistant; guests get 401.

SSE streaming: The /stream endpoint returns ``text/event-stream`` with events:
  data: {"type":"token","text":"..."}
  data: {"type":"tool_call","name":"...","args":{}}
  data: {"type":"tool_result","name":"...","ok":true}
  data: {"type":"done","message":{...}}
  data: {"type":"error","code":"..."}
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.ai_assistant.api.schemas import SendMessageRequest
from app.modules.ai_assistant.application import chat_service, usage_service
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.shared.responses import success

router = APIRouter(prefix="/ai/chat", tags=["ai-assistant"])

# Separate prefix: usage meter is not a chat-session resource.
usage_router = APIRouter(prefix="/ai/usage", tags=["ai-assistant"])


@usage_router.get(
    "/me",
    summary="My AI usage today (request count vs daily allowance)",
)
async def my_ai_usage(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await usage_service.my_usage(session, principal=auth.principal)
    return success(data)


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new AI assistant chat session",
)
async def create_session(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await chat_service.create_session(session, principal=auth.principal)
    return success(data)


@router.get(
    "/sessions",
    summary="List the caller's recent chat sessions",
)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=50),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await chat_service.list_sessions(session, principal=auth.principal, limit=limit)
    return success(data)


@router.get(
    "/sessions/{session_id}/messages",
    summary="List messages in a chat session (owner only)",
)
async def get_messages(
    session_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await chat_service.get_session_messages(
        session, principal=auth.principal, session_id=session_id, limit=limit
    )
    return success(data)


@router.post(
    "/sessions/{session_id}/messages",
    summary="Send a user message; receive the assistant's reply",
)
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await chat_service.send_message(
        session,
        principal=auth.principal,
        session_id=session_id,
        text=body.text,
    )
    return success(data)


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="Send a user message and stream the assistant reply via SSE",
    response_class=StreamingResponse,
)
async def stream_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    """Server-Sent Events stream for a single assistant turn.

    The response is ``text/event-stream``. Each SSE event carries a JSON
    payload; clients parse ``event.data`` as JSON. Stream ends with a ``done``
    event whose ``message`` field mirrors the standard POST response. Provider,
    model, token counts, and internal metadata are never included.
    """

    async def _generate() -> AsyncGenerator[str, None]:
        try:
            async for event in chat_service.stream_message(
                session,
                principal=auth.principal,
                session_id=session_id,
                text=body.text,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'code': 'stream_failed'})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/sessions/{session_id}/messages/{message_id}/confirm",
    summary="Confirm a pending tool_call and execute it",
)
async def confirm_tool_action(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Execute a ``confirmation_required`` tool that was paused for user review.

    The frontend calls this after the user taps "Confirm" on a tool confirmation
    card. The message identified by ``message_id`` must be owned by the caller,
    belong to ``session_id``, and have ``requires_confirmation=True``. Executing
    the action is idempotent — a second confirm on the same message returns the
    cached result.
    """
    data = await chat_service.confirm_tool_action(
        session,
        principal=auth.principal,
        session_id=session_id,
        message_id=message_id,
    )
    return success(data)


@router.delete(
    "/sessions/{session_id}",
    summary="Archive (soft-delete) a chat session",
)
async def archive_session(
    session_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await chat_service.archive_session(
        session, principal=auth.principal, session_id=session_id
    )
    return success(data)
