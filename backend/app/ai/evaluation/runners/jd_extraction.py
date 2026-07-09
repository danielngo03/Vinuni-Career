"""Eval runner + checker for the ``jd_extraction`` family.

Exercises the REAL ``jd_upload_service.extract_jd_from_upload_with`` pipeline —
including the cascade's key-allowlist strip, the JDExtractionSchema pydantic
validation, and the per-field ``needs_review`` confidence heuristic. Only the
I/O boundaries are mocked: text extraction (``cascade.extract_text``) and the
structurer/vision_runner seams (injected via ``extract_jd_from_upload_with``).
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

from app.ai.evaluation.models import Probe
from app.ai.extraction.adapters.ocr import set_ocr_adapter
from app.ai.extraction.jd import cascade
from app.modules.opportunities.application import jd_upload_service as svc
from app.shared.exceptions import AIUnavailableError


class _NoOcr:
    """Disabled OCR adapter — makes the eval environment-independent."""

    engine_family = "none"
    engine_version = "none"

    @property
    def available(self) -> bool:
        return False

    def recognize(self, data: bytes, langs: str) -> str:
        return ""


async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    raw_text = inp.get("raw_text", "")
    llm_json = inp.get("llm_json") or {}
    provider_down = inp.get("provider") == "unavailable"

    async def _fake_structurer(text: str) -> dict:
        if provider_down:
            raise AIUnavailableError()
        return llm_json

    def _fake_vision(*args: Any, **kwargs: Any):
        return None  # dataset drives the text path

    set_ocr_adapter(_NoOcr())
    try:
        with mock.patch.object(
            cascade,
            "extract_text",
            return_value=type(
                "R",
                (),
                {"text": raw_text, "page_count": 1, "engine": "pdfplumber", "ocr_used": False},
            )(),
        ):
            try:
                result = await svc.extract_jd_from_upload_with(
                    filename="jd.pdf",
                    data=b"%PDF-fake",
                    structurer=_fake_structurer,
                    vision_runner=_fake_vision,
                )
            except Exception as exc:  # noqa: BLE001
                # Prefer details["reason"] (the JD status like "not_a_jd") when
                # present — ValidationFailedError.code is always "VALIDATION_FAILED"
                # (class-level) which is too generic for per-status assertions. Only
                # fall back to .code when details carries no "reason".
                details_reason = (getattr(exc, "details", {}) or {}).get("reason")
                code = details_reason or getattr(exc, "code", None)
                return Probe(kind="jd_extraction", raised_code=code, raised_message=str(exc))
    finally:
        set_ocr_adapter(None)

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="jd_extraction", blob=blob, data=result)


def check(key: str, exp: Any, probe: Probe) -> str | None:
    """Assertion checks for ``jd_extraction`` probes."""
    if key == "error_code":
        return (
            None
            if probe.raised_code == exp
            else (f"expected error_code {exp!r}, got {probe.raised_code!r}")
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
        return None if got == want else (f"{field} needs_review expected {want}, got {got!r}")
    if key == "needs_review":
        got = d.get("needs_review")
        return None if got == exp else f"needs_review expected {exp!r}, got {got!r}"
    if key == "blob_excludes":
        return None if str(exp).lower() not in probe.blob else f"result should exclude {exp!r}"
    if key == "blob_contains":
        return None if str(exp).lower() in probe.blob else f"result should contain {exp!r}"
    return None  # unknown / informational key
