"""Eval runner + checker for the ``market_intelligence`` family.

Exercises the REAL report composition
(``market_intelligence_service.build_report``, pure) and the REAL narrative
path (``narrate_report`` → ``app.ai.cv.llm.generate_note`` under the OFFLINE
provider, or the ``_offline_provider.DownProvider`` for fallback cases). No
DB: aggregates come straight from the case input, mirroring what
``_collect_aggregates`` would return.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.evaluation.models import Probe
from app.ai.evaluation.runners._offline_provider import maybe_provider_down
from app.modules.dashboards.application import market_intelligence_service as svc


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}

    def _int(key: str) -> int:
        try:
            return int(inp.get(key, 0))
        except (TypeError, ValueError):
            return 0

    raw_et = inp.get("employment_type_counts")
    raw_skills = inp.get("skill_counts")
    report = svc.build_report(
        active_jobs=_int("active_jobs"),
        jobs_last_30d=_int("jobs_last_30d"),
        jobs_prev_30d=_int("jobs_prev_30d"),
        employment_type_counts=raw_et if isinstance(raw_et, dict) else {},
        skill_counts=raw_skills if isinstance(raw_skills, dict) else {},
        disclosed_salary_jobs=_int("disclosed_salary_jobs"),
    )

    narrative: str | None = None
    if not report["low_signal"]:
        with maybe_provider_down(inp.get("provider") == "unavailable"):
            narrative = await svc.narrate_report(report)

    payload = {
        **report,
        "ai_narrative": narrative,
        "ai_narrative_available": narrative is not None,
    }
    return Probe(
        kind="market_intelligence",
        blob=json.dumps(payload, ensure_ascii=False).lower(),
        data=payload,
    )


def check(key: str, exp: Any, probe: Probe) -> str | None:
    d = probe.data
    if key in ("trend", "active_jobs", "jobs_last_30d", "salary_disclosure_rate"):
        got = d.get(key)
        return None if got == exp else f"{key} expected {exp!r}, got {got!r}"
    if key == "low_signal":
        got = bool(d.get("low_signal"))
        return None if got == bool(exp) else f"low_signal expected {exp}, got {got}"
    if key == "ai_narrative_available":
        got = bool(d.get("ai_narrative_available"))
        return None if got == bool(exp) else (
            f"ai_narrative_available expected {exp}, got {got}"
        )
    if key == "top_skill":
        skills = [s.get("skill") for s in d.get("top_skills") or []]
        first = skills[0] if skills else None
        return None if first == exp else f"top_skill expected {exp!r}, got {first!r}"
    if key == "employment_type_count":
        n = len(d.get("employment_types") or [])
        return None if n == int(exp) else (
            f"employment_type_count expected {exp}, got {n}"
        )
    if key == "no_crash":
        return None
    return None  # unknown / informational key
