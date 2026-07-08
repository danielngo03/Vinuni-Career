"""Mock-interview use cases — RBAC, quota, caps, transactions, audit.

Owns everything transactional. The LLM adapters (``conversation_service``,
``report_service``) and grounding/realtime helpers are called from here; this is
the only layer that persists turns, enforces permissions, and writes audit +
analytics. Every session/turn query is hard-scoped to the owner; partners never
reach this module (no route/facade), and only a platform superadmin may read
another user's session (support), never write it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.realtime import mint_session
from app.ai.gateway.realtime.providers import RealtimeUnavailableError
from app.ai.prompts.mock_interview import v1 as prompts
from app.ai.safety.input_guard import redact_pii, sanitize_instruction
from app.core.config import get_settings
from app.modules.analytics.application import ingestion_service
from app.modules.mock_interview.api import presenters
from app.modules.mock_interview.application import (
    caps,
    conversation_service,
    grounding_service,
    report_service,
)
from app.modules.mock_interview.domain.models import (
    MODALITIES,
    MODALITY_REALTIME,
    MODALITY_VOICE,
    SPEAKER_CANDIDATE,
    SPEAKER_INTERVIEWER,
    STATUS_ABORTED,
    STATUS_ACTIVE,
    STATUS_COMPLETED,
    MockInterviewSession,
    MockInterviewTurn,
)
from app.modules.mock_interview.infrastructure import repository as repo
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal

_ANALYTICS_AGGREGATE = "mock_interview_session"
_MODERATION_SOURCE = "mock_interview_safety"


# --------------------------------------------------------------------------- #
# RBAC + helpers                                                               #
# --------------------------------------------------------------------------- #
def _require_student(principal: Principal) -> uuid.UUID:
    """Only students own mock interviews. Superadmin allowed for support."""

    if principal.user_id is None:
        raise AuthRequiredError()
    if not principal.is_superadmin and principal.persona != "student":
        raise PermissionDeniedError(details={"reason": "student_only"})
    return principal.user_id


def _audit_ctx(principal: Principal, ctx: Any | None) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=getattr(ctx, "ip", None),
        user_agent=getattr(ctx, "user_agent", None),
    )


def _redacted(text: str) -> str:
    red, _ = redact_pii(text or "")
    return red


async def _record_event(
    session: AsyncSession, *, event_type: str, session_id: uuid.UUID, props: dict
) -> None:
    await ingestion_service.record_event_safe(
        session,
        event_type=event_type,
        aggregate_type=_ANALYTICS_AGGREGATE,
        aggregate_id=session_id,
        actor_type="student",
        properties=props,
    )


# --------------------------------------------------------------------------- #
# Pre-session                                                                  #
# --------------------------------------------------------------------------- #
async def prep(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    locale: str = "vi",
) -> dict[str, Any]:
    _require_student(principal)
    return await grounding_service.build_prep(
        session, principal=principal, job_id=job_id, locale=locale
    )


# --------------------------------------------------------------------------- #
# Create                                                                       #
# --------------------------------------------------------------------------- #
async def create_session(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any | None,
    job_id: uuid.UUID,
    cv_id: uuid.UUID | None,
    modality: str = MODALITY_VOICE,
    locale: str = "vi",
) -> dict[str, Any]:
    user_id = _require_student(principal)
    modality = modality if modality in MODALITIES else MODALITY_VOICE
    locale = (locale or "vi")[:8]

    # 1) Validate + build grounding (job public + CV owned/ready). No LLM cost.
    built = await grounding_service.build_grounding(
        session, principal=principal, job_id=job_id, cv_id=cv_id, locale=locale
    )
    grounding = built["grounding"]
    chosen_cv_id = built["cv_id"]

    now = datetime.now(tz=UTC)
    # 2) Auto-recover abandoned sessions so a stuck/closed tab never blocks the
    # student forever (a genuinely concurrent session, started recently, still
    # blocks — only sessions older than the hard cap + grace are expired).
    await repo.expire_stale_active(
        session,
        user_id=user_id,
        cutoff=now - timedelta(seconds=caps.MAX_SESSION_SECONDS + 300),
        now=now,
    )

    # 3) Concurrency: one live session at a time.
    if await repo.count_active(session, user_id=user_id) >= caps.MAX_CONCURRENT_PER_USER:
        raise ConflictError(
            "Bạn đang có một buổi phỏng vấn thử chưa kết thúc.",
            details={"reason": "ACTIVE_SESSION_EXISTS"},
        )

    # 4) Session caps (daily / weekly) — count sessions started in the window.
    _enforce_session_caps(await _session_counts(session, user_id=user_id, now=now))

    # 4) Weekly AI request quota (shared platform cap).
    from app.modules.ai_assistant.application import usage_service

    await usage_service.enforce_quota(session, principal=principal)

    # 5) Persist the session row (active).
    row = MockInterviewSession(
        user_id=user_id,
        job_id=job_id,
        cv_profile_id=uuid.UUID(chosen_cv_id) if chosen_cv_id else None,
        locale=locale,
        modality=modality,
        status=STATUS_ACTIVE,
        started_at=now,
        grounding_json=grounding,
        grounding_version=int(grounding.get("grounding_version") or prompts.PROMPT_VERSION),
        model_ref=get_settings().ai_interview_model_alias,
        provider_ref="interview",
    )
    session.add(row)
    await session.flush()

    # 6) Opening interviewer turn (LLM; never raises — static fallback inside).
    opening_text = await conversation_service.generate_opening(
        session,
        user_id=user_id,
        grounding=grounding,
        target_questions=caps.DEFAULT_TARGET_QUESTIONS,
    )
    opening = MockInterviewTurn(
        session_id=row.id,
        seq=1,
        speaker=SPEAKER_INTERVIEWER,
        text=opening_text,
        text_redacted=_redacted(opening_text),
    )
    session.add(opening)
    row.question_count = 1

    # 7) Optional realtime (Tier V2). Falls back to browser voice on any failure.
    realtime: dict[str, Any] | None = None
    if modality == MODALITY_REALTIME:
        realtime = await _try_mint_realtime(session, row=row, grounding=grounding)
        if realtime is None:
            row.modality = MODALITY_VOICE
            modality = MODALITY_VOICE

    await write_audit(
        session,
        action="mock_interview.session_created",
        resource_type="mock_interview_session",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        after={"job_id": str(job_id), "modality": modality},
    )
    await _record_event(
        session,
        event_type="mock_interview.started",
        session_id=row.id,
        props={"modality": modality, "signal": built.get("signal") or "ok"},
    )
    await session.commit()

    return {
        "session_id": str(row.id),
        "modality": modality,
        "locale": locale,
        "cv_id": chosen_cv_id,
        "opening": {"seq": 1, "speaker": SPEAKER_INTERVIEWER, "text": opening_text},
        "caps": {
            "max_session_seconds": caps.MAX_SESSION_SECONDS,
            "max_questions": caps.MAX_QUESTIONS,
            "idle_timeout_seconds": caps.IDLE_TIMEOUT_SECONDS,
            "target_questions": caps.DEFAULT_TARGET_QUESTIONS,
        },
        "realtime": realtime,
    }


async def _try_mint_realtime(
    session: AsyncSession, *, row: MockInterviewSession, grounding: dict[str, Any]
) -> dict[str, Any] | None:
    instruction = prompts.build_conversation_system_prompt(
        grounding, target_questions=caps.DEFAULT_TARGET_QUESTIONS
    )
    try:
        descriptor = await mint_session(
            session,
            system_instruction=instruction,
            locale=row.locale,
            max_output_tokens=caps.QUESTION_MAX_TOKENS,
            user_id=row.user_id,
            session_id=row.id,
        )
    except RealtimeUnavailableError:
        return None
    row.provider_ref = descriptor.provider_ref
    row.model_ref = descriptor.model_ref
    return {
        "transport": descriptor.transport,
        "url": descriptor.url,
        "ephemeral_token": descriptor.ephemeral_token,
        "expires_at": descriptor.expires_at,
        "duration_cap_s": caps.MAX_SESSION_SECONDS,
        "turn_limit": caps.MAX_QUESTIONS,
    }


async def _session_counts(
    session: AsyncSession, *, user_id: uuid.UUID, now: datetime
) -> tuple[int, int]:
    daily = await repo.count_sessions_since(
        session, user_id=user_id, since=now - timedelta(days=1)
    )
    weekly = await repo.count_sessions_since(
        session, user_id=user_id, since=now - timedelta(days=7)
    )
    return daily, weekly


def _enforce_session_caps(counts: tuple[int, int]) -> None:
    from app.shared.exceptions import QuotaExceededError

    daily, weekly = counts
    if daily >= caps.DAILY_SESSION_CAP:
        raise QuotaExceededError(
            "Bạn đã đạt giới hạn số buổi phỏng vấn thử trong ngày.",
            details={"reason": "MOCK_INTERVIEW_SESSION_CAP", "scope": "daily"},
        )
    if weekly >= caps.WEEKLY_SESSION_CAP:
        raise QuotaExceededError(
            "Bạn đã đạt giới hạn số buổi phỏng vấn thử trong tuần.",
            details={"reason": "MOCK_INTERVIEW_SESSION_CAP", "scope": "weekly"},
        )


# --------------------------------------------------------------------------- #
# Turn (streaming, Tier V1 / text)                                             #
# --------------------------------------------------------------------------- #
async def _load_owned(
    session: AsyncSession, *, principal: Principal, session_id: uuid.UUID
) -> MockInterviewSession:
    row = await repo.get_session(
        session, session_id=session_id, user_id=principal.user_id
    )
    if row is None:
        raise ResourceNotFoundError()
    return row


async def assert_turnable(
    session: AsyncSession, *, principal: Principal, session_id: uuid.UUID
) -> None:
    """Pre-flight for the streaming endpoint so real HTTP status codes surface
    (404 not-owner, 409 not-active) BEFORE the 200 stream starts."""

    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)
    if row.status != STATUS_ACTIVE:
        raise ConflictError(
            "Buổi phỏng vấn này đã kết thúc.",
            details={"reason": "SESSION_NOT_ACTIVE"},
        )


async def stream_turn(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    answer: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Persist the candidate answer, then stream the next interviewer turn.

    Yields SSE-ready dicts: ``{"type":"token","text":...}`` chunks then a final
    ``{"type":"done", ...}``. Never leaves the candidate turn unsaved (it is
    committed before streaming the reply).
    """

    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)
    if row.status != STATUS_ACTIVE:
        raise ConflictError(
            "Buổi phỏng vấn này đã kết thúc.",
            details={"reason": "SESSION_NOT_ACTIVE"},
        )

    clean_answer, flags = sanitize_instruction((answer or "")[: caps.MAX_ANSWER_CHARS])
    candidate_text = clean_answer or (answer or "").strip()[: caps.MAX_ANSWER_CHARS]
    turns = await repo.load_turns(session, session_id=session_id)
    next_seq = (turns[-1].seq if turns else 0) + 1
    candidate_turn = MockInterviewTurn(
        session_id=row.id,
        seq=next_seq,
        speaker=SPEAKER_CANDIDATE,
        text=candidate_text,
        text_redacted=_redacted(candidate_text),
    )
    session.add(candidate_turn)
    if "injection" in flags:
        row.flagged = True
    await session.commit()  # durability: candidate answer survives a dropped stream
    turns.append(candidate_turn)

    grounding = row.grounding_json or {}
    parts: list[str] = []
    async for chunk in conversation_service.stream_interviewer(
        session,
        user_id=row.user_id,
        grounding=grounding,
        turns=turns,
        target_questions=caps.DEFAULT_TARGET_QUESTIONS,
    ):
        parts.append(chunk)
        yield {"type": "token", "text": chunk}

    clean_text, ended = conversation_service.strip_end_marker("".join(parts))
    if not clean_text:
        clean_text = prompts.fallback_next_turn(grounding)
    iseq = next_seq + 1
    session.add(
        MockInterviewTurn(
            session_id=row.id,
            seq=iseq,
            speaker=SPEAKER_INTERVIEWER,
            text=clean_text,
            text_redacted=_redacted(clean_text),
        )
    )
    row.question_count = int(row.question_count or 0) + 1
    reached_end = (
        ended
        or row.question_count >= caps.DEFAULT_TARGET_QUESTIONS
        or iseq >= caps.MAX_TURNS_PERSISTED
    )
    await session.commit()
    yield {
        "type": "done",
        "seq": iseq,
        "text": clean_text,
        "question_count": row.question_count,
        "ended": reached_end,
    }


