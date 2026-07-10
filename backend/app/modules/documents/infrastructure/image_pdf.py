"""Wrap an uploaded raster-image CV into a single-page PDF (Pillow-only).

Owner decision 2026-07-10: when a student uploads an IMAGE CV (png/jpg/jpeg/webp),
the backend converts it to a PDF so the STORED/SERVED artifact is always a PDF.
That gives one viewer path (the recruiter always embeds a PDF) and a
watermarkable download (see ``pdf_watermark``). The vision-LLM extraction tier
may still receive the downscaled ORIGINAL image; only the served/downloaded
artifact becomes a PDF.

Design notes:
- Pillow-only (no new dependency; ``reportlab``/``pypdf`` are not installed). The
  image is flattened to RGB, its long edge is capped to keep the PDF small, and
  the PDF page is sized to the image aspect ratio scaled to fit within A4 bounds
  (no letterboxing, no distortion — the page simply matches the CV image).
- Best-effort: an unreadable/corrupt/exotic image returns ``None`` and the caller
  keeps the original bytes (the ingestion cascade then makes the final
  accept/reject decision). Conversion NEVER raises, so a hostile or truncated
  image can never crash the upload path.
- A decompression-bomb image raises inside Pillow (``Image.MAX_IMAGE_PIXELS``) and
  is caught here -> ``None`` (rejected downstream, never rendered).
"""

from __future__ import annotations

import io
from pathlib import PurePosixPath

# Long-edge cap for the embedded image. Keeps the generated PDF small while
# staying comfortably readable for a full-page CV (an A4 page at ~150dpi is
# ~1240x1754px, so 1754 preserves crisp text without bloating storage).
_MAX_LONG_EDGE_PX = 1754

# A4 physical size in inches (portrait). Used to pick a DPI that fits the image
# within an A4 page while preserving its exact aspect ratio.
_A4_WIDTH_IN = 8.27
_A4_HEIGHT_IN = 11.69
_MIN_DPI = 72.0


def image_to_pdf(data: bytes) -> bytes | None:
    """Convert raster-image bytes to a single-page PDF, or ``None`` on failure.

    Preserves aspect ratio; caps resolution; never raises. Supports every raster
    format Pillow can decode (png/jpg/jpeg/webp and more).
    """

    try:
        from PIL import Image
    except Exception:  # noqa: BLE001 - Pillow missing -> keep original bytes
        return None

    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()  # force full decode so truncated/corrupt bytes fail here
            img = opened.convert("RGB")

            longest = max(img.size)
            if longest > _MAX_LONG_EDGE_PX:
                scale = _MAX_LONG_EDGE_PX / float(longest)
                img = img.resize(
                    (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
                )

            width_px, height_px = img.size
            # DPI so the image fits within A4 bounds preserving aspect ratio; the
            # constraining edge maps to the A4 edge, the other stays inside it.
            dpi = max(width_px / _A4_WIDTH_IN, height_px / _A4_HEIGHT_IN, _MIN_DPI)

            buf = io.BytesIO()
            img.save(buf, format="PDF", resolution=float(dpi))
            out = buf.getvalue()
    except Exception:  # noqa: BLE001 - corrupt/exotic/bomb image -> keep original
        return None

    # Sanity check: a real PDF was produced.
    return out if out[:5] == b"%PDF-" else None


def _swap_ext(filename: str, new_suffix: str) -> str:
    """Replace a filename's extension (image CV → ``.pdf``); keep it bounded."""

    stem = PurePosixPath(filename).stem or "cv"
    return f"{stem}{new_suffix}"[:500]


def _ext(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix if len(suffix) <= 10 else ""


def served_upload_artifact(
    filename: str, data: bytes, content_type: str | None
) -> tuple[bytes, str, str, str]:
    """Resolve the bytes/mime/name/ext actually STORED and SERVED for an upload.

    Owner decision 2026-07-10: an uploaded IMAGE CV (png/jpg/jpeg/webp) becomes a
    PDF so the served/downloaded artifact is always a PDF (one viewer path,
    watermarkable download). Non-images — or an image Pillow cannot convert
    (corrupt/exotic/decompression-bomb) — are stored unchanged; the ingestion
    cascade then makes the final accept/reject decision, so conversion never
    blocks the upload path.

    Returns ``(stored_bytes, stored_mime, stored_name, stored_ext)``. This is the
    single source of truth for image→PDF conversion shared by both upload paths.
    """

    from app.ai.extraction.text_extraction import FileKind, sniff_kind

    default_mime = (content_type or "application/octet-stream")[:100]
    if sniff_kind(filename, data) is FileKind.IMAGE:
        pdf = image_to_pdf(data)
        if pdf is not None:
            return pdf, "application/pdf", _swap_ext(filename, ".pdf"), ".pdf"
    return data, default_mime, filename[:500], _ext(filename)


__all__ = ["image_to_pdf", "served_upload_artifact"]
