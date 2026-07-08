"""Eval runner + checker for the ``cv_edit_command`` family
(``ai_edit_command`` — natural-language CV edit, ``docs/CV_STUDIO_SPEC.md``
"Natural-Language AI Editing").

Runs the REAL request path — ``app.ai.safety.input_guard.sanitize_instruction``
(exactly what ``cv_ai_service.request_edit_command`` calls before building
context) followed by ``app.ai.cv.edit_command.generate_cv_edit_patch`` — under
a scripted fake JSON provider (offline, no network). This is intentionally a
separate family from ``cv_ai_suggestions`` because ``ai_edit_command`` is not
in ``run_cv_task``'s ``_HANDLERS`` dispatcher (it is a standalone module with
its own prompt + JSON-operations contract) and needs a fake provider that
returns *scripted operations JSON* per case, unlike the deterministic
grounded-text tasks in ``cv_suggestions.py``.

Dataset ``input`` shape:
```
{
  "language": "vi" | "en",
  "instruction": "<free text, as if typed by the student>",
  "cv_sections": [...],                 # the CV's existing sections
  "raw_notes": "...",                   # optional
  "model_response": {"operations": [...], "explanation": "..."},
  "provider": "unavailable",            # OR
  "malformed_json": true,               # simulates a garbage completion
}
```
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

from app.ai.cv.edit_command import generate_cv_edit_patch
from app.ai.cv.tasks import CvAiContext, CvAiResult
from app.ai.evaluation.leak_checks import no_forbidden_terms
from app.ai.evaluation.models import Probe
from app.ai.gateway.base import AICompletion
from app.ai.safety import input_guard
from app.shared.exceptions import AIUnavailableError


class _ScriptedProvider:
    """Fake provider returning a fixed JSON completion (no network)."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def complete(self, *args: Any, **kwargs: Any) -> AICompletion:
        return AICompletion(text=json.dumps(self._payload), model_alias="offline")


class _GarbageProvider:
    """Fake provider returning non-JSON text — drives the malformed-JSON path."""

    async def complete(self, *args: Any, **kwargs: Any) -> AICompletion:
        return AICompletion(text="not json at all, sorry", model_alias="offline")


class _BrokenProvider:
    """Fake provider that always raises — drives the AI_UNAVAILABLE path."""

    async def complete(self, *args: Any, **kwargs: Any) -> AICompletion:
        raise RuntimeError("provider unavailable (eval fallback case)")


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}

    # Mirrors the real request path: instruction is sanitized (PII redaction +
    # injection-pattern stripping) BEFORE it is ever placed in the prompt.
    instruction_raw = inp.get("instruction")
    instruction, guard_flags = input_guard.sanitize_instruction(instruction_raw)

    ctx = CvAiContext(
        task_type="ai_edit_command",
        language=inp.get("language", "vi"),
        instruction=instruction,
        raw_notes=inp.get("raw_notes"),
        cv_sections=inp.get("cv_sections") or [],
        target_section=inp.get("target_section"),
    )

    provider: _BrokenProvider | _GarbageProvider | _ScriptedProvider
    if inp.get("provider") == "unavailable":
        provider = _BrokenProvider()
    elif inp.get("malformed_json"):
        provider = _GarbageProvider()
    else:
        response = inp.get("model_response") or {"operations": [], "explanation": ""}
        provider = _ScriptedProvider(response)

    try:
        with mock.patch("app.ai.cv.llm.get_provider", lambda: provider):
            result: CvAiResult = await generate_cv_edit_patch(ctx)
    except AIUnavailableError as exc:
        return Probe(kind="cv_edit", raised_code=exc.code, raised_message=str(exc))

    diff = result.to_diff()
    payload = {"status": "pending", "diff": diff}
    return Probe(
        kind="cv_edit",
        blob=json.dumps(payload, ensure_ascii=False).lower(),
        diff=diff,
        after_blob=json.dumps(diff.get("after"), ensure_ascii=False).lower(),
        summary=result.summary,
        data={
            "sanitized_instruction": instruction or "",
            "guard_flags": guard_flags,
            "instruction_raw": instruction_raw or "",
        },
    )


def _after_items(probe: Probe) -> list[Any]:
    diff = probe.diff or {}
    sections = (diff.get("after") or {}).get("sections") or []
    if not sections:
        return []
    content = sections[0].get("content") or {}
    items = content.get("items")
    return items if isinstance(items, list) else []


def check(key: str, exp: Any, probe: Probe) -> str | None:  # noqa: C901
    if key == "error_code":
        return None if probe.raised_code == exp else (
            f"expected error_code {exp!r}, got {probe.raised_code!r}"
        )
    if key == "no_stack_trace":
        bad = "traceback" in probe.raised_message.lower()
        return "stack trace leaked in error message" if bad else None
    if key == "instruction_flagged":
        flags = probe.data.get("guard_flags") or []
        return None if exp in flags else f"expected guard flag {exp!r}, got {flags!r}"
    if key == "sanitized_instruction_not_contains":
        sanitized = (probe.data.get("sanitized_instruction") or "").lower()
        return None if str(exp).lower() not in sanitized else (
            f"sanitized instruction should not contain {exp!r}"
        )
    if probe.diff is None:  # any remaining check needs a diff
        return f"no diff produced (task raised {probe.raised_code!r})"
    if key == "applicable":
        return None if bool(probe.diff.get("applicable")) == bool(exp) else (
            f"applicable expected {exp}, got {probe.diff.get('applicable')}"
        )
    if key == "requires_fact_confirmation":
        got = bool(probe.diff.get("requires_fact_confirmation"))
        return None if got == bool(exp) else (
            f"requires_fact_confirmation expected {exp}, got {got}"
        )
    if key in ("after_contains",):
        return None if str(exp).lower() in (probe.after_blob or "") else (
            f"after content should contain {exp!r}"
        )
    if key.startswith("after_not_contains"):
        return None if str(exp).lower() not in (probe.after_blob or "") else (
            f"after content should NOT contain {exp!r}"
        )
    if key == "after_bullet_count":
        n = len(_after_items(probe))
        return None if n == int(exp) else f"after bullet count expected {exp}, got {n}"
    if key == "unsupported_claims_nonempty":
        got = bool(probe.diff.get("unsupported_claims"))
        return None if got == bool(exp) else (
            f"unsupported_claims nonempty expected {exp}, got {got}"
        )
    if key == "summary_not_contains":
        return None if str(exp).lower() not in (probe.summary or "").lower() else (
            f"summary should not contain {exp!r}"
        )
    if key in ("grounded_in_owner_data_only", "no_evidence_from_other_users"):
        return no_forbidden_terms(probe.blob)
    if key in ("no_crash",):
        return None  # reaching here means the task ran without an unexpected crash
    return None  # unknown / informational key
