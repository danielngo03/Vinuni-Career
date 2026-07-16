"""The interviewer "brain" — a thin adapter over the safe text gateway.

One interviewer turn at a time, grounded on the session's JD+CV grounding AND the
frozen interview plan (a ``plan_slice`` steers the next question toward the planned
competency at the current difficulty tier). The interviewer speaks first
(assistant), the candidate replies (user). This module does NO persistence and NO
RBAC — ``session_service`` owns the transaction, turn storage, and permissions.
Here we only turn (grounding + plan slice + prior turns) into the next interviewer
utterance, with a static fallback when the provider is down.

Every gateway call carries a student ``UsageContext`` (feature ``interview_sim``)
so the billable/energy ledger settles the turn (idempotent per seq).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncGenerator, Iterable
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.observability import billable_usage
from app.ai.prompts.mock_interview import v1 as prompts
from app.core.config import get_settings
from app.modules.mock_interview.application import caps
from app.modules.mock_interview.domain.models import (
    SPEAKER_INTERVIEWER,
    MockInterviewTurn,
)

_START_HINT = "Let's begin the interview."
_END_MARK = "[END]"

# The deterministic OfflineProvider (safe fallback when real AI calls are
# disabled) emits a literal ``"[offline] ..."`` test scaffold that echoes the
# candidate's own input. That scaffold must NEVER render as an interviewer
# question — this marker lets us detect and suppress it (see ``stream_interviewer``).
_OFFLINE_STUB_MARKER = "[offline]"


def is_offline_stub(text: str | None) -> bool:
    """True when ``text`` is (or begins with) the OfflineProvider stub scaffold."""

    return _OFFLINE_STUB_MARKER in (text or "")


def _alias() -> str:
    return get_settings().ai_interview_model_alias


def _usage_ctx(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None,
    task_type: str,
    part: str,
) -> billable_usage.UsageContext:
    """Build the student billable context for one interview gateway call."""

    idem = (
        billable_usage.make_idempotency_key("interview_sim", session_id, part)
        if session_id is not None
        else None
    )
    return billable_usage.UsageContext(
        actor_persona=billable_usage.PERSONA_STUDENT,
        feature_key=billable_usage.FEATURE_INTERVIEW_SIM,
        task_type=task_type,
        billing_scope=billable_usage.SCOPE_USER,
        actor_user_id=user_id,
        session_id=session_id,
        resource_type="mock_interview_session",
        resource_id=session_id,
        idempotency_key=idem,
    )


def strip_end_marker(text: str) -> tuple[str, bool]:
    """Return (clean_text, interviewer_signalled_end)."""

    ended = _END_MARK in (text or "")
    cleaned = (text or "").replace(_END_MARK, "").strip()
    return cleaned, ended


def build_transcript_lines(turns: Iterable[MockInterviewTurn]) -> list[str]:
    """Render stored turns into 'Interviewer:/Candidate:' lines for the report."""

    lines: list[str] = []
    for t in turns:
        who = "Interviewer" if t.speaker == SPEAKER_INTERVIEWER else "Candidate"
        text = (t.text or "").strip()
        if text:
            lines.append(f"{who}: {text}")
    return lines


def _history_messages(
    system_prompt: str, turns: Iterable[MockInterviewTurn]
) -> list[AIMessage]:
    # Seed with a user nudge so the first non-system message is always 'user'
    # (valid alternation across providers), then replay the transcript.
    messages = [
        AIMessage(role="system", content=system_prompt),
        AIMessage(role="user", content=_START_HINT),
    ]
    for t in turns:
        role: Literal["assistant", "user"] = (
            "assistant" if t.speaker == SPEAKER_INTERVIEWER else "user"
        )
        text = (t.text or "").strip()
        if text:
            messages.append(AIMessage(role=role, content=text[: caps.MAX_ANSWER_CHARS]))
    return messages


async def generate_opening(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    grounding: dict[str, Any],
    target_questions: int,
    session_id: uuid.UUID | None = None,
    plan_slice: dict[str, Any] | None = None,
) -> str:
    """The interviewer's first utterance (greeting + first question).

    Retained as a metered fallback: the frozen plan normally supplies the opening
    (built once at create), so ``session_service`` uses ``plan['opening']`` and only
    reaches here if a caller wants a fresh model-generated opening.
    """

    system = prompts.build_conversation_system_prompt(
        grounding, target_questions=target_questions, plan_slice=plan_slice
    )
    messages = [
        AIMessage(role="system", content=system),
        AIMessage(role="user", content=_START_HINT),
    ]
    runner = AiTaskRunner(
        db,
        alias=_alias(),
        task_type=prompts.CONVERSATION_TASK_TYPE,
        user_id=user_id,
        session_id=session_id,
        usage_context=_usage_ctx(
            user_id=user_id,
            session_id=session_id,
            task_type=prompts.CONVERSATION_TASK_TYPE,
            part="opening",
        ),
    )
    try:
        resp = await runner.complete(
            messages, temperature=0.7, max_tokens=caps.QUESTION_MAX_TOKENS
        )
        text, _ = strip_end_marker(resp.text)
        # Suppress the offline stub scaffold — never return it as the opening.
        if not text or is_offline_stub(text):
            return prompts.fallback_first_turn(grounding)
        return text
    except Exception:  # noqa: BLE001 - any gateway failure degrades to fallback
        return prompts.fallback_first_turn(grounding)


async def stream_interviewer(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    grounding: dict[str, Any],
    turns: list[MockInterviewTurn],
    target_questions: int,
    session_id: uuid.UUID | None = None,
    plan_slice: dict[str, Any] | None = None,
    turn_seq: int | None = None,
) -> AsyncGenerator[str, None]:
    """Stream the next interviewer turn as scrubbed token chunks.

    ``turns`` is the full transcript INCLUDING the candidate's just-added answer
    as the final entry (so the model's last message is the candidate's reply).
    ``plan_slice`` steers the question toward the next planned competency.
    On any provider failure a single static fallback chunk is yielded.

    When no real provider is active the AI gateway resolves to the deterministic
    ``OfflineProvider``, whose ``"[offline] ..."`` stub echoes the candidate's own
    input. That scaffold must never be shown as an interviewer question, so we
    skip the gateway entirely and yield the static, human-quality fallback turn.
    """

    # Gate on the FINAL post-precedence decision: when this is False the factory
    # WILL return ``OfflineProvider`` for any alias, so degrade to the static turn
    # instead of streaming its test scaffold. Happy path (real provider on) is
    # unchanged.
    try:
        from app.ai.gateway.factory import real_provider_active

        provider_live = real_provider_active()
    except Exception:  # noqa: BLE001 - treat any resolution failure as "not live"
        provider_live = False
    if not provider_live:
        yield prompts.fallback_next_turn(grounding)
        return

    system = prompts.build_conversation_system_prompt(
        grounding, target_questions=target_questions, plan_slice=plan_slice
    )
    messages = _history_messages(system, turns)
    runner = AiTaskRunner(
        db,
        alias=_alias(),
        task_type=prompts.CONVERSATION_TASK_TYPE,
        user_id=user_id,
        session_id=session_id,
        usage_context=_usage_ctx(
            user_id=user_id,
            session_id=session_id,
            task_type=prompts.CONVERSATION_TASK_TYPE,
            part=f"turn:{turn_seq}" if turn_seq is not None else "turn",
        ),
    )
    produced = False
    try:
        async for chunk in runner.stream(
            messages, temperature=0.7, max_tokens=caps.QUESTION_MAX_TOKENS
        ):
            if not chunk:
                continue
            # Defensive: if the offline stub somehow reaches here while a provider
            # is nominally "live", drop the whole turn and use the static fallback
            # rather than leaking scaffold text. The marker is always at the very
            # start of the stub, so only the first chunk needs the check.
            if not produced and is_offline_stub(chunk):
                yield prompts.fallback_next_turn(grounding)
                return
            produced = True
            yield chunk
    except Exception:  # noqa: BLE001 - any gateway/policy failure degrades gracefully
        if not produced:
            yield prompts.fallback_next_turn(grounding)
        return
    if not produced:
        yield prompts.fallback_next_turn(grounding)


# --------------------------------------------------------------------------- #
# Adaptive difficulty + real-time nudge — a cheap, best-effort answer signal   #
# --------------------------------------------------------------------------- #
_TIER_ORDER = list(caps.DIFFICULTY_TIERS)

_DEPTHS = ("shallow", "solid", "deep")

# Bilingual cues for the DETERMINISTIC depth/STAR read (no LLM). Deliberately small
# and boundary-tolerant; the LLM only ENRICHES this base when a real provider is on.
_REASONING_CUES = (
    "because", "so that", "therefore", "trade-off", "tradeoff", "decided", "chose",
    "reason", "vì", "bởi", "nên", "quyết định", "lý do", "do đó",
)
_RESULT_CUES = (
    "result", "outcome", "impact", "increased", "reduced", "improved", "achieved",
    "led to", "grew", "kết quả", "tăng", "giảm", "cải thiện", "đạt được", "dẫn đến",
)
_ACTION_CUES = (
    "i built", "i implemented", "i designed", "i led", "i wrote", "i created",
    "i developed", "i optimiz", "tôi đã", "xây dựng", "triển khai", "thiết kế",
    "phát triển", "tôi làm", "mình đã",
)


def _step_tier(current: str, direction: int) -> str:
    """Move one difficulty tier up (+1) / down (-1), clamped."""

    try:
        idx = _TIER_ORDER.index(current)
    except ValueError:
        idx = 1
    idx = max(0, min(len(_TIER_ORDER) - 1, idx + direction))
    return _TIER_ORDER[idx]


def _deterministic_depth(answer: str) -> tuple[str, bool]:
    """Deterministic depth + STAR read of an answer — no LLM, offline-safe.

    Returns ``(depth, star)`` where depth is shallow / solid / deep. This is the
    always-present base for both adaptive difficulty and the real-time nudge; the
    optional LLM signal only refines it.
    """

    ans = (answer or "").strip()
    if not ans:
        return "shallow", False
    low = ans.lower()
    n = len(re.findall(r"[\wÀ-ỹ]+", low))
    has_number = bool(re.search(r"\d", ans)) or "%" in ans
    reasoning = any(k in low for k in _REASONING_CUES)
    result = any(k in low for k in _RESULT_CUES) or "%" in ans
    action = any(k in low for k in _ACTION_CUES)
    star = bool(action and result and n >= 25)
    if n < 18 and not has_number:
        depth = "shallow"
    elif has_number and (reasoning or result) and n >= 35:
        depth = "deep"
    else:
        depth = "solid"
    return depth, star


def _next_tier(depth: str, current: str) -> str:
    """A deep answer escalates one tier; a shallow answer eases one tier."""

    if depth == "deep":
        return _step_tier(current, +1)
    if depth == "shallow":
        return _step_tier(current, -1)
    return current


async def read_answer_signal(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    question: str,
    answer: str,
    current_tier: str,
) -> dict[str, Any]:
    """Read the last answer's depth + STAR + the next difficulty tier.

    Deterministic-first: the depth/STAR base is computed with NO LLM (offline/tests
    stay deterministic). Only when a real provider is active do we spend a tiny,
    best-effort flash probe to REFINE it; on ANY failure the deterministic base
    stands. Returns ``{"depth", "star", "next_tier"}``. The interview never depends
    on this — it drives adaptive difficulty and the real-time nudge only.
    """

    current = current_tier if current_tier in caps.DIFFICULTY_TIERS else "intermediate"
    ans = (answer or "").strip()
    depth, star = _deterministic_depth(ans)
    if ans:
        try:
            from app.ai.gateway.factory import real_provider_active

            active = real_provider_active()
        except Exception:  # noqa: BLE001
            active = False
        if active:
            refined = await _llm_answer_signal(
                db,
                user_id=user_id,
                session_id=session_id,
                question=question,
                answer=ans,
            )
            if refined is not None:
                llm_depth, llm_star = refined
                if llm_depth in _DEPTHS:
                    depth = llm_depth
                if llm_star is not None:
                    star = llm_star
    return {"depth": depth, "star": star, "next_tier": _next_tier(depth, current)}


def build_nudge(depth: str, star: bool, locale: str) -> dict[str, str] | None:
    """Map an answer signal to a SHORT, leak-safe coaching nudge (or ``None``).

    Deterministic and never a score: a shallow answer -> add specifics; a solid
    answer without STAR structure -> try STAR; a deep answer (or a solid STAR
    answer) is already strong -> no nudge.
    """

    if depth == "shallow":
        return {"text": prompts.interview_nudge_text("specifics", locale)}
    if depth == "solid" and not star:
        return {"text": prompts.interview_nudge_text("star", locale)}
    return None


async def _llm_answer_signal(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    question: str,
    answer: str,
) -> tuple[str | None, bool | None] | None:
    """Best-effort flash probe for (depth, star). ``None`` on any failure."""

    runner = AiTaskRunner(
        db,
        alias=_alias(),
        task_type=prompts.ANSWER_SIGNAL_TASK_TYPE,
        user_id=user_id,
        session_id=session_id,
        usage_context=_usage_ctx(
            user_id=user_id,
            session_id=session_id,
            task_type=prompts.ANSWER_SIGNAL_TASK_TYPE,
            part=None if session_id is None else "signal",
        ),
    )
    try:
        resp = await runner.complete(
            [
                AIMessage(role="system", content=prompts.ANSWER_SIGNAL_SYSTEM_PROMPT),
                AIMessage(
                    role="user",
                    content=prompts.build_answer_signal_user_message(question, answer),
                ),
            ],
            temperature=0.0,
            max_tokens=caps.ANSWER_SIGNAL_MAX_TOKENS,
        )
    except Exception:  # noqa: BLE001 - signal is optional; deterministic base stands
        return None
    return _parse_signal(resp.text)


def _parse_signal(text: str | None) -> tuple[str | None, bool | None]:
    """Parse the depth + star signal from the flash probe's JSON (best-effort)."""

    raw = (text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                depth = str(obj.get("depth") or "").lower()
                star = obj.get("star")
                return (
                    depth if depth in _DEPTHS else None,
                    bool(star) if isinstance(star, bool) else None,
                )
        except (ValueError, TypeError):
            pass
    low = raw.lower()
    for depth in ("shallow", "deep", "solid"):
        if depth in low:
            return depth, None
    return None, None
