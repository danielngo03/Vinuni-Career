"""Eval runner + checker for the ``interview_prep`` family.

Exercises the real validation chain from
``interview_sim_service.generate_interview_prep`` (job-specific tailored
interview questions — LLM-backed, distinct from the deterministic
``cv_ai.start_interview_sim`` tool covered by the ``interview_sim`` family).
Uses the extracted, pure ``normalize_interview_prep_result`` function.
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
                task_type="interview_sim", system_prompt="", user_content=""
            )
            result = svc.normalize_interview_prep_result(raw)
        except AIUnavailableError:
            result = dict(svc._STATIC_FALLBACK)

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="interview_prep", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``interview_prep`` probes."""
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "is_fallback":
        got = bool(result.get("is_fallback"))
        return None if got == bool(exp) else f"is_fallback expected {exp}, got {got}"
    if key == "question_count_at_most":
        n = len(result.get("questions") or [])
        return None if n <= int(exp) else f"question_count {n} exceeds cap {exp}"
    if key == "question_count_at_least":
        n = len(result.get("questions") or [])
        return None if n >= int(exp) else f"question_count {n} below minimum {exp}"
    if key == "all_questions_are_dicts_with_text":
        for q in result.get("questions") or []:
            if not isinstance(q, dict) or not isinstance(q.get("question"), str):
                return f"malformed question entry leaked: {q!r}"
        return None
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
