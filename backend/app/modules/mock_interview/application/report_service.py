"""Post-session coaching report — through the safe TEXT gateway.

Runs on ``AiTaskRunner`` so it automatically gets budget/policy guards, output
scrubbing, usage logging, telemetry, and 1% eval sampling to ``ai_eval_samples``
(the AI-ops review surface). Output is COACHING only — the normalizer structurally
drops any score/rating the model might emit (no-score invariant). Any failure
degrades to a deterministic, gap-keyed static report; it never raises.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.prompts.mock_interview import v1 as prompts
from app.core.config import get_settings
from app.modules.mock_interview.application import caps
from app.shared.exceptions import AIUnavailableError


def _alias() -> str:
    return get_settings().ai_interview_model_alias


def _parse_json(text: str | None) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw[:4].lower() == "json":
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AIUnavailableError()
    try:
        obj = json.loads(raw[start : end + 1])
    except (ValueError, TypeError) as exc:
        raise AIUnavailableError() from exc
    if not isinstance(obj, dict):
        raise AIUnavailableError()
    return obj


def normalize_report(data: dict[str, Any]) -> dict[str, Any]:
    """Validate the raw LLM report into the safe shape. NO score fields.

    Any ``score``/``rating``/``grade`` key is dropped by omission — we only copy
    the whitelisted coaching fields. Raises ``AIUnavailableError`` when the model
    produced nothing usable so the caller falls back.
    """

    if not isinstance(data, dict):
        raise AIUnavailableError()
    per_question: list[dict[str, str]] = []
    for item in (data.get("per_question") or [])[:6]:
        if not isinstance(item, dict):
            continue
        per_question.append(
            {
                "question": str(item.get("question") or "")[:200],
                "suggestion": str(item.get("suggestion") or "")[:400],
                "observation": str(item.get("observation") or "")[:400],
            }
        )
    overall = str(data.get("overall_observations") or "")[:800]
    gaps = [
        str(g)[:160] for g in (data.get("gaps_to_work_on") or []) if str(g).strip()
    ][:8]
    strengths = [
        str(s)[:160] for s in (data.get("strengths") or []) if str(s).strip()
    ][:8]
    if not overall and not per_question and not gaps:
        raise AIUnavailableError()
    return {
        "per_question": per_question,
        "overall_observations": overall,
        "gaps_to_work_on": gaps,
        "strengths": strengths,
        "prompt_version": prompts.PROMPT_VERSION,
        "is_fallback": False,
    }


async def generate_report(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    grounding: dict[str, Any],
    transcript_lines: list[str],
) -> dict[str, Any]:
    """Generate the coaching report. Never raises — falls back on any failure."""

    locale = grounding.get("locale") or "vi"
    system = prompts.build_report_system_prompt(locale)
    user = prompts.build_report_user_message(grounding, transcript_lines)
    runner = AiTaskRunner(
        db,
        alias=_alias(),
        task_type=prompts.REPORT_TASK_TYPE,
        user_id=user_id,
    )
    try:
        resp = await runner.complete(
            [
                AIMessage(role="system", content=system),
                AIMessage(role="user", content=user),
            ],
            temperature=0.4,
            max_tokens=caps.REPORT_MAX_TOKENS,
        )
        return normalize_report(_parse_json(resp.text))
    except Exception:  # noqa: BLE001 - degrade to deterministic static report
        fallback = prompts.static_fallback_report(grounding)
        fallback["is_fallback"] = True
        fallback["prompt_version"] = prompts.PROMPT_VERSION
        return fallback
