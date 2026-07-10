"""Mock Interview HTTP router — student-facing. HTTP only, no business logic.

Every endpoint requires an authenticated principal; the application layer gates
student ownership (partners are denied there, guests get 401 here). The turn
endpoint streams Server-Sent Events like the AI chat endpoint.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.mock_interview.api.schemas import (
    CreateSessionRequest,
    EndSessionRequest,
    RecordTurnsRequest,
    ShareRequest,
    TtsRequest,
    TurnRequest,
)
from app.modules.mock_interview.application import progress_service, session_service
from app.shared.exceptions import AppError, ValidationFailedError
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


@router.get("/progress", summary="My progress across interviews (recurring themes)")
async def progress(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await progress_service.build_progress(session, principal=auth.principal)
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
        ctx=auth.ctx,
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


@router.post(
    "/sessions/{session_id}/tts",
    summary="Synthesize interviewer text to speech (server voice tier)",
)
async def tts(
    session_id: uuid.UUID,
    body: TtsRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Return WAV audio for the interviewer's line. Owner-scoped + metered; the
    body is bounded and the audio is never persisted."""

    audio, mime = await session_service.synthesize_turn_audio(
        session,
        principal=auth.principal,
        session_id=session_id,
        text=body.text,
        voice=body.voice,
    )
    return Response(
        content=audio,
        media_type=mime,
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/sessions/{session_id}/stt",
    summary="Transcribe the student's spoken answer (server voice tier)",
)
async def stt(
    session_id: uuid.UUID,
    audio: UploadFile = File(...),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Transcribe uploaded answer audio to text. Owner-scoped + metered; the
    upload is bounded and never persisted. The transcript is returned for the
    student to review/submit as the turn answer — never auto-submitted."""

    settings = get_settings()
    raw = await audio.read()
    max_bytes = int(getattr(settings, "ai_speech_max_audio_bytes", 8 * 1024 * 1024))
    if not raw:
        raise ValidationFailedError(
            "Không có dữ liệu âm thanh.", details={"reason": "EMPTY_AUDIO"}
        )
    if len(raw) > max_bytes:
        raise ValidationFailedError(
            "Đoạn ghi âm quá dài. Hãy trả lời ngắn gọn hơn.",
            details={"reason": "AUDIO_TOO_LARGE"},
        )
    mime = audio.content_type or "audio/webm"
    transcript = await session_service.transcribe_answer_audio(
        session,
        principal=auth.principal,
        session_id=session_id,
        audio=raw,
        mime_type=mime,
    )
    return success({"transcript": transcript})
