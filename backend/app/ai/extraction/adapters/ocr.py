"""OCR fallback adapter (dependency-gated + test-mockable).

OCR runs only when native/layout text is too sparse (scanned PDF or image). The
default engine is Tesseract ``vie+eng`` and is used ONLY when both the python
binding (``pytesseract``) and the ``tesseract`` binary are present. When OCR is
unavailable the cascade records ``LOW_QUALITY_SCAN`` and offers the manual/review
recovery path — it never tells the user an engine is missing
(``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3.4 / §7; ``docs/EDGE_CASES_FAILURE_MODES.md``).

Tests inject a fake engine via :func:`set_ocr_adapter` so the OCR path is covered
without installing Tesseract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OcrEngine(Protocol):
    """An OCR engine: report availability + recognize image/PDF page bytes."""

    engine_family: str
    engine_version: str

    @property
    def available(self) -> bool: ...

    def recognize(self, data: bytes, langs: str) -> str: ...


class TesseractOcrAdapter:
    """Tesseract-backed OCR, available only when binding + binary are present."""

    engine_family = "ocr_tesseract"

    def __init__(self) -> None:
        self._checked = False
        self._available = False
        self.engine_version = "tesseract"

    @property
    def available(self) -> bool:
        if not self._checked:
            self._checked = True
            try:
                import pytesseract

                version = pytesseract.get_tesseract_version()
                self.engine_version = f"tesseract-{version}"
                self._available = True
            except Exception:  # noqa: BLE001 - binding or binary missing
                self._available = False
        return self._available

    def recognize(self, data: bytes, langs: str) -> str:
        """OCR ``data`` (PDF bytes or image bytes) → plain text.

        PDF bytes are rasterized page-by-page via PyMuPDF before being sent to
        Tesseract. Calling ``Image.open`` on raw PDF bytes silently produces an
        empty or corrupt result. Image bytes (PNG/JPEG/TIFF) go directly to
        pytesseract as before.
        """
        import io

        import pytesseract
        from PIL import Image

        if data[:4] == b"%PDF":
            return self._recognize_pdf(data, langs)

        image = Image.open(io.BytesIO(data))
        return (pytesseract.image_to_string(image, lang=langs) or "").strip()

    def _recognize_pdf(self, data: bytes, langs: str) -> str:
        """Rasterize each PDF page to a PIL Image then run Tesseract."""
        import io

        import pytesseract
        from PIL import Image

        pages_text: list[str] = []

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=data, filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                page_text = (pytesseract.image_to_string(img, lang=langs) or "").strip()
                if page_text:
                    pages_text.append(page_text)
            doc.close()
        except ImportError:
            # PyMuPDF not installed — fall through with empty text so the
            # cascade records LOW_QUALITY_SCAN and offers the review path.
            pass
        except Exception:
            pass

        return "\n\n".join(pages_text)


_ocr_adapter: OcrEngine | None = None


def get_ocr_adapter() -> OcrEngine:
    """Process-wide OCR adapter (Tesseract by default; overridable in tests)."""

    global _ocr_adapter
    if _ocr_adapter is None:
        _ocr_adapter = TesseractOcrAdapter()
    return _ocr_adapter


def set_ocr_adapter(adapter: OcrEngine | None) -> None:
    """Override the OCR adapter (test seam). Pass ``None`` to reset to default."""

    global _ocr_adapter
    _ocr_adapter = adapter


__all__ = ["OcrEngine", "TesseractOcrAdapter", "get_ocr_adapter", "set_ocr_adapter"]
