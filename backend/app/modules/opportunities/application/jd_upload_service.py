"""JD (Job Description) upload and AI extraction service.

Flow:
  1. Partner uploads a PDF or DOCX containing their job description.
  2. We extract raw text (native PDF text → OCR fallback if needed).
  3. We call the LLM to parse structured fields from the raw text.
  4. The structured draft is returned to the partner for review + form prefill.
  5. Partner reviews, edits, then submits via the normal create-job flow.

Privacy: raw PDF bytes and raw text never leave the backend or appear in logs.
Only the LLM-extracted structured fields (no PII) are returned to the client.
AI internals (model, provider, tokens) are never exposed in the response.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.ai.cv.llm import generate_json_note
from app.ai.extraction.text_extraction import ExtractionError, extract_text
from app.ai.prompts.jd_extraction import v1 as jd_extraction_prompt
from app.shared.exceptions import AIUnavailableError, ValidationFailedError

logger = logging.getLogger(__name__)

_SUPPORTED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

# Fields the LLM may return; unknown keys are ignored.
_EXPECTED_KEYS = {
    "title", "title_en", "description_vi", "description_en",
    "requirements_vi", "requirements_en", "benefits_vi", "benefits_en",
    "employment_type", "location_type", "locations",
    "required_skills", "preferred_skills",
    "experience_min_years", "experience_max_years",
    "degree_required", "salary_min", "salary_max", "salary_currency",
    "salary_is_disclosed", "headcount", "detected_language",
}

# Fields the LLM may fabricate/normalize rather than quote verbatim (currency
# conversion, enum classification, year counts) — these ALWAYS carry
# needs_review=True when present, since verbatim-quotability cannot vouch for
# a normalized/interpreted value the way it can for prose (§10.1 confidence
# signal design, documented below in ``_score_field_confidence``).
_ALWAYS_REVIEW_FIELDS = frozenset({
    "employment_type", "location_type", "degree_required",
    "experience_min_years", "experience_max_years",
    "salary_min", "salary_max", "salary_currency", "headcount", "locations",
})
# Free-text fields the extraction prompt is instructed to copy/translate from
# the source — checked for verbatim (normalized) presence in the raw text.
_QUOTABLE_TEXT_FIELDS = frozenset({
    "title", "title_en", "description_vi", "description_en",
    "requirements_vi", "requirements_en", "benefits_vi", "benefits_en",
})
_QUOTABLE_LIST_FIELDS = frozenset({"required_skills", "preferred_skills"})
# Trivial metadata fields that never need a per-field review flag.
_NO_REVIEW_FIELDS = frozenset({"salary_is_disclosed", "detected_language"})


class JDLocation(BaseModel):
    city: str | None = None
    country: str | None = None


class JDExtractionSchema(BaseModel):
    """Pydantic v2 schema for ``jd_extraction`` output (types/enums beyond
    the plain key-allowlist ``_EXPECTED_KEYS`` used to enforce alone).

    Any field that fails validation (wrong type, out-of-enum value) is
    dropped and the row is re-validated rather than the whole extraction
    being discarded — a partially-structured draft is still useful to the
    partner, per the "never invent, degrade gracefully" rule.
    """

    title: str | None = None
    title_en: str | None = None
    description_vi: str | None = None
    description_en: str | None = None
    requirements_vi: str | None = None
    requirements_en: str | None = None
    benefits_vi: str | None = None
    benefits_en: str | None = None
    employment_type: Literal["full_time", "part_time", "internship", "contract"] | None = None
    location_type: Literal["onsite", "remote", "hybrid"] | None = None
    locations: list[JDLocation] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    degree_required: Literal["bachelor", "master", "phd", "high_school", "none"] | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_is_disclosed: bool = False
    headcount: int | None = None
    detected_language: Literal["vi", "en", "mixed"] | None = None


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_quotable(value: str, raw_text_normalized: str) -> bool:
    normalized = _normalize_for_match(value)[:80]
    return bool(normalized) and normalized in raw_text_normalized


def _validate_and_score(
    structured: dict[str, Any], raw_text: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate ``structured`` against :class:`JDExtractionSchema` and derive
    a per-field confidence signal.

    Confidence heuristic (documented deviation — no ``field_confidence`` map
    is requested from the LLM itself, to avoid a second model call / prompt
    round-trip for a signal that's cheaply derivable): a free-text field is
    "high confidence" when its (whitespace/case-normalized) value can be
    found verbatim in the source text — i.e. the model actually quoted it,
    per the prompt's "extract ONLY information explicitly stated" rule.
    Enum/numeric fields that require currency conversion or classification
    can never be verified this way, so they always carry ``needs_review``.
    """

    try:
        model = JDExtractionSchema.model_validate(structured)
    except ValidationError as exc:
        bad_fields = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
        logger.info(
            "jd_extraction_schema_validation_failed",
            extra={"invalid_field_count": len(bad_fields)},
        )
        cleaned = {k: v for k, v in structured.items() if k not in bad_fields}
        model = JDExtractionSchema.model_validate(cleaned)

    validated = model.model_dump()
    raw_normalized = _normalize_for_match(raw_text)
    field_confidence: dict[str, Any] = {}

    for field_name in _EXPECTED_KEYS:
        if field_name in _NO_REVIEW_FIELDS:
            continue
        value = validated.get(field_name)
        if value in (None, "", [], {}):
            continue
        if field_name in _QUOTABLE_TEXT_FIELDS and isinstance(value, str):
            needs_review = not _is_quotable(value, raw_normalized)
        elif field_name in _QUOTABLE_LIST_FIELDS and isinstance(value, list):
            needs_review = not all(
                _is_quotable(str(item), raw_normalized) for item in value
            )
        elif field_name in _ALWAYS_REVIEW_FIELDS:
            needs_review = True
        else:
            needs_review = False
        field_confidence[field_name] = {"needs_review": needs_review}

    return validated, field_confidence


