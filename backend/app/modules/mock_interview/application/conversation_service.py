"""The interviewer "brain" — a thin adapter over the safe text gateway.

One interviewer turn at a time, grounded on the session's JD+CV grounding. The
interviewer speaks first (assistant), the candidate replies (user). This module
does NO persistence and NO RBAC — ``session_service`` owns the transaction, turn
storage, and permissions. Here we only turn (grounding + prior turns) into the
next interviewer utterance, with a static fallback when the provider is down.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterable
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.prompts.mock_interview import v1 as prompts
from app.core.config import get_settings
from app.modules.mock_interview.application import caps
from app.modules.mock_interview.domain.models import (
    SPEAKER_INTERVIEWER,
    MockInterviewTurn,
)

_START_HINT = "Let's begin the interview."
_END_MARK = "[END]"


def _alias() -> str:
    return get_settings().ai_interview_model_alias


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
) -> str:
    """The interviewer's first utterance (greeting + first question)."""

    system = prompts.build_conversation_system_prompt(
        grounding, target_questions=target_questions
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
    )
    try:
        resp = await runner.complete(
            messages, temperature=0.7, max_tokens=caps.QUESTION_MAX_TOKENS
        )
        text, _ = strip_end_marker(resp.text)
        return text or prompts.fallback_first_turn(grounding)
    except Exception:  # noqa: BLE001 - any gateway failure degrades to fallback
        return prompts.fallback_first_turn(grounding)


async def stream_interviewer(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    grounding: dict[str, Any],
    turns: list[MockInterviewTurn],
    target_questions: int,
) -> AsyncGenerator[str, None]:
    """Stream the next interviewer turn as scrubbed token chunks.

    ``turns`` is the full transcript INCLUDING the candidate's just-added answer
    as the final entry (so the model's last message is the candidate's reply).
    On any provider failure a single static fallback chunk is yielded.
    """

    system = prompts.build_conversation_system_prompt(
        grounding, target_questions=target_questions
    )
    messages = _history_messages(system, turns)
    runner = AiTaskRunner(
        db,
        alias=_alias(),
        task_type=prompts.CONVERSATION_TASK_TYPE,
        user_id=user_id,
    )
    produced = False
    try:
        async for chunk in runner.stream(
            messages, temperature=0.7, max_tokens=caps.QUESTION_MAX_TOKENS
        ):
            if chunk:
                produced = True
                yield chunk
    except Exception:  # noqa: BLE001 - any gateway/policy failure degrades gracefully
        if not produced:
            yield prompts.fallback_next_turn(grounding)
        return
    if not produced:
        yield prompts.fallback_next_turn(grounding)
