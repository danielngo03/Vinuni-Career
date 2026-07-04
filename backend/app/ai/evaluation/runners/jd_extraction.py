"""Eval runner + checker for the ``jd_extraction`` family.

Exercises the REAL ``jd_upload_service.extract_jd_from_upload`` pipeline —
including the key-allowlist strip, the new ``JDExtractionSchema`` pydantic
validation, and the per-field ``needs_review`` confidence heuristic added
this batch (§10.1 gap: JD extraction previously had no schema validation and
no eval dataset). Only the two I/O boundaries are mocked: text extraction
(``extract_text`` — real PDF/OCR parsing is covered by its own extraction
adapter tests) and the LLM JSON call (``generate_json_note`` — offline
provider text is not valid JSON, so a canned dict/exception stands in for
"what the model returned", exactly like ``recommend.py`` stubs the reranker
boundary).
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

from app.ai.evaluation.models import Probe
from app.modules.opportunities.application import jd_upload_service as svc
from app.shared.exceptions import AIUnavailableError


class _FakeExtraction:
    def __init__(self, text: str) -> None:
        self.text = text


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    raw_text = inp.get("raw_text", "")
    llm_json = inp.get("llm_json") or {}
    provider_down = inp.get("provider") == "unavailable"

    async def _fake_generate_json_note(**kwargs: Any) -> dict:
        if provider_down:
            raise AIUnavailableError()
        return llm_json

    with (
        mock.patch.object(svc, "extract_text", return_value=_FakeExtraction(raw_text)),
        mock.patch.object(svc, "generate_json_note", new=_fake_generate_json_note),
    ):
        try:
            result = await svc.extract_jd_from_upload(
                filename="jd.pdf", data=b"%PDF-fake", content_type="application/pdf"
            )
        except Exception as exc:
            code = getattr(exc, "code", None)
            return Probe(kind="jd_extraction", raised_code=code, raised_message=str(exc))

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="jd_extraction", blob=blob, data=result)


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``jd_extraction`` probes."""
    if key == "error_code":
        return None if probe.raised_code == exp else (
            f"expected error_code {exp!r}, got {probe.raised_code!r}"
        )
    if key == "no_stack_trace":
        bad = "traceback" in probe.raised_message.lower()
        return "stack trace leaked in error message" if bad else None
    if key == "no_crash":
        return None

    d = probe.data or {}
    if key == "is_ai_extraction":
        got = d.get("is_ai_extraction")
        return None if got == exp else f"is_ai_extraction expected {exp!r}, got {got!r}"
    if key == "field_equals":
        field = exp.get("field")
        want = exp.get("value")
        got = d.get(field)
        return None if got == want else f"{field} expected {want!r}, got {got!r}"
    if key == "field_absent":
        got = d.get(exp)
        empty = got in (None, "", [], {})
        return None if empty else f"{exp} should be absent/empty, got {got!r}"
    if key == "field_needs_review":
        field = exp.get("field")
        want = bool(exp.get("value"))
        got = (d.get("field_confidence", {}).get(field) or {}).get("needs_review")
        return None if got == want else (
            f"{field} needs_review expected {want}, got {got!r}"
        )
    if key == "needs_review":
        got = d.get("needs_review")
        return None if got == exp else f"needs_review expected {exp!r}, got {got!r}"
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
