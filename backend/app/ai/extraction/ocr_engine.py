from __future__ import annotations

import logging
from pathlib import Path

from app.ai.ingestion.gatekeeper import detect_file_kind, extract_text_for_gatekeeping

logger = logging.getLogger(__name__)


class ExtractionUnavailableError(RuntimeError):
    """The file is valid, but no configured extractor can process it."""


class OCREngine:
    """Local text extractor with explicit failure instead of fabricated content.

    Native text and DOCX are handled deterministically. PDF extraction uses
    pypdf when the optional AI dependencies are installed, then falls back to
    the conservative gatekeeper parser. Image OCR must be supplied by a real
    vision/OCR adapter.
    """

    def extract_text_from_file(self, file_path: str, mime_type: str | None = None) -> str:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        content = path.read_bytes()
        kind = detect_file_kind(content)
        logger.info("Extracting %s document from %s", kind, path)

        if kind in {"text", "docx"}:
            text = extract_text_for_gatekeeping(content, kind)
        elif kind == "pdf":
            text = self._extract_pdf(path, content)
        elif kind == "image":
            raise ExtractionUnavailableError(
                "Image OCR requires a configured vision extraction provider"
            )
        else:
            raise ExtractionUnavailableError(
                f"Unsupported document format for {path.name} ({mime_type or 'unknown MIME'})"
            )
        if not text.strip():
            raise ExtractionUnavailableError(
                f"No text could be extracted from {path.name}; OCR/VLM processing is required"
            )
        return text

    def _extract_pdf(self, path: Path, content: bytes) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            return extract_text_for_gatekeeping(content, "pdf")

        try:
            reader = PdfReader(path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pypdf extraction failed for %s: %s", path, exc)
            return extract_text_for_gatekeeping(content, "pdf")


ocr_engine = OCREngine()
