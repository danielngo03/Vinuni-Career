"""Post-session ANALYZER — per-competency coverage / STAR / gap analysis.

Runs ONCE at session end (latency is fine there) on a reasoning-tier model, and
feeds :mod:`report_service` so the coaching report can prioritise the real gaps
and turn them into learning directions. Deterministic-first: the base analysis is
derived with NO LLM from the frozen plan + deterministic coverage state; the model
call only ENRICHES it (per-competency STAR components, evidence quotes, gap
severity). Any model/validation failure degrades to the deterministic base — it
never raises and never blocks the report.

NO score / rating / grade anywhere (owner rule): the analyzer emits categorical
coverage + gap-severity buckets only, never a number.
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
from app.modules.mock_interview.application import caps, plan_service

_ANALYSIS_ALIAS = "reasoning_default"

_SEVERITIES = frozenset({"none", "low", "medium", "high"})
_STAR = frozenset({"S", "T", "A", "R"})


def _deterministic_analysis(
    plan: dict[str, Any], coverage: dict[str, Any] | None
) -> dict[str, Any]:
    """Per-competency analysis from the plan + coverage — no LLM, no fabrication."""

    cov_comps = (coverage or {}).get("competencies") or {}
    per: list[dict[str, Any]] = []
    uncovered: list[str] = []
    for comp in plan.get("competency_map") or []:
        if not isinstance(comp, dict):
            continue
        cid = str(comp.get("id") or "")
        label = str(comp.get("label") or "")[:120]
        if not cid or not label:
            continue
        covered = bool((cov_comps.get(cid) or {}).get("covered"))
        # Deterministic gap severity: an explicit CV "gap" that was never probed
        # is the highest-signal gap; a covered competency has no residual gap.
        cv_ev = str(comp.get("cv_evidence") or "").lower()
        if covered:
            severity = "none"
        elif cv_ev == "gap":
            severity = "high"
        elif cv_ev == "unclear":
            severity = "medium"
        else:
            severity = "low"
        per.append(
            {
                "competency_id": cid,
                "label": label,
                "covered": covered,
                "star_components": [],
                "evidence_quote": "",
                "gap_severity": severity,
            }
        )
        if not covered:
            uncovered.append(label)
    return {
        "analysis_version": prompts.PLAN_VERSION,
        "source": "deterministic",
        "per_competency": per,
        "uncovered": uncovered,
    }


def _validate(
    obj: dict[str, Any] | None, base: dict[str, Any]
) -> dict[str, Any] | None:
    """Merge a raw LLM analysis onto the deterministic base, or ``None`` if junk."""

    if not isinstance(obj, dict):
        return None
    raw = obj.get("per_competency")
    if not isinstance(raw, list) or not raw:
        return None
    by_id = {str(p.get("competency_id")): p for p in raw if isinstance(p, dict)}
    per: list[dict[str, Any]] = []
    for item in base["per_competency"]:
        cid = item["competency_id"]
        enrich = by_id.get(cid) or {}
        star = [s for s in (enrich.get("star_components") or []) if s in _STAR]
        sev = str(enrich.get("gap_severity") or "").lower()
        # ``covered`` stays deterministic (we know what was actually asked); the
        # model only enriches STAR components, an evidence quote, and severity.
        per.append(
            {
                "competency_id": cid,
                "label": item["label"],
                "covered": item["covered"],
                "star_components": star,
                "evidence_quote": str(enrich.get("evidence_quote") or "")[:240],
                "gap_severity": sev if sev in _SEVERITIES else item["gap_severity"],
            }
        )
    return {
        "analysis_version": prompts.PLAN_VERSION,
        "source": "llm",
        "per_competency": per,
        "uncovered": [p["label"] for p in per if not p["covered"]],
    }


def _parse_json(text: str | None) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw[:4].lower() == "json":
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


async def analyze(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    grounding: dict[str, Any],
    plan: dict[str, Any] | None,
    coverage: dict[str, Any] | None,
    transcript_lines: list[str],
) -> dict[str, Any]:
    """Analyze the transcript against the plan. Never raises — deterministic base.

    Returns a dict ``{per_competency, uncovered, source, analysis_version}``. When
    there is no plan (e.g. a legacy session), returns an empty analysis so the
    report path is unchanged.
    """

    if not plan or not (plan.get("competency_map")):
        return {
            "analysis_version": prompts.PLAN_VERSION,
            "source": "deterministic",
            "per_competency": [],
            "uncovered": [],
        }

    base = _deterministic_analysis(plan, coverage)
    locale = grounding.get("locale") or "vi"
    system = prompts.build_analysis_system_prompt(locale)
    user = prompts.build_analysis_user_message(grounding, plan, transcript_lines)
    usage_ctx = billable_usage.UsageContext(
        actor_persona=billable_usage.PERSONA_STUDENT,
        feature_key=billable_usage.FEATURE_INTERVIEW_SIM,
        task_type=prompts.ANALYSIS_TASK_TYPE,
        billing_scope=billable_usage.SCOPE_USER,
        actor_user_id=user_id,
        session_id=session_id,
        resource_type="mock_interview_session",
        resource_id=session_id,
        idempotency_key=billable_usage.make_idempotency_key(
            "interview_sim", session_id, "analysis"
        ),
    )
    runner = AiTaskRunner(
        db,
        alias=_ANALYSIS_ALIAS,
        task_type=prompts.ANALYSIS_TASK_TYPE,
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
            temperature=0.3,
            max_tokens=caps.ANALYSIS_MAX_TOKENS,
        )
        return _validate(_parse_json(resp.text), base) or base
    except Exception:  # noqa: BLE001 - degrade to the deterministic analysis
        return base


__all__ = ["analyze", "coverage_summary_for"]


def coverage_summary_for(coverage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Thin re-export so callers get the coverage summary from one place."""

    return plan_service.coverage_summary(coverage)
