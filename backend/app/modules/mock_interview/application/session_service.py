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

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.realtime import mint_session
from app.ai.gateway.realtime.providers import RealtimeUnavailableError
from app.ai.prompts.mock_interview import v1 as prompts
from app.ai.safety.input_guard import redact_pii, sanitize_instruction
from app.core.config import get_settings
from app.modules.analytics.application import ingestion_service
from app.modules.mock_interview.api import presenters
from app.modules.mock_interview.application import (
    analysis_service,
    caps,
    conversation_service,
    grounding_service,
    plan_service,
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
    AIUnavailableError,
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
    data = await grounding_service.build_prep(
        session, principal=principal, job_id=job_id, locale=locale
    )
    # Capability flag for the client: when true, the "voice" mode uses the
    # server Gemini speech tier (natural TTS + robust STT). When false, the
    # client falls back to browser-native speech or text. Leak-safe boolean —
    # no provider/model detail is exposed.
    from app.ai.gateway import speech
    from app.ai.gateway.realtime import live_relay

    # Two independent voice capabilities, both leak-safe booleans:
    #  - server_voice: turn-based Gemini STT+TTS around the text turn engine.
    #  - realtime_relay: true full-duplex Live voice over the server WS relay
    #    (preferred when available; the turn-based tier is the fallback).
    data["server_voice"] = speech.speech_enabled()
    data["realtime_relay"] = live_relay.live_relay_enabled()
    return data


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
    # A session cannot legitimately take a turn past MAX_SESSION_SECONDS (see
    # _assert_within_caps), so anything older than that + a short grace is
    # abandoned and can be recovered — the student is not blocked for 15 minutes.
    await repo.expire_stale_active(
        session,
        user_id=user_id,
        cutoff=now - timedelta(seconds=caps.MAX_SESSION_SECONDS + 120),
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

    # 5) TXN 1 — claim the single active slot FAST, BEFORE any model latency.
    # The partial unique index (uq_mock_interview_one_active_per_user) is the
    # authoritative concurrency guard: if two creates race past the count check
    # above, the second COMMIT trips IntegrityError here — BEFORE any planner /
    # opening LLM call is made. Committing now (instead of holding the row +
    # partial-unique lock across the planner+opening latency) mirrors how
    # ``stream_turn`` commits the candidate turn before streaming.
    session_row_id = uuid.uuid4()
    row = MockInterviewSession(
        id=session_row_id,
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
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            "Bạn đang có một buổi phỏng vấn thử chưa kết thúc.",
            details={"reason": "ACTIVE_SESSION_EXISTS"},
        ) from exc

    # 6) PLANNER — ONE strong-model call, FROZEN on the row and reused every turn
    # (deterministic fallback inside; never blocks create). No txn/lock held.
    plan = await plan_service.build_plan(
        session, grounding=grounding, user_id=user_id, session_id=session_row_id
    )
    coverage = plan_service.init_coverage(
        plan, difficulty=grounding.get("difficulty")
    )
    opening_text = str(plan.get("opening") or "") or prompts.fallback_first_turn(grounding)
    # The opening is a greeting + first question. Attribute it to a competency
    # ONLY on a real keyword match (no forced target) so a generic "introduce
    # yourself" greeting does not consume a competency slot.
    coverage = plan_service.record_interviewer_question(
        coverage, plan, question_text=opening_text, seq=1, targeted_id=None
    )

    # 7) TXN 2 — persist the frozen plan + coverage + opening turn (short txn).
    opening = MockInterviewTurn(
        session_id=session_row_id,
        seq=1,
        speaker=SPEAKER_INTERVIEWER,
        text=opening_text,
        text_redacted=_redacted(opening_text),
    )
    session.add(opening)
    row.plan_json = plan
    row.plan_version = int(plan.get("plan_version") or prompts.PLAN_VERSION)
    row.coverage_json = coverage
    row.question_count = 1

    # 8) Optional realtime (Tier V2). Falls back to browser voice on any failure.
    realtime: dict[str, Any] | None = None
    if modality == MODALITY_REALTIME:
        realtime = await _try_mint_realtime(
            session, row=row, grounding=grounding, plan=plan, coverage=coverage
        )
        if realtime is None:
            row.modality = MODALITY_VOICE
            modality = MODALITY_VOICE

    await write_audit(
        session,
        action="mock_interview.session_created",
        resource_type="mock_interview_session",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        after={"job_id": str(job_id), "modality": modality, "plan_source": plan.get("source")},
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
        "low_signal": bool(grounding.get("low_signal")),
        "coverage": plan_service.coverage_summary(coverage),
        "realtime": realtime,
    }


async def _try_mint_realtime(
    session: AsyncSession,
    *,
    row: MockInterviewSession,
    grounding: dict[str, Any],
    plan: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    plan_slice = (
        plan_service.build_plan_slice(plan, coverage) if plan and coverage else None
    )
    instruction = prompts.build_conversation_system_prompt(
        grounding,
        target_questions=caps.DEFAULT_TARGET_QUESTIONS,
        plan_slice=plan_slice,
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


def _assert_within_caps(row: MockInterviewSession) -> None:
    """Server-side hard stop for the per-session caps (ADR-0016 §5).

    These caps are advertised in the create response, but a misbehaving/looping
    client could otherwise ignore the ``ended`` hint and keep POSTing answers —
    billing unbounded interviewer turns. Enforce them here, in the service, so
    the DB/cost invariants hold regardless of the client.
    """

    if int(row.question_count or 0) >= caps.MAX_QUESTIONS:
        raise ConflictError(
            "Buổi phỏng vấn đã đạt số câu hỏi tối đa. Hãy kết thúc để nhận nhận xét.",
            details={"reason": "SESSION_QUESTION_LIMIT"},
        )
    elapsed = (datetime.now(tz=UTC) - _aware(row.started_at)).total_seconds()
    if elapsed >= caps.MAX_SESSION_SECONDS:
        raise ConflictError(
            "Buổi phỏng vấn đã đạt thời lượng tối đa. Hãy kết thúc để nhận nhận xét.",
            details={"reason": "SESSION_TIME_LIMIT"},
        )


async def assert_turnable(
    session: AsyncSession, *, principal: Principal, session_id: uuid.UUID
) -> None:
    """Pre-flight for the streaming endpoint so real HTTP status codes surface
    (404 not-owner, 409 not-active / cap reached) BEFORE the 200 stream starts."""

    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)
    if row.status != STATUS_ACTIVE:
        raise ConflictError(
            "Buổi phỏng vấn này đã kết thúc.",
            details={"reason": "SESSION_NOT_ACTIVE"},
        )
    _assert_within_caps(row)


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
    # Lock the session row for the seq allocation so two concurrent turn writers
    # serialize (H2) — no-op on SQLite, real FOR UPDATE on Postgres.
    row = await repo.get_session(
        session, session_id=session_id, user_id=principal.user_id, for_update=True
    )
    if row is None:
        raise ResourceNotFoundError()
    if row.status != STATUS_ACTIVE:
        raise ConflictError(
            "Buổi phỏng vấn này đã kết thúc.",
            details={"reason": "SESSION_NOT_ACTIVE"},
        )
    _assert_within_caps(row)

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
        await _flag_and_escalate(session, row=row)
    try:
        # durability: candidate answer survives a dropped stream; the unique
        # (session_id, seq) index rejects a duplicate-seq double-submit.
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            "Câu trả lời trùng lặp. Vui lòng thử lại.",
            details={"reason": "TURN_CONFLICT"},
        ) from exc
    turns.append(candidate_turn)

    grounding = row.grounding_json or {}
    plan = row.plan_json or {}
    coverage = row.coverage_json or (
        plan_service.init_coverage(plan, difficulty=grounding.get("difficulty"))
        if plan
        else {}
    )
    plan_slice: dict[str, Any] | None = None
    targeted_id: str | None = None
    if plan and coverage:
        # Adaptive difficulty: a cheap, best-effort read of the answer just given
        # picks the next tier (no-op / same tier when AI is unavailable or offline).
        last_q = next(
            (t.text for t in reversed(turns[:-1]) if t.speaker == SPEAKER_INTERVIEWER),
            "",
        )
        new_tier = await conversation_service.answer_signal(
            session,
            user_id=row.user_id,
            session_id=row.id,
            question=last_q or "",
            answer=candidate_text,
            current_tier=str(coverage.get("current_tier") or "intermediate"),
        )
        coverage = plan_service.set_tier(coverage, new_tier)
        plan_slice = plan_service.build_plan_slice(plan, coverage)
        targeted_id = plan_slice.get("target_id") if plan_slice else None

    parts: list[str] = []
    async for chunk in conversation_service.stream_interviewer(
        session,
        user_id=row.user_id,
        grounding=grounding,
        turns=turns,
        target_questions=caps.DEFAULT_TARGET_QUESTIONS,
        session_id=row.id,
        plan_slice=plan_slice,
        turn_seq=next_seq,
    ):
        parts.append(chunk)
        yield {"type": "token", "text": chunk}

    clean_text, ended = conversation_service.strip_end_marker("".join(parts))
    if not clean_text:
        clean_text = prompts.fallback_next_turn(grounding)

    # M4: the student may have ended the session while the reply was streaming.
    # Re-read the row; if it is no longer active, drop the interviewer turn rather
    # than appending it after the report was already built.
    fresh = await repo.get_session(
        session, session_id=session_id, user_id=row.user_id, for_update=True
    )
    if fresh is None or fresh.status != STATUS_ACTIVE:
        yield {
            "type": "done",
            "seq": next_seq,
            "text": clean_text,
            "question_count": int((fresh or row).question_count or 0),
            "ended": True,
        }
        return

    latest = await repo.load_turns(session, session_id=session_id)
    iseq = (latest[-1].seq if latest else next_seq) + 1
    session.add(
        MockInterviewTurn(
            session_id=fresh.id,
            seq=iseq,
            speaker=SPEAKER_INTERVIEWER,
            text=clean_text,
            text_redacted=_redacted(clean_text),
        )
    )
    fresh.question_count = int(fresh.question_count or 0) + 1
    # Deterministic coverage update (NO LLM): attribute the asked question to a
    # planned competency so the NEXT turn targets what is still uncovered.
    if plan and coverage:
        fresh.coverage_json = plan_service.record_interviewer_question(
            coverage, plan, question_text=clean_text, seq=iseq, targeted_id=targeted_id
        )
    reached_end = (
        ended
        or fresh.question_count >= caps.DEFAULT_TARGET_QUESTIONS
        or iseq >= caps.MAX_TURNS_PERSISTED
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # A racing writer took our seq; the reply was still shown to the client.
        yield {
            "type": "done",
            "seq": iseq,
            "text": clean_text,
            "question_count": int(fresh.question_count or 0),
            "ended": reached_end,
        }
        return
    yield {
        "type": "done",
        "seq": iseq,
        "text": clean_text,
        "question_count": fresh.question_count,
        "ended": reached_end,
        # Live coverage so the room's topic chips advance per turn (leak-safe
        # summary — covered/remaining labels only, never ids/weights/scores).
        "coverage": plan_service.coverage_summary(fresh.coverage_json),
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
    ctx: Any | None = None,
) -> dict[str, Any]:
    """Append provider-produced transcript turns (realtime path). Owner + active.

    Candidate text is client/provider supplied, so it runs through the SAME
    injection guard as the typed turn path (a flagged turn escalates to
    moderation), the running total is hard-capped at ``MAX_TURNS_PERSISTED``, and
    the batch write is audited (metadata only).
    """

    _require_student(principal)
    row = await repo.get_session(
        session, session_id=session_id, user_id=principal.user_id, for_update=True
    )
    if row is None:
        raise ResourceNotFoundError()
    if row.status != STATUS_ACTIVE:
        raise ConflictError(details={"reason": "SESSION_NOT_ACTIVE"})
    existing = await repo.load_turns(session, session_id=session_id)
    seq = existing[-1].seq if existing else 0
    added = 0
    for item in turns_in[: caps.MAX_TURNS_PERSISTED]:
        if len(existing) + added >= caps.MAX_TURNS_PERSISTED:
            break  # hard total ceiling (L4) — never exceed the persisted-turn cap
        speaker = (
            SPEAKER_INTERVIEWER
            if str(item.get("speaker")) == SPEAKER_INTERVIEWER
            else SPEAKER_CANDIDATE
        )
        text = str(item.get("text") or "").strip()[: caps.MAX_ANSWER_CHARS]
        if not text:
            continue
        # Candidate turns pass the injection guard (interviewer text is provider
        # output, not attacker-controlled, so it is stored as-is).
        if speaker == SPEAKER_CANDIDATE:
            clean, flags = sanitize_instruction(text)
            text = clean or text
            if "injection" in flags:
                await _flag_and_escalate(session, row=row)
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
    if added:
        await write_audit(
            session,
            action="mock_interview.turns_recorded",
            resource_type="mock_interview_session",
            resource_id=row.id,
            context=_audit_ctx(principal, ctx),
            after={"added": added, "flagged": bool(row.flagged)},
        )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(details={"reason": "TURN_CONFLICT"}) from exc
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
    # Fast idempotency pre-check (no lock) — short-circuit an already-completed
    # session without taking a row lock or reaching any model.
    pre = await _load_owned(session, principal=principal, session_id=session_id)
    if pre.status == STATUS_COMPLETED:
        turns = await repo.load_turns(session, session_id=session_id)
        return presenters.session_detail(pre, turns)
    if pre.status != STATUS_ACTIVE:
        raise ConflictError(details={"reason": "SESSION_NOT_ACTIVE"})

    if turns_in:
        await record_turns(
            session,
            principal=principal,
            session_id=session_id,
            turns_in=turns_in,
            ctx=ctx,
        )

    # TXN A — claim completion UNDER LOCK, re-checking status AFTER the lock, so a
    # second concurrent ``/end`` cannot also generate + bill a report. We mark the
    # session completed here and COMMIT (releasing the lock) BEFORE the expensive
    # report generation, so the lock is never held across model latency.
    row = await repo.get_session(
        session, session_id=session_id, user_id=principal.user_id, for_update=True
    )
    if row is None:
        raise ResourceNotFoundError()
    if row.status == STATUS_COMPLETED:
        # A concurrent ``/end`` won the claim first — return its stored detail
        # idempotently (its report may still be generating; the client re-fetches).
        turns = await repo.load_turns(session, session_id=session_id)
        return presenters.session_detail(row, turns)
    if row.status != STATUS_ACTIVE:
        raise ConflictError(details={"reason": "SESSION_NOT_ACTIVE"})

    now = datetime.now(tz=UTC)
    turns = await repo.load_turns(session, session_id=session_id)
    row.status = STATUS_COMPLETED
    row.ended_at = now
    row.question_count = sum(1 for t in turns if t.speaker == SPEAKER_INTERVIEWER)
    row.duration_seconds = caps.clamp_duration(
        duration_seconds
        if duration_seconds is not None
        else int((now - _aware(row.started_at)).total_seconds())
    )
    # Flagged sessions are escalated to moderation at FLAG time (see
    # _flag_and_escalate), so ending does not need to re-enqueue.
    await session.commit()  # claim committed; lock released; report_json still null

    # Report generation runs OUTSIDE the open txn / lock (analyzer + report LLM
    # calls, latency OK). Analyzer + coverage enrich the coaching; both degrade to
    # deterministic output and never raise.
    grounding = row.grounding_json or {}
    plan = row.plan_json or {}
    coverage = row.coverage_json or {}
    transcript_lines = conversation_service.build_transcript_lines(turns)
    analysis = await analysis_service.analyze(
        session,
        user_id=row.user_id,
        session_id=row.id,
        grounding=grounding,
        plan=plan,
        coverage=coverage,
        transcript_lines=transcript_lines,
    )
    report = await report_service.generate_report(
        session,
        user_id=row.user_id,
        grounding=grounding,
        transcript_lines=transcript_lines,
        session_id=row.id,
        analysis=analysis,
        coverage=coverage,
    )

    # TXN B — attach the report + audit + event (short txn).
    row.report_json = report
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


async def _flag_and_escalate(
    session: AsyncSession, *, row: MockInterviewSession
) -> None:
    """Flag a session and escalate to moderation at FLAG time (metadata only).

    Escalating when the flag is first raised — not only in ``end_session`` —
    means a flagged session that is later aborted, deleted, or abandoned (→
    ``expired``) still reaches the moderation queue. Idempotent: a second flagged
    turn in the same session does not re-enqueue.
    """

    if row.flagged:
        return
    row.flagged = True

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
    # HARD owner scoping — this student route returns the caller's OWN session
    # only, even for a superadmin. Cross-user reads for AI-ops support must go
    # through ops_service.view_transcript, which redacts by default, requires the
    # identity grant + the student's opt-in for raw text, and audits every open
    # (ADR-0016 §6). Widening ownership here would leak raw PII transcripts with
    # no consent gate and no audit trail.
    row = await repo.get_session(
        session, session_id=session_id, user_id=principal.user_id
    )
    if row is None:
        raise ResourceNotFoundError()
    turns = await repo.load_turns(session, session_id=session_id)
    return presenters.session_detail(row, turns)


# --------------------------------------------------------------------------- #
# Voice tier: server-mediated speech (STT + TTS)                              #
# --------------------------------------------------------------------------- #


async def synthesize_turn_audio(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    text: str,
    voice: str | None = None,
) -> tuple[bytes, str]:
    """Synthesize interviewer ``text`` to speech for a session the caller owns.

    Ownership-scoped (404 for a non-owner) and metered. Raises a user-safe
    ``AIUnavailableError`` when the speech tier is off/unconfigured or the
    provider call fails, so the client degrades to captions/text.
    """

    _require_student(principal)
    await _load_owned(session, principal=principal, session_id=session_id)
    from app.ai.gateway import speech

    try:
        return await speech.synthesize(
            text,
            voice=voice,
            session=session,
            user_id=principal.user_id,
            session_id=session_id,
        )
    except speech.SpeechUnavailableError as exc:
        raise AIUnavailableError(
            "Giọng nói tạm thời không khả dụng. Bạn vẫn có thể tiếp tục bằng phụ đề/văn bản.",
            details={"reason": "SPEECH_UNAVAILABLE"},
        ) from exc


async def transcribe_answer_audio(
    session: AsyncSession,
    *,
    principal: Principal,
    session_id: uuid.UUID,
    audio: bytes,
    mime_type: str,
    locale: str = "vi",
) -> str:
    """Transcribe the student's spoken answer for a session they own.

    Ownership-scoped and metered. The transcript is returned to the client to
    review and submit as the turn answer (never auto-submitted). Raises a
    user-safe ``AIUnavailableError`` when speech is unavailable.
    """

    _require_student(principal)
    await _load_owned(session, principal=principal, session_id=session_id)
    from app.ai.gateway import speech

    try:
        return await speech.transcribe(
            audio,
            mime_type,
            locale=locale,
            session=session,
            user_id=principal.user_id,
            session_id=session_id,
        )
    except speech.SpeechUnavailableError as exc:
        raise AIUnavailableError(
            "Không nhận dạng được giọng nói lúc này. Bạn có thể gõ câu trả lời.",
            details={"reason": "SPEECH_UNAVAILABLE"},
        ) from exc


async def build_live_relay_context(
    session: AsyncSession, *, principal: Principal, session_id: uuid.UUID
) -> dict[str, Any]:
    """Owner-scoped context for the realtime Live relay: the CV+JD-grounded
    interviewer system prompt, the voice, and the hard duration cap.

    Raises 404 for a non-owner and 409 if the session already ended. The relay
    itself streams audio; this only authorizes and prepares the grounded prompt
    so the WS route stays HTTP-thin.
    """

    _require_student(principal)
    row = await _load_owned(session, principal=principal, session_id=session_id)
    if row.status != STATUS_ACTIVE:
        raise ConflictError(
            "Buổi phỏng vấn này đã kết thúc.",
            details={"reason": "SESSION_NOT_ACTIVE"},
        )
    grounding = dict(row.grounding_json or {})
    plan = row.plan_json or {}
    coverage = row.coverage_json or {}
    plan_slice = (
        plan_service.build_plan_slice(plan, coverage) if plan and coverage else None
    )
    instruction = prompts.build_conversation_system_prompt(
        grounding,
        target_questions=caps.DEFAULT_TARGET_QUESTIONS,
        plan_slice=plan_slice,
    )
    voice = getattr(get_settings(), "ai_realtime_voice", "Aoede")
    return {
        "system_instruction": instruction,
        "voice": voice,
        "max_seconds": caps.MAX_SESSION_SECONDS,
        "locale": row.locale,
    }
