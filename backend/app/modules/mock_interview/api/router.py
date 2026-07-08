"""Mock Interview HTTP router — student-facing. HTTP only, no business logic.

Every endpoint requires an authenticated principal; the application layer gates
student ownership (partners are denied there, guests get 401 here). The turn
endpoint streams Server-Sent Events like the AI chat endpoint.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.mock_interview.api.schemas import (
    CreateSessionRequest,
    EndSessionRequest,
    RecordTurnsRequest,
    ShareRequest,
    TurnRequest,
)
from app.modules.mock_interview.application import session_service
from app.shared.exceptions import AppError
from app.shared.responses import success

router = APIRouter(prefix="/mock-interview", tags=["mock-interview"])


@router.get("/prep", summary="Pre-session CV picker for a job")
async def prep(
    job_id: uuid.UUID = Query(...),
    locale: str = Query("vi", max_length=8),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await session_service.prep(
        session, principal=auth.principal, job_id=job_id, locale=locale
    )
    return success(data)


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Start a mock-interview session",
)
async def create_session(
    body: CreateSessionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await session_service.create_session(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        job_id=body.job_id,
        cv_id=body.cv_id,
        modality=body.modality,
        locale=body.locale,
    )
    return success(data)


@router.post(
    "/sessions/{session_id}/turns/stream",
    response_class=StreamingResponse,
    summary="Answer + stream the interviewer's next turn (SSE)",
)
async def stream_turn(
    session_id: uuid.UUID,
    body: TurnRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    # Pre-flight so 404/409 surface as real status codes before the 200 stream.
    await session_service.assert_turnable(
        session, principal=auth.principal, session_id=session_id
    )

    async def _generate() -> AsyncGenerator[str, None]:
        try:
            async for event in session_service.stream_turn(
                session,
                principal=auth.principal,
                session_id=session_id,
                answer=body.answer,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except AppError as exc:
            yield f"data: {json.dumps({'type': 'error', 'code': exc.code})}\n\n"
        except Exception:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'code': 'stream_failed'})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/sessions/{session_id}/turns",
    summary="Flush realtime transcript turns (Tier V2 resilience)",
)
async def record_turns(
    session_id: uuid.UUID,
    body: RecordTurnsRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await session_service.record_turns(
        session,
        principal=auth.principal,
        session_id=session_id,
        turns_in=[t.model_dump() for t in body.turns],
    )
    return success(data)


@router.post("/sessions/{session_id}/end", summary="End session + coaching report")
async def end_session(
    session_id: uuid.UUID,
    body: EndSessionRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await session_service.end_session(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        session_id=session_id,
        duration_seconds=body.duration_seconds,
        turns_in=[t.model_dump() for t in body.turns] if body.turns else None,
    )
    return success(data)


@router.post("/sessions/{session_id}/abort", summary="Abort an active session")
async def abort_session(
    session_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await session_service.abort_session(
        session, principal=auth.principal, ctx=auth.ctx, session_id=session_id
    )
    return success(data)


@router.post("/sessions/{session_id}/share", summary="Toggle share-for-improvement")
async def share_session(
    session_id: uuid.UUID,
    body: ShareRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await session_service.set_share_opt_in(
        session,
        principal=auth.principal,
        ctx=auth.ctx,
        session_id=session_id,
        opt_in=body.opt_in,
    )
    return success(data)


@router.delete("/sessions/{session_id}", summary="Delete own session (privacy)")
async def delete_session(
    session_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await session_service.delete_session(
        session, principal=auth.principal, ctx=auth.ctx, session_id=session_id
    )
    return success({"deleted": True})


@router.get("/sessions", summary="List my mock-interview sessions")
async def list_sessions(
    limit: int = Query(20, ge=1, le=50),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await session_service.list_sessions(
        session, principal=auth.principal, limit=limit
    )
    return success(data)


@router.get("/sessions/{session_id}", summary="Get one session (transcript + report)")
async def get_session(
    session_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await session_service.get_session(
        session, principal=auth.principal, session_id=session_id
    )
    return success(data)
