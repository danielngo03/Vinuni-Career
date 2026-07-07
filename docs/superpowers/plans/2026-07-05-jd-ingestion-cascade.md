# JD Ingestion Cascade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild partner JD upload into a strong, cost-tiered multi-tier extraction cascade (native text → vision-LLM for images/scans → OCR fallback → is-JD gate → text-LLM structuring) that supports images and auto-fills **every** field the backend `Job` model already supports, returning prefill data only (never persisted).

**Architecture:** A new self-contained package `backend/app/ai/extraction/jd/` orchestrates the cascade, reusing the CV pipeline's *generic* primitives read-only (text extraction, OCR adapter, gateway, secret redaction, security gate). JD-specific validity, schema, prompts, vision normalization live in the new package. The existing `jd_upload_service.extract_jd_from_upload` is rewritten to call the cascade and return a backward-compatible + additively-richer dict; the router accepts images and maps reject statuses to user-safe 422s.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pdfplumber/PyMuPDF, Tesseract (`vie+eng`), AI gateway (`chat_cheap`=deepseek text, `vision_cheap`=gemini-2.5-flash), pytest.

## Global Constraints

- Prompts live in `backend/app/ai/prompts/{task}/v{N}.py`, **English only**; static system prefix before dynamic content (`.claude/rules/ai.md` §8.2).
- Never expose provider/model/API-key/token/latency/prompt/internal-status to end users; all model text passes the gateway output guard.
- Cost-tiered: native text (free) → local OCR → cheap vision-LLM for images/styled-or-scanned PDFs → text-LLM structuring. Escalate to the vision tier ONLY when native text is insufficient. Digital PDFs/DOCX/TXT must NOT reach the vision tier.
- The vision tier MAY receive DOWNSCALED document images (owner decision 2026-07-05). The text-LLM structuring tier receives extracted TEXT ONLY (secrets redacted first).
- Never call any model for blank / corrupt / infected / password-protected / not-a-JD uploads. The vision tier returns `is_jd=false`/no result for non-JDs. The cascade must NEVER fabricate a JD from a non-JD/blank/junk file.
- **Extraction is auto-fill only — nothing is written to the database.** Blanks stay blank (numbers/text) or default `not_required` (requirement groups). Never fabricate; normalized/interpreted fields carry `needs_review=true`.
- All LLM calls go through the AI gateway/factory — no direct provider SDK calls in domain modules. Unit tests use offline/fake providers; real calls opt-in only.
- Do NOT edit `cv_*` files or `adapters/vision.py` (a concurrent session owns CV extraction). Reuse generic primitives via read-only import; copy small helpers into the JD package if needed.
- Backward compatibility: `POST /jobs/upload-jd` must keep returning the current top-level keys (`title`, `description_vi/en`, `requirements_vi/en`, `benefits_vi/en`, `employment_type`, `location_type`, `locations`, `required_skills`, `preferred_skills`, `experience_min_years`, `experience_max_years`, `degree_required`, `salary_min/max/currency`, `salary_is_disclosed`, `headcount`, `detected_language`, `is_ai_extraction`, `field_confidence`, `needs_review`, `prompt_version`). New fields are additive.

**Reused primitives (exact signatures — consume, do not modify):**
- `app.ai.extraction.text_extraction`: `sniff_kind(filename: str, data: bytes) -> FileKind`; `extract_text(filename: str, data: bytes) -> ExtractionResult` (`.text`, `.page_count`, `.ocr_used`, `.engine`); `class FileKind(StrEnum)` = PDF|DOCX|TXT|IMAGE|UNKNOWN; `class ExtractionError(Exception)` with `.code`.
- `app.ai.extraction.adapters.ocr`: `get_ocr_adapter() -> OcrEngine`; `set_ocr_adapter(adapter|None)`; `OcrEngine.available: bool`, `OcrEngine.recognize(data: bytes, langs: str) -> str` (handles both PDF bytes and image bytes).
- `app.ai.extraction.cv_validation`: `security_gate(data: bytes, filename: str) -> str | None`; `compute_checksum(data: bytes) -> str` (both generic — reuse).
- `app.ai.cv.llm`: `async generate_json_note(*, task_type: str, system_prompt: str, user_content: str, temperature: float=0.2, max_tokens: int=1500) -> dict` (routes through gateway, output-guards, logs usage, raises `AIUnavailableError` on failure or malformed JSON).
- `app.ai.gateway.runtime_config.current() -> EffectiveAiConfig` (`.real_calls_active`, `.provider_routes: dict[str, (provider, base_url, model)]`).
- `app.ai.gateway.factory`: `_get_api_key(provider_name) -> str`, `real_provider_active() -> bool`.
- `app.ai.gateway.output_guard.scrub_text(s: str) -> str`.
- `app.shared.exceptions`: `AIUnavailableError`, `ValidationFailedError(message, details=...)`.

---

### Task 1: Config knobs for the JD engine

**Files:**
- Modify: `backend/app/core/config.py` (after the CV vision block, ~line 130)
- Test: `backend/tests/unit/core/test_jd_config.py`

**Interfaces:**
- Produces: `Settings.jd_max_upload_bytes: int`, `jd_ocr_langs: str`, `jd_vision_extraction_enabled: bool`, `jd_vision_provider_alias: str`, `jd_vision_max_image_px: int`, `jd_vision_max_pages: int`, `jd_llm_structuring_provider_alias: str`, `jd_extraction_max_seconds: int`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/core/test_jd_config.py
from app.core.config import get_settings


def test_jd_engine_defaults_present():
    s = get_settings()
    assert s.jd_vision_extraction_enabled is True
    assert s.jd_vision_provider_alias == "vision_cheap"
    assert s.jd_llm_structuring_provider_alias == "chat_cheap"
    assert s.jd_ocr_langs == "vie+eng"
    assert s.jd_vision_max_pages == 3
    assert s.jd_vision_max_image_px == 2200
    assert s.jd_max_upload_bytes == 10 * 1024 * 1024
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/core/test_jd_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'jd_vision_extraction_enabled'`

- [ ] **Step 3: Add the settings**

In `backend/app/core/config.py`, immediately after the line `cv_vision_max_pages: int = 4  # max rasterized pages sent per scanned PDF`, add:

```python

    # JD (job description) upload extraction engine. Mirrors the CV cascade knobs
    # but independent so partner JD tuning never affects student CV parsing.
    # Cost-tiered: native text (free) -> local OCR -> cheap vision-LLM for images
    # and styled/scanned PDFs -> text-LLM structuring. Extraction is auto-fill
    # ONLY (never persisted). Engine names never appear in user-facing responses.
    jd_max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    jd_ocr_langs: str = "vie+eng"
    jd_vision_extraction_enabled: bool = True
    jd_vision_provider_alias: str = "vision_cheap"
    jd_vision_max_image_px: int = 2200  # long-edge cap; controls vision token cost
    jd_vision_max_pages: int = 3  # JDs are short; cap rasterized pages tightly
    jd_llm_structuring_provider_alias: str = "chat_cheap"
    jd_extraction_max_seconds: int = 25
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/core/test_jd_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/unit/core/test_jd_config.py
git commit -m "feat(jd): add JD extraction engine config knobs"
```

---

### Task 2: Extended JD extraction schema + confidence scoring

**Files:**
- Create: `backend/app/ai/extraction/jd/__init__.py` (empty)
- Create: `backend/app/ai/extraction/jd/schema.py`
- Test: `backend/tests/unit/ai_extraction_jd/test_jd_schema.py`

**Interfaces:**
- Produces:
  - `JDExtractionSchema` (Pydantic v2) with the full field set + nested `candidate_requirements`.
  - `EXPECTED_KEYS: frozenset[str]` — top-level keys allowed through the allowlist strip.
  - `validate_and_score(structured: dict, raw_text: str) -> tuple[dict, dict]` → `(validated_fields, field_confidence)` where `field_confidence[name] = {"needs_review": bool}`.
  - `default_candidate_requirements() -> dict` — all groups defaulting to `not_required`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai_extraction_jd/test_jd_schema.py
from app.ai.extraction.jd.schema import (
    EXPECTED_KEYS,
    default_candidate_requirements,
    validate_and_score,
)


def test_defaults_requirement_groups_to_not_required():
    cr = default_candidate_requirements()
    assert cr["gender"]["mode"] == "not_required"
    assert cr["age"]["mode"] == "not_required"
    assert cr["marital_status"]["mode"] == "not_required"
    assert cr["languages"] == []
    assert cr["certifications"] == []


