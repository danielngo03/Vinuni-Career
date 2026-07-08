"""Cost-tiered JD ingestion cascade.

Order: file/security gate -> native text -> (image/scanned? -> vision-LLM;
digital text -> skip vision) -> OCR fallback -> is-JD gate -> text-LLM
structuring -> validate + score. Extraction is auto-fill only; nothing persists.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.ai.extraction import cv_validation
from app.ai.extraction.adapters.base import is_cid_corrupted as _is_cid_corrupted
from app.ai.extraction.adapters.ocr import get_ocr_adapter
from app.ai.extraction.jd import structuring as _structuring
from app.ai.extraction.jd import validation as jd_validation
from app.ai.extraction.jd import vision as _vision
from app.ai.extraction.jd.policy import JdEnginePolicy, resolve_jd_policy
from app.ai.extraction.jd.schema import validate_and_score
from app.ai.extraction.text_extraction import (
    ExtractionError,
    FileKind,
    extract_text,
    sniff_kind,
)
from app.shared.exceptions import AIUnavailableError

logger = logging.getLogger(__name__)

_NATIVE_TEXT_MIN = 40  # below this a PDF is treated as scanned/needs-vision

# text_extraction ExtractionError.code -> outcome status
_EXTRACTION_ERROR_STATUS = {
    "PASSWORD_PROTECTED_FILE": "password_protected_file",
    "CORRUPT_FILE": "corrupt_file",
    "UNSUPPORTED_FILE_TYPE": "unsupported_file_type",
}


@dataclass(slots=True)
class JdExtractionOutcome:
    status: str
    fields: dict = field(default_factory=dict)
    field_confidence: dict = field(default_factory=dict)
    needs_review: bool = False
    raw_text_preview: str | None = None
    detected_language: str | None = None
    cv_language_required: str = "any"
    is_ai_extraction: bool = False
    # internal diagnostics — never surfaced to end users
    vision_used: bool = False
    ocr_used: bool = False
    llm_used: bool = False


def _fail(status: str) -> JdExtractionOutcome:
    return JdExtractionOutcome(status=status)


def _finalize(raw_llm: dict, raw_text: str, *, vision_used: bool,
              ocr_used: bool, llm_used: bool) -> JdExtractionOutcome:
    # Treat is_jd=False, is_jd=null/omitted, and is_jd=0 as non-JD.
    # "is False" would silently pass null through as a valid JD.
    if not raw_llm.get("is_jd"):
        return _fail("not_a_jd")
    validated, conf = validate_and_score(raw_llm, raw_text)
    return JdExtractionOutcome(
        status="ok",
        fields=validated,
        field_confidence=conf,
        needs_review=any(e.get("needs_review") for e in conf.values()),
        detected_language=validated.get("detected_language"),
        cv_language_required=validated.get("cv_language_required") or "any",
        is_ai_extraction=True,
        vision_used=vision_used,
        ocr_used=ocr_used,
        llm_used=llm_used,
    )


async def run_jd_cascade(filename: str, data: bytes, *,
                         policy: JdEnginePolicy | None = None,
                         structurer=_structuring.run_jd_text_structuring,
                         vision_runner=_vision.run_jd_vision_extraction) -> JdExtractionOutcome:
    pol = policy or resolve_jd_policy()

    # Tier 0 — file + security gate
    if len(data) > pol.max_bytes:
        return _fail("file_too_large")
    kind = sniff_kind(filename, data)
    if kind not in (FileKind.PDF, FileKind.DOCX, FileKind.TXT, FileKind.IMAGE):
        return _fail("unsupported_file_type")
    if cv_validation.security_gate(data, filename) is not None:
        return _fail("file_rejected_security")

    # Tier 1 — native text (blocking pdfplumber/PyMuPDF -> offload off the loop)
    try:
        extraction = await asyncio.to_thread(extract_text, filename, data)
    except ExtractionError as exc:
        return _fail(_EXTRACTION_ERROR_STATUS.get(exc.code, "corrupt_file"))
    native_text = (extraction.text or "").strip()
    ocr_used = extraction.ocr_used

    is_image = kind is FileKind.IMAGE
    cid_pdf = kind is FileKind.PDF and _is_cid_corrupted(native_text)
    scanned_pdf = kind is FileKind.PDF and len(native_text) < _NATIVE_TEXT_MIN

    # Tier 3 — vision (images / scanned PDFs / CID-font-corrupted PDFs).
    # vision_runner is synchronous (PIL/PyMuPDF rasterize + blocking HTTP) ->
    # offload so it never stalls the request event loop.
    if is_image or scanned_pdf or cid_pdf:
        vision_json = await asyncio.to_thread(
            vision_runner,
            data, kind,
            enabled=pol.vision_enabled,
            max_image_px=pol.vision_max_image_px,
            max_pages=pol.vision_max_pages,
            native_text=native_text or None,
        )
        if isinstance(vision_json, dict):
            return _finalize(vision_json, native_text,
                             vision_used=True, ocr_used=ocr_used, llm_used=False)

        # Tier 4 — OCR fallback when vision produced nothing
        if not native_text:
            adapter = get_ocr_adapter()
            if getattr(adapter, "available", False):
                try:
                    recognized = await asyncio.to_thread(
                        adapter.recognize, data, pol.ocr_langs
                    )
                    native_text = (recognized or "").strip()
                    ocr_used = True
                except Exception:  # noqa: BLE001 - OCR is best-effort
                    native_text = ""

    # Tier 5 — is-JD gate (text path)
    # Hard-stop on clearly invalid content; "insufficient" passes through to LLM
    # which may still extract useful fields from a short-but-valid JD.
    _HARD_REJECT = {"blank", "not_a_jd", "low_quality_scan"}
    status = jd_validation.classify_jd_content(native_text, kind=kind, ocr_used=ocr_used)
    if status in _HARD_REJECT:
        return _fail(status)

    # Tier 6 — text-LLM structuring
    try:
        raw_llm = await structurer(native_text)
    except AIUnavailableError:
        return JdExtractionOutcome(
            status="ai_unavailable",
            is_ai_extraction=False,
            raw_text_preview=native_text[:2000],
            ocr_used=ocr_used,
        )

    # Tier 7 — validate + score
    return _finalize(raw_llm, native_text, vision_used=False, ocr_used=ocr_used, llm_used=True)
