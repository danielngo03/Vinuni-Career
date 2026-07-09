"""Eval runner + checker for the ``recommend_cv_for_job`` family.

Deterministic CV-to-job fit scoring + best-CV recommendation
(``app.ai.cv.job_fit``), mirroring ``documents/.../job_fit_service.py`` for
the OFFLINE path (AI enrichment always disabled — ``real_provider_active``
is patched to ``False`` by the harness for the whole eval run, see
``app.ai.evaluation.harness.run``).
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.cv import job_fit
from app.ai.evaluation.models import Probe
from app.ai.gateway.factory import real_provider_active

DEFAULT_STALE_DAYS = 60


def _present_recommend(
    job: dict[str, Any], cvs: list[dict[str, Any]], stale_days: int
) -> dict[str, Any]:
    """Mirror ``job_fit_service`` for the OFFLINE path (no model call)."""

    cv_inputs = [
        job_fit.CvInput(
            cv_id=str(cv.get("cv_id")),
            title=cv.get("title") or "",
            language=cv.get("language") or "vi",
            sections=cv.get("sections") or [],
            last_updated_days=int(cv.get("last_updated_days") or 0),
        )
        for cv in cvs
    ]
    outcome = job_fit.evaluate(job, cv_inputs, stale_days=stale_days)
    # Optional AI enrichment is gated on a real provider; offline -> never called.
    ai_available = real_provider_active()
    results = [
        {
            "cv_id": fit.cv_id,
            "title": fit.title,
            "score": fit.score,
            "bands": fit.bands.as_dict(),
            "matched_skills": fit.matched_skills,
            "gaps": fit.gaps,
            "stale": fit.stale,
            "last_updated_days": fit.last_updated_days,
            "explanation": None,  # offline: no enrichment string
        }
        for fit in outcome.results
    ]
    return {
        "recommended_cv_id": outcome.recommended_cv_id,
        "results": results,
        "signal": outcome.signal,
        "ai_explanation_available": ai_available,
    }


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    job = inp.get("job") or {}
    cvs = inp.get("cvs") or []
    stale_days = int(inp.get("stale_days", DEFAULT_STALE_DAYS))
    result = _present_recommend(job, cvs, stale_days)
    second = _present_recommend(job, cvs, stale_days)  # determinism probe
    return Probe(
        kind="rec",
        blob=json.dumps(result, ensure_ascii=False).lower(),
        result=result,
        second=second,
        input_cv_ids=[str(cv.get("cv_id")) for cv in cvs],
    )


def _results(probe: Probe) -> list[dict[str, Any]]:
    if probe.result is None:
        return []
    res = probe.result.get("results")
    return res if isinstance(res, list) else []


def _result_by_id(probe: Probe, cv_id: str) -> dict[str, Any] | None:
    return next((r for r in _results(probe) if r.get("cv_id") == cv_id), None)


def check(key: str, exp: Any, probe: Probe) -> str | None:  # noqa: C901
    result = probe.result or {}
    results = _results(probe)
    if key == "recommended_cv_id":
        got = result.get("recommended_cv_id")
        return None if got == exp else f"recommended_cv_id expected {exp!r}, got {got!r}"
    if key == "recommended_in_inputs":
        got = result.get("recommended_cv_id")
        ok = got is None or got in probe.input_cv_ids
        return None if ok else f"recommended {got!r} is not in the owner's CV inputs"
    if key == "signal":
        return (
            None
            if result.get("signal") == exp
            else (f"signal expected {exp!r}, got {result.get('signal')!r}")
        )
    if key == "result_count":
        return (
            None
            if len(results) == int(exp)
            else (f"result_count expected {exp}, got {len(results)}")
        )
    if key == "ranking":
        order = [r.get("cv_id") for r in results]
        return None if order == list(exp) else f"ranking expected {exp}, got {order}"
    if key == "deterministic":
        return (
            None
            if probe.result == probe.second
            else ("re-run produced a different result (non-deterministic)")
        )
    if key == "ai_explanation_available":
        got = bool(result.get("ai_explanation_available"))
        return None if got == bool(exp) else (f"ai_explanation_available expected {exp}, got {got}")
    if key == "explanation_null":
        bad = [r.get("cv_id") for r in results if r.get("explanation") is not None]
        return None if not bad else f"explanation must be null offline; non-null for {bad}"
    if key == "score_in_range":
        for r in results:
            if not (0 <= int(r.get("score", -1)) <= 100):
                return f"score out of range for {r.get('cv_id')!r}: {r.get('score')}"
            for band, val in (r.get("bands") or {}).items():
                if not (0 <= int(val) <= 100):
                    return f"band {band} out of range for {r.get('cv_id')!r}: {val}"
        return None
    if key == "score_gt":
        a = _result_by_id(probe, exp[0])
        b = _result_by_id(probe, exp[1])
        if a is None or b is None:
            return f"score_gt: missing CV in results ({exp})"
        return (
            None
            if a["score"] > b["score"]
            else (f"expected score[{exp[0]}]={a['score']} > score[{exp[1]}]={b['score']}")
        )
    if key in ("matched_contains", "gaps_contains"):
        field_name = "matched_skills" if key == "matched_contains" else "gaps"
        for cv_id, terms in (exp or {}).items():
            row = _result_by_id(probe, cv_id)
            if row is None:
                return f"{key}: no result for {cv_id!r}"
            have = {str(t).lower() for t in row.get(field_name, [])}
            for term in terms:
                if str(term).lower() not in have:
                    return f"{key}: {cv_id!r} {field_name} should contain {term!r}"
        return None
    if key == "stale_flags":
        for cv_id, flag in (exp or {}).items():
            row = _result_by_id(probe, cv_id)
            if row is None:
                return f"stale_flags: no result for {cv_id!r}"
            if bool(row.get("stale")) != bool(flag):
                return f"stale_flags: {cv_id!r} expected {flag}, got {row.get('stale')}"
        return None
    if key == "no_crash":
        return None
    return None  # unknown / informational key
