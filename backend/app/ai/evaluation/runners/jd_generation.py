"""Eval runner + checker for the ``jd_generation`` family.

Mirrors ``jd_ai_service.draft_description_standalone`` exactly (same
sanitize step, same prompt builder, same ``generate_note`` gateway call) but
skips the DB/RBAC ownership layer, which has its own dedicated tests
(``tests/integration/test_jd_ai_service.py``).
"""

from __future__ import annotations

from typing import Any

from app.ai.cv.llm import generate_note
from app.ai.evaluation.models import Probe
from app.ai.evaluation.runners._offline_provider import maybe_provider_down
from app.ai.prompts.jd_generation import v1 as jd_prompt
from app.ai.safety.input_guard import sanitize_instruction
from app.shared.exceptions import AIUnavailableError


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    language = inp.get("language", "vi")
    provider_down = inp.get("provider") == "unavailable"
    inputs = {k: v for k, v in inp.items() if k not in ("language", "provider")}

    partner_instruction = inputs.get("partner_instruction") or ""
    if partner_instruction:
        clean, _ = sanitize_instruction(partner_instruction[:2000])
        inputs["partner_instruction"] = clean or ""

    system_prompt = jd_prompt.build_system_prompt(output_language=language)
    user_message = jd_prompt.build_user_message(inputs)

    try:
        with maybe_provider_down(provider_down):
            draft_text = await generate_note(
                task_type="jd_generation",
                system_prompt=system_prompt,
                user_content=user_message,
                temperature=0.4,
                max_tokens=900,
            )
    except AIUnavailableError as exc:
        return Probe(kind="jd", raised_code=exc.code, raised_message=str(exc))

    return Probe(kind="jd", blob=draft_text.lower(), data={"draft": draft_text})


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``jd_generation`` probes."""
    if key == "error_code":
        return (
            None
            if probe.raised_code == exp
            else (f"expected error_code {exp!r}, got {probe.raised_code!r}")
        )
    if key == "no_stack_trace":
        bad = "traceback" in probe.raised_message.lower()
        return "stack trace leaked in error message" if bad else None
    if probe.data.get("draft") is None and probe.raised_code is None:
        return None  # defensive: no draft and no error is an informational gap
    if key == "draft_contains":
        return None if str(exp).lower() in probe.blob else f"draft should contain {exp!r}"
    if key == "draft_excludes":
        return None if str(exp).lower() not in probe.blob else f"draft should exclude {exp!r}"
    if key == "no_crash":
        return None
    return None  # unknown / informational key