class JDFileError(ValidationFailedError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            "Không thể xử lý tệp. Vui lòng thử lại hoặc nhập thủ công.",
            details={"reason": reason},
        )


async def extract_jd_from_upload(
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> dict:
    """Extract structured job-description fields from an uploaded document.

    Returns a dict of fields suitable for prefilling the job-creation form.
    Always returns something safe — on AI unavailability, returns the raw text
    so the partner can still copy-paste manually.

    Never raises; degrades to partial/empty extraction with ``is_ai_extraction=False``
    on any failure.
    """
    if len(data) > _MAX_FILE_BYTES:
        raise JDFileError("file_too_large")

    # ── Text extraction ─────────────────────────────────────────────────────
    try:
        result = extract_text(filename, data)
    except ExtractionError as exc:
        raise JDFileError(exc.code.lower()) from exc
    except Exception as exc:
        logger.warning("JD text extraction failed: %s", exc)
        raise JDFileError("extraction_failed") from exc

    raw_text = result.text.strip()
    if not raw_text:
        raise JDFileError("no_text_found")

    # ── LLM structuring ─────────────────────────────────────────────────────
    try:
        extracted = await generate_json_note(
            task_type="jd_extraction",
            system_prompt=jd_extraction_prompt.STATIC_SYSTEM_PROMPT,
            user_content=jd_extraction_prompt.build_user_message(raw_text),
            temperature=0.1,
            max_tokens=2000,
        )
    except AIUnavailableError:
        logger.info("JD AI extraction unavailable — returning raw text fallback")
        return {
            "is_ai_extraction": False,
            "raw_text_preview": raw_text[:2000],
            "prompt_version": jd_extraction_prompt.PROMPT_VERSION,
        }
    except Exception as exc:
        logger.warning("JD AI extraction unexpected error: %s", exc)
        return {
            "is_ai_extraction": False,
            "raw_text_preview": raw_text[:2000],
            "prompt_version": jd_extraction_prompt.PROMPT_VERSION,
        }

    # Strip unknown keys to avoid leaking AI internals.
    structured = {k: v for k, v in extracted.items() if k in _EXPECTED_KEYS}

    # Pydantic schema validation (types/enums beyond the key-allowlist above)
    # + per-field confidence signal (§10.1 — extend beyond null-for-absent).
    validated, field_confidence = _validate_and_score(structured, raw_text)
    validated["is_ai_extraction"] = True
    validated["prompt_version"] = jd_extraction_prompt.PROMPT_VERSION
    validated["field_confidence"] = field_confidence
    validated["needs_review"] = any(
        entry.get("needs_review") for entry in field_confidence.values()
    )

    return validated
