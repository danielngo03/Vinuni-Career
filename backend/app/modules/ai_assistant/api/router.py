"""AI assistant HTTP router.

Endpoints:
  POST   /ai/chat/sessions                               Create a new chat session
  GET    /ai/chat/sessions                               List the caller's sessions (non-archived)
  PATCH  /ai/chat/sessions/{id}                          Rename a session
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

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.ai_assistant.api.schemas import (
    ConfirmActionRequest,
    EditMessageRequest,
    SendMessageRequest,
    UpdateSessionRequest,
)
from app.modules.ai_assistant.application import (
    attachment_service,
    chat_exports,
    chat_service,
    conversation_service,
    usage_service,
)
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.shared.exceptions import ValidationFailedError
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


@usage_router.get(
    "/summary",
    summary="My AI usage detail (windows, reset timing, per-feature breakdown, recent activity)",
)
async def my_ai_usage_summary(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Powers the billing/usage screen's AI-usage panel.

    Returns the same day/week quota windows as ``/me`` plus reset timestamps, a
    per-feature request breakdown, and a recent-activity list over the last 30
    days. Never exposes provider/model names, aliases, tokens, cost, or latency.
    """
    data = await usage_service.my_usage_detail(session, principal=auth.principal)
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


@router.patch(
    "/sessions/{session_id}",
    summary="Rename a chat session",
)
async def rename_session(
    session_id: uuid.UUID,
    body: UpdateSessionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await chat_service.rename_session(
        session,
        principal=auth.principal,
        session_id=session_id,
        title=body.title,
    )
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
    summary="Confirm or cancel a pending tool_call",
)
async def confirm_tool_action(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    body: ConfirmActionRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Resolve a ``confirmation_required`` tool that was paused for user review.

    The frontend calls this after the user taps "Confirm" or "Cancel" on a tool
    confirmation card. The message identified by ``message_id`` must be owned by
    the caller, belong to ``session_id``, and have ``requires_confirmation=True``.

    Body ``{"decision": "confirm"|"cancel"}``; an omitted body means confirm
    (backward compatible). Confirm executes the tool (idempotent — a second
    confirm returns the cached result). Cancel executes NOTHING, resolves the
    card, and returns ``{"confirmed": false, "reply": <ack message>}``.
    """
    decision = body.decision if body is not None else "confirm"
    if decision == "cancel":
        data = await conversation_service.cancel_tool_action(
            session,
            principal=auth.principal,
            session_id=session_id,
            message_id=message_id,
        )
        return success(data)
    data = await conversation_service.confirm_tool_action_normalized(
        session,
        principal=auth.principal,
        session_id=session_id,
        message_id=message_id,
    )
    return success(data)


@router.patch(
    "/sessions/{session_id}/messages/{message_id}",
    summary="Edit a user message and replay the turn (owner only)",
)
async def edit_message(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    body: EditMessageRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Edit one of the caller's own USER messages.

    Sets ``edited_at``, soft-deletes every later message in the thread, and
    re-runs the assistant turn through the same pipeline as send_message.
    Returns ``{"reply": <message dict>}``; the client should refetch the thread
    (GET messages excludes soft-deleted rows).
    """
    data = await conversation_service.edit_message(
        session,
        principal=auth.principal,
        session_id=session_id,
        message_id=message_id,
        text=body.text,
    )
    return success(data)


@router.post(
    "/sessions/{session_id}/messages/{message_id}/regenerate",
    summary="Regenerate the assistant reply for the last user message (owner only)",
)
async def regenerate_reply(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Redo the assistant reply for the thread's LAST user message.

    ``message_id`` may be that user message or the assistant message being
    redone (both validated as the tail of the thread). The stale reply chain is
    soft-deleted and a fresh turn runs. Returns ``{"reply": <message dict>}``.
    """
    data = await conversation_service.regenerate_reply(
        session,
        principal=auth.principal,
        session_id=session_id,
        message_id=message_id,
    )
    return success(data)


@router.get(
    "/exports/{export_id}",
    summary="Download an assistant-generated export file (owner-only, RBAC + expiry)",
)
async def download_export(
    export_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Return the bytes of a file the assistant generated for the caller.

    Owner-scoped and expiry-checked in ``chat_exports.fetch_export``; the raw
    storage/bytes are never otherwise exposed (only the URL is handed out).
    """
    row = await chat_exports.fetch_export(session, auth.principal, export_id)
    return Response(
        content=row.content,
        media_type=row.mime,
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )


@router.post(
    "/sessions/{session_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    summary="Attach a file/image to a chat session for AI analysis (owner only)",
)
async def upload_attachment(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Store an owner-scoped chat attachment; analysis is a separate metered tool.

    Session ownership is enforced inside ``attachment_service.upload_attachment``
    (404 on a non-owned session). Rejects blank/oversized/unsupported/
    security-failed files with a user-safe error; raw bytes are never returned.
    """
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes:
        raise ValidationFailedError(
            "Tệp quá lớn. Hãy nén hoặc chia nhỏ tệp rồi tải lại.",
            details={"reason": "file_too_large"},
        )
    result = await attachment_service.upload_attachment(
        session,
        principal=auth.principal,
        session_id=session_id,
        filename=file.filename or "upload",
        data=data,
        content_type=file.content_type,
    )
    return success(result)


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
