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


# --------------------------------------------------------------------------- #
# Gap -> learning links (DETERMINISTIC, no tokens, no fabrication)             #
# --------------------------------------------------------------------------- #
# A small curated map of common skill fragments -> concrete, HONEST learning
# TOPICS (generic study directions, never fabricated course names or URLs). Keys
# are matched as case-insensitive substrings of a gap label. ``kind`` is one of
# "skill" | "topic" | "resource". Titles keep standard technical terms in their
# original form (code-switching rule) so they read naturally in vi and en.
_LEARNING_MAP: dict[str, list[tuple[str, str]]] = {
    "sql": [
        ("Indexing & query plans", "topic"),
        ("Normalization & schema design", "topic"),
        ("Joins & aggregation practice", "resource"),
    ],
    "postgres": [
        ("Indexing & query plans", "topic"),
        ("Transactions & isolation levels", "topic"),
    ],
    "database": [
        ("Data modelling & normalization", "topic"),
        ("Indexing basics", "topic"),
    ],
    "python": [
        ("Idiomatic Python & data structures", "topic"),
        ("Testing with pytest", "skill"),
        ("Async & concurrency basics", "topic"),
    ],
    "javascript": [
        ("Closures & the event loop", "topic"),
        ("Promises & async/await", "topic"),
    ],
    "typescript": [
        ("Type system & generics", "topic"),
        ("Narrowing & discriminated unions", "topic"),
    ],
    "react": [
        ("Hooks & component state", "topic"),
        ("Rendering & performance", "topic"),
    ],
    "fastapi": [
        ("Dependency injection & routing", "topic"),
        ("Request validation with Pydantic", "skill"),
    ],
    "api": [
        ("REST design & status codes", "topic"),
        ("Auth & pagination patterns", "topic"),
    ],
    "docker": [
        ("Images, layers & Dockerfiles", "topic"),
        ("Containerizing a small app", "resource"),
    ],
    "kubernetes": [
        ("Pods, deployments & services", "topic"),
        ("kubectl hands-on basics", "resource"),
    ],
    "cloud": [
        ("Core compute & storage services", "topic"),
        ("Networking & IAM basics", "topic"),
    ],
    "aws": [
        ("Core compute & storage services", "topic"),
        ("IAM & security basics", "topic"),
    ],
    "system design": [
        ("Scalability & load balancing", "topic"),
        ("Caching strategies", "topic"),
        ("Designing a small system end-to-end", "resource"),
    ],
    "algorithm": [
        ("Big-O & complexity analysis", "topic"),
        ("Common patterns (two pointers, DP)", "resource"),
    ],
    "data structure": [
        ("Arrays, maps, trees & graphs", "topic"),
        ("Practice problems by structure", "resource"),
    ],
    "machine learning": [
        ("Model evaluation & overfitting", "topic"),
        ("A small end-to-end ML project", "resource"),
    ],
    "security": [
        ("OWASP Top 10 basics", "topic"),
        ("Authn vs authz fundamentals", "topic"),
    ],
    "test": [
        ("Unit vs integration testing", "topic"),
        ("Writing testable code", "skill"),
    ],
    "git": [
        ("Branching & pull-request flow", "skill"),
    ],
    # Behavioral / soft competencies.
    "communicat": [
        ("STAR storytelling", "skill"),
        ("Structuring a clear, concise answer", "topic"),
    ],
    "leadership": [
        ("Leading without authority", "topic"),
        ("Giving & receiving feedback", "skill"),
    ],
    "team": [
        ("Collaboration & conflict resolution", "skill"),
    ],
    "ownership": [
        ("Driving a task end-to-end", "topic"),
    ],
    "problem solv": [
        ("Structured problem breakdown", "skill"),
    ],
    "motivat": [
        ("Articulating your why & role fit", "topic"),
    ],
}

# How many learning items to attach per gap (keep it tight and actionable).
_MAX_LEARNING = 3


def _generic_learning(label: str, locale: str) -> list[dict[str, str]]:
    """Honest, generic learning directions when no curated topic matches."""

    vi = (locale or "vi").lower().startswith("vi")
    lab = str(label or "").strip()[:80]
    if vi:
        return [
            {"title": f"Kiến thức nền tảng về {lab}", "kind": "topic"},
            {"title": f"Một dự án nhỏ thực hành {lab}", "kind": "resource"},
        ]
    return [
        {"title": f"Core concepts of {lab}", "kind": "topic"},
        {"title": f"A small practice project on {lab}", "kind": "resource"},
    ]


def build_gap_learning(label: str, locale: str) -> list[dict[str, str]]:
    """Deterministic learning topics for one gap label (curated first, generic else)."""

    low = str(label or "").lower()
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for key, topics in _LEARNING_MAP.items():
        if key in low:
            for title, kind in topics:
                tl = title.lower()
                if tl not in seen:
                    items.append({"title": title, "kind": kind})
                    seen.add(tl)
        if len(items) >= _MAX_LEARNING:
            break
    if not items:
        items = _generic_learning(label, locale)
    return items[:_MAX_LEARNING]


def _gap_why(label: str, grounding: dict[str, Any] | None, locale: str) -> str:
    """Honest 'why this matters' tied to the JD (deterministic)."""

    vi = (locale or "vi").lower().startswith("vi")
    job = (grounding or {}).get("job") or {}
    blob = " ".join(
        [
            str(job.get("title") or ""),
            " ".join(str(s) for s in (job.get("required_skills") or [])),
            " ".join(str(r) for r in (job.get("requirements") or [])),
        ]
    ).lower()
    low = str(label or "").lower()
    tied = bool(low) and (
        low in blob or any(tok in blob for tok in low.split() if len(tok) >= 3)
    )
    if vi:
        return (
            "Đây là yêu cầu trong mô tả công việc; hãy chuẩn bị ví dụ cụ thể để thể hiện."
            if tied
            else "Hãy củng cố phần này bằng một ví dụ cụ thể mà bạn có thể trình bày."
        )
    return (
        "This maps to a job requirement — prepare a concrete example to demonstrate it."
        if tied
        else "Strengthen this area with a concrete example you can speak to."
    )


def enrich_report_gaps(
    report: dict[str, Any] | None,
    grounding: dict[str, Any] | None,
    locale: str | None,
) -> dict[str, Any] | None:
    """Return an API COPY of the report with structured gaps + learning links.

    The stored ``report_json`` keeps ``gaps_to_work_on`` as plain strings (internal
    read models such as progress/ops depend on that). At the API boundary the
    presenter calls this to turn each gap into ``{label, why, learning}`` where the
    ``learning`` topics are DETERMINISTIC (no tokens, no fabricated names/URLs). The
    input report is never mutated, so repeated calls are stable/idempotent.
    """

    if not isinstance(report, dict):
        return report
    loc = (locale or (grounding or {}).get("locale") or "vi")
    out = dict(report)
    enriched: list[dict[str, Any]] = []
    for gap in report.get("gaps_to_work_on") or []:
        if isinstance(gap, dict):
            label = str(gap.get("label") or "").strip()
            why = str(gap.get("why") or "").strip()
        else:
            label = str(gap or "").strip()
            why = ""
        if not label:
            continue
        enriched.append(
            {
                "label": label[:160],
                "why": (why or _gap_why(label, grounding, loc))[:240],
                "learning": build_gap_learning(label, loc),
            }
        )
    out["gaps_to_work_on"] = enriched
    return out


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
