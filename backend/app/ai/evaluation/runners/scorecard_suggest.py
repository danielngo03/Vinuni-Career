"""Eval runner + checker for the ``scorecard_suggest`` family.

Exercises the real prompt + validation chain from
``scorecard_ai_service.suggest_scorecard`` — ``generate_json_note`` under the
offline provider, then the REAL (extracted, pure) ``normalize_scorecard_result``/
``fallback_scorecard_result`` functions, bypassing only the DB/RBAC/application-
ownership layer. This is a `human_review` §3 task: the AI never writes a
scorecard, so what matters most here is that a malformed/out-of-range/
hallucinated model response can never produce an invalid score, recommendation,
or confidence value.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

from app.ai.evaluation.models import Probe
from app.modules.recruitment.application import scorecard_ai_service as svc
from app.shared.exceptions import AIUnavailableError


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    llm_json = inp.get("llm_json")
    provider_down = inp.get("provider") == "unavailable"

    async def _fake_generate_json_note(**_kwargs: Any) -> dict:
        if provider_down:
            raise AIUnavailableError()
        return llm_json or {}

    with mock.patch.object(svc, "generate_json_note", new=_fake_generate_json_note):
        try:
            raw = await svc.generate_json_note(
                task_type="scorecard_suggest", system_prompt="", user_content=""
            )
            result = svc.normalize_scorecard_result(raw)
        except AIUnavailableError:
            result = svc.fallback_scorecard_result()
        except Exception as exc:  # defensive — should never happen offline
            return Probe(kind="scorecard_suggest", raised_message=str(exc))

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="scorecard_suggest", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:  # noqa: C901
    """Assertion checks for ``scorecard_suggest`` probes."""
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "is_fallback":
        got: Any = bool(result.get("is_fallback"))
        return None if got == bool(exp) else f"is_fallback expected {exp}, got {got}"
    if key == "recommendation_equals":
        got = result.get("recommendation")
        return None if got == exp else f"recommendation expected {exp!r}, got {got!r}"
    if key == "confidence_equals":
        got = result.get("confidence")
        return None if got == exp else f"confidence expected {exp!r}, got {got!r}"
    if key == "criterion_score_equals":
        field = exp.get("field")
        want = exp.get("value")
        got = (result.get("criteria", {}).get(field) or {}).get("score")
        return None if got == want else f"{field} score expected {want!r}, got {got!r}"
    if key == "all_scores_in_range_or_none":
        for name, entry in (result.get("criteria") or {}).items():
            score = entry.get("score")
            if score is not None and not (1 <= int(score) <= 5):
                return f"{name} score out of range: {score!r}"
        return None
    if key == "all_criteria_present":
        criteria = result.get("criteria") or {}
        expected_keys = {"technical", "communication", "culture_fit", "motivation"}
        missing = expected_keys - set(criteria.keys())
        return None if not missing else f"missing criteria keys: {missing}"
    if key == "reasoning_length_at_most":
        for name, entry in (result.get("criteria") or {}).items():
            n = len(entry.get("reasoning") or "")
            if n > int(exp):
                return f"{name} reasoning length {n} exceeds cap {exp}"
        return None
    if key == "overall_reasoning_length_at_most":
        n = len(result.get("overall_reasoning") or "")
        return None if n <= int(exp) else f"overall_reasoning length {n} exceeds cap {exp}"
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
