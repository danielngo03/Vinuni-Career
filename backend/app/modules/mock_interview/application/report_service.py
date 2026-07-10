"""Post-session coaching report — through the safe TEXT gateway.

Runs on ``AiTaskRunner`` so it automatically gets budget/policy guards, output
scrubbing, usage logging, telemetry, 1% eval sampling to ``ai_eval_samples`` AND
the student billable/energy ledger (via ``UsageContext``). The report consumes the
frozen plan's coverage state + the post-session analyzer so coaching prioritises
the real, uncovered gaps and turns them into learning directions. Output is
COACHING only — the normalizer structurally drops any score/rating the model might
emit (no-score invariant). Any failure degrades to a deterministic, gap-keyed
static report; it never raises.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.observability import billable_usage
from app.ai.prompts.mock_interview import v1 as prompts
from app.core.config import get_settings
from app.modules.mock_interview.application import caps, plan_service
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


def _merge_uncovered_gaps(
    gaps: list[str], analysis: dict[str, Any] | None
) -> list[str]:
    """Ensure deterministic uncovered competencies surface as gaps (dedup, capped)."""

    out = list(gaps)
    have = " ".join(out).lower()
    for label in (analysis or {}).get("uncovered") or []:
        text = str(label).strip()
        if text and text.lower() not in have:
            out.append(text[:160])
            have += " " + text.lower()
        if len(out) >= 8:
            break
    return out[:8]


def _attach_coverage(
    report: dict[str, Any],
    *,
    analysis: dict[str, Any] | None,
    coverage: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach the DETERMINISTIC coverage summary + uncovered gaps (no score)."""

    summary = plan_service.coverage_summary(coverage)
    if summary is not None:
        report["coverage"] = summary
    report["gaps_to_work_on"] = _merge_uncovered_gaps(
        report.get("gaps_to_work_on") or [], analysis
    )
    return report


async def generate_report(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    grounding: dict[str, Any],
    transcript_lines: list[str],
    session_id: uuid.UUID | None = None,
    analysis: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate the coaching report. Never raises — falls back on any failure.

    ``analysis`` (per-competency, from ``analysis_service``) and ``coverage`` (the
    deterministic coverage state) enrich the prompt and are also folded into the
    final report as a leak-safe, score-free coverage summary.
    """

    locale = grounding.get("locale") or "vi"
    system = prompts.build_report_system_prompt(locale)
    user = prompts.build_report_user_message(
        grounding, transcript_lines, analysis=analysis, coverage=coverage
    )
    usage_ctx = billable_usage.UsageContext(
        actor_persona=billable_usage.PERSONA_STUDENT,
        feature_key=billable_usage.FEATURE_INTERVIEW_SIM,
        task_type=prompts.REPORT_TASK_TYPE,
        billing_scope=billable_usage.SCOPE_USER,
        actor_user_id=user_id,
        session_id=session_id,
        resource_type="mock_interview_session",
        resource_id=session_id,
        idempotency_key=(
            billable_usage.make_idempotency_key("interview_sim", session_id, "report")
            if session_id is not None
            else None
        ),
    )
    runner = AiTaskRunner(
        db,
        alias=_alias(),
        task_type=prompts.REPORT_TASK_TYPE,
        user_id=user_id,
        session_id=session_id,
        usage_context=usage_ctx,
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
        report = normalize_report(_parse_json(resp.text))
    except Exception:  # noqa: BLE001 - degrade to deterministic static report
        report = prompts.static_fallback_report(grounding)
        report["is_fallback"] = True
        report["prompt_version"] = prompts.PROMPT_VERSION
    return _attach_coverage(report, analysis=analysis, coverage=coverage)
