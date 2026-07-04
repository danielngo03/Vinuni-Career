"""Native (non-OCR) text extraction adapter.

Default lightweight engine is ``pdfplumber`` (always available). A PyMuPDF /
``pymupdf4llm`` path is used ONLY when the dependency is importable AND selected
by ``cv_native_pdf_engine`` — otherwise it transparently falls back to pdfplumber
(``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3.2 / §4). DOCX/TXT go through the
shared deterministic extractors.

Beyond text, the PDF path reports whether pages carry embedded images so the
cascade can tell a SCANNED PDF (image-based -> OCR) apart from a genuinely BLANK
one. Password-protected / corrupt files raise :class:`ExtractionError` with a
stable user-safe code. OCR is NOT done here — the cascade owns the OCR stage.
"""

from __future__ import annotations

import io

from app.ai.extraction.adapters.base import ExtractionSignals, is_disordered
from app.ai.extraction.text_extraction import (
    ExtractionError,
    FileKind,
    extract_text,
    sniff_kind,
)


def pymupdf_available() -> bool:
    """True when a PyMuPDF-backed engine can be imported."""

    try:
        import pymupdf4llm  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        pass
    try:
        import fitz  # noqa: F401  (PyMuPDF)

        return True
    except Exception:  # noqa: BLE001
        return False


def _extract_pdfplumber(data: bytes) -> tuple[str, int, bool]:
    """Return ``(text, page_count, has_images)`` via pdfplumber.

    Raises :class:`ExtractionError` for password/corrupt inputs.
    """

    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = pdf.pages
            parts = [(page.extract_text() or "") for page in pages]
            has_images = any(bool(page.images) for page in pages)
            page_count = len(pages)
    except Exception as exc:  # noqa: BLE001 - pdfplumber raises low-level errors
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise ExtractionError("PASSWORD_PROTECTED_FILE") from exc
        raise ExtractionError("CORRUPT_FILE") from exc
    return "\n".join(parts).strip(), page_count, has_images


def _extract_pymupdf(data: bytes) -> tuple[str, int, bool, str]:
    """Return ``(text, page_count, has_images, version)`` via PyMuPDF."""

    import fitz  # PyMuPDF

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise ExtractionError("PASSWORD_PROTECTED_FILE") from exc
        raise ExtractionError("CORRUPT_FILE") from exc
    try:
        if doc.needs_pass:
            raise ExtractionError("PASSWORD_PROTECTED_FILE")
        parts = [page.get_text("text") or "" for page in doc]
        has_images = any(bool(page.get_images()) for page in doc)
        pages = doc.page_count
    finally:
        doc.close()
    return "\n".join(parts).strip(), pages, has_images, f"pymupdf-{fitz.VersionBind}"


class NativeTextAdapter:
    """Resolve + run the effective native text engine for a document."""

    engine_family = "native"

    def __init__(self, pdf_engine: str = "pdfplumber") -> None:
        if pdf_engine == "pymupdf4llm" and pymupdf_available():
            self.pdf_engine = "pymupdf4llm"
        else:
            self.pdf_engine = "pdfplumber"

    def extract(self, filename: str, data: bytes) -> ExtractionSignals:
        kind = sniff_kind(filename, data)
        if kind is FileKind.PDF:
            if self.pdf_engine == "pymupdf4llm":
                text, pages, has_images, version = _extract_pymupdf(data)
            else:
                text, pages, has_images = _extract_pdfplumber(data)
                version = "pdfplumber"
            return ExtractionSignals(
                text=text,
                page_count=pages,
                engine_family="native_pdf",
                engine_version=version,
                has_images=has_images,
                disordered=is_disordered(text),
            )

        # python-docx / utf-8 / image path (no OCR hook here).
        result = extract_text(filename, data)
        family = {
            FileKind.DOCX: "native_docx",
            FileKind.TXT: "native_txt",
            FileKind.IMAGE: "native_image",
        }.get(kind, "native")
        return ExtractionSignals(
            text=result.text,
            page_count=result.page_count,
            engine_family=family,
            engine_version=result.engine,
            has_images=(kind is FileKind.IMAGE),
            disordered=is_disordered(result.text),
        )


__all__ = ["NativeTextAdapter", "pymupdf_available"]
