"""JD (Job Description) upload → cost-tiered extraction → form auto-fill.

Flow: partner uploads a PDF/DOCX/TXT/image JD → the JD ingestion cascade
(native text → vision-LLM for images/scans → OCR fallback → is-JD gate →
text-LLM structuring) returns the FULL structured field set. The result is used
ONLY to prefill the job-creation form — nothing is written to the database.

Privacy: raw bytes/text never leave the backend or appear in logs; only the
structured fields (no AI internals) are returned to the client.
"""

from __future__ import annotations

import logging

from app.ai.extraction.jd import structuring as _structuring
from app.ai.extraction.jd import validation as jd_validation
from app.ai.extraction.jd import vision as _vision
from app.ai.extraction.jd.cascade import JdExtractionOutcome, run_jd_cascade
from app.ai.prompts.jd_extraction import v2 as jd_prompt
from app.shared.exceptions import ValidationFailedError

logger = logging.getLogger(__name__)

# Reject statuses that map to a user-safe 422 (vs. the ok/ai_unavailable dict).
_REJECT_STATUSES = {
    "blank",
    "not_a_jd",
    "low_quality_scan",
    "insufficient",
    "file_too_large",
    "unsupported_file_type",
    "password_protected_file",
    "corrupt_file",
    "file_rejected_security",
}

# File-gate statuses reuse a generic file message when no JD-specific copy exists.
_GENERIC_FILE_COPY = {
    "file_too_large": (
        "Tệp quá lớn. Hãy nén hoặc chia nhỏ rồi thử lại.",
        "File is too large. Compress it and try again.",
    ),
    "unsupported_file_type": (
        "Định dạng không hỗ trợ. Hãy tải PDF, DOCX, TXT hoặc ảnh.",
        "Unsupported file type. Upload a PDF, DOCX, TXT, or image.",
    ),
    "password_protected_file": (
        "Tệp PDF đang đặt mật khẩu. Hãy gỡ mật khẩu rồi tải lại.",
        "This PDF is password-protected. Remove it and retry.",
    ),
    "corrupt_file": (
        "Không đọc được tệp này. Hãy xuất lại bản mới và thử lại.",
        "We could not read this file. Export a fresh copy and retry.",
    ),
    "file_rejected_security": (
        "Tệp không vượt qua kiểm tra an toàn.",
        "This file failed the security check.",
    ),
}


def _reject_details(status: str) -> dict:
    if status in _GENERIC_FILE_COPY:
        vi, en = _GENERIC_FILE_COPY[status]
        return {
            "reason": status,
            "message_vi": vi,
            "message_en": en,
            "next_actions": ["upload_another", "fill_manually"],
        }
    return jd_validation.reject_copy(status)


def _to_response(outcome: JdExtractionOutcome) -> dict:
    if outcome.status in _REJECT_STATUSES:
        details = _reject_details(outcome.status)
        raise ValidationFailedError(details["message_vi"], details=details)

    if outcome.status == "ai_unavailable":
        return {
            "is_ai_extraction": False,
            "status": "ai_unavailable",
            "raw_text_preview": outcome.raw_text_preview,
            "prompt_version": jd_prompt.PROMPT_VERSION,
        }

    # ok — flatten fields to the top level (backward-compatible) + meta.
    response = dict(outcome.fields)
    response["is_ai_extraction"] = True
    response["status"] = "ok"
    response["field_confidence"] = outcome.field_confidence
    response["needs_review"] = outcome.needs_review
    response["prompt_version"] = jd_prompt.PROMPT_VERSION
    return response


async def extract_jd_from_upload_with(
    *, filename: str, data: bytes, structurer, vision_runner
) -> dict:
    """Testable core: run the cascade with injected AI seams, map to a response."""
    outcome = await run_jd_cascade(
        filename, data, structurer=structurer, vision_runner=vision_runner
    )
    return _to_response(outcome)


async def extract_jd_from_upload(
    filename: str, data: bytes, content_type: str | None = None
) -> dict:
    """Extract structured JD fields for form prefill. Never persists anything.

    Returns a flat dict (ok) or an ``ai_unavailable`` dict; raises
    ``ValidationFailedError`` (user-safe) for blank/not-a-JD/corrupt/etc.
    """
    return await extract_jd_from_upload_with(
        filename=filename,
        data=data,
        structurer=_structuring.run_jd_text_structuring,
        vision_runner=_vision.run_jd_vision_extraction,
    )
