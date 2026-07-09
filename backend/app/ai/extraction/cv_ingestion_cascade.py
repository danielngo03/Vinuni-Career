"""Local-first CV ingestion cascade (pure, no DB).

Runs the adapter cascade from ``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3:

1. security + file gates (size / type / security / duplicate);
2. native text extraction (password/corrupt detection);
3. layout-aware extraction if native text is disordered (gated, no-op default);
4. OCR fallback if there is too little native text (gated; unavailable ->
   ``LOW_QUALITY_SCAN``);
5. CV classifier + quality checks (reuses ``cv_validation`` quality codes);
6. deterministic structuring into ``extracted_data`` + ``review_fields``;
7. optional LLM-on-TEXT structuring fallback (disabled by default; text only).

Returns an :class:`IngestionOutcome` with a user-safe ``quality_code`` plus
INTERNAL engine diagnostics. No raw text is logged here; callers persist
``extracted_data`` only on the owner-only ingestion row.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.extraction import cv_validation
from app.ai.extraction.adapters import (
    OCR_TRIGGER_THRESHOLD,
    EnginePolicy,
    LayoutAdapter,
    NativeTextAdapter,
    StructuringAdapter,
    get_ocr_adapter,
    is_cid_corrupted,
    resolve_policy,
    run_llm_structuring,
    run_vision_extraction,
)
from app.ai.extraction.text_extraction import ExtractionError, FileKind, sniff_kind

_SUPPORTED_KINDS = {FileKind.PDF, FileKind.DOCX, FileKind.TXT, FileKind.IMAGE}
_VI_DIACRITICS = "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"


@dataclass(slots=True)
class IngestionOutcome:
    accepted: bool
    quality_code: str
    needs_review: bool = False
    checksum: str | None = None
    detected_language: str | None = None
    mixed_language: bool = False
    page_count: int = 0
    text_length: int = 0
    extracted_data: dict | None = None
    review_fields: list[dict] = field(default_factory=list)
    # INTERNAL diagnostics — never surfaced to users.
    engine_family: str = "none"
    engine_version: str = "none"
    ocr_used: bool = False
    ocr_unavailable: bool = False
    layout_used: bool = False
    llm_used: bool = False
    vision_used: bool = False


def _section_text(section: dict) -> str:
    """Flatten a structured section (entries or items) into plain text.

    Handles both shapes: ``{"items": [{"text"|"name"}]}`` and
    ``{"entries": [{"heading","subheading","note","highlights":[...]}]}``.
    """

    parts: list[str] = []
    for item in section.get("items", []) or []:
        if isinstance(item, dict):
            parts.append(str(item.get("text") or item.get("name") or ""))
    for entry in section.get("entries", []) or []:
        if isinstance(entry, dict):
            parts.append(str(entry.get("heading") or ""))
            parts.append(str(entry.get("subheading") or ""))
            parts.append(str(entry.get("note") or ""))
            hl = entry.get("highlights")
            if isinstance(hl, list):
                parts.extend(str(h) for h in hl)
    return " ".join(p for p in parts if p)


def _mixed_language(text: str) -> bool:
    lowered = text.lower()
    has_vi = any(ch in lowered for ch in _VI_DIACRITICS)
    # crude latin/english signal: ascii letters present beyond the vi set
    has_en = any(c.isascii() and c.isalpha() for c in lowered)
    return has_vi and has_en


def run_cascade(
    filename: str,
    data: bytes,
    *,
    max_bytes: int,
    existing_checksums: tuple[str, ...] | list[str] = (),
    policy: EnginePolicy | None = None,
) -> IngestionOutcome:
    policy = policy or resolve_policy()
    checksum = cv_validation.compute_checksum(data)

    # ---- 1. Security + file gates -------------------------------------------
    if len(data) > max_bytes:
        return IngestionOutcome(False, "FILE_TOO_LARGE", checksum=checksum)
    kind = sniff_kind(filename, data)
    if kind not in _SUPPORTED_KINDS:
        return IngestionOutcome(False, "UNSUPPORTED_FILE_TYPE", checksum=checksum)
    reject = cv_validation.security_gate(data, filename)
    if reject is not None:
        return IngestionOutcome(False, reject, checksum=checksum)
    if checksum in set(existing_checksums):
        return IngestionOutcome(False, "DUPLICATE_FILE", checksum=checksum)

    # ---- 2. Native text extraction ------------------------------------------
    native = NativeTextAdapter(policy.native_pdf)
    try:
        signals = native.extract(filename, data)
    except ExtractionError as exc:
        code = (
            exc.code if exc.code in ("PASSWORD_PROTECTED_FILE", "CORRUPT_FILE") else "CORRUPT_FILE"
        )
        return IngestionOutcome(False, code, checksum=checksum)

    text = signals.text
    engine_family = signals.engine_family
    engine_version = signals.engine_version
    page_count = signals.page_count
    ocr_used = False
    ocr_unavailable = False
    layout_used = False

    # ---- 3. Layout-aware extraction (gated; no-op default) ------------------
    if signals.disordered:
        layout = LayoutAdapter(policy.layout)
        improved = layout.improve(filename, data, signals)
        if improved is not None:
            text = improved.text
            engine_family = improved.engine_family
            engine_version = improved.engine_version
            layout_used = True

    # ---- 4. Vision-first structuring for styled CVs (images AND PDFs) -------
    # The styled, multi-column CV templates students actually upload defeat both
    # local OCR (images) and native text extraction (PDFs interleave columns), so
    # when a multimodal route is configured we use the vision model as the primary
    # structurer for BOTH. For PDFs we also hand it the native text: it reads the
    # page image for correct structure and the embedded text for exact spelling of
    # emails/phones/dates. Local OCR / deterministic parsing remain the offline
    # fallbacks.
    is_image = kind is FileKind.IMAGE
    is_pdf = kind is FileKind.PDF
    cid_corrupted = is_pdf and is_cid_corrupted(text)
    # A PDF needs OCR/vision when image-based (scanned), or when native text is
    # CID-font garbage (visually rich PDF with unreadable encoded glyphs).
    needs_ocr = (
        is_image
        or cid_corrupted
        or (is_pdf and len(text.strip()) < OCR_TRIGGER_THRESHOLD and signals.has_images)
    )
    # Send to vision every image, and every PDF that actually has content (text or
    # images) — a truly empty PDF skips the paid call and classifies as blank.
    vision_candidate = is_image or (is_pdf and bool(text.strip() or signals.has_images))

    vision_structured: dict | None = None
    if policy.vision_enabled and vision_candidate:
        vision_structured = run_vision_extraction(
            data,
            kind,
            enabled=True,
            max_image_px=policy.vision_max_image_px,
            max_pages=policy.vision_max_pages,
            native_text=text if is_pdf else None,
        )
        if vision_structured is not None:
            engine_family = "vision_llm_gateway"
            engine_version = "v1"

    # Local OCR fallback (image / scanned PDF) — only when vision produced nothing
    # (offline/test runs, missing key, model error). Degraded but functional.
    if vision_structured is None and needs_ocr and policy.ocr != "none":
        ocr = get_ocr_adapter()
        if ocr.available:
            try:
                ocr_text = ocr.recognize(data, policy.ocr_langs)
            except Exception:  # noqa: BLE001 - OCR is best-effort
                ocr_text = ""
            if ocr_text.strip():
                text = ocr_text
                engine_family = getattr(ocr, "engine_family", "ocr")
                engine_version = getattr(ocr, "engine_version", "ocr")
                ocr_used = True
            else:
                ocr_unavailable = True
        else:
            ocr_unavailable = True
    elif vision_structured is None and needs_ocr:
        ocr_unavailable = True

    # The document required OCR but neither the OCR engine nor the vision tier
    # could read it -> low-quality scan (docs/CV_INGESTION_EXTRACTION_SPEC.md §4).
    if needs_ocr and not ocr_used and vision_structured is None:
        return IngestionOutcome(
            accepted=False,
            quality_code="LOW_QUALITY_SCAN",
            checksum=checksum,
            page_count=page_count,
            text_length=len(text),
            engine_family=engine_family,
            engine_version=engine_version,
            ocr_used=False,
            ocr_unavailable=True,
            layout_used=layout_used,
        )

    # ---- 6. Vision structuring path -----------------------------------------
    # The vision tier already returned structured data; use it directly.
    if vision_structured is not None:
        extracted = vision_structured["extracted_data"]
        review_fields = vision_structured["review_fields"]
        detected_language = vision_structured.get("detected_language")
        combined_text = " ".join(
            _section_text(section) for section in extracted.values() if isinstance(section, dict)
        )
        return IngestionOutcome(
            accepted=True,
            quality_code="REVIEW_REQUIRED",
            needs_review=any(f.get("needs_review") for f in review_fields),
            checksum=checksum,
            detected_language=detected_language,
            mixed_language=_mixed_language(combined_text),
            page_count=page_count or 1,
            text_length=len(combined_text),
            extracted_data=extracted,
            review_fields=review_fields,
            engine_family=engine_family,
            engine_version=engine_version,
            ocr_used=ocr_used,
            ocr_unavailable=ocr_unavailable,
            layout_used=layout_used,
            vision_used=True,
        )

    # ---- 7. CV classifier + quality checks (text path) ----------------------
    code, needs_review = cv_validation.classify_content(text, kind=kind, ocr_used=ocr_used)
    if not (code == "REVIEW_REQUIRED"):
        return IngestionOutcome(
            accepted=False,
            quality_code=code,
            needs_review=needs_review,
            checksum=checksum,
            page_count=page_count,
            text_length=len(text),
            engine_family=engine_family,
            engine_version=engine_version,
            ocr_used=ocr_used,
            ocr_unavailable=ocr_unavailable,
            layout_used=layout_used,
        )

    # ---- 8. Deterministic structuring (+ optional LLM-on-TEXT) --------------
    structured = StructuringAdapter().structure(text)
    extracted = structured["extracted_data"]
    review_fields = structured["review_fields"]
    detected_language = structured.get("detected_language")

    llm_used = False
    if policy.llm_enabled:
        refined = run_llm_structuring(text, structured)  # text only — never bytes
        if refined is not None:
            extracted = refined.get("extracted_data", extracted)
            review_fields = refined.get("review_fields", review_fields)
            detected_language = refined.get("detected_language", detected_language)
            llm_used = True

    return IngestionOutcome(
        accepted=True,
        quality_code=code,
        needs_review=any(f.get("needs_review") for f in review_fields),
        checksum=checksum,
        detected_language=detected_language,
        mixed_language=_mixed_language(text),
        page_count=page_count,
        text_length=len(text),
        extracted_data=extracted,
        review_fields=review_fields,
        engine_family=engine_family,
        engine_version=engine_version,
        ocr_used=ocr_used,
        ocr_unavailable=ocr_unavailable,
        layout_used=layout_used,
        llm_used=llm_used,
    )


__all__ = ["IngestionOutcome", "run_cascade"]