# --------------------------------------------------------------------------- #
# Realtime transcript flush (Tier V2 resilience)                              #
# --------------------------------------------------------------------------- #
async def record_turns(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    turns_in: list[dict[str, Any]],
) -> dict[str, Any]:
    """Append provider-produced transcript turns (realtime path). Owner + active."""

    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)
    if row.status != STATUS_ACTIVE:
        raise ConflictError(details={"reason": "SESSION_NOT_ACTIVE"})
    existing = await repo.load_turns(session, session_id=session_id)
    seq = existing[-1].seq if existing else 0
    added = 0
    for item in turns_in[: caps.MAX_TURNS_PERSISTED]:
        speaker = (
            SPEAKER_INTERVIEWER
            if str(item.get("speaker")) == SPEAKER_INTERVIEWER
            else SPEAKER_CANDIDATE
        )
        text = str(item.get("text") or "").strip()[: caps.MAX_ANSWER_CHARS]
        if not text:
            continue
        seq += 1
        session.add(
            MockInterviewTurn(
                session_id=row.id,
                seq=seq,
                speaker=speaker,
                text=text,
                text_redacted=_redacted(text),
            )
        )
        if speaker == SPEAKER_INTERVIEWER:
            row.question_count = int(row.question_count or 0) + 1
        added += 1
    await session.commit()
    return {"added": added, "question_count": row.question_count}


