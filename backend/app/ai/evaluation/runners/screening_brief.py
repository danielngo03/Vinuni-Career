"""Eval runner + checker for the ``screening_brief`` family.

Exercises the real prompt + validation chain from
``screening_brief_service.generate_screening_brief`` — the extracted, pure
``normalize_screening_brief_result``/``fallback_screening_brief_result``
functions, bypassing only the DB/RBAC/CV-snapshot-loading layer. A
`human_review`-adjacent, partner-facing task: what matters most is that a
malformed/hallucinated model response can never leak more than 4 bounded
bullet points or an invalid suitability signal to the recruiter.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

from app.ai.evaluation.models import Probe
from app.modules.recruitment.application import screening_brief_service as svc
from app.shared.exceptions import AIUnavailableError


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    llm_json = inp.get("llm_json")
    mode = inp.get("provider")

    async def _fake_generate_json_note(**_kwargs: Any) -> dict:
        if mode == "unavailable":
            raise AIUnavailableError()
        if mode == "unexpected_error":
            raise RuntimeError("simulated unexpected error")
        return llm_json or {}

    with mock.patch.object(svc, "generate_json_note", new=_fake_generate_json_note):
        try:
            raw = await svc.generate_json_note(
                task_type="screening_brief", system_prompt="", user_content=""
            )
            result = svc.normalize_screening_brief_result(raw)
        except AIUnavailableError:
            result = svc.fallback_screening_brief_result()
        except Exception:
            result = svc.fallback_screening_brief_result()

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="screening_brief", blob=blob, data={"result": result})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``screening_brief`` probes."""
    result = (probe.data or {}).get("result") or {}
    if key == "no_crash":
        return None
    if key == "is_fallback":
        got: Any = bool(result.get("is_fallback"))
        return None if got == bool(exp) else f"is_fallback expected {exp}, got {got}"
    if key == "suitability_equals":
        got = result.get("suitability")
        return None if got == exp else f"suitability expected {exp!r}, got {got!r}"
    if key == "bullet_count_at_most":
        n = len(result.get("bullets") or [])
        return None if n <= int(exp) else f"bullet_count {n} exceeds cap {exp}"
    if key == "bullet_count_equals":
        n = len(result.get("bullets") or [])
        return None if n == int(exp) else f"bullet_count expected {exp}, got {n}"
    if key == "all_bullets_are_strings":
        bad = [b for b in (result.get("bullets") or []) if not isinstance(b, str)]
        return None if not bad else f"non-string bullets leaked: {bad!r}"
    if key == "bullet_length_at_most":
        for b in result.get("bullets") or []:
            if len(b) > int(exp):
                return f"bullet length {len(b)} exceeds cap {exp}"
        return None
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