def test_extracts_new_structured_fields():
    structured = {
        "title": "Kỹ sư phần mềm",
        "salary_mode": "range",
        "salary_min": 20000000,
        "salary_max": 30000000,
        "salary_period": "monthly",
        "salary_gross_net": "gross",
        "experience_mode": "min",
        "experience_min_years": 2,
        "seniority_level": "junior",
        "application_deadline": "2026-08-31",
        "candidate_requirements": {"gender": {"mode": "required", "values": ["female"]}},
    }
    raw = "Kỹ sư phần mềm, lương 20-30 triệu gross/tháng, tối thiểu 2 năm, chỉ tuyển nữ."
    validated, conf = validate_and_score(structured, raw)
    assert validated["salary_mode"] == "range"
    assert validated["experience_mode"] == "min"
    assert validated["candidate_requirements"]["gender"]["mode"] == "required"
    # absent groups defaulted to not_required
    assert validated["candidate_requirements"]["marital_status"]["mode"] == "not_required"
    # normalized/interpreted fields always flagged for review
    assert conf["salary_min"]["needs_review"] is True
    assert conf["candidate_requirements"]["needs_review"] is True


def test_invalid_enum_field_is_dropped_not_fatal():
    structured = {"title": "X", "employment_type": "banana", "required_skills": ["Python"]}
    validated, conf = validate_and_score(structured, "X Python full time")
    assert validated.get("employment_type") in (None, "")
    assert "Python" in validated["required_skills"]


def test_expected_keys_include_new_fields():
    for k in ("salary_mode", "experience_mode", "seniority_level",
              "industry", "application_deadline", "candidate_requirements"):
        assert k in EXPECTED_KEYS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ai.extraction.jd'`

- [ ] **Step 3: Create the package + schema**

Create empty `backend/app/ai/extraction/jd/__init__.py`.

Create `backend/app/ai/extraction/jd/schema.py`:

```python
"""Extended structured schema for JD (job-description) extraction.

Covers EVERY field the backend ``Job`` model + ``JobCreateRequest`` support so an
uploaded JD can auto-fill the whole posting form. Golden rules:
- Present in the JD -> fill it. Absent -> null (numbers/text) or ``not_required``
  (requirement groups). Never fabricate.
- Interpreted/normalized fields (enums, currency conversion, year counts, parsed
  dates, whole eligibility block) always carry ``needs_review=True`` because a
  verbatim-quote check cannot vouch for a value the model transformed.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

# ---- nested requirement models (mirror opportunities/api/schemas.py) --------


class _RequirementGroup(BaseModel):
    mode: Literal["not_required", "required", "preferred"] = "not_required"
    values: list[str] = Field(default_factory=list, max_length=50)
    note: str | None = Field(default=None, max_length=1000)


class _AgeRequirement(BaseModel):
    mode: Literal["not_required", "at_least", "up_to", "range"] = "not_required"
    min: int | None = Field(default=None, ge=14, le=80)
    max: int | None = Field(default=None, ge=14, le=80)


class _LanguageRequirement(BaseModel):
    language: str = Field(min_length=1, max_length=60)
    proficiency: str | None = Field(default=None, max_length=80)
    required: bool = True


class _CertificationRequirement(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    required: bool = True


class _CandidateRequirements(BaseModel):
    education: _RequirementGroup = Field(default_factory=_RequirementGroup)
    nationalities: _RequirementGroup = Field(default_factory=_RequirementGroup)
    gender: _RequirementGroup = Field(default_factory=_RequirementGroup)
    age: _AgeRequirement = Field(default_factory=_AgeRequirement)
    marital_status: _RequirementGroup = Field(default_factory=_RequirementGroup)
    languages: list[_LanguageRequirement] = Field(default_factory=list, max_length=20)
    certifications: list[_CertificationRequirement] = Field(default_factory=list, max_length=30)
    work_authorization: _RequirementGroup = Field(default_factory=_RequirementGroup)
    note: str | None = Field(default=None, max_length=2000)


class _JDLocation(BaseModel):
    type: Literal["onsite", "remote", "hybrid"] | None = None
    province_code: str | None = Field(default=None, max_length=10)
    city: str | None = Field(default=None, max_length=100)
    country: str = Field(default="Vietnam", max_length=100)


class JDExtractionSchema(BaseModel):
    """Full JD field set. Invalid fields are dropped and re-validated so a
    partial draft is still useful (never invent; degrade gracefully)."""

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
    locations: list[_JDLocation] = Field(default_factory=list)
    seniority_level: str | None = Field(default=None, max_length=30)
    industry: str | None = Field(default=None, max_length=120)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_min_years: int | None = Field(default=None, ge=0, le=60)
    experience_max_years: int | None = Field(default=None, ge=0, le=60)
    experience_mode: Literal["no_requirement", "fresher", "range", "min", "max"] | None = None
    degree_required: Literal["bachelor", "master", "phd", "high_school", "none"] | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=5)
    salary_is_disclosed: bool = False
    salary_mode: Literal["negotiable", "hidden", "fixed", "range", "from", "to"] | None = None
    salary_period: Literal["monthly", "yearly"] | None = None
    salary_gross_net: Literal["unspecified", "gross", "net"] | None = None
    headcount: int | None = Field(default=None, ge=1, le=10000)
    application_deadline: str | None = Field(default=None, max_length=40)
    candidate_requirements: _CandidateRequirements = Field(default_factory=_CandidateRequirements)
    detected_language: Literal["vi", "en", "mixed"] | None = None


EXPECTED_KEYS: frozenset[str] = frozenset(JDExtractionSchema.model_fields.keys())

# Free-text fields the prompt is told to copy/translate -> verifiable by verbatim match.
_QUOTABLE_TEXT = frozenset({
    "title", "title_en", "description_vi", "description_en",
    "requirements_vi", "requirements_en", "benefits_vi", "benefits_en",
})
_QUOTABLE_LIST = frozenset({"required_skills", "preferred_skills"})
# Never need a per-field review flag.
_NO_REVIEW = frozenset({"salary_is_disclosed", "detected_language"})
# Everything else that is present but not a verbatim quote is a normalized value.


def default_candidate_requirements() -> dict:
    return _CandidateRequirements().model_dump()


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_quotable(value: str, raw_norm: str) -> bool:
    norm = _normalize_for_match(value)[:80]
    return bool(norm) and norm in raw_norm


def validate_and_score(structured: dict[str, Any], raw_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate ``structured`` against :class:`JDExtractionSchema` and derive a
    per-field ``needs_review`` signal. Absent requirement groups default to
    ``not_required``."""

    payload = {k: v for k, v in structured.items() if k in EXPECTED_KEYS}
    try:
        model = JDExtractionSchema.model_validate(payload)
    except ValidationError as exc:
        bad = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
        model = JDExtractionSchema.model_validate({k: v for k, v in payload.items() if k not in bad})

    validated = model.model_dump()
    raw_norm = _normalize_for_match(raw_text)
    conf: dict[str, Any] = {}
    for name in EXPECTED_KEYS:
        if name in _NO_REVIEW:
            continue
        value = validated.get(name)
        if name == "candidate_requirements":
            # flagged only when the block carries any real (non-default) requirement
            active = _has_active_requirement(value)
            if active:
                conf[name] = {"needs_review": True}
            continue
        if value in (None, "", [], {}):
            continue
        if name in _QUOTABLE_TEXT and isinstance(value, str):
            conf[name] = {"needs_review": not _is_quotable(value, raw_norm)}
        elif name in _QUOTABLE_LIST and isinstance(value, list):
            conf[name] = {"needs_review": not all(_is_quotable(str(i), raw_norm) for i in value)}
        else:
            conf[name] = {"needs_review": True}  # enums/numbers/dates/locations
    return validated, conf


def _has_active_requirement(cr: dict | None) -> bool:
    if not isinstance(cr, dict):
        return False
    for key in ("education", "nationalities", "gender", "marital_status", "work_authorization"):
        if (cr.get(key) or {}).get("mode", "not_required") != "not_required":
            return True
    if (cr.get("age") or {}).get("mode", "not_required") != "not_required":
        return True
    if cr.get("languages") or cr.get("certifications") or cr.get("note"):
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_schema.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/extraction/jd/__init__.py backend/app/ai/extraction/jd/schema.py backend/tests/unit/ai_extraction_jd/test_jd_schema.py
git commit -m "feat(jd): extended JD extraction schema with full field coverage + confidence"
```

---

### Task 3: JD-validity classifier (is-this-a-JD gate)

**Files:**
- Create: `backend/app/ai/extraction/jd/validation.py`
- Test: `backend/tests/unit/ai_extraction_jd/test_jd_validation.py`

