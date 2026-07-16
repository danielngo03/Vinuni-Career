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

import asyncio
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
# Multi-round persona labels (leak-safe, localized product copy)              #
# --------------------------------------------------------------------------- #
# Short human labels for the presenter/room chips. The raw ``persona`` key stays
# internal; only these localized labels are exposed.
_PERSONA_LABELS = {
    "screening": {"vi": "Sơ loại", "en": "Screening"},
    "technical": {"vi": "Chuyên môn", "en": "Technical"},
    "hiring_manager": {"vi": "Nhà tuyển dụng", "en": "Hiring manager"},
}
# Deterministic round display name (used when the plan has no explicit label).
_ROUND_LABELS = {
    "screening": {"vi": "Vòng sơ loại", "en": "Screening round"},
    "technical": {"vi": "Vòng chuyên môn", "en": "Technical round"},
    "hiring_manager": {"vi": "Vòng nhà tuyển dụng", "en": "Hiring manager round"},
}

# Competency labels that read as behavioral/soft (screening/hiring-manager fodder).
_BEHAVIORAL_HINTS = frozenset(
    {
        "motivat", "fit", "communicat", "team", "leadership", "ownership",
        "collaborat", "manage", "culture", "mentor", "stakeholder", "conflict",
        "interpersonal", "adapt", "problem solv", "learning", "growth", "attitude",
    }
)


def _loc(locale: str | None) -> str:
    return "vi" if (locale or "vi").lower().startswith("vi") else "en"


def _persona_label(persona: str | None, locale: str) -> str:
    return _PERSONA_LABELS.get(str(persona or ""), {}).get(_loc(locale), "")


def _competency_kind(label: str, focus: str) -> str:
    """Classify a competency as ``behavioral`` or ``technical`` (deterministic)."""

    low = str(label or "").lower()
    if any(h in low for h in _BEHAVIORAL_HINTS):
        return "behavioral"
    return "behavioral" if focus == "behavioral" else "technical"


# --------------------------------------------------------------------------- #
# Deterministic ROUND derivation (no LLM, no extra model call)                 #
# --------------------------------------------------------------------------- #
def _derive_rounds(
    competency_map: list[dict[str, Any]], grounding: dict[str, Any]
) -> list[dict[str, Any]]:
    """Partition the competency map into 2-3 realistic interview rounds.

    Deterministic and leak-safe: behavioral/intro competencies form a warm
    ``screening`` round, technical competencies form a ``technical`` round, and the
    single highest-weight (or genuine-gap) competency is reserved for a
    ``hiring_manager`` scenario round. Every competency lands in EXACTLY one round
    (a clean partition), so round-by-round progression covers them all. Rounds with
    no competencies are dropped, yielding 1-3 rounds depending on the JD.
    """

    focus = str(grounding.get("focus") or "mixed")
    locale = _loc(grounding.get("locale"))
    comps = [c for c in competency_map if isinstance(c, dict) and c.get("id")]
    if not comps:
        return []
    order = [str(c["id"]) for c in comps]
    kinds = {str(c["id"]): _competency_kind(str(c.get("label") or ""), focus) for c in comps}

    # Reserve ONE hiring-manager competency only when there are enough to fill a
    # third round: a genuine gap with the highest weight, else the highest-weight
    # competency overall (tie-break to the LAST/most-scenario one, not the intro).
    hm_id: str | None = None
    if len(comps) >= 3:
        gaps = [c for c in comps if str(c.get("cv_evidence") or "").lower() == "gap"]
        pool = gaps or comps
        hm = max(pool, key=lambda c: (int(c.get("weight") or 1), order.index(str(c["id"]))))
        hm_id = str(hm["id"])

    screening = [cid for cid in order if cid != hm_id and kinds[cid] == "behavioral"]
    technical = [cid for cid in order if cid != hm_id and kinds[cid] == "technical"]
    # A screening round always opens with background/motivation: if the JD produced
    # no behavioral competency, borrow the most-important technical one to open on.
    if not screening and technical:
        screening = [technical.pop(0)]

    ordered: list[tuple[str, list[str]]] = []
    if screening:
        ordered.append(("screening", screening))
    if technical:
        ordered.append(("technical", technical))
    if hm_id:
        ordered.append(("hiring_manager", [hm_id]))
    if not ordered:  # pathological: all competencies filtered — one screening round
        ordered = [("screening", order)]

    return [
        {
            "id": f"r{i}",
            "label": _ROUND_LABELS[persona][locale],
            "persona": persona,
            "competency_ids": ids,
        }
        for i, (persona, ids) in enumerate(ordered, start=1)
    ]


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
        "rounds": _derive_rounds(competency_map, grounding),
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
        # Rounds are DERIVED deterministically from the (LLM or fallback) competency
        # map — no extra model call, always a clean partition over the final ids.
        "rounds": _derive_rounds(competency_map, grounding),
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
    llm_timeout_s: float = caps.PLAN_LLM_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return the frozen interview plan. Never raises — deterministic on failure.

    Runs ONE metered strong-model call, time-boxed to ``llm_timeout_s``; any
    failure (provider down, invalid JSON, timeout, offline provider in tests)
    degrades to the deterministic plan so session create stays responsive. The
    realtime relay passes a tighter budget (it only needs a coverage hint).
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
        # Time-box the strong-model call: a hung/slow planner must not stall the
        # whole session create. On timeout (or any gateway/parse failure) we use
        # the already-computed deterministic plan, keeping create responsive.
        resp = await asyncio.wait_for(
            runner.complete(
                [
                    AIMessage(role="system", content=system),
                    AIMessage(role="user", content=user),
                ],
                temperature=0.4,
                max_tokens=caps.PLAN_MAX_TOKENS,
            ),
            timeout=llm_timeout_s,
        )
        validated = _validate_llm_plan(_parse_json(resp.text), grounding)
        return validated or deterministic
    except Exception:  # noqa: BLE001 - timeout / gateway / parse failure -> deterministic plan
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
    rounds = plan.get("rounds") or []
    return {
        "version": prompts.PLAN_VERSION,
        "current_tier": tier,
        # The round whose competencies are being probed now (first round at start).
        "current_round": str(rounds[0]["id"]) if rounds else None,
        "order": order,
        "competencies": comps,
    }