# --------------------------------------------------------------------------- #
# End (coaching report)                                                        #
# --------------------------------------------------------------------------- #
async def end_session(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any | None,
    session_id: uuid.UUID,
    duration_seconds: int | None = None,
    turns_in: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)

    # Idempotent: ending an already-completed session returns its stored detail.
    if row.status == STATUS_COMPLETED:
        turns = await repo.load_turns(session, session_id=session_id)
        return presenters.session_detail(row, turns)
    if row.status != STATUS_ACTIVE:
        raise ConflictError(details={"reason": "SESSION_NOT_ACTIVE"})

    if turns_in:
        await record_turns(
            session, principal=principal, session_id=session_id, turns_in=turns_in
        )

    turns = await repo.load_turns(session, session_id=session_id)
    grounding = row.grounding_json or {}
    transcript_lines = conversation_service.build_transcript_lines(turns)
    report = await report_service.generate_report(
        session,
        user_id=row.user_id,
        grounding=grounding,
        transcript_lines=transcript_lines,
    )

    now = datetime.now(tz=UTC)
    row.report_json = report
    row.status = STATUS_COMPLETED
    row.ended_at = now
    row.question_count = sum(
        1 for t in turns if t.speaker == SPEAKER_INTERVIEWER
    )
    row.duration_seconds = caps.clamp_duration(
        duration_seconds
        if duration_seconds is not None
        else int((now - _aware(row.started_at)).total_seconds())
    )

    if row.flagged:
        await _escalate_flagged(session, row=row)

    await write_audit(
        session,
        action="mock_interview.session_completed",
        resource_type="mock_interview_session",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        after={"duration_seconds": row.duration_seconds, "flagged": row.flagged},
    )
    await _record_event(
        session,
        event_type="mock_interview.completed",
        session_id=row.id,
        props={
            "modality": row.modality,
            "question_count": row.question_count,
            "flagged": bool(row.flagged),
            "is_fallback": bool(report.get("is_fallback")),
        },
    )
    await session.commit()
    return presenters.session_detail(row, turns)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _escalate_flagged(
    session: AsyncSession, *, row: MockInterviewSession
) -> None:
    """Send a flagged session to the moderation queue (metadata only)."""

    from app.modules.moderation.application import review_queue_service

    await review_queue_service.enqueue(
        session,
        source=_MODERATION_SOURCE,
        resource_type="mock_interview_session",
        resource_id=row.id,
        org_id=None,
        severity="low",
        findings={"reason": "input_guard_flag", "modality": row.modality},
    )
    await _record_event(
        session,
        event_type="mock_interview.flagged",
        session_id=row.id,
        props={"modality": row.modality},
    )


