"""Text-native document extraction with an OCR fallback interface.

Order of operations (``docs/LOCAL_DEV_STACK.md`` §4):

1. Text-native extraction first — pdfplumber (PDF), python-docx (DOCX), UTF-8 (TXT).
2. OCR fallback (Tesseract ``vie+eng``) only when native text is empty/low quality.

Heavy OCR is **not** run by default; an injectable hook keeps Phase 0 lightweight.
Raw PDF bytes never go to an LLM — only extracted text does.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)

# Optional OCR hook: callable(data: bytes, langs: str) -> str. Left unset by
# default so Phase 0 stays lightweight; wired in a later phase.
OcrHook = Callable[[bytes, str], str]
_ocr_hook: OcrHook | None = None


def set_ocr_hook(hook: OcrHook | None) -> None:
    global _ocr_hook
    _ocr_hook = hook


class FileKind(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    IMAGE = "image"
    UNKNOWN = "unknown"


class ExtractionError(Exception):
    """Raised on unrecoverable extraction problems with a machine code."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(slots=True)
class ExtractionResult:
    text: str
    page_count: int = 0
    engine: str = "none"
    ocr_used: bool = False
    warnings: list[str] = field(default_factory=list)


_EXT_MAP = {
    ".pdf": FileKind.PDF,
    ".docx": FileKind.DOCX,
    ".txt": FileKind.TXT,
    ".png": FileKind.IMAGE,
    ".jpg": FileKind.IMAGE,
    ".jpeg": FileKind.IMAGE,
}

_MAGIC = {
    b"%PDF": FileKind.PDF,
    b"PK\x03\x04": FileKind.DOCX,  # zip container (docx)
    b"\x89PNG": FileKind.IMAGE,
    b"\xff\xd8\xff": FileKind.IMAGE,
}


def sniff_kind(filename: str, data: bytes) -> FileKind:
    """Determine file kind via magic bytes first, extension as a hint."""

    for magic, kind in _MAGIC.items():
        if data.startswith(magic):
            return kind
    lower = filename.lower()
    for ext, kind in _EXT_MAP.items():
        if lower.endswith(ext):
            return kind
    # Fall back to treating decodable bytes as text.
    try:
        data.decode("utf-8")
        return FileKind.TXT
    except UnicodeDecodeError:
        return FileKind.UNKNOWN


def _extract_pdf(data: bytes) -> ExtractionResult:
    import pdfplumber  # imported lazily to keep import time low

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = pdf.pages
            parts = [(page.extract_text() or "") for page in pages]
            page_count = len(pages)
    except Exception as exc:  # pdfplumber raises various low-level errors
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise ExtractionError("PASSWORD_PROTECTED_FILE") from exc
        raise ExtractionError("CORRUPT_FILE") from exc

    text = "\n".join(parts).strip()
    result = ExtractionResult(text=text, page_count=page_count, engine="pdfplumber")

    if not text and _ocr_hook is not None:
        from app.core.config import get_settings

        try:
            ocr_text = _ocr_hook(data, get_settings().tesseract_ocr_langs)
        except Exception:  # OCR is best-effort
            ocr_text = ""
        result.text = ocr_text.strip()
        result.ocr_used = True
        result.engine = "tesseract"
    return result


def _extract_docx(data: bytes) -> ExtractionResult:
    import docx  # python-docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError("CORRUPT_FILE") from exc
    paragraphs = [p.text for p in document.paragraphs]
    text = "\n".join(paragraphs).strip()
    return ExtractionResult(text=text, page_count=1, engine="python-docx")


def _extract_txt(data: bytes) -> ExtractionResult:
    try:
        text = data.decode("utf-8").strip()
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1").strip()
        except Exception as exc:
            raise ExtractionError("CORRUPT_FILE") from exc
    return ExtractionResult(text=text, page_count=1, engine="utf-8")


def extract_text(filename: str, data: bytes) -> ExtractionResult:
    """Extract text from a supported document.

    Raises :class:`ExtractionError` with a machine code for unsupported types,
    password-protected, or corrupt files.
    """

    kind = sniff_kind(filename, data)
    if kind is FileKind.PDF:
        return _extract_pdf(data)
    if kind is FileKind.DOCX:
        return _extract_docx(data)
    if kind is FileKind.TXT:
        return _extract_txt(data)
    if kind is FileKind.IMAGE:
        # Images require OCR; only attempt when a hook is wired.
        if _ocr_hook is None:
            return ExtractionResult(text="", page_count=1, engine="none", ocr_used=False)
        from app.core.config import get_settings

        try:
            text = _ocr_hook(data, get_settings().tesseract_ocr_langs)
        except Exception:
            text = ""
        return ExtractionResult(
            text=text.strip(), page_count=1, engine="tesseract", ocr_used=True
        )
    raise ExtractionError("UNSUPPORTED_FILE_TYPE")