**Interfaces:**
- Consumes: `cv_validation.security_gate`, `cv_validation.compute_checksum`, `text_extraction.FileKind`.
- Produces:
  - `classify_jd_content(text: str, *, kind: FileKind, ocr_used: bool) -> str` returning one of `ok | blank | not_a_jd | low_quality_scan | insufficient`.
  - `reject_copy(status: str) -> dict` → `{"reason": status, "message_vi": ..., "message_en": ..., "next_actions": [...]}`.
  - `JD_SIGNALS: list[str]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai_extraction_jd/test_jd_validation.py
from app.ai.extraction.jd.validation import classify_jd_content, reject_copy
from app.ai.extraction.text_extraction import FileKind


def test_real_jd_text_is_ok():
    text = ("Tuyển dụng Nhân viên Kinh doanh. Mô tả công việc: tìm kiếm khách hàng. "
            "Yêu cầu: tốt nghiệp đại học, 1 năm kinh nghiệm. Quyền lợi: lương thưởng hấp dẫn. "
            "Mức lương: 10-15 triệu.")
    assert classify_jd_content(text, kind=FileKind.PDF, ocr_used=False) == "ok"


def test_cv_text_is_rejected_as_not_a_jd():
    cv = ("Nguyen Van A. Email: a@example.com. Kinh nghiệm làm việc tại công ty X. "
          "Học vấn: Đại học Bách Khoa. Kỹ năng: Python.")
    assert classify_jd_content(cv, kind=FileKind.PDF, ocr_used=False) == "not_a_jd"


def test_blank_text_is_blank():
    assert classify_jd_content("   ", kind=FileKind.PDF, ocr_used=False) == "blank"


def test_blank_image_is_low_quality_scan():
    assert classify_jd_content("", kind=FileKind.IMAGE, ocr_used=True) == "low_quality_scan"


def test_reject_copy_is_user_safe_bilingual():
    copy = reject_copy("not_a_jd")
    assert copy["reason"] == "not_a_jd"
    assert copy["message_vi"] and copy["message_en"]
    assert "upload_another" in copy["next_actions"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_validation.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the classifier**

Create `backend/app/ai/extraction/jd/validation.py`:

```python
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
    "mô tả công việc", "trách nhiệm", "nhiệm vụ", "yêu cầu", "quyền lợi",
    "phúc lợi", "mức lương", "tuyển dụng", "vị trí", "kinh nghiệm",
    "job description", "responsibilities", "requirements", "benefits",
    "we are hiring", "we are looking for", "qualifications", "salary",
    "employment type", "full-time", "part-time", "internship",
]

# CV/résumé signals that, when dominant WITHOUT hiring language, mean the file is
# a candidate résumé mistakenly uploaded to the JD flow.
_CV_ONLY_SIGNALS = ["học vấn", "curriculum vitae", "resume", "objective", "career objective"]

