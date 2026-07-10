"""Interview PLANNER + deterministic coverage tracking.

Two responsibilities, both leak-safe and deterministic-first:

1. :func:`build_plan` — build the frozen interview plan ONCE at session create.
   The heavy lifting is DETERMINISTIC (no LLM): JD competencies are extracted from
   the grounding and mapped to CV evidence (covered / gap) reusing the matched-skill
   / gap data ``grounding_service`` already computed. A SINGLE strong-model call
   (alias ``interview_planner``) then refines the competency map + tiered question
   bank + opening. On ANY model/validation failure we fall back to a purely
   deterministic plan built from grounding — session create is NEVER blocked.

2. Coverage tracking — after each interviewer turn the asked question is mapped to
   a planned competency with NO LLM (keyword match against the plan) and the
   coverage state is updated. This drives which competency the next turn targets
   (:func:`build_plan_slice`) and the "what's left / covered" summary the presenter
   shows (:func:`coverage_summary`).

Nothing here exposes a provider/model/token/score. The plan + coverage are product
data frozen on the session row and reused for free by every later turn/tier/report.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.base import AIMessage
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.observability import billable_usage
from app.ai.prompts.mock_interview import v1 as prompts
from app.modules.mock_interview.application import caps

_PLANNER_ALIAS = "interview_planner"

# Words too generic to help competency matching (kept small + English-only; CV/JD
# free text is already sanitized upstream).
_STOP = frozenset(
    {
        "the", "and", "for", "with", "your", "you", "about", "a", "an", "of", "to",
        "in", "on", "is", "are", "how", "what", "why", "when", "can", "could",
        "would", "tell", "me", "walk", "through", "this", "that", "their", "role",
        "experience", "skill", "skills", "question", "questions", "please",
    }
)

_WORD_RE = re.compile(r"[a-zA-ZÀ-ỹ0-9+#.]+")


# --------------------------------------------------------------------------- #
# Tokenization / matching helpers                                             #
# --------------------------------------------------------------------------- #
def _tokens(text: str | None) -> set[str]:
    out: set[str] = set()
    for raw in _WORD_RE.findall((text or "").lower()):
        tok = raw.strip(".")
        if len(tok) >= 2 and tok not in _STOP:
            out.add(tok)
    return out


# --------------------------------------------------------------------------- #
# Deterministic template question bank                                        #
# --------------------------------------------------------------------------- #
def _tier_questions(label: str, focus: str) -> dict[str, str]:
    """Deterministic tiered questions for one competency (English guidance)."""

    lab = label.strip()
    if focus == "behavioral":
        return {
            "foundational": f"What does {lab} mean to you, and where have you shown it?",
            "intermediate": (
                f"Tell me about a specific time {lab} mattered. What was your role, "
                "and what happened?"
            ),
            "advanced": (
                f"Describe the hardest situation where {lab} was tested — how did you "
                "handle the ambiguity and what was the result?"
            ),
        }
    return {
        "foundational": f"Can you explain the fundamentals of {lab} and where you have used it?",
        "intermediate": (
            f"Walk me through a specific time you applied {lab} — your role, the "
            "approach, and the outcome."
        ),
        "advanced": (
            f"How would you design or scale a solution involving {lab} under real-world "
            "constraints and trade-offs?"
        ),
    }


def _is_star_competency(label: str, focus: str, cv_evidence: str) -> bool:
    if focus == "behavioral":
        return True
    behavioral_hint = any(
        h in label.lower()
        for h in ("team", "leadership", "communicat", "ownership", "collaborat", "manage")
    )
    return behavioral_hint or cv_evidence == "gap"


# --------------------------------------------------------------------------- #
# Deterministic plan (fallback + evidence base for the LLM plan)              #
# --------------------------------------------------------------------------- #
def _cv_evidence_for(skill: str, matched: set[str], gaps: set[str]) -> str:
    low = skill.lower()
    if any(low in m or m in low for m in matched):
        return "covered"
    if any(low in g or g in low for g in gaps):
        return "gap"
    return "unclear"


def _generic_competencies(focus: str) -> list[tuple[str, str]]:
    """Fallback competencies for a low-signal JD (label, jd_evidence)."""

    base = [
        ("Motivation and role fit", "Why this role / company"),
        ("Relevant experience", "Most relevant CV experience"),
        ("Problem solving", "Approach to solving problems"),
        ("Communication", "Clarity and structure of answers"),
    ]
    if focus == "technical":
        base.insert(1, ("Core technical foundations", "Fundamentals for the role"))
    return base


def _deterministic_plan(grounding: dict[str, Any]) -> dict[str, Any]:
    """Build a plan purely from grounding — no LLM. Always well-formed."""

    job = grounding.get("job") or {}
    focus = str(grounding.get("focus") or "mixed")
    matched = {str(s).lower() for s in (grounding.get("matched_skills") or [])}
    gaps = {str(s).lower() for s in (grounding.get("gaps") or [])}

    seen: set[str] = set()
    picks: list[tuple[str, str, str, int]] = []  # (label, jd_evidence, cv_evidence, weight)

    for skill in (job.get("required_skills") or []):
        label = str(skill).strip()[:80]
        key = label.lower()
        if not label or key in seen:
            continue
        seen.add(key)
        picks.append((label, f"Required skill: {label}", _cv_evidence_for(label, matched, gaps), 3))
        if len(picks) >= caps.MAX_COMPETENCIES:
            break

    if len(picks) < caps.MAX_COMPETENCIES:
        for req in (job.get("requirements") or []):
            label = str(req).strip()[:80]
            key = label.lower()
            if len(label) < 6 or key in seen:
                continue
            seen.add(key)
            picks.append(
                (label, f"JD requirement: {label}", _cv_evidence_for(label, matched, gaps), 2)
            )
            if len(picks) >= caps.MAX_COMPETENCIES:
                break

    if not picks:
        for label, jd_ev in _generic_competencies(focus):
            picks.append((label, jd_ev, "unclear", 1))

    competency_map: list[dict[str, Any]] = []
    question_bank: list[dict[str, Any]] = []
    for i, (label, jd_ev, cv_ev, weight) in enumerate(picks[: caps.MAX_COMPETENCIES], start=1):
        cid = f"c{i}"
        competency_map.append(
            {
                "id": cid,
                "label": label,
                "jd_evidence": jd_ev,
                "cv_evidence": cv_ev,
                "weight": weight,
            }
        )
        question_bank.append(
            {
                "competency_id": cid,
                "tiers": _tier_questions(label, focus),
                "star_target": _is_star_competency(label, focus, cv_ev),
            }
        )

    return {
        "plan_version": prompts.PLAN_VERSION,
        "source": "deterministic",
        "competency_map": competency_map,
        "question_bank": question_bank,
        "opening": prompts.fallback_first_turn(grounding),
    }


# --------------------------------------------------------------------------- #
# LLM plan parsing / validation                                               #
# --------------------------------------------------------------------------- #
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


def _validate_llm_plan(
    obj: dict[str, Any] | None, grounding: dict[str, Any]
) -> dict[str, Any] | None:
    """Normalize a raw LLM plan into the canonical shape, or ``None`` if unusable."""

    if not isinstance(obj, dict):
        return None
    focus = str(grounding.get("focus") or "mixed")
    raw_comps = obj.get("competency_map")
    if not isinstance(raw_comps, list) or not raw_comps:
        return None
    banks = {
        str(b.get("competency_id")): b
        for b in (obj.get("question_bank") or [])
        if isinstance(b, dict)
    }

    competency_map: list[dict[str, Any]] = []
    question_bank: list[dict[str, Any]] = []
    for i, comp in enumerate(raw_comps[: caps.MAX_COMPETENCIES], start=1):
        if not isinstance(comp, dict):
            continue
        label = str(comp.get("label") or "").strip()[:80]
        if not label:
            continue
        cid = f"c{i}"
        try:
            weight = int(comp.get("weight") or 2)
        except (TypeError, ValueError):
            weight = 2
        competency_map.append(
            {
                "id": cid,
                "label": label,
                "jd_evidence": str(comp.get("jd_evidence") or "")[:200],
                "cv_evidence": str(comp.get("cv_evidence") or "unclear")[:200],
                "weight": max(1, min(3, weight)),
            }
        )
        src = banks.get(str(comp.get("id"))) or {}
        raw_tiers = src.get("tiers") if isinstance(src.get("tiers"), dict) else {}
        template = _tier_questions(label, focus)
        tiers = {
            tier: str((raw_tiers or {}).get(tier) or template[tier]).strip()[:400]
            or template[tier]
            for tier in caps.DIFFICULTY_TIERS
        }
        question_bank.append(
            {
                "competency_id": cid,
                "tiers": tiers,
                "star_target": bool(
                    src.get("star_target")
                    if "star_target" in src
                    else _is_star_competency(label, focus, competency_map[-1]["cv_evidence"])
                ),
            }
        )
    if not competency_map:
        return None
    opening = str(obj.get("opening") or "").strip()
    return {
        "plan_version": prompts.PLAN_VERSION,
        "source": "llm",
        "competency_map": competency_map,
        "question_bank": question_bank,
        "opening": opening or prompts.fallback_first_turn(grounding),
    }


# --------------------------------------------------------------------------- #
# Public entry: build the frozen plan                                         #
# --------------------------------------------------------------------------- #
async def build_plan(
    db: AsyncSession,
    *,
    grounding: dict[str, Any],
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> dict[str, Any]:
    """Return the frozen interview plan. Never raises — deterministic on failure.

    Runs ONE metered strong-model call; any failure (provider down, invalid JSON,
    offline provider in tests) degrades to the deterministic plan.
    """

    deterministic = _deterministic_plan(grounding)
    system = prompts.build_planner_system_prompt(
        grounding, max_competencies=caps.MAX_COMPETENCIES
    )
    user = prompts.build_planner_user_message(grounding)
    usage_ctx = billable_usage.UsageContext(
        actor_persona=billable_usage.PERSONA_STUDENT,
        feature_key=billable_usage.FEATURE_INTERVIEW_SIM,
        task_type=prompts.PLAN_TASK_TYPE,
        billing_scope=billable_usage.SCOPE_USER,
        actor_user_id=user_id,
        session_id=session_id,
        resource_type="mock_interview_session",
        resource_id=session_id,
        idempotency_key=billable_usage.make_idempotency_key(
            "interview_sim", session_id, "plan"
        ),
    )
    runner = AiTaskRunner(
        db,
        alias=_PLANNER_ALIAS,
        task_type=prompts.PLAN_TASK_TYPE,
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
            max_tokens=caps.PLAN_MAX_TOKENS,
        )
        validated = _validate_llm_plan(_parse_json(resp.text), grounding)
        return validated or deterministic
    except Exception:  # noqa: BLE001 - any gateway/parse failure -> deterministic plan
        return deterministic


# --------------------------------------------------------------------------- #
# Coverage state (deterministic, no LLM)                                       #
# --------------------------------------------------------------------------- #
def init_coverage(plan: dict[str, Any], *, difficulty: str | None = None) -> dict[str, Any]:
    """Fresh coverage state for a plan. ``current_tier`` seeds from JD difficulty."""

    order: list[str] = []
    comps: dict[str, Any] = {}
    for comp in plan.get("competency_map") or []:
        if not isinstance(comp, dict):
            continue
        cid = str(comp.get("id") or "")
        if not cid:
            continue
        order.append(cid)
        comps[cid] = {
            "label": str(comp.get("label") or "")[:120],
            "covered": False,
            "asked_seq": [],
        }
    tier = difficulty if difficulty in caps.DIFFICULTY_TIERS else "intermediate"
    return {
        "version": prompts.PLAN_VERSION,
        "current_tier": tier,
        "order": order,
        "competencies": comps,
    }


def _covered_ids(coverage: dict[str, Any]) -> list[str]:
    comps = coverage.get("competencies") or {}
    return [cid for cid in (coverage.get("order") or []) if (comps.get(cid) or {}).get("covered")]


def _remaining_ids(coverage: dict[str, Any]) -> list[str]:
    comps = coverage.get("competencies") or {}
    return [
        cid
        for cid in (coverage.get("order") or [])
        if not (comps.get(cid) or {}).get("covered")
    ]


def _label(coverage: dict[str, Any], cid: str) -> str:
    return str(((coverage.get("competencies") or {}).get(cid) or {}).get("label") or "")


def _match_competency(
    plan: dict[str, Any], coverage: dict[str, Any], question_text: str
) -> str | None:
    """Best deterministic competency match for an asked question (or ``None``)."""

    q_tokens = _tokens(question_text)
    if not q_tokens:
        return None
    banks = {
        str(b.get("competency_id")): b
        for b in (plan.get("question_bank") or [])
        if isinstance(b, dict)
    }
    best_id: str | None = None
    best_score = 0
    for cid in coverage.get("order") or []:
        label = _label(coverage, cid)
        comp_tokens = set(_tokens(label))
        bank = banks.get(cid) or {}
        tiers = bank.get("tiers") if isinstance(bank.get("tiers"), dict) else {}
        for val in (tiers or {}).values():
            comp_tokens |= _tokens(str(val))
        overlap = len(q_tokens & comp_tokens)
        if overlap > best_score:
            best_score = overlap
            best_id = cid
    return best_id if best_score >= 1 else None


def record_interviewer_question(
    coverage: dict[str, Any],
    plan: dict[str, Any],
    *,
    question_text: str,
    seq: int,
    targeted_id: str | None = None,
) -> dict[str, Any]:
    """Deterministically attribute an asked question to a competency and mark it.

    Prefers a keyword match against the plan; falls back to ``targeted_id`` (the
    competency the plan slice steered the interviewer toward) when the question is
    too generic to match. Returns a NEW coverage dict (never mutates the input) so
    a JSON-column re-assignment is always seen as a change by the ORM (the caller
    may pass the row's own ``coverage_json`` object).
    """

    updated = copy.deepcopy(coverage)
    comps = updated.setdefault("competencies", {})
    if not comps:
        return updated
    matched = _match_competency(plan, updated, question_text)
    cid = matched or (targeted_id if targeted_id in comps else None)
    if cid is None:
        return updated
    entry = comps.get(cid)
    if not isinstance(entry, dict):
        return updated
    entry["covered"] = True
    asked = entry.setdefault("asked_seq", [])
    if seq not in asked:
        asked.append(int(seq))
    return updated


def set_tier(coverage: dict[str, Any], tier: str) -> dict[str, Any]:
    """Set the current difficulty tier (adaptive difficulty). Returns a NEW dict
    (no-op value on bad input)."""

    if tier not in caps.DIFFICULTY_TIERS:
        return coverage
    updated = copy.deepcopy(coverage)
    updated["current_tier"] = tier
    return updated


def next_target_id(coverage: dict[str, Any]) -> str | None:
    """The next competency to target: the first not-yet-covered one, else ``None``."""

    remaining = _remaining_ids(coverage)
    return remaining[0] if remaining else None


def build_plan_slice(
    plan: dict[str, Any], coverage: dict[str, Any]
) -> dict[str, Any] | None:
    """Build the 'ask this next' slice for the interviewer prompt (no LLM).

    ``None`` when every competency is covered — the interviewer then wraps up /
    explores freely exactly as it did before the planner existed.
    """

    if not coverage or not plan:
        return None
    target = next_target_id(coverage)
    if target is None:
        return None
    bank = next(
        (
            b
            for b in (plan.get("question_bank") or [])
            if isinstance(b, dict) and str(b.get("competency_id")) == target
        ),
        {},
    )
    raw_tiers = bank.get("tiers")
    tiers: dict[str, Any] = raw_tiers if isinstance(raw_tiers, dict) else {}
    tier = str(coverage.get("current_tier") or "intermediate")
    if tier not in caps.DIFFICULTY_TIERS:
        tier = "intermediate"
    candidate = [q for q in [tiers.get(tier), tiers.get("intermediate")] if q]
    return {
        "target_id": target,
        "target_label": _label(coverage, target),
        "target_tier": tier,
        "candidate_questions": candidate[:2],
        "star_target": bool(bank.get("star_target")),
        "covered_labels": [_label(coverage, c) for c in _covered_ids(coverage)],
        "remaining_labels": [_label(coverage, c) for c in _remaining_ids(coverage)][:8],
    }


def coverage_summary(coverage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Leak-safe 'what's covered / what's left' summary for the presenter."""

    if not coverage or not coverage.get("order"):
        return None
    covered = [_label(coverage, c) for c in _covered_ids(coverage) if _label(coverage, c)]
    remaining = [_label(coverage, c) for c in _remaining_ids(coverage) if _label(coverage, c)]
    total = len(coverage.get("order") or [])
    return {
        "total": total,
        "covered_count": len(covered),
        "covered": covered,
        "remaining": remaining,
    }