# --------------------------------------------------------------------------- #
# Round progression (deterministic, no LLM)                                    #
# --------------------------------------------------------------------------- #
def _next_target_by_rounds(
    plan: dict[str, Any], coverage: dict[str, Any]
) -> tuple[str | None, dict[str, Any] | None]:
    """First uncovered competency in ROUND order + the round it belongs to.

    Round order is the primary progression axis: we finish a round's competencies
    before moving to the next round. Falls back to ``(None, None)`` when the plan
    has no rounds (legacy plan) so the caller uses the flat order instead.
    """

    rounds = plan.get("rounds") or []
    if not rounds:
        return None, None
    covered = set(_covered_ids(coverage))
    for rnd in rounds:
        if not isinstance(rnd, dict):
            continue
        for cid in rnd.get("competency_ids") or []:
            if str(cid) not in covered:
                return str(cid), rnd
    return None, None


def _current_round_id(plan: dict[str, Any], coverage: dict[str, Any]) -> str | None:
    """The round being probed now: the first round with an uncovered competency."""

    _cid, rnd = _next_target_by_rounds(plan, coverage)
    return str(rnd["id"]) if rnd else None


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
    # Advance the round pointer: after marking this competency covered, the current
    # round is whichever round still has an uncovered competency (None when done).
    updated["current_round"] = _current_round_id(plan, updated)
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
    # Round-aware target: finish a round's competencies before the next round, so
    # the persona voice advances screening -> technical -> hiring_manager. Legacy
    # plans (no rounds) fall back to the flat competency order.
    target, rnd = _next_target_by_rounds(plan, coverage)
    if target is None and not (plan.get("rounds") or []):
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
    slice_out: dict[str, Any] = {
        "target_id": target,
        "target_label": _label(coverage, target),
        "target_tier": tier,
        "candidate_questions": candidate[:2],
        "star_target": bool(bank.get("star_target")),
        "covered_labels": [_label(coverage, c) for c in _covered_ids(coverage)],
        "remaining_labels": [_label(coverage, c) for c in _remaining_ids(coverage)][:8],
    }
    if isinstance(rnd, dict):
        slice_out["round_id"] = str(rnd.get("id") or "")
        slice_out["round_label"] = str(rnd.get("label") or "")
        slice_out["persona"] = str(rnd.get("persona") or "")
    return slice_out


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


def round_progress(
    plan: dict[str, Any] | None,
    coverage: dict[str, Any] | None,
    locale: str | None,
) -> dict[str, Any] | None:
    """Leak-safe multi-round progress for the presenter / create / done event.

    Returns ``{"rounds": [{id, label, persona_label, status}], "current_round": id}``
    where ``status`` is ``done`` (all competencies covered), ``active`` (the round
    being probed now), or ``upcoming``. Only labels are exposed — never persona
    keys, competency ids, weights, or scores. ``None`` for a legacy plan with no
    rounds.
    """

    if not plan or not coverage:
        return None
    rounds = plan.get("rounds") or []
    if not rounds:
        return None
    covered = set(_covered_ids(coverage))
    current: str | None = None
    for rnd in rounds:
        if isinstance(rnd, dict) and any(
            str(c) not in covered for c in (rnd.get("competency_ids") or [])
        ):
            current = str(rnd.get("id") or "")
            break
    out: list[dict[str, Any]] = []
    for rnd in rounds:
        if not isinstance(rnd, dict):
            continue
        ids = [str(c) for c in (rnd.get("competency_ids") or [])]
        rid = str(rnd.get("id") or "")
        if ids and all(c in covered for c in ids):
            status = "done"
        elif rid == current:
            status = "active"
        else:
            status = "upcoming"
        out.append(
            {
                "id": rid,
                "label": str(rnd.get("label") or ""),
                "persona_label": _persona_label(rnd.get("persona"), locale or "vi"),
                "status": status,
            }
        )
    return {"rounds": out, "current_round": current}
