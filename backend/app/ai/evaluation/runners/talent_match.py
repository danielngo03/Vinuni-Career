"""Eval runner + checker for the ``talent_match`` family (talent-pool rerank).

Exercises the REAL pure functions from
``talent_pool.application.talent_search_service`` — deterministic scoring/tier/
reasons AND the LLM-rerank normalization/scrub/bias guard — bypassing only the
DB/RBAC/pool-loading layer. What matters most for this partner-facing task: a
malformed / hallucinated / injection-laden model response can never leak a raw
score, provider/model, or PII, and an AI-off path always yields useful
deterministic reasons.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.modules.talent_pool.application import talent_search_service as svc


def _run_rerank(inp: dict[str, Any]) -> dict[str, Any]:
    raw_json = inp.get("raw_json") or {}
    valid_refs = {int(r) for r in (inp.get("valid_refs") or [])}
    normalized = svc.normalize_rerank(raw_json, valid_refs=valid_refs)
    out_refs = sorted(normalized.keys())
    reasons_flat = [r for v in normalized.values() for r in v.get("reasons", [])]
    tiers = {ref: v.get("tier") for ref, v in normalized.items()}
    return {
        "kind": "rerank",
        "out_refs": out_refs,
        "tiers": tiers,
        "reasons": reasons_flat,
    }


def _run_deterministic(inp: dict[str, Any]) -> dict[str, Any]:
    query_terms = svc.tokenize(
        f"{inp.get('need_text', '')} {' '.join(inp.get('required_skills') or [])} "
        f"{inp.get('query_text', '')}"
    )
    fraction, matched, missing = svc.deterministic_match(
        query_terms=query_terms,
        required_skills=list(inp.get("required_skills") or []),
        candidate_skills=list(inp.get("candidate_skills") or []),
        candidate_text=str(inp.get("candidate_text") or ""),
    )
    tier = svc.tier_from_fraction(fraction)
    reasons = svc.deterministic_reasons(
        matched_skills=matched,
        missing=missing,
        years=inp.get("years"),
        locale=str(inp.get("locale") or "vi"),
    )
    return {
        "kind": "deterministic",
        "tier": tier,
        "reasons": reasons,
        "matched_skills": matched,
        "missing": missing,
    }


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    mode = inp.get("mode", "deterministic")
    if mode == "rerank":
        result = _run_rerank(inp)
    else:  # "deterministic" | "fallback"
        result = _run_deterministic(inp)
    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="talent_match", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "tier_equals":
        got = result.get("tier")
        return None if got == exp else f"tier expected {exp!r}, got {got!r}"
    if key == "tier_in":
        allowed = exp if isinstance(exp, list) else [exp]
        got = result.get("tier")
        return None if got in allowed else f"tier {got!r} not in {allowed!r}"
    if key == "reason_count_at_most":
        n = len(result.get("reasons") or [])
        return None if n <= int(exp) else f"reason count {n} exceeds cap {exp}"
    if key == "reasons_nonempty":
        n = len(result.get("reasons") or [])
        return None if n > 0 else "expected at least one reason"
    if key == "all_reasons_are_strings":
        bad = [r for r in (result.get("reasons") or []) if not isinstance(r, str)]
        return None if not bad else f"non-string reasons leaked: {bad!r}"
    if key == "reason_length_at_most":
        for r in result.get("reasons") or []:
            if len(r) > int(exp):
                return f"reason length {len(r)} exceeds cap {exp}"
        return None
    if key == "out_refs_subset":
        allowed_refs = {int(r) for r in exp}
        bad = [r for r in (result.get("out_refs") or []) if r not in allowed_refs]
        return None if not bad else f"unexpected refs leaked: {bad!r}"
    if key == "out_ref_count_equals":
        n = len(result.get("out_refs") or [])
        return None if n == int(exp) else f"out_ref count expected {exp}, got {n}"
    if key == "matched_contains":
        want = [str(x).lower() for x in (exp if isinstance(exp, list) else [exp])]
        got = {str(x).lower() for x in (result.get("matched_skills") or [])}
        missing = [w for w in want if w not in got]
        return None if not missing else f"matched_skills missing {missing!r}"
    if key == "missing_contains":
        want = [str(x).lower() for x in (exp if isinstance(exp, list) else [exp])]
        got = {str(x).lower() for x in (result.get("missing") or [])}
        absent = [w for w in want if w not in got]
        return None if not absent else f"missing gaps absent {absent!r}"
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
