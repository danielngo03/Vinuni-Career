"""JD upload validity classification (user-safe, deterministic, no LLM).

Distinct from CV validation: a JD is recognised by hiring/role-description
signals, NOT by CV signals (a résumé must be REJECTED here). Reuses the generic
security gate + checksum from ``cv_validation`` (those are not CV-specific).
"""

from __future__ import annotations

from collections.abc import Iterable

from app.ai.extraction.text_extraction import FileKind

_BLANK_THRESHOLD = 40
_INSUFFICIENT_THRESHOLD = 120

# Hiring / job-description signals (vi + en). Presence indicates a JD.
JD_SIGNALS: list[str] = [
    "mô tả công việc",
    "trách nhiệm",
    "nhiệm vụ",
    "yêu cầu",
    "quyền lợi",
    "phúc lợi",
    "mức lương",
    "tuyển dụng",
    "vị trí",
    "kinh nghiệm",
    "job description",
    "responsibilities",
    "requirements",
    "benefits",
    "we are hiring",
    "we are looking for",
    "qualifications",
    "salary",
    "employment type",
    "full-time",
    "part-time",
    "internship",
]

# CV/résumé signals that, when dominant WITHOUT hiring language, mean the file is
# a candidate résumé mistakenly uploaded to the JD flow.
_CV_ONLY_SIGNALS = ["học vấn", "curriculum vitae", "resume", "objective", "career objective"]

_COPY: dict[str, tuple[str, str, list[str]]] = {
    "blank": (
        "Tệp này có vẻ trống hoặc không có nội dung đọc được. "
        "Hãy tải lên bản mô tả công việc khác.",
        "This file looks blank or unreadable. Upload another job description.",
        ["upload_another", "fill_manually"],
    ),
    "not_a_jd": (
        "Tệp này không giống một bản mô tả công việc (JD). Hãy tải lên đúng JD hoặc nhập thủ công.",
        "This file does not look like a job description. Upload a JD or fill the form manually.",
        ["upload_another", "fill_manually"],
    ),
    "low_quality_scan": (
        "Bản scan/ảnh quá mờ nên không đọc được. Hãy tải bản rõ hơn hoặc PDF chọn được text.",
        "The scan/image is too unclear to read. Upload a clearer file or a text-selectable PDF.",
        ["upload_another", "fill_manually"],
    ),
    "insufficient": (
        "Bản mô tả chưa đủ thông tin để tự điền. Bạn có thể nhập thủ công phần còn thiếu.",
        "The description has too little content to auto-fill. You can fill the rest manually.",
        ["fill_manually", "upload_another"],
    ),
}


def _has_signal(text: str, signals: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in signals)


def classify_jd_content(text: str, *, kind: FileKind, ocr_used: bool) -> str:
    """Return ``ok | blank | not_a_jd | low_quality_scan | insufficient``."""
    text = text.strip()
    if len(text) < _BLANK_THRESHOLD:
        return "low_quality_scan" if (kind is FileKind.IMAGE or ocr_used) else "blank"
    has_jd = _has_signal(text, JD_SIGNALS)
    if not has_jd:
        return "not_a_jd"
    # Looks like a résumé (CV-only signals dominate, no hiring framing beyond a
    # stray keyword)? Guard against a CV slipping through.
    if _has_signal(text, _CV_ONLY_SIGNALS) and not _has_signal(
        text,
        [
            "tuyển dụng",
            "mô tả công việc",
            "we are hiring",
            "we are looking for",
            "job description",
            "responsibilities",
            "quyền lợi",
            "benefits",
            # Additional hiring-context overrides that co-occur with "học vấn" in JDs
            # (e.g. the JD lists education requirements under a "học vấn" section header).
            "trách nhiệm",
            "phúc lợi",
            "vị trí tuyển",
            "tuyển dụng",
        ],
    ):
        return "not_a_jd"
    if len(text) < _INSUFFICIENT_THRESHOLD:
        return "insufficient"
    return "ok"


def reject_copy(status: str) -> dict:
    vi, en, actions = _COPY.get(status, _COPY["not_a_jd"])
    return {"reason": status, "message_vi": vi, "message_en": en, "next_actions": list(actions)}