# --------------------------------------------------------------------------- #
# Abort / delete / share / read                                               #
# --------------------------------------------------------------------------- #
async def abort_session(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any | None,
    session_id: uuid.UUID,
) -> dict[str, Any]:
    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)
    if row.status == STATUS_ACTIVE:
        row.status = STATUS_ABORTED
        row.ended_at = datetime.now(tz=UTC)
        await write_audit(
            session,
            action="mock_interview.session_aborted",
            resource_type="mock_interview_session",
            resource_id=row.id,
            context=_audit_ctx(principal, ctx),
        )
        await session.commit()
    turns = await repo.load_turns(session, session_id=session_id)
    return presenters.session_detail(row, turns)


async def delete_session(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any | None,
    session_id: uuid.UUID,
) -> None:
    """A student may permanently delete their own session (privacy)."""

    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)
    await write_audit(
        session,
        action="mock_interview.session_deleted",
        resource_type="mock_interview_session",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
    )
    await session.delete(row)  # turns cascade
    await session.commit()


async def set_share_opt_in(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: Any | None,
    session_id: uuid.UUID,
    opt_in: bool,
) -> dict[str, Any]:
    """Toggle the student's consent to share a pseudonymized transcript.

    Mirrors the toggle into the compliance consent ledger so AI-ops can only pool
    a transcript when the student has actually opted in.
    """

    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)
    row.share_opt_in = bool(opt_in)
    if ctx is not None:
        from app.modules.compliance.application import consent_service
        from app.modules.compliance.domain.models import CONSENT_INTERVIEW_RECORDING

        try:
            await consent_service.set_mine(
                session,
                principal=principal,
                consent_type=CONSENT_INTERVIEW_RECORDING,
                granted=bool(opt_in),
                ctx=ctx,
            )
        except Exception:  # noqa: BLE001 - consent ledger is best-effort here
            pass
    await write_audit(
        session,
        action="mock_interview.share_opt_in_set",
        resource_type="mock_interview_session",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        after={"share_opt_in": row.share_opt_in},
    )
    await session.commit()
    turns = await repo.load_turns(session, session_id=session_id)
    return presenters.session_detail(row, turns)


async def list_sessions(
    session: AsyncSession, *, principal: Principal, limit: int = 20
) -> list[dict[str, Any]]:
    uid = _require_student(principal)
    rows = await repo.list_for_user(session, user_id=uid, limit=limit)
    return [presenters.session_summary(r) for r in rows]


async def get_session(
    session: AsyncSession, *, principal: Principal, session_id: uuid.UUID
) -> dict[str, Any]:
    _require_student(principal)
    # Owner-scoped; a superadmin may read any session for support.
    owner = None if principal.is_superadmin else principal.user_id
    row = await repo.get_session(session, session_id=session_id, user_id=owner)
    if row is None:
        raise ResourceNotFoundError()
    turns = await repo.load_turns(session, session_id=session_id)
    return presenters.session_detail(row, turns)
