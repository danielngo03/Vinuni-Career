"""Partner-download PDF watermark (VinUni logo + "VinUni Career").

Owner decision 2026-07-10 (``docs/SECURITY_PRIVACY.md``: partner CV downloads are
watermarked): the partner INLINE VIEW stays the clean original file, but the
partner DOWNLOAD (``Content-Disposition: attachment``) is stamped with the VinUni
logo + the text "VinUni Career" so a downloaded CV is visibly a controlled copy.

Approach (PyMuPDF / ``fitz`` — already a dependency; no ``reportlab``/``pypdf``):
- a subtle, tiled DIAGONAL "VinUni Career" text at low opacity across every page
  (non-destructive, readable — the CV underneath stays legible), plus
- a footer strip with the VinUni logo + "VinUni Career" on every page.

Robustness:
- best-effort: any failure (non-PDF bytes, corrupt PDF, missing lib) returns the
  ORIGINAL bytes unchanged, so the download never breaks. It NEVER raises.
- the logo is a bundled backend asset (``assets/vinuni-logo.png``); when the asset
  is missing the watermark degrades to TEXT-ONLY (still "VinUni Career") rather
  than crashing on a hardcoded path.
- stamping preserves the PDF magic (``%PDF``), so the stored-XSS hardening
  (nosniff + sandbox CSP + attachment) in the serving path is unaffected.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

WATERMARK_TEXT = "VinUni Career"

# Bundled logo asset (copied from the shared VinUni brand kit). Optional: the
# watermark falls back to text-only when it is absent.
_LOGO_PATH = Path(__file__).parent / "assets" / "vinuni-logo.png"

# Visual tuning — subtle + non-destructive.
_DIAG_FONTSIZE = 22.0
_DIAG_OPACITY = 0.10
_DIAG_COLOR = (0.55, 0.55, 0.55)
_DIAG_ANGLE = 45
_DIAG_STEP_X = 240.0
_DIAG_STEP_Y = 170.0
_FOOTER_FONTSIZE = 8.5
_FOOTER_OPACITY = 0.55
_FOOTER_COLOR = (0.40, 0.40, 0.40)
_LOGO_MAX_PT = 16.0  # footer logo box size in PDF points


def _logo_bytes() -> bytes | None:
    """Return bundled logo bytes, or ``None`` when the asset is absent/unreadable."""

    try:
        if _LOGO_PATH.is_file():
            return _LOGO_PATH.read_bytes()
    except Exception:  # noqa: BLE001 - never let a missing asset break a download
        return None
    return None


def _stamp_page(page, logo: bytes | None) -> None:
    import fitz

    rect = page.rect
    width, height = rect.width, rect.height

    # 1) Tiled diagonal "VinUni Career" across the whole page (subtle).
    mat = fitz.Matrix(_DIAG_ANGLE)
    y = _DIAG_STEP_Y * 0.5
    while y < height + _DIAG_STEP_Y:
        x = -_DIAG_STEP_X * 0.25
        while x < width:
            pivot = fitz.Point(x, y)
            try:
                page.insert_text(
                    pivot,
                    WATERMARK_TEXT,
                    fontsize=_DIAG_FONTSIZE,
                    fontname="helv",
                    color=_DIAG_COLOR,
                    fill_opacity=_DIAG_OPACITY,
                    morph=(pivot, mat),
                    overlay=True,
                )
            except Exception:  # noqa: BLE001 - skip a bad glyph cell, keep going
                pass
            x += _DIAG_STEP_X
        y += _DIAG_STEP_Y

    # 2) Footer: logo (if available) + "VinUni Career" text, bottom-left.
    margin = 28.0
    baseline_y = height - 20.0
    text_x = margin
    if logo is not None:
        try:
            logo_rect = fitz.Rect(
                margin, height - margin - _LOGO_MAX_PT, margin + _LOGO_MAX_PT, height - margin
            )
            page.insert_image(logo_rect, stream=logo, keep_proportion=True, overlay=True)
            text_x = margin + _LOGO_MAX_PT + 6.0
        except Exception:  # noqa: BLE001 - logo optional; fall back to text-only
            text_x = margin
    try:
        page.insert_text(
            fitz.Point(text_x, baseline_y),
            WATERMARK_TEXT,
            fontsize=_FOOTER_FONTSIZE,
            fontname="helv",
            color=_FOOTER_COLOR,
            fill_opacity=_FOOTER_OPACITY,
            overlay=True,
        )
    except Exception:  # noqa: BLE001
        pass


def stamp_watermark(pdf_bytes: bytes) -> bytes:
    """Stamp the VinUni logo + "VinUni Career" onto every page of a PDF.

    Best-effort and non-raising: returns the ORIGINAL bytes unchanged when the
    input is not a PDF, PyMuPDF is unavailable, or stamping fails for any reason.
    """

    if not pdf_bytes[:5] == b"%PDF-":
        return pdf_bytes

    try:
        import fitz
    except Exception:  # noqa: BLE001 - PyMuPDF missing -> serve original
        logger.warning("pdf_watermark: PyMuPDF unavailable; serving un-watermarked download")
        return pdf_bytes

    logo = _logo_bytes()
    if logo is None:
        logger.info("pdf_watermark: logo asset missing; using text-only watermark")

    doc = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.needs_pass:  # cannot stamp an encrypted PDF
            return pdf_bytes
        for page in doc:
            _stamp_page(page, logo)
        out = doc.tobytes()
    except Exception:  # noqa: BLE001 - any failure -> serve the original bytes
        logger.warning("pdf_watermark: stamping failed; serving un-watermarked download")
        return pdf_bytes
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:  # noqa: BLE001
                pass

    out_bytes = bytes(out)
    return out_bytes if out_bytes[:5] == b"%PDF-" else pdf_bytes


__all__ = ["stamp_watermark", "WATERMARK_TEXT"]
