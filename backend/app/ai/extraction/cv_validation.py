"""CV upload validation with user-safe classification.

Implements the failure taxonomy from ``docs/EDGE_CASES_FAILURE_MODES.md`` §2 and
the ``quality_code`` values in ``docs/API_CONTRACTS.md`` (CV Parse Status).

Pipeline order (deterministic, no LLM in Phase 0):

1. file-type / size / security / duplicate checks (cheap, fail fast)
2. text-native extraction (password / corrupt detection)
3. content-quality classification (blank / not-a-cv / insufficient / review)

Never exposes parser internals, OCR details, storage paths, or raw extracted
text. Returns only friendly vi/en messages and safe next actions. The LLM is not
invoked for blank, corrupt, security-rejected, or not-a-CV files.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from app.ai.extraction.text_extraction import ExtractionError, FileKind, extract_text, sniff_kind

# Minimum characters of readable text before we consider a document non-blank.
_BLANK_TEXT_THRESHOLD = 40
# Minimum text length for a plausible CV before flagging low-quality/insufficient.
_LOW_QUALITY_THRESHOLD = 120

_SUPPORTED_KINDS = {FileKind.PDF, FileKind.DOCX, FileKind.TXT, FileKind.IMAGE}

# CV signal keywords (Vietnamese + English). Presence indicates a CV/resume.
_CV_SIGNALS = [
    "kinh nghiệm",
    "học vấn",
    "kỹ năng",
    "mục tiêu",
    "dự án",
    "chứng chỉ",
    "experience",
    "education",
    "skills",
    "objective",
    "project",
    "summary",
    "curriculum vitae",
    "resume",
    "work history",
    "certification",
]

# Contact / identity signals used for "insufficient content" detection.
_CONTACT_SIGNALS = ["@", "email", "phone", "điện thoại", "sđt", "tel", "linkedin"]

# Optional virus-scan hook: callable(data, filename) -> bool (True = clean).
SecurityScanner = Callable[[bytes, str], bool]
_scanner: SecurityScanner | None = None

# EICAR test signature — lets us exercise the security-rejected path safely.
_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR"


def set_security_scanner(scanner: SecurityScanner | None) -> None:
    global _scanner
    _scanner = scanner


@dataclass(slots=True)
class CVValidationResult:
    """User-safe validation outcome for a CV upload."""

    accepted: bool
    quality_code: str
    user_message_vi: str
    user_message_en: str
    recoverability: str  # retry | fix_input | manual_review | blocked
    next_actions: list[str] = field(default_factory=list)
    checksum: str | None = None
    needs_review: bool = False


# quality_code -> (vi, en, recoverability, next_actions)
_COPY: dict[str, tuple[str, str, str, list[str]]] = {
    "UNSUPPORTED_FILE_TYPE": (
        "Định dạng tệp không được hỗ trợ. Hãy tải lên CV dạng PDF, DOCX, TXT hoặc ảnh.",
        "Unsupported file type. Upload a PDF, DOCX, TXT, or image CV.",
        "fix_input",
        ["upload_another", "create_from_template"],
    ),
    "FILE_TOO_LARGE": (
        "Tệp quá lớn. Hãy nén hoặc chia nhỏ tệp rồi tải lại.",
        "File is too large. Compress or split it and try again.",
        "fix_input",
        ["upload_another"],
    ),
    "FILE_REJECTED_SECURITY": (
        "Tệp không vượt qua kiểm tra an toàn. Hãy tải lên một tệp sạch.",
        "This file failed the security check. Please upload a clean file.",
        "fix_input",
        ["upload_another"],
    ),
    "PASSWORD_PROTECTED_FILE": (
        "Tệp PDF đang được đặt mật khẩu. Hãy gỡ mật khẩu rồi tải lại.",
        "This PDF is password-protected. Remove the password and upload again.",
        "fix_input",
        ["upload_another"],
    ),
    "CORRUPT_FILE": (
        "Không đọc được tệp này. Hãy xuất lại bản mới và thử lại.",
        "We could not read this file. Export a fresh copy and retry.",
        "retry",
        ["upload_another", "create_from_template"],
    ),
    "DUPLICATE_FILE": (
        "Bạn đã tải tệp này trước đó. Hãy dùng CV hiện có hoặc tải tệp khác.",
        "You already uploaded this file. Use the existing CV or upload a different file.",
        "fix_input",
        ["use_existing", "upload_another"],
    ),
    "BLANK_DOCUMENT": (
        "Tệp này có vẻ là trang trắng hoặc không có nội dung đọc được. "
        "Bạn có thể tải lên tệp khác hoặc tạo CV bằng mẫu có sẵn.",
        "This file looks blank or unreadable. Upload another file or create a CV from a template.",
        "fix_input",
        ["upload_another", "create_from_template"],
    ),
    "LOW_QUALITY_SCAN": (
        "Bản scan quá mờ nên hệ thống không đọc chính xác. "
        "Hãy tải bản rõ hơn, DOCX, hoặc PDF có thể chọn text.",
        "The scan is too unclear to read reliably. "
        "Upload a clearer scan, DOCX, or text-selectable PDF.",
        "fix_input",
        ["upload_another", "create_from_template"],
    ),
    "EXTRACTION_PENDING_AI": (
        "Trích xuất bằng AI đang tạm ngưng. Tệp của bạn đã được lưu — hệ thống sẽ "
        "tự trích xuất khi AI sẵn sàng, hoặc bạn có thể thử lại sau.",
        "AI extraction is paused right now. Your file is saved — we'll extract it "
        "once AI is available again, or you can retry later.",
        "retry",
        ["retry_extraction", "keep_original", "create_from_template"],
    ),
    "NOT_A_CV": (
        "Tệp này không giống CV/hồ sơ ứng tuyển. Hãy tải lên CV, "
        "hoặc bắt đầu bằng mẫu CV và nhập thông tin thủ công.",
        "This file does not look like a CV/resume. Upload a CV or start from a template.",
        "fix_input",
        ["upload_another", "create_from_template"],
    ),
    "INSUFFICIENT_CV_CONTENT": (
        "CV chưa có đủ thông tin tối thiểu. Hãy kiểm tra lại hoặc tạo CV từ mẫu.",
        "This CV is missing minimum required information. Review it or create from a template.",
        "manual_review",
        ["review_fields", "create_from_template"],
    ),
    "REVIEW_REQUIRED": (
        "Chúng tôi đã trích xuất được một số thông tin nhưng cần bạn kiểm tra "
        "trước khi nhập vào CV.",
        "We extracted some information, but you need to review it before importing.",
        "manual_review",
        ["review_fields", "upload_another"],
    ),
    "OK": (
        "Đã trích xuất CV thành công.",
        "CV extracted successfully.",
        "retry",
        ["review_fields", "import_to_cv"],
    ),
}


def copy_for(code: str) -> tuple[str, str, str, list[str]]:
    """Return user-safe ``(vi, en, recoverability, next_actions)`` for a quality code.

    Public accessor so the documents presenters can render the same friendly
    message/next-actions stored against a parse run without duplicating copy.
    """

    vi, en, recover, actions = _COPY.get(code, _COPY["REVIEW_REQUIRED"])
    return vi, en, recover, list(actions)


def _result(code: str, *, accepted: bool, checksum: str | None, needs_review: bool = False):
    vi, en, recover, actions = _COPY[code]
    return CVValidationResult(
        accepted=accepted,
        quality_code=code,
        user_message_vi=vi,
        user_message_en=en,
        recoverability=recover,
        next_actions=list(actions),
        checksum=checksum,
        needs_review=needs_review,
    )


def compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _has_signal(text: str, signals: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in signals)


def security_gate(data: bytes, filename: str) -> str | None:
    """Run the cheap pre-storage security check.

    Returns ``"FILE_REJECTED_SECURITY"`` when the file fails the EICAR signature
    check or an injected scanner (fail-secure: scanner errors are rejections),
    else ``None``. Shared by the upload validator and the ingestion cascade so the
    security policy lives in one place.
    """

    if _EICAR in data:
        return "FILE_REJECTED_SECURITY"
    if _scanner is not None:
        try:
            clean = _scanner(data, filename)
        except Exception:
            clean = False  # fail-secure
        if not clean:
            return "FILE_REJECTED_SECURITY"
    return None


def classify_content(text: str, *, kind: FileKind, ocr_used: bool) -> tuple[str, bool]:
    """Classify extracted ``text`` into a content quality code.

    Returns ``(quality_code, needs_review)``. The order mirrors
    ``docs/EDGE_CASES_FAILURE_MODES.md`` §2: blank/low-quality -> not-a-CV ->
    insufficient -> review-required. Deterministic; no AI.
    """

    text = text.strip()
    if len(text) < _BLANK_TEXT_THRESHOLD:
        if kind is FileKind.IMAGE or ocr_used:
            return "LOW_QUALITY_SCAN", False
        return "BLANK_DOCUMENT", False
    if not _has_signal(text, _CV_SIGNALS):
        return "NOT_A_CV", False
    has_contact = _has_signal(text, _CONTACT_SIGNALS)
    if len(text) < _LOW_QUALITY_THRESHOLD or not has_contact:
        return "INSUFFICIENT_CV_CONTENT", True
    return "REVIEW_REQUIRED", True


def validate_cv_upload(
    filename: str,
    data: bytes,
    *,
    max_bytes: int,
    existing_checksums: Iterable[str] = (),
) -> CVValidationResult:
    """Validate and classify a CV upload, returning a user-safe result."""

    checksum = compute_checksum(data)

    # 1a. Size.
    if len(data) > max_bytes:
        return _result("FILE_TOO_LARGE", accepted=False, checksum=checksum)

    # 1b. File type.
    kind = sniff_kind(filename, data)
    if kind not in _SUPPORTED_KINDS:
        return _result("UNSUPPORTED_FILE_TYPE", accepted=False, checksum=checksum)

    # 1c. Security scan (fail-secure: errors/None treated as rejection).
    reject = security_gate(data, filename)
    if reject is not None:
        return _result(reject, accepted=False, checksum=checksum)

    # 1d. Duplicate.
    if checksum in set(existing_checksums):
        return _result("DUPLICATE_FILE", accepted=False, checksum=checksum)

    # 2. Extraction (password / corrupt detection).
    try:
        extraction = extract_text(filename, data)
    except ExtractionError as exc:
        code = exc.code if exc.code in _COPY else "CORRUPT_FILE"
        return _result(code, accepted=False, checksum=checksum)

    # 3. Content quality.
    code, needs_review = classify_content(
        extraction.text, kind=kind, ocr_used=extraction.ocr_used
    )
    accepted = code == "REVIEW_REQUIRED"
    return _result(code, accepted=accepted, checksum=checksum, needs_review=needs_review)
