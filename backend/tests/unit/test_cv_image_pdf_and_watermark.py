"""Unit tests for image→PDF conversion + partner-download watermark (pure helpers).

Owner decisions 2026-07-10:
- an uploaded IMAGE CV (png/jpg/jpeg/webp) is converted to a PDF for the served
  artifact (``image_pdf``);
- the partner CV DOWNLOAD is stamped with the VinUni logo + "VinUni Career"
  (``pdf_watermark``), while the inline view stays the clean original.
"""

from __future__ import annotations

import io

import fitz
from app.modules.documents.infrastructure import pdf_watermark
from app.modules.documents.infrastructure.image_pdf import (
    image_to_pdf,
    served_upload_artifact,
)


def _png(text: str = "CV") -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (480, 640), "white")
    ImageDraw.Draw(img).text((20, 40), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _image(fmt: str) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 560), "white")
    ImageDraw.Draw(img).text((20, 40), "CV", fill="black")
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# image_to_pdf                                                                 #
# --------------------------------------------------------------------------- #


def test_png_converts_to_single_page_pdf() -> None:
    pdf = image_to_pdf(_png())
    assert pdf is not None
    assert pdf[:5] == b"%PDF-"
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        assert doc.page_count == 1


def test_jpeg_and_webp_convert_to_pdf() -> None:
    for fmt in ("JPEG", "WEBP"):
        pdf = image_to_pdf(_image(fmt))
        assert pdf is not None and pdf[:5] == b"%PDF-", fmt


def test_pdf_page_preserves_aspect_ratio_within_a4() -> None:
    # A portrait CV image must produce a portrait page that fits within A4 bounds.
    pdf = image_to_pdf(_png())
    assert pdf is not None
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        rect = doc[0].rect
    assert rect.height > rect.width  # portrait preserved
    # A4 = 595 x 842 pt; the page fits within those bounds (± rounding).
    assert rect.width <= 596 and rect.height <= 843


def test_corrupt_image_returns_none() -> None:
    assert image_to_pdf(b"\x89PNG\r\n\x1a\n" + b"not-a-real-image" * 4) is None
    assert image_to_pdf(b"") is None
    assert image_to_pdf(b"%PDF-1.4 already a pdf") is None  # not an image


# --------------------------------------------------------------------------- #
# served_upload_artifact                                                       #
# --------------------------------------------------------------------------- #


def test_image_upload_is_served_as_pdf() -> None:
    data, mime, name, ext = served_upload_artifact("resume.png", _png(), "image/png")
    assert mime == "application/pdf"
    assert name == "resume.pdf"
    assert ext == ".pdf"
    assert data[:5] == b"%PDF-"


def test_webp_upload_is_served_as_pdf() -> None:
    data, mime, name, ext = served_upload_artifact("cv.webp", _image("WEBP"), "image/webp")
    assert mime == "application/pdf" and ext == ".pdf" and name == "cv.pdf"
    assert data[:5] == b"%PDF-"


def test_non_image_upload_is_unchanged() -> None:
    pdf_in = b"%PDF-1.4\n...body..."
    data, mime, name, ext = served_upload_artifact("cv.pdf", pdf_in, "application/pdf")
    assert data == pdf_in and mime == "application/pdf" and name == "cv.pdf" and ext == ".pdf"


def test_corrupt_image_upload_keeps_original_bytes() -> None:
    bad = b"\x89PNG\r\n\x1a\n" + b"garbage" * 8
    data, mime, name, ext = served_upload_artifact("broken.png", bad, "image/png")
    # Unconvertible image -> stored as-is; the ingestion cascade rejects it later.
    assert data == bad and mime == "image/png" and ext == ".png"


# --------------------------------------------------------------------------- #
# pdf_watermark.stamp_watermark                                                #
# --------------------------------------------------------------------------- #


def _clean_pdf() -> bytes:
    pdf = image_to_pdf(_png("CANDIDATE"))
    assert pdf is not None
    return pdf


def test_stamp_adds_vinuni_career_text_to_every_page() -> None:
    clean = _clean_pdf()
    stamped = pdf_watermark.stamp_watermark(clean)
    assert stamped[:5] == b"%PDF-"
    assert stamped != clean  # actually modified
    with fitz.open(stream=stamped, filetype="pdf") as doc:
        assert all("VinUni Career" in page.get_text() for page in doc)


def test_clean_pdf_has_no_watermark_text() -> None:
    # Guard the watermark assertion above: the source PDF is genuinely clean.
    clean = _clean_pdf()
    with fitz.open(stream=clean, filetype="pdf") as doc:
        assert all("VinUni Career" not in page.get_text() for page in doc)


def test_stamp_non_pdf_returns_input_unchanged() -> None:
    junk = b"<html><script>alert(1)</script></html>"
    assert pdf_watermark.stamp_watermark(junk) == junk
    assert pdf_watermark.stamp_watermark(b"") == b""


def test_stamp_is_idempotent_shape() -> None:
    # Re-stamping stays a valid PDF and keeps the watermark (non-destructive).
    once = pdf_watermark.stamp_watermark(_clean_pdf())
    twice = pdf_watermark.stamp_watermark(once)
    assert twice[:5] == b"%PDF-"
    with fitz.open(stream=twice, filetype="pdf") as doc:
        assert all("VinUni Career" in page.get_text() for page in doc)