_COPY: dict[str, tuple[str, str, list[str]]] = {
    "blank": (
        "Tệp này có vẻ trống hoặc không có nội dung đọc được. Hãy tải lên bản mô tả công việc khác.",
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
        text, ["tuyển dụng", "mô tả công việc", "we are hiring", "we are looking for",
               "job description", "responsibilities", "quyền lợi", "benefits"]
    ):
        return "not_a_jd"
    if len(text) < _INSUFFICIENT_THRESHOLD:
        return "insufficient"
    return "ok"


def reject_copy(status: str) -> dict:
    vi, en, actions = _COPY.get(status, _COPY["not_a_jd"])
    return {"reason": status, "message_vi": vi, "message_en": en, "next_actions": list(actions)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_validation.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/extraction/jd/validation.py backend/tests/unit/ai_extraction_jd/test_jd_validation.py
git commit -m "feat(jd): is-this-a-JD validity gate rejecting CVs/blank/junk"
```

---

### Task 4: JD prompts v2 (text + vision) for the full field set

**Files:**
- Create: `backend/app/ai/prompts/jd_extraction/v2.py`
- Test: `backend/tests/unit/ai_extraction_jd/test_jd_prompt_v2.py`

**Interfaces:**
- Produces: `PROMPT_VERSION: int = 2`; `TEXT_SYSTEM_PROMPT: str`; `VISION_SYSTEM_PROMPT: str`; `build_text_user_message(raw_text: str) -> str`; `VISION_USER_PROMPT: str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai_extraction_jd/test_jd_prompt_v2.py
from app.ai.prompts.jd_extraction import v2


def test_prompt_version_and_schema_fields_present():
    assert v2.PROMPT_VERSION == 2
    for token in ("candidate_requirements", "salary_mode", "experience_mode",
                  "seniority_level", "application_deadline", "is_jd"):
        assert token in v2.TEXT_SYSTEM_PROMPT
        assert token in v2.VISION_SYSTEM_PROMPT


def test_user_message_truncates_long_text():
    msg = v2.build_text_user_message("x" * 9000)
    assert "document truncated" in msg
    assert len(msg) < 9000 + 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_prompt_v2.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the prompt module**

Create `backend/app/ai/prompts/jd_extraction/v2.py`:

```python
# Version: 2 | Date: 2026-07-05 | Author: ai-engineer
# Task: jd_extraction — parse an uploaded JD (text or image/scan) into the FULL
# structured field set that auto-fills the job-posting form.
"""Prompt templates for ``jd_extraction`` (v2): text + vision variants.

Covers every field the backend Job model supports, including structured salary
modes, experience mode, seniority, industry, application deadline, and the full
candidate_requirements eligibility block (gender/age/marital/nationality/
languages/certifications/work authorization/education). Never invents data —
missing fields are null and requirement groups default to not_required.
"""

from __future__ import annotations

PROMPT_VERSION = 2

_SCHEMA = """{
  "is_jd": true|false,
  "detected_language": "vi"|"en"|"mixed",
  "title": "<string|null>", "title_en": "<string|null>",
  "description_vi": "<string|null>", "description_en": "<string|null>",
  "requirements_vi": "<string|null>", "requirements_en": "<string|null>",
  "benefits_vi": "<string|null>", "benefits_en": "<string|null>",
  "employment_type": "full_time|part_time|internship|contract|null",
  "location_type": "onsite|remote|hybrid|null",
  "locations": [{"type":"onsite|remote|hybrid","city":"<string|null>","country":"<string>"}],
  "seniority_level": "intern|fresher|junior|middle|senior|lead|manager|director|null",
  "industry": "<string|null>",
  "required_skills": ["<skill>"], "preferred_skills": ["<skill>"],
  "experience_min_years": <int|null>, "experience_max_years": <int|null>,
  "experience_mode": "no_requirement|fresher|range|min|max|null",
  "degree_required": "bachelor|master|phd|high_school|none|null",
  "salary_min": <int|null>, "salary_max": <int|null>, "salary_currency": "<string|null>",
  "salary_mode": "negotiable|hidden|fixed|range|from|to|null",
  "salary_period": "monthly|yearly|null",
  "salary_gross_net": "unspecified|gross|net|null",
  "headcount": <int|null>,
  "application_deadline": "<YYYY-MM-DD|null>",
  "candidate_requirements": {
    "gender": {"mode":"not_required|required|preferred","values":["male|female|..."]},
    "age": {"mode":"not_required|at_least|up_to|range","min":<int|null>,"max":<int|null>},
    "marital_status": {"mode":"not_required|required|preferred","values":["single|married|..."]},
    "nationalities": {"mode":"not_required|required|preferred","values":["<country>"]},
    "work_authorization": {"mode":"not_required|required|preferred","values":["<string>"]},
    "education": {"mode":"not_required|required|preferred","values":["<string>"]},
    "languages": [{"language":"<string>","proficiency":"<string|null>","required":true}],
    "certifications": [{"name":"<string>","required":true}],
    "note": "<string|null>"
  }
}"""

_RULES = """EXTRACTION RULES:
1. Extract ONLY information explicitly stated. Never infer, fabricate, or autocomplete.
2. Return null for any field not present. Requirement groups default to mode "not_required".
3. Salary: normalize "10 triệu" -> 10000000, "5M VND" -> 5000000, "$1000" -> 1000 currency="USD".
   Pick salary_mode: a single figure with "thỏa thuận"/"negotiable" -> "negotiable" (min/max null);
   a min-max pair -> "range"; only a floor ("from 10tr") -> "from"; only a ceiling -> "to";
   one exact number -> "fixed". Set salary_period ("monthly"/"yearly") and salary_gross_net
   ("gross"/"net") only when stated, else "monthly"/"unspecified".
4. Experience: set experience_mode ("fresher" if entry-level/no experience; "min"/"max"/"range"
   from the years stated; "no_requirement" if truly unstated). Put years in the number fields.
5. Locations: one entry per worksite; each carries its own type. A job can mix onsite+remote.
6. Eligibility: if the JD states gender/age/marital/nationality/language/certification/work
   authorization requirements (e.g. "chỉ tuyển nữ", "tuổi 22-30", "đã kết hôn"), fill the matching
   group; otherwise leave it "not_required". Do NOT moralize or omit stated requirements.
7. Skills: short searchable tags, not sentences.
8. Set is_jd=false ONLY if the document is clearly NOT a job description (a CV/résumé, invoice,
   article, receipt, form, or blank page). Never fabricate a JD from a non-JD.
9. Return ONLY one JSON object matching the schema — no prose, no markdown fences."""

TEXT_SYSTEM_PROMPT = f"""You are a precise job-description parser for a Vietnamese \
university career platform. Extract structured job-posting fields from raw text copied \
from a partner's JD document (Vietnamese, English, or both).

{_RULES}

OUTPUT JSON SCHEMA:
{_SCHEMA}
"""

VISION_SYSTEM_PROMPT = f"""You are a precise job-description parser for a Vietnamese \
university career platform. You are given one or more IMAGES of a single job-description \
document (and possibly its raw embedded text for reference). Transcribe and STRUCTURE it \
into clean JSON. Preserve Vietnamese diacritics exactly. Read multi-column layouts in \
natural order.

{_RULES}

OUTPUT JSON SCHEMA:
{_SCHEMA}
"""

VISION_USER_PROMPT = (
    "Transcribe and structure this job description into the JSON schema. "
    "Return only the JSON object."
)


def build_text_user_message(raw_text: str) -> str:
    truncated = raw_text[:8000]
    if len(raw_text) > 8000:
        truncated += "\n\n[... document truncated ...]"
    return f"<JOB_DESCRIPTION_TEXT>\n{truncated}\n</JOB_DESCRIPTION_TEXT>\n\nExtract fields as JSON."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_prompt_v2.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/prompts/jd_extraction/v2.py backend/tests/unit/ai_extraction_jd/test_jd_prompt_v2.py
git commit -m "feat(jd): v2 extraction prompts (text + vision) for full field set"
```

---

### Task 5: JD text-LLM structuring adapter

**Files:**
- Create: `backend/app/ai/extraction/jd/structuring.py`
- Test: `backend/tests/unit/ai_extraction_jd/test_jd_structuring.py`

**Interfaces:**
- Consumes: `app.ai.cv.llm.generate_json_note`, `app.ai.extraction.adapters.base.redact_secrets`, `prompts.jd_extraction.v2`.
- Produces: `async run_jd_text_structuring(text: str) -> dict` — returns raw LLM JSON dict; raises `AIUnavailableError` on failure. Module-level name `generate_json_note` (imported) so tests can monkeypatch `jd.structuring.generate_json_note`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai_extraction_jd/test_jd_structuring.py
import pytest

from app.ai.extraction.jd import structuring
from app.shared.exceptions import AIUnavailableError


@pytest.mark.asyncio
async def test_run_jd_text_structuring_returns_llm_json(monkeypatch):
    async def fake(**kwargs):
        assert kwargs["task_type"] == "jd_extraction"
        assert "JOB_DESCRIPTION_TEXT" in kwargs["user_content"]
        return {"title": "Backend Engineer", "employment_type": "full_time"}

    monkeypatch.setattr(structuring, "generate_json_note", fake)
    out = await structuring.run_jd_text_structuring("We are hiring a Backend Engineer, full-time.")
    assert out["title"] == "Backend Engineer"


@pytest.mark.asyncio
async def test_propagates_ai_unavailable(monkeypatch):
    async def boom(**kwargs):
        raise AIUnavailableError()

    monkeypatch.setattr(structuring, "generate_json_note", boom)
    with pytest.raises(AIUnavailableError):
        await structuring.run_jd_text_structuring("some jd text")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_structuring.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `backend/app/ai/extraction/jd/structuring.py`:

```python
"""Text-LLM structuring tier for JD extraction (text-only; secrets redacted).

Routes through the shared gateway JSON helper so provider/model/token internals
never leak and usage is tracked. Never receives raw bytes — only extracted text.
"""

from __future__ import annotations

from app.ai.cv.llm import generate_json_note  # generic gateway JSON helper
from app.ai.extraction.adapters.base import redact_secrets
from app.ai.prompts.jd_extraction import v2 as prompt


async def run_jd_text_structuring(text: str) -> dict:
    """Structure JD ``text`` into the v2 JSON field set. Raises AIUnavailableError."""
    safe = redact_secrets(text)
    return await generate_json_note(
        task_type="jd_extraction",
        system_prompt=prompt.TEXT_SYSTEM_PROMPT,
        user_content=prompt.build_text_user_message(safe),
        temperature=0.1,
        max_tokens=2200,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_structuring.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/extraction/jd/structuring.py backend/tests/unit/ai_extraction_jd/test_jd_structuring.py
git commit -m "feat(jd): text-LLM structuring tier (text-only, redacted)"
```

---

### Task 6: JD vision adapter (images/scans) + test seam

**Files:**
- Create: `backend/app/ai/extraction/jd/vision.py`
- Test: `backend/tests/unit/ai_extraction_jd/test_jd_vision.py`

**Interfaces:**
- Consumes: `runtime_config.current()`, `factory._get_api_key`, `factory.real_provider_active`, `output_guard.scrub_text`, `redact_secrets`, `FileKind`, `prompts.jd_extraction.v2`.
- Produces:
  - `JdVisionEngine` Protocol (`.available: bool`, `.extract(data, kind, *, max_image_px, max_pages, native_text=None) -> dict | None`).
  - `GatewayJdVisionAdapter`, `DisabledJdVisionAdapter`.
  - `get_jd_vision_adapter()`, `set_jd_vision_adapter(adapter|None)`.
  - `run_jd_vision_extraction(data, kind, *, enabled, max_image_px, max_pages, native_text=None) -> dict | None` (best-effort; never raises; returns raw LLM JSON dict with `is_jd`, or None).
- Note: image-prep helpers are copied JD-local (do NOT import private names from `adapters/vision.py`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai_extraction_jd/test_jd_vision.py
from app.ai.extraction.jd import vision as jdv
from app.ai.extraction.text_extraction import FileKind


class _FakeAdapter:
    available = True

    def extract(self, data, kind, *, max_image_px, max_pages, native_text=None):
        return {"is_jd": True, "title": "Sales Executive", "employment_type": "full_time"}


def teardown_function():
    jdv.set_jd_vision_adapter(None)


def test_run_uses_injected_adapter_when_enabled():
    jdv.set_jd_vision_adapter(_FakeAdapter())
    out = jdv.run_jd_vision_extraction(
        b"\xff\xd8\xff", FileKind.IMAGE, enabled=True, max_image_px=2200, max_pages=3
    )
    assert out["title"] == "Sales Executive"


def test_run_returns_none_when_disabled():
    jdv.set_jd_vision_adapter(_FakeAdapter())
    assert jdv.run_jd_vision_extraction(
        b"\xff\xd8\xff", FileKind.IMAGE, enabled=False, max_image_px=2200, max_pages=3
    ) is None


def test_disabled_default_adapter_is_unavailable():
    jdv.set_jd_vision_adapter(jdv.DisabledJdVisionAdapter())
    assert jdv.run_jd_vision_extraction(
        b"\xff\xd8\xff", FileKind.IMAGE, enabled=True, max_image_px=2200, max_pages=3
    ) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_vision.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the adapter**

Create `backend/app/ai/extraction/jd/vision.py`:

```python
"""Vision-LLM tier for JD extraction: image / scanned-PDF JD -> structured JSON.

Runs ONLY when native text is insufficient (never on digital text PDFs). Images
are downscaled and scanned PDFs send at most ``max_pages`` rasterized pages. The
model id is resolved via an alias and never exposed. Gateway-backed by default;
a disabled adapter is used offline/in tests. Best-effort — never raises.

Image-prep helpers are copied JD-local (kept independent from the CV vision
adapter so a concurrent CV session can evolve that file freely).
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Protocol, runtime_checkable

import httpx

from app.ai.extraction.adapters.base import redact_secrets
from app.ai.extraction.text_extraction import FileKind
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import _get_api_key, real_provider_active
from app.ai.gateway.output_guard import scrub_text
from app.ai.prompts.jd_extraction import v2 as prompt
from app.core.config import get_settings

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_MAX_OUTPUT_TOKENS = 3000
_MAX_NATIVE_TEXT_CHARS = 8000
_NO_KEY_PROVIDERS = {"ollama-local", "ollama"}
_NATIVE_TEXT_PREFIX = (
    "For reference, here is the raw text embedded in the document. Reading ORDER "
    "may be scrambled; rely on the image(s) for structure but use this text for the "
    "EXACT spelling of numbers, emails, and dates. RAW TEXT:\n"
)


@runtime_checkable
class JdVisionEngine(Protocol):
    @property
    def available(self) -> bool: ...

    def extract(self, data: bytes, kind: FileKind, *, max_image_px: int,
                max_pages: int, native_text: str | None = None) -> dict | None: ...


class DisabledJdVisionAdapter:
    engine_family = "jd_vision_llm"
    engine_version = "disabled"

    @property
    def available(self) -> bool:
        return False

    def extract(self, data, kind, *, max_image_px, max_pages, native_text=None):
        return None


class GatewayJdVisionAdapter:
    engine_family = "jd_vision_llm_gateway"
    engine_version = "v2"

    def _alias(self, cfg: runtime_config.EffectiveAiConfig) -> str:
        configured = get_settings().jd_vision_provider_alias
        if configured in cfg.provider_routes:
            return configured
        return "vision_cheap" if "vision_cheap" in cfg.provider_routes else configured

    @property
    def available(self) -> bool:
        cfg = runtime_config.current()
        route = cfg.provider_routes.get(self._alias(cfg))
        if not real_provider_active() or route is None:
            return False
        provider_name = route[0]
        if provider_name in _NO_KEY_PROVIDERS:
            return True
        return bool(_get_api_key(provider_name))

    def extract(self, data, kind, *, max_image_px, max_pages, native_text=None):
        cfg = runtime_config.current()
        route = cfg.provider_routes.get(self._alias(cfg))
        if route is None:
            return None
        provider_name, base_url, model_id = route
        api_key = _get_api_key(provider_name)
        if not api_key and provider_name not in _NO_KEY_PROVIDERS:
            return None

        images = _prepare_images(data, kind, max_px=max_image_px, max_pages=max_pages)
        if not images:
            return None

        content: list[dict] = [{"type": "text", "text": prompt.VISION_USER_PROMPT}]
        if native_text and native_text.strip():
            redacted = redact_secrets(native_text)[:_MAX_NATIVE_TEXT_CHARS]
            content.append({"type": "text", "text": _NATIVE_TEXT_PREFIX + redacted})
        for jpeg in images:
            b64 = base64.b64encode(jpeg).decode("ascii")
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": prompt.VISION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0.0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://career.vinuni.edu.vn",
            "X-Title": "VinUni Career Platform",
        }
        try:
            with httpx.Client(timeout=float(get_settings().jd_extraction_max_seconds)) as client:
                resp = client.post(f"{base_url.rstrip('/')}/chat/completions",
                                   json=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

        choice = (body.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content", "")
        if isinstance(raw, list):
            raw = "".join(p.get("text", "") for p in raw if isinstance(p, dict))
        return _extract_json(scrub_text(raw or ""))


# ---- JD-local image prep (independent copy; do not import from CV vision) ----

def _prepare_images(data: bytes, kind: FileKind, *, max_px: int, max_pages: int) -> list[bytes]:
    if kind is FileKind.IMAGE:
        jpeg = _downscale_to_jpeg(data, max_px)
        return [jpeg] if jpeg else []
    if kind is FileKind.PDF:
        return _pdf_pages_to_jpeg(data, max_pages=max_pages, max_px=max_px)
    return []


def _downscale_to_jpeg(data: bytes, max_px: int) -> bytes | None:
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as opened:
            img = opened.convert("RGB")
            longest = max(img.size)
            if longest > max_px:
                scale = max_px / float(longest)
                img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _pdf_pages_to_jpeg(data: bytes, *, max_pages: int, max_px: int) -> list[bytes]:
    pages: list[bytes] = []
    try:
        import fitz  # PyMuPDF
        with fitz.open(stream=data, filetype="pdf") as doc:
            for index, page in enumerate(doc):
                if index >= max_pages:
                    break
                pix = page.get_pixmap(dpi=150)
                jpeg = _downscale_to_jpeg(pix.tobytes("png"), max_px)
                if jpeg:
                    pages.append(jpeg)
    except ImportError:
        return []
    except Exception:  # noqa: BLE001
        return pages
    return pages


def _extract_json(raw: str) -> dict | None:
    text = raw.strip()
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


# ---- process-wide seam (mirrors OCR/vision adapter seams) --------------------

_adapter: JdVisionEngine | None = None


def get_jd_vision_adapter() -> JdVisionEngine:
    global _adapter
    if _adapter is None:
        _adapter = GatewayJdVisionAdapter()
    return _adapter


def set_jd_vision_adapter(adapter: JdVisionEngine | None) -> None:
    global _adapter
    _adapter = adapter


def run_jd_vision_extraction(data: bytes, kind: FileKind, *, enabled: bool,
                             max_image_px: int, max_pages: int,
                             native_text: str | None = None) -> dict | None:
    """Run the JD vision tier if enabled + available. Best-effort; never raises."""
    if not enabled:
        return None
    adapter = get_jd_vision_adapter()
    if not adapter.available:
        return None
    try:
        return adapter.extract(data, kind, max_image_px=max_image_px,
                               max_pages=max_pages, native_text=native_text)
    except Exception:  # noqa: BLE001 - vision is best-effort
        return None


__all__ = [
    "JdVisionEngine", "DisabledJdVisionAdapter", "GatewayJdVisionAdapter",
    "get_jd_vision_adapter", "set_jd_vision_adapter", "run_jd_vision_extraction",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_vision.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/extraction/jd/vision.py backend/tests/unit/ai_extraction_jd/test_jd_vision.py
git commit -m "feat(jd): vision-LLM tier for image/scanned JD uploads"
```

---

### Task 7: JD cascade orchestration

**Files:**
- Create: `backend/app/ai/extraction/jd/policy.py`
- Create: `backend/app/ai/extraction/jd/cascade.py`
- Test: `backend/tests/unit/ai_extraction_jd/test_jd_cascade.py`

**Interfaces:**
- Consumes: everything from Tasks 2/3/5/6 + reused primitives; `cv_validation.security_gate`, `cv_validation.compute_checksum`.
- Produces:
  - `policy.JdEnginePolicy` dataclass + `policy.resolve_jd_policy() -> JdEnginePolicy` (`max_bytes`, `ocr_langs`, `vision_enabled`, `vision_max_image_px`, `vision_max_pages`).
  - `cascade.JdExtractionOutcome` dataclass: `status: str` (`ok|blank|not_a_jd|low_quality_scan|insufficient|ai_unavailable|file_too_large|unsupported_file_type|password_protected_file|corrupt_file|file_rejected_security`), `fields: dict`, `field_confidence: dict`, `needs_review: bool`, `raw_text_preview: str | None`, `detected_language: str | None`, `is_ai_extraction: bool`, internal diagnostics `vision_used/ocr_used/llm_used: bool`.
  - `async cascade.run_jd_cascade(filename: str, data: bytes, *, policy: JdEnginePolicy | None = None, structurer=..., vision_runner=...) -> JdExtractionOutcome`. `structurer` defaults to `structuring.run_jd_text_structuring`; `vision_runner` defaults to `vision.run_jd_vision_extraction` (injected for tests).
  - Module-level re-exports `extract_text`, `sniff_kind` (so tests can monkeypatch `cascade.extract_text`).
- Escalation: IMAGE always → vision; PDF with `< 40` native chars AND `has_images`/no text → vision; otherwise text path. If vision returns a dict with `is_jd != False`, it is the structured source (no text-LLM call). Text path: OCR fallback (if image/scanned and vision produced nothing) → is-JD gate on the text → text-LLM structuring.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/ai_extraction_jd/test_jd_cascade.py
import pytest

from app.ai.extraction.jd import cascade
from app.ai.extraction.text_extraction import ExtractionResult
from app.shared.exceptions import AIUnavailableError


class _Res(ExtractionResult):
    pass


@pytest.mark.asyncio
async def test_digital_pdf_uses_text_path_no_vision(monkeypatch):
    jd_text = ("Tuyển Nhân viên Kinh doanh. Mô tả công việc: bán hàng. "
               "Yêu cầu: 1 năm kinh nghiệm. Quyền lợi: lương 10-15 triệu.")
    monkeypatch.setattr(cascade, "extract_text",
                        lambda f, d: ExtractionResult(text=jd_text, page_count=1, engine="pdfplumber"))

    async def fake_structurer(text):
        return {"title": "Nhân viên Kinh doanh", "employment_type": "full_time",
                "salary_mode": "range", "salary_min": 10000000, "salary_max": 15000000}

    vision_calls = []

    def fake_vision(*a, **k):
        vision_calls.append(1)
        return None

    out = await cascade.run_jd_cascade("jd.pdf", b"%PDF-1.4 fake",
                                       structurer=fake_structurer, vision_runner=fake_vision)
    assert out.status == "ok"
    assert out.is_ai_extraction is True
    assert out.fields["employment_type"] == "full_time"
    assert out.fields["salary_mode"] == "range"
    assert vision_calls == []  # digital text never reaches vision


@pytest.mark.asyncio
async def test_image_uses_vision_path(monkeypatch):
    monkeypatch.setattr(cascade, "extract_text",
                        lambda f, d: ExtractionResult(text="", page_count=1, engine="none"))

    def fake_vision(data, kind, *, enabled, max_image_px, max_pages, native_text=None):
        return {"is_jd": True, "title": "Sales Exec", "employment_type": "full_time",
                "candidate_requirements": {"gender": {"mode": "required", "values": ["female"]}}}

    async def fake_structurer(text):
        raise AssertionError("text structurer must not run on the vision path")

    out = await cascade.run_jd_cascade("jd.png", b"\xff\xd8\xff fake",
                                       structurer=fake_structurer, vision_runner=fake_vision)
    assert out.status == "ok"
    assert out.fields["title"] == "Sales Exec"
    assert out.fields["candidate_requirements"]["gender"]["mode"] == "required"
    assert out.vision_used is True


@pytest.mark.asyncio
async def test_cv_pdf_rejected_as_not_a_jd(monkeypatch):
    cv_text = ("Nguyen Van A. Email a@x.com. Học vấn: Đại học. "
               "Kinh nghiệm: công ty X. Kỹ năng: Python.")
    monkeypatch.setattr(cascade, "extract_text",
                        lambda f, d: ExtractionResult(text=cv_text, page_count=1, engine="pdfplumber"))

    async def fake_structurer(text):
        raise AssertionError("must not call LLM for a non-JD")

    out = await cascade.run_jd_cascade("resume.pdf", b"%PDF fake",
                                       structurer=fake_structurer, vision_runner=lambda *a, **k: None)
    assert out.status == "not_a_jd"
    assert out.is_ai_extraction is False
    assert out.fields == {}


@pytest.mark.asyncio
async def test_ai_unavailable_returns_raw_text_fallback(monkeypatch):
    jd_text = "Tuyển dụng: Mô tả công việc và yêu cầu, quyền lợi mức lương 10 triệu." * 3
    monkeypatch.setattr(cascade, "extract_text",
                        lambda f, d: ExtractionResult(text=jd_text, page_count=1, engine="pdfplumber"))

    async def down(text):
        raise AIUnavailableError()

    out = await cascade.run_jd_cascade("jd.pdf", b"%PDF fake",
                                       structurer=down, vision_runner=lambda *a, **k: None)
    assert out.status == "ai_unavailable"
    assert out.is_ai_extraction is False
    assert out.raw_text_preview and "Tuyển dụng" in out.raw_text_preview


@pytest.mark.asyncio
async def test_oversize_file_rejected(monkeypatch):
    from app.ai.extraction.jd.policy import JdEnginePolicy
    pol = JdEnginePolicy(max_bytes=10, ocr_langs="vie+eng", vision_enabled=False,
                         vision_max_image_px=2200, vision_max_pages=3)
    out = await cascade.run_jd_cascade("jd.pdf", b"x" * 50, policy=pol)
    assert out.status == "file_too_large"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_cascade.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3a: Implement the policy**

Create `backend/app/ai/extraction/jd/policy.py`:

```python
"""Resolve JD engine settings into an effective policy for the cascade."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings


@dataclass(slots=True)
class JdEnginePolicy:
    max_bytes: int
    ocr_langs: str
    vision_enabled: bool
    vision_max_image_px: int
    vision_max_pages: int


def resolve_jd_policy(settings: Settings | None = None) -> JdEnginePolicy:
    s = settings or get_settings()
    return JdEnginePolicy(
        max_bytes=s.jd_max_upload_bytes,
        ocr_langs=s.jd_ocr_langs,
        vision_enabled=s.jd_vision_extraction_enabled,
        vision_max_image_px=s.jd_vision_max_image_px,
        vision_max_pages=s.jd_vision_max_pages,
    )
```

- [ ] **Step 3b: Implement the cascade**

Create `backend/app/ai/extraction/jd/cascade.py`:

```python
"""Cost-tiered JD ingestion cascade.

Order: file/security gate -> native text -> (image/scanned? -> vision-LLM;
digital text -> skip vision) -> OCR fallback -> is-JD gate -> text-LLM
structuring -> validate + score. Extraction is auto-fill only; nothing persists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.ai.extraction import cv_validation
from app.ai.extraction.adapters.ocr import get_ocr_adapter
from app.ai.extraction.jd import structuring as _structuring
from app.ai.extraction.jd import validation as jd_validation
from app.ai.extraction.jd import vision as _vision
from app.ai.extraction.jd.policy import JdEnginePolicy, resolve_jd_policy
from app.ai.extraction.jd.schema import validate_and_score
from app.ai.extraction.text_extraction import (
    ExtractionError,
    FileKind,
    extract_text,
    sniff_kind,
)
from app.shared.exceptions import AIUnavailableError

logger = logging.getLogger(__name__)

_NATIVE_TEXT_MIN = 40  # below this a PDF is treated as scanned/needs-vision

# text_extraction ExtractionError.code -> outcome status
_EXTRACTION_ERROR_STATUS = {
    "PASSWORD_PROTECTED_FILE": "password_protected_file",
    "CORRUPT_FILE": "corrupt_file",
    "UNSUPPORTED_FILE_TYPE": "unsupported_file_type",
}


@dataclass(slots=True)
class JdExtractionOutcome:
    status: str
    fields: dict = field(default_factory=dict)
    field_confidence: dict = field(default_factory=dict)
    needs_review: bool = False
    raw_text_preview: str | None = None
    detected_language: str | None = None
    is_ai_extraction: bool = False
    # internal diagnostics — never surfaced to end users
    vision_used: bool = False
    ocr_used: bool = False
    llm_used: bool = False


def _fail(status: str) -> JdExtractionOutcome:
    return JdExtractionOutcome(status=status)


def _finalize(raw_llm: dict, raw_text: str, *, vision_used: bool,
              ocr_used: bool, llm_used: bool) -> JdExtractionOutcome:
    if raw_llm.get("is_jd") is False:
        return _fail("not_a_jd")
    validated, conf = validate_and_score(raw_llm, raw_text)
    return JdExtractionOutcome(
        status="ok",
        fields=validated,
        field_confidence=conf,
        needs_review=any(e.get("needs_review") for e in conf.values()),
        detected_language=validated.get("detected_language"),
        is_ai_extraction=True,
        vision_used=vision_used,
        ocr_used=ocr_used,
        llm_used=llm_used,
    )


async def run_jd_cascade(filename: str, data: bytes, *,
                         policy: JdEnginePolicy | None = None,
                         structurer=_structuring.run_jd_text_structuring,
                         vision_runner=_vision.run_jd_vision_extraction) -> JdExtractionOutcome:
    pol = policy or resolve_jd_policy()

    # Tier 0 — file + security gate
    if len(data) > pol.max_bytes:
        return _fail("file_too_large")
    kind = sniff_kind(filename, data)
    if kind not in (FileKind.PDF, FileKind.DOCX, FileKind.TXT, FileKind.IMAGE):
        return _fail("unsupported_file_type")
    if cv_validation.security_gate(data, filename) is not None:
        return _fail("file_rejected_security")

    # Tier 1 — native text
    try:
        extraction = extract_text(filename, data)
    except ExtractionError as exc:
        return _fail(_EXTRACTION_ERROR_STATUS.get(exc.code, "corrupt_file"))
    native_text = (extraction.text or "").strip()
    ocr_used = extraction.ocr_used

    is_image = kind is FileKind.IMAGE
    scanned_pdf = kind is FileKind.PDF and len(native_text) < _NATIVE_TEXT_MIN

    # Tier 3 — vision (images / scanned PDFs only)
    if is_image or scanned_pdf:
        vision_json = vision_runner(
            data, kind,
            enabled=pol.vision_enabled,
            max_image_px=pol.vision_max_image_px,
            max_pages=pol.vision_max_pages,
            native_text=native_text or None,
        )
        if isinstance(vision_json, dict):
            return _finalize(vision_json, native_text,
                             vision_used=True, ocr_used=ocr_used, llm_used=False)

        # Tier 4 — OCR fallback when vision produced nothing
        if not native_text:
            adapter = get_ocr_adapter()
            if getattr(adapter, "available", False):
                try:
                    native_text = (adapter.recognize(data, pol.ocr_langs) or "").strip()
                    ocr_used = True
                except Exception:  # noqa: BLE001 - OCR is best-effort
                    native_text = ""

    # Tier 5 — is-JD gate (text path)
    status = jd_validation.classify_jd_content(native_text, kind=kind, ocr_used=ocr_used)
    if status != "ok":
        return _fail(status)

    # Tier 6 — text-LLM structuring
    try:
        raw_llm = await structurer(native_text)
    except AIUnavailableError:
        return JdExtractionOutcome(
            status="ai_unavailable",
            is_ai_extraction=False,
            raw_text_preview=native_text[:2000],
            ocr_used=ocr_used,
        )

    # Tier 7 — validate + score
    return _finalize(raw_llm, native_text, vision_used=False, ocr_used=ocr_used, llm_used=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd/test_jd_cascade.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/extraction/jd/policy.py backend/app/ai/extraction/jd/cascade.py backend/tests/unit/ai_extraction_jd/test_jd_cascade.py
git commit -m "feat(jd): cost-tiered JD ingestion cascade orchestration"
```

---

### Task 8: Wire the cascade into the service, router, and eval runner

**Files:**
- Modify: `backend/app/modules/opportunities/application/jd_upload_service.py` (rewrite `extract_jd_from_upload`; keep `JDLocation`/`JDFileError` removed or unused code out)
- Modify: `backend/app/modules/opportunities/api/router.py:643-663` (`upload_jd_document`)
- Modify: `backend/app/ai/evaluation/runners/jd_extraction.py` (mock the new seams)
- Test: `backend/tests/integration/test_jd_upload_service.py`

**Interfaces:**
- Consumes: `cascade.run_jd_cascade`, `cascade.JdExtractionOutcome`, `jd_validation.reject_copy`, `prompts.jd_extraction.v2.PROMPT_VERSION`.
- Produces:
  - `async jd_upload_service.extract_jd_from_upload(filename, data, content_type=None) -> dict`. On `ok`/`ai_unavailable` returns a flat dict (backward-compatible keys + new fields). On reject statuses raises `ValidationFailedError` with `details=reject_copy(status)`.
  - Router accepts image content types and passes bytes through unchanged; returns the dict on success.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/integration/test_jd_upload_service.py
import pytest

from app.ai.extraction.jd import cascade
from app.ai.extraction.text_extraction import ExtractionResult
from app.modules.opportunities.application import jd_upload_service as svc
from app.shared.exceptions import ValidationFailedError


@pytest.mark.asyncio
async def test_ok_returns_backward_compatible_and_new_fields(monkeypatch):
    jd_text = ("Tuyển Kỹ sư Backend. Mô tả công việc: xây dựng API. "
               "Yêu cầu: 2 năm kinh nghiệm. Quyền lợi: lương 20-30 triệu gross.")
    monkeypatch.setattr(cascade, "extract_text",
                        lambda f, d: ExtractionResult(text=jd_text, page_count=1, engine="pdfplumber"))

    async def fake_structurer(text):
        return {"title": "Kỹ sư Backend", "employment_type": "full_time",
                "salary_mode": "range", "salary_min": 20000000, "salary_max": 30000000,
                "salary_gross_net": "gross", "experience_mode": "min",
                "experience_min_years": 2, "detected_language": "vi",
                "candidate_requirements": {"gender": {"mode": "required", "values": ["female"]}}}

    monkeypatch.setattr("app.ai.extraction.jd.cascade._structuring.run_jd_text_structuring",
                        fake_structurer, raising=False)
    # simpler: inject via the cascade default by patching the structurer arg
    out = await svc.extract_jd_from_upload_with(
        filename="jd.pdf", data=b"%PDF fake", structurer=fake_structurer,
        vision_runner=lambda *a, **k: None,
    )
    # backward-compatible keys
    assert out["is_ai_extraction"] is True
    assert out["employment_type"] == "full_time"
    assert out["field_confidence"]["employment_type"]["needs_review"] is True
    # new fields
    assert out["salary_mode"] == "range"
    assert out["candidate_requirements"]["gender"]["mode"] == "required"
    assert out["status"] == "ok"


@pytest.mark.asyncio
async def test_not_a_jd_raises_user_safe_error(monkeypatch):
    cv_text = "Nguyen Van A. Email a@x.com. Học vấn Đại học. Kinh nghiệm. Kỹ năng Python."
    monkeypatch.setattr(cascade, "extract_text",
                        lambda f, d: ExtractionResult(text=cv_text, page_count=1, engine="pdfplumber"))

    async def unused(text):
        raise AssertionError("no LLM for non-JD")

    with pytest.raises(ValidationFailedError) as ei:
        await svc.extract_jd_from_upload_with(
            filename="resume.pdf", data=b"%PDF fake",
            structurer=unused, vision_runner=lambda *a, **k: None)
    assert ei.value.details["reason"] == "not_a_jd"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/test_jd_upload_service.py -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'extract_jd_from_upload_with'`)

- [ ] **Step 3a: Rewrite the service**

Replace the body of `backend/app/modules/opportunities/application/jd_upload_service.py` with:

```python
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

from app.ai.extraction.jd import validation as jd_validation
from app.ai.extraction.jd.cascade import JdExtractionOutcome, run_jd_cascade
from app.ai.extraction.jd import structuring as _structuring
from app.ai.extraction.jd import vision as _vision
from app.ai.prompts.jd_extraction import v2 as jd_prompt
from app.shared.exceptions import ValidationFailedError

logger = logging.getLogger(__name__)

# Reject statuses that map to a user-safe 422 (vs. the ok/ai_unavailable dict).
_REJECT_STATUSES = {
    "blank", "not_a_jd", "low_quality_scan", "insufficient",
    "file_too_large", "unsupported_file_type",
    "password_protected_file", "corrupt_file", "file_rejected_security",
}

# File-gate statuses reuse a generic file message when no JD-specific copy exists.
_GENERIC_FILE_COPY = {
    "file_too_large": ("Tệp quá lớn. Hãy nén hoặc chia nhỏ rồi thử lại.",
                       "File is too large. Compress it and try again."),
    "unsupported_file_type": ("Định dạng không hỗ trợ. Hãy tải PDF, DOCX, TXT hoặc ảnh.",
                              "Unsupported file type. Upload a PDF, DOCX, TXT, or image."),
    "password_protected_file": ("Tệp PDF đang đặt mật khẩu. Hãy gỡ mật khẩu rồi tải lại.",
                                "This PDF is password-protected. Remove it and retry."),
    "corrupt_file": ("Không đọc được tệp này. Hãy xuất lại bản mới và thử lại.",
                     "We could not read this file. Export a fresh copy and retry."),
    "file_rejected_security": ("Tệp không vượt qua kiểm tra an toàn.",
                               "This file failed the security check."),
}


def _reject_details(status: str) -> dict:
    if status in _GENERIC_FILE_COPY:
        vi, en = _GENERIC_FILE_COPY[status]
        return {"reason": status, "message_vi": vi, "message_en": en,
                "next_actions": ["upload_another", "fill_manually"]}
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


async def extract_jd_from_upload_with(*, filename: str, data: bytes,
                                      structurer, vision_runner) -> dict:
    """Testable core: run the cascade with injected AI seams, map to a response."""
    outcome = await run_jd_cascade(filename, data,
                                   structurer=structurer, vision_runner=vision_runner)
    return _to_response(outcome)


async def extract_jd_from_upload(filename: str, data: bytes,
                                 content_type: str | None = None) -> dict:
    """Extract structured JD fields for form prefill. Never persists anything.

    Returns a flat dict (ok) or an ``ai_unavailable`` dict; raises
    ``ValidationFailedError`` (user-safe) for blank/not-a-JD/corrupt/etc.
    """
    return await extract_jd_from_upload_with(
        filename=filename, data=data,
        structurer=_structuring.run_jd_text_structuring,
        vision_runner=_vision.run_jd_vision_extraction,
    )
```

- [ ] **Step 3b: Update the router to accept images**

In `backend/app/modules/opportunities/api/router.py`, change the `upload_jd_document` endpoint (lines 643-663). Update the `summary`, the `File(...)` description, and keep the pass-through:

```python
@jobs_router.post(
    "/upload-jd",
    summary="Upload a job description (PDF/DOCX/TXT/image) and extract structured fields",
)
async def upload_jd_document(
    file: UploadFile = File(..., description="PDF, DOCX, TXT, or image job description"),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    """Extract structured job fields from an uploaded document for form prefill.

    Supports digital PDFs/DOCX/TXT and images/scans (OCR + vision). Returns
    prefill-ready fields on success, a raw-text fallback when AI is unavailable,
    and a user-safe validation error for blank/not-a-JD/corrupt files. Never
    writes to the database.
    """
    data = await file.read()
    result = await jd_upload_service.extract_jd_from_upload(
        filename=file.filename or "upload",
        data=data,
        content_type=file.content_type,
    )
    return result
```

- [ ] **Step 3c: Update the eval runner to the new seams**

Replace the `run_case` body in `backend/app/ai/evaluation/runners/jd_extraction.py` so it drives the cascade through the service's injectable seams (the dataset's `llm_json` becomes the mocked structured output; `provider: unavailable` raises):

```python
async def run_case(case: dict[str, Any]) -> Probe:
    inp = case.get("input") or {}
    raw_text = inp.get("raw_text", "")
    llm_json = inp.get("llm_json") or {}
    provider_down = inp.get("provider") == "unavailable"

    async def _fake_structurer(text: str) -> dict:
        if provider_down:
            raise AIUnavailableError()
        return llm_json

    def _fake_vision(*args: Any, **kwargs: Any):
        return None  # dataset drives the text path

    from app.ai.extraction.jd import cascade

    with mock.patch.object(
        cascade, "extract_text",
        return_value=type("R", (), {"text": raw_text, "page_count": 1,
                                     "engine": "pdfplumber", "ocr_used": False})(),
    ):
        try:
            result = await svc.extract_jd_from_upload_with(
                filename="jd.pdf", data=b"%PDF-fake",
                structurer=_fake_structurer, vision_runner=_fake_vision,
            )
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "code", None) or (
                getattr(exc, "details", {}) or {}).get("reason")
            return Probe(kind="jd_extraction", raised_code=code, raised_message=str(exc))

    blob = json.dumps(result, ensure_ascii=False, default=str).lower()
    return Probe(kind="jd_extraction", blob=blob, data=result)
```

Keep the existing `check(...)` function unchanged. Remove the now-unused `_FakeExtraction` class and the old `extract_text`/`generate_json_note` imports/patches.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integration/test_jd_upload_service.py app/ai/evaluation -k jd -v`
Expected: PASS (service tests + jd_extraction eval cases green)

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/opportunities/application/jd_upload_service.py backend/app/modules/opportunities/api/router.py backend/app/ai/evaluation/runners/jd_extraction.py backend/tests/integration/test_jd_upload_service.py
git commit -m "feat(jd): wire cascade into upload service + router (images, reject statuses, full fields)"
```

---

### Task 9: Refresh the eval dataset for the new fields + not-a-JD + fallback

**Files:**
- Modify: `backend/app/ai/evaluation/datasets/jd_extraction/happy_path.jsonl` (add cases for the new fields)
- Modify: `backend/app/ai/evaluation/datasets/jd_extraction/adversarial.jsonl` (add a not-a-JD/CV case)
- Modify: `backend/app/ai/evaluation/datasets/jd_extraction/fallback.jsonl` (ensure `provider: unavailable` case)
- Test: run the offline eval for the task.

**Interfaces:**
- Consumes: the `check(...)` keys already supported — `field_equals`, `field_needs_review`, `is_ai_extraction`, `error_code`, `no_crash`, `blob_excludes`.

- [ ] **Step 1: Add happy-path cases for the new structured fields**

Append to `backend/app/ai/evaluation/datasets/jd_extraction/happy_path.jsonl` (one JSON object per line):

```json
{"id": "jde_happy_salary_range_gross", "input": {"raw_text": "Tuyển Kỹ sư Backend. Mô tả công việc: xây dựng API. Yêu cầu tối thiểu 2 năm kinh nghiệm. Quyền lợi: lương 20-30 triệu gross/tháng.", "llm_json": {"title": "Kỹ sư Backend", "employment_type": "full_time", "salary_mode": "range", "salary_min": 20000000, "salary_max": 30000000, "salary_period": "monthly", "salary_gross_net": "gross", "experience_mode": "min", "experience_min_years": 2, "detected_language": "vi"}}, "expect": {"is_ai_extraction": true, "field_equals": {"field": "salary_mode", "value": "range"}, "field_needs_review": {"field": "salary_min", "value": true}, "no_crash": true}}
{"id": "jde_happy_gender_female_only", "input": {"raw_text": "Tuyển Lễ tân. Mô tả công việc: đón khách. Yêu cầu: chỉ tuyển nữ, tuổi 22-30. Quyền lợi: thưởng.", "llm_json": {"title": "Lễ tân", "employment_type": "full_time", "candidate_requirements": {"gender": {"mode": "required", "values": ["female"]}, "age": {"mode": "range", "min": 22, "max": 30}}, "detected_language": "vi"}}, "expect": {"field_equals": {"field": "candidate_requirements", "value": {"education": {"mode": "not_required", "values": [], "note": null}, "nationalities": {"mode": "not_required", "values": [], "note": null}, "gender": {"mode": "required", "values": ["female"], "note": null}, "age": {"mode": "range", "min": 22, "max": 30}, "marital_status": {"mode": "not_required", "values": [], "note": null}, "languages": [], "certifications": [], "work_authorization": {"mode": "not_required", "values": [], "note": null}, "note": null}}, "field_needs_review": {"field": "candidate_requirements", "value": true}, "no_crash": true}}
```

- [ ] **Step 2: Add an adversarial not-a-JD (CV) case**

Append to `backend/app/ai/evaluation/datasets/jd_extraction/adversarial.jsonl`:

```json
{"id": "jde_adv_cv_uploaded_as_jd", "input": {"raw_text": "Nguyen Van A. Email: a@example.com. Học vấn: Đại học Bách Khoa. Kinh nghiệm làm việc tại công ty X. Kỹ năng: Python, SQL.", "llm_json": {}}, "expect": {"error_code": "not_a_jd", "no_crash": true}}
```

- [ ] **Step 3: Ensure a provider-unavailable fallback case exists**

Append to `backend/app/ai/evaluation/datasets/jd_extraction/fallback.jsonl` (if not already present):

```json
{"id": "jde_fallback_provider_down", "input": {"raw_text": "Tuyển dụng Nhân viên. Mô tả công việc, yêu cầu, quyền lợi, mức lương 10 triệu.", "provider": "unavailable", "llm_json": {}}, "expect": {"is_ai_extraction": false, "no_crash": true, "blob_excludes": "traceback"}}
```

- [ ] **Step 4: Run the offline eval for jd_extraction**

Run: `cd backend && uv run pytest app/ai/evaluation -k jd_extraction -v`
Expected: PASS — all jd_extraction dataset cases green (happy/adversarial/fallback/low_quality/privacy).
If a runner-level pytest entry point differs, run the project's eval command: `cd backend && uv run python -m app.ai.evaluation.run --task jd_extraction` and confirm no failures.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/evaluation/datasets/jd_extraction/
git commit -m "test(jd): eval dataset for structured fields, not-a-JD, and fallback"
```

---

### Task 10: Full quality-gate pass

**Files:** none new — verification only.

- [ ] **Step 1: Lint**

Run: `cd backend && uv run ruff check app tests`
Expected: no new errors in `app/ai/extraction/jd/`, `app/ai/prompts/jd_extraction/`, `app/modules/opportunities/application/jd_upload_service.py`, `app/modules/opportunities/api/router.py`, `app/core/config.py`.

- [ ] **Step 2: Types**

Run: `cd backend && uv run mypy app --ignore-missing-imports`
Expected: no new type errors in the files above.

- [ ] **Step 3: Full JD test suite**

Run: `cd backend && uv run pytest tests/unit/ai_extraction_jd tests/integration/test_jd_upload_service.py tests/unit/core/test_jd_config.py app/ai/evaluation -k jd -v`
Expected: all PASS.

- [ ] **Step 4: Confirm no persistence + no leakage (manual scan)**

Verify by reading the diff: `extract_jd_from_upload` and the cascade never call a repository/session/`add`/`commit`; no `provider`/`model`/`alias`/token strings appear in any returned dict. The router still returns the bare dict (no schema change that breaks the current frontend upload button).

- [ ] **Step 5: Commit any lint/type fixups**

```bash
git add -A
git commit -m "chore(jd): quality-gate fixups for JD ingestion cascade"
```

---

## Self-Review

**Spec coverage:**
- §4 tiers → Tasks 1 (config), 3 (is-JD gate), 5 (text-LLM), 6 (vision), 7 (cascade orchestration incl. OCR fallback + native/security gates). ✓
- §5 full-field schema (salary modes, experience mode, seniority, industry, deadline, candidate_requirements) → Task 2 + Task 4 prompt. ✓
- §6 API contract (status codes, ai_unavailable raw-text, reject 422, no-DB) → Task 8. ✓
- §7 config knobs → Task 1. ✓
- §8 coordination (no CV edits; JD-local vision copy) → Tasks 6/7 (read-only reuse of `security_gate`, `get_ocr_adapter`, `generate_json_note`; JD-local image prep). Tests for image/not-a-JD/blank/corrupt/OCR-unavailable/AI-disabled → Tasks 3/6/7/8. ✓
- §10 acceptance criteria 1–9 → Tasks 7 (crit 1,2,3), 2/8 (crit 4,5), 8 (crit 6,7,8), 10 (crit 9). ✓
- Eval dataset (ai.md requirement) → Task 9. ✓

**Placeholder scan:** No TBD/TODO; every code step contains full code; every test step has real assertions. ✓

**Type consistency:** `run_jd_cascade(..., structurer=, vision_runner=)` signature is consistent across Tasks 7/8; `JdExtractionOutcome` fields (`status`, `fields`, `field_confidence`, `needs_review`, `raw_text_preview`, `is_ai_extraction`, `vision_used`) used consistently in cascade + service. `validate_and_score` returns `(dict, dict)` used identically in Tasks 2/7. `run_jd_vision_extraction(...)` keyword signature matches its call in the cascade. ✓

**Note for the executing engineer:** Task 8 Step 1's test references `svc.extract_jd_from_upload_with` — implement that function (Task 8 Step 3a) exactly as named. The eval runner (Task 8 Step 3c) mocks `cascade.extract_text` and injects `structurer`/`vision_runner`; do not also try to patch `generate_json_note` on the service (it no longer lives there).
