"""Mock Interview HTTP router — student-facing. HTTP only, no business logic.

Every endpoint requires an authenticated principal; the application layer gates
student ownership (partners are denied there, guests get 401 here). The turn
endpoint streams Server-Sent Events like the AI chat endpoint.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.realtime import live_relay
from app.core.config import get_settings
from app.core.db import get_db_session, get_sessionmaker
from app.modules.auth.api.deps import (
    CurrentAuth,
    get_current_auth,
    principal_from_access_token,
)
from app.modules.auth.application.context import RequestContext
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
from app.shared.permissions import Principal
from app.shared.responses import success

logger = logging.getLogger(__name__)

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


@router.websocket("/sessions/{session_id}/live")
async def live_interview(websocket: WebSocket, session_id: uuid.UUID) -> None:
    """TRUE realtime voice interview — server-mediated Gemini Live relay.

    The browser cannot hold the Google service-account credential, so the server
    brokers the Live socket and relays audio both ways. The access token is a
    query param (``?token=``) because browsers cannot set the Authorization
    header on a WS handshake; owner scoping + the grounded interviewer prompt are
    resolved in the application layer before any audio flows. Transcript turns
    are persisted after the session for the coaching report.
    """

    if not live_relay.live_relay_enabled():
        await websocket.close(code=1011, reason="unavailable")
        return
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=1008, reason="auth")
        return
    await websocket.accept()

    maker = get_sessionmaker()
    # 1) Authenticate + build the grounded context + energy precheck (short DB
    # session, then release). The precheck runs BEFORE the Live socket is opened.
    refuse_reason: str | None = None
    try:
        async with maker() as db:
            principal = await principal_from_access_token(db, token)
            ctx = await session_service.build_live_relay_context(
                db, principal=principal, session_id=session_id
            )
            refuse_reason = await _relay_precheck(db, principal=principal)
    except AppError as exc:
        await websocket.send_json({"type": "error", "reason": exc.code})
        await websocket.close(code=1008)
        return
    except Exception:
        logger.warning("live_interview.init_failed", exc_info=True)
        await websocket.send_json({"type": "error", "reason": "init_failed"})
        await websocket.close(code=1011)
        return

    if refuse_reason is not None:
        # Energy exhausted: refuse with a leak-safe reason and let the client
        # degrade to the turn-based voice / text tier.
        await _try_send(websocket, {"type": "error", "reason": refuse_reason})
        await websocket.close(code=1008)
        return

    request_ctx = RequestContext(
        ip=websocket.client.host if websocket.client else None,
        user_agent=websocket.headers.get("user-agent"),
    )
    # A per-turn counter (mutable box so the closure can bump it) drives an
    # idempotent per-turn energy charge key.
    turn_counter = {"seq": 0}

    async def _on_turn(batch: list[dict[str, str]]) -> None:
        """Persist + meter the just-completed turn(s) in a SHORT DB session.

        Called on every ``turn_complete`` (and once on close for the tail), so a
        crash mid-interview no longer loses the transcript. Best-effort: a
        persistence/accounting failure is logged but never breaks the relay.
        """

        turn_counter["seq"] += 1
        seq = turn_counter["seq"]
        try:
            async with maker() as db2:
                # ``record_turns`` re-runs the injection guard on candidate text,
                # caps the running total, and commits internally.
                await session_service.record_turns(
                    db2,
                    principal=principal,
                    session_id=session_id,
                    turns_in=batch,
                    ctx=request_ctx,
                )
                interviewer_chars = sum(
                    len(t.get("text") or "")
                    for t in batch
                    if t.get("speaker") == "interviewer"
                )
                candidate_chars = sum(
                    len(t.get("text") or "")
                    for t in batch
                    if t.get("speaker") != "interviewer"
                )
                if interviewer_chars:
                    # Ops telemetry (metadata only) + masked energy settlement for
                    # the realtime tier — previously the relay logged NOTHING.
                    from app.ai.observability.usage import log_ai_usage_async

                    await log_ai_usage_async(
                        db2,
                        task_type="mock_interview_realtime",
                        alias="interview_realtime",
                        success=True,
                        prompt_chars=candidate_chars,
                        completion_chars=interviewer_chars,
                        user_id=principal.user_id,
                        session_id=session_id,
                    )
                    await _settle_relay_energy(
                        db2, principal=principal, session_id=session_id, seq=seq
                    )
                    await db2.commit()
        except Exception:  # noqa: BLE001 - persistence/accounting is best-effort
            logger.warning("live_interview.turn_persist_failed", exc_info=True)

    # 2) Run the relay — NO DB session held during the (minutes-long) stream.
    # Turns are persisted incrementally through the ``_on_turn`` callback.
    try:
        await live_relay.run_interview_live(
            websocket,
            system_instruction=ctx["system_instruction"],
            voice=ctx["voice"],
            on_turn=_on_turn,
            max_seconds=int(ctx["max_seconds"]),
        )
    except WebSocketDisconnect:
        pass
    except live_relay.LiveRelayUnavailable:
        await _try_send(websocket, {"type": "error", "reason": "unavailable"})
    except Exception:
        logger.warning("live_interview.relay_failed", exc_info=True)
        await _try_send(websocket, {"type": "error", "reason": "relay_failed"})

    try:
        await websocket.close()
    except Exception:
        pass


async def _try_send(websocket: WebSocket, payload: dict) -> None:
    """Send a JSON frame, swallowing errors if the socket is already gone."""

    try:
        await websocket.send_json(payload)
    except Exception:
        pass


async def _relay_precheck(db: AsyncSession, *, principal: Principal) -> str | None:
    """Best-effort energy/enablement precheck BEFORE opening the Live socket.

    Returns a leak-safe reason string when the relay must be refused (the
    student's masked energy account is exhausted), else ``None``. Never raises for
    a non-decision error — a transient billing hiccup must not block the
    interview; the per-turn settlement still records real usage once it runs.
    """

    if principal.user_id is None:
        return None
    try:
        from app.modules.billing.application import energy_service

        if await energy_service.is_exhausted(
            db, scope_type=energy_service.ACCOUNT_SCOPE_USER, scope_id=principal.user_id
        ):
            return "energy_exhausted"
    except Exception:  # noqa: BLE001 - precheck is best-effort
        logger.debug("live_interview.precheck_skipped", exc_info=True)
    return None


async def _settle_relay_energy(
    db: AsyncSession, *, principal: Principal, session_id: uuid.UUID, seq: int
) -> None:
    """Best-effort energy settlement for one realtime interviewer turn (turn count).

    Idempotent on ``(session, "realtime", seq)`` so a re-run never double charges.
    Never raises — accounting must not break the live interview. Degrades to a
    no-op when billing is unavailable (the ``ai_usage_log`` row still exists)."""

    if principal.user_id is None:
        return
    try:
        from app.ai.observability.billable_usage import (
            FEATURE_INTERVIEW_SIM,
            PERSONA_STUDENT,
            RESULT_SUCCESS,
            SCOPE_USER,
            UsageContext,
            make_idempotency_key,
        )
        from app.modules.billing.application.energy_service import charge

        ctx = UsageContext(
            actor_persona=PERSONA_STUDENT,
            feature_key=FEATURE_INTERVIEW_SIM,
            task_type="mock_interview_realtime",
            billing_scope=SCOPE_USER,
            actor_user_id=principal.user_id,
            session_id=session_id,
            resource_type="mock_interview_session",
            resource_id=session_id,
            idempotency_key=make_idempotency_key(
                FEATURE_INTERVIEW_SIM, session_id, "realtime", seq
            ),
        )
        await charge(db, ctx=ctx, result_status=RESULT_SUCCESS, base_units=1)
    except Exception:  # noqa: BLE001 - accounting must never break the interview
        logger.debug("live_interview.energy_settle_skipped", exc_info=True)
