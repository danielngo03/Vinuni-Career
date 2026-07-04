"""CV upload validation negative + positive fixtures (vi/en)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.ai.extraction.cv_validation import compute_checksum, validate_cv_upload

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MAX_BYTES = 50 * 1024 * 1024


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_valid_english_cv_accepted_for_review() -> None:
    result = validate_cv_upload("cv_en.txt", _read("cv_en.txt"), max_bytes=MAX_BYTES)
    assert result.accepted is True
    assert result.quality_code == "REVIEW_REQUIRED"
    assert result.needs_review is True


def test_valid_vietnamese_cv_accepted_for_review() -> None:
    result = validate_cv_upload("cv_vi.txt", _read("cv_vi.txt"), max_bytes=MAX_BYTES)
    assert result.accepted is True
    assert result.quality_code == "REVIEW_REQUIRED"


def test_blank_document_rejected() -> None:
    result = validate_cv_upload("blank.txt", _read("blank.txt"), max_bytes=MAX_BYTES)
    assert result.accepted is False
    assert result.quality_code == "BLANK_DOCUMENT"


def test_not_a_cv_rejected_without_llm() -> None:
    result = validate_cv_upload("not_cv.txt", _read("not_cv.txt"), max_bytes=MAX_BYTES)
    assert result.accepted is False
    assert result.quality_code == "NOT_A_CV"


def test_unsupported_file_type_rejected() -> None:
    # A binary blob that is neither PDF/DOCX nor decodable text.
    result = validate_cv_upload("weird.bin", b"\x00\x01\x02\x99\xfe", max_bytes=MAX_BYTES)
    assert result.accepted is False
    assert result.quality_code == "UNSUPPORTED_FILE_TYPE"


def test_file_too_large_rejected() -> None:
    result = validate_cv_upload("cv_en.txt", _read("cv_en.txt"), max_bytes=10)
    assert result.accepted is False
    assert result.quality_code == "FILE_TOO_LARGE"


def test_security_rejected_eicar() -> None:
    payload = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
    result = validate_cv_upload("cv.txt", payload, max_bytes=MAX_BYTES)
    assert result.accepted is False
    assert result.quality_code == "FILE_REJECTED_SECURITY"


def test_corrupt_pdf_rejected() -> None:
    # Valid PDF magic but garbage body -> parser cannot parse.
    result = validate_cv_upload("broken.pdf", b"%PDF-1.4 not really a pdf", max_bytes=MAX_BYTES)
    assert result.accepted is False
    assert result.quality_code in {"CORRUPT_FILE", "PASSWORD_PROTECTED_FILE"}


def test_password_protected_pdf_rejected(monkeypatch) -> None:
    # When the extractor reports an encrypted/locked PDF, the validator must
    # surface PASSWORD_PROTECTED_FILE specifically (not the generic CORRUPT_FILE),
    # with a fix_input recovery path. Patch the extraction boundary so the test is
    # deterministic and does not depend on a binary encrypted-PDF fixture.
    from app.ai.extraction import text_extraction

    def _raise_password(filename: str, data: bytes):  # noqa: ARG001
        raise text_extraction.ExtractionError("PASSWORD_PROTECTED_FILE")

    monkeypatch.setattr(
        "app.ai.extraction.cv_validation.extract_text", _raise_password
    )
    result = validate_cv_upload(
        "locked.pdf", b"%PDF-1.4 encrypted body", max_bytes=MAX_BYTES
    )
    assert result.accepted is False
    assert result.quality_code == "PASSWORD_PROTECTED_FILE"
    assert result.recoverability == "fix_input"
    assert "upload_another" in result.next_actions


def test_low_quality_scan_for_unreadable_image() -> None:
    # An image/scan with no OCR-readable text (no OCR hook wired) is classified as
    # LOW_QUALITY_SCAN, not BLANK_DOCUMENT — exercising cv_validation's image/
    # ocr_used quality_code branch.
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    result = validate_cv_upload("scan.png", png, max_bytes=MAX_BYTES)
    assert result.accepted is False
    assert result.quality_code == "LOW_QUALITY_SCAN"
    assert result.recoverability == "fix_input"


def test_duplicate_file_rejected() -> None:
    data = _read("cv_en.txt")
    checksum = compute_checksum(data)
    result = validate_cv_upload(
        "cv_en.txt", data, max_bytes=MAX_BYTES, existing_checksums=[checksum]
    )
    assert result.accepted is False
    assert result.quality_code == "DUPLICATE_FILE"


def test_insufficient_content_flagged_for_review() -> None:
    # Has a CV signal keyword, passes the blank threshold, but has no contact
    # info and is under the low-quality length threshold.
    text = "Kỹ năng: Python, FastAPI, SQLAlchemy, Redis và Git cơ bản."
    result = validate_cv_upload("short.txt", text.encode("utf-8"), max_bytes=MAX_BYTES)
    assert result.accepted is False
    assert result.quality_code == "INSUFFICIENT_CV_CONTENT"


@pytest.mark.parametrize("name", ["cv_en.txt", "cv_vi.txt", "not_cv.txt", "blank.txt"])
def test_results_never_leak_internals(name: str) -> None:
    result = validate_cv_upload(name, _read(name), max_bytes=MAX_BYTES)
    blob = (result.user_message_vi + result.user_message_en).lower()
    for forbidden in ("pdfplumber", "tesseract", "ocr", "traceback", "storage"):
        assert forbidden not in blob
