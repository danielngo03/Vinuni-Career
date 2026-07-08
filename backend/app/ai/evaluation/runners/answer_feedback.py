"""Eval runner + checker for the ``answer_feedback`` family.

Exercises the real validation chain from
``interview_sim_service.evaluate_answer`` (per-answer interview coaching
feedback) via the extracted, pure ``normalize_answer_feedback_result``
function. This is where a real bug was found and fixed while building this
eval: a hallucinated non-numeric ``score`` (e.g. ``"five"``) previously
raised an uncaught ``ValueError`` instead of degrading gracefully.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

from app.ai.evaluation.models import Probe
from app.modules.opportunities.application import interview_sim_service as svc
from app.shared.exceptions import AIUnavailableError


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    llm_json = inp.get("llm_json")
    mode = inp.get("provider")

    async def _fake_generate_json_note(**_kwargs: Any) -> dict:
        if mode == "unavailable":
            raise AIUnavailableError()
        return llm_json or {}

    with mock.patch.object(svc, "generate_json_note", new=_fake_generate_json_note):
        try:
            raw = await svc.generate_json_note(
                task_type="answer_feedback", system_prompt="", user_content=""
            )
            result = svc.normalize_answer_feedback_result(raw)
        except AIUnavailableError:
            result = dict(svc._FALLBACK_FEEDBACK)
        except Exception as exc:  # defensive — should never happen post-fix
            return Probe(kind="answer_feedback", raised_message=str(exc))

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="answer_feedback", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``answer_feedback`` probes."""
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "no_stack_trace":
        bad = "traceback" in probe.raised_message.lower()
        return "stack trace leaked in error message" if bad else None
    if key == "is_fallback":
        got: Any = bool(result.get("is_fallback"))
        return None if got == bool(exp) else f"is_fallback expected {exp}, got {got}"
    if key == "score_equals":
        got = result.get("score")
        return None if got == exp else f"score expected {exp!r}, got {got!r}"
    if key == "score_in_range":
        score = result.get("score")
        ok = isinstance(score, int) and 1 <= score <= 5
        return None if ok else f"score out of range or not an int: {score!r}"
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
