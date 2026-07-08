"""Eval runner + checker for the ``cover_letter`` family.

Mirrors ``cover_letter_service.generate_cover_letter``'s AI + static-fallback
dual path exactly (same prompt builder, same ``generate_note`` gateway call,
same static template function) but skips the DB/RBAC/profile-loading layer —
a prompt/safety-layer eval, not an RBAC or job-visibility test.
"""

from __future__ import annotations

from typing import Any

from app.ai.cv.llm import generate_note
from app.ai.evaluation.models import Probe
from app.ai.evaluation.runners._offline_provider import maybe_provider_down
from app.ai.prompts.cover_letter import v1 as cover_prompt
from app.ai.safety.input_guard import sanitize_instruction
from app.modules.opportunities.application.cover_letter_service import _static_draft
from app.shared.exceptions import AIUnavailableError


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    provider_down = inp.get("provider") == "unavailable"
    inputs = {k: v for k, v in inp.items() if k != "provider"}

    student_note = inputs.get("student_note")
    if student_note and str(student_note).strip():
        safe_note, _flags = sanitize_instruction(str(student_note).strip()[:400])
        if safe_note:
            inputs["student_note"] = safe_note
        else:
            inputs.pop("student_note", None)
    else:
        inputs.pop("student_note", None)

    user_content = cover_prompt.build_user_message(inputs)

    try:
        with maybe_provider_down(provider_down):
            draft = await generate_note(
                task_type="cover_letter",
                system_prompt=cover_prompt.STATIC_SYSTEM_PROMPT,
                user_content=user_content,
                temperature=0.35,
                max_tokens=700,
            )
        return Probe(
            kind="cover_letter",
            blob=draft.lower(),
            data={"draft": draft.strip(), "is_fallback": False},
        )
    except AIUnavailableError:
        static = _static_draft(
            inputs.get("title") or "this position",
            inputs.get("company_name") or "the company",
            inputs.get("student_name") or "the student",
        )
        return Probe(
            kind="cover_letter",
            blob=static.lower(),
            data={"draft": static, "is_fallback": True},
        )


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``cover_letter`` probes."""
    d = probe.data
    if key == "is_fallback":
        got = bool(d.get("is_fallback"))
        return None if got == bool(exp) else f"is_fallback expected {exp}, got {got}"
    if key == "draft_contains":
        return None if str(exp).lower() in probe.blob else f"draft should contain {exp!r}"
    if key == "draft_excludes":
        return None if str(exp).lower() not in probe.blob else f"draft should exclude {exp!r}"
    if key == "no_crash":
        return None
    return None  # unknown / informational key
