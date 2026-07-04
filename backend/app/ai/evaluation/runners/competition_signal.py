"""Eval runner + checker for the ``competition_signal_explanation`` family.

Exercises the REAL deterministic scoring pipeline from
``app.modules.opportunities.application.competition_service`` —
``compute_jd_complexity`` / ``compute_signal`` / ``map_raw_to_level`` — plus
the REAL optional AI-enrichment gate ``_maybe_explain`` (§3 table: `restricted`
to an advisory one-sentence rationale, never the decision itself). This
family does not fake the DB/Job ORM layer (``competition_signal``'s outer
function loads a real ``Job`` row and a cross-module application count) —
that HTTP/DB integration is covered by the module's own integration tests.
What matters for the offline AI gate is the deterministic score never being
overridden by the model, and the optional explanation degrading safely
(never invented data, never leaking provider/model internals, never running
at all unless BOTH the real-provider gate AND the admin toggle are on —
which is exactly what ``real_provider_active``/``runtime_config.current()``
are mocked here to control).

``real_provider_active`` and ``generate_note`` are both imported at module
level in ``competition_service``, so they are patched directly on the
service module object (not its source module) — the same pattern as
``scorecard_suggest.py``/``jd_extraction.py``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest import mock

from app.ai.evaluation.models import Probe
from app.modules.opportunities.application import competition_service as svc
from app.shared.exceptions import AIUnavailableError


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    experience_min_years = inp.get("experience_min_years")
    required_skills_count = int(inp.get("required_skills_count", 0))
    employment_type = inp.get("employment_type", "full_time")
    application_count = int(inp.get("application_count", 0))
    show_count = bool(inp.get("show_application_count", False))

    real_provider_active_flag = bool(inp.get("real_provider_active", False))
    explanation_enabled = bool(inp.get("explanation_enabled", True))
    ai_text = inp.get("ai_text")
    provider_down = inp.get("provider") == "unavailable"

    jd_complexity, exp_tier, skills_tier = svc.compute_jd_complexity(
        experience_min_years=experience_min_years,
        required_skills_count=required_skills_count,
        employment_type=employment_type,
    )
    raw, level = svc.compute_signal(
        jd_complexity=jd_complexity, application_count=application_count
    )

    async def _fake_generate_note(**_kwargs: Any) -> str:
        if provider_down:
            raise AIUnavailableError()
        return ai_text if ai_text is not None else "Vai trò này có mức độ cạnh tranh phù hợp."

    with (
        mock.patch.object(svc, "real_provider_active", return_value=real_provider_active_flag),
        mock.patch.object(
            svc.runtime_config,
            "current",
            return_value=SimpleNamespace(job_fit_ai_explanation_enabled=explanation_enabled),
        ),
        mock.patch.object(svc, "generate_note", new=_fake_generate_note),
    ):
        try:
            explanation, available = await svc._maybe_explain(
                job_title=inp.get("job_title", "Software Engineer Intern"),
                level=level,
                experience_tier=exp_tier,
                skills_tier=skills_tier,
                employment_type=employment_type,
            )
        except Exception as exc:  # defensive — should never happen offline
            return Probe(kind="competition_signal", raised_message=str(exc))

    result = {
        "level": level,
        "label": svc._LEVEL_LABELS[level],
        "explanation": explanation,
        "ai_explanation_available": available,
        "basis": "estimated",
        "jd_complexity_score": jd_complexity,
        "raw_score": raw,
        "application_count": application_count if show_count else None,
    }
    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="competition_signal", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``competition_signal_explanation`` probes."""
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "level_equals":
        got = result.get("level")
        return None if got == exp else f"level expected {exp!r}, got {got!r}"
    if key == "ai_explanation_available":
        got = bool(result.get("ai_explanation_available"))
        return None if got == bool(exp) else (
            f"ai_explanation_available expected {exp}, got {got}"
        )
    if key == "explanation_is_none":
        got = result.get("explanation") is None
        return None if got == bool(exp) else f"explanation_is_none expected {exp}, got {got}"
    if key == "application_count_is_none":
        got = result.get("application_count") is None
        return None if got == bool(exp) else (
            f"application_count_is_none expected {exp}, got {got}"
        )
    if key == "application_count_equals":
        got = result.get("application_count")
        return None if got == exp else f"application_count expected {exp!r}, got {got!r}"
    if key == "jd_complexity_score_equals":
        got = result.get("jd_complexity_score")
        return None if got == exp else f"jd_complexity_score expected {exp!r}, got {got!r}"
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
