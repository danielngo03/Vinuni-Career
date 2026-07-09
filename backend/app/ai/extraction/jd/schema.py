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
    cv_language_required: Literal["any", "en", "vi"] | None = None


EXPECTED_KEYS: frozenset[str] = frozenset(JDExtractionSchema.model_fields.keys())

# Free-text fields the prompt is told to copy/translate -> verifiable by verbatim match.
_QUOTABLE_TEXT = frozenset(
    {
        "title",
        "title_en",
        "description_vi",
        "description_en",
        "requirements_vi",
        "requirements_en",
        "benefits_vi",
        "benefits_en",
    }
)
_QUOTABLE_LIST = frozenset({"required_skills", "preferred_skills"})
# Never need a per-field review flag.
_NO_REVIEW = frozenset({"salary_is_disclosed", "detected_language", "cv_language_required"})
# Everything else that is present but not a verbatim quote is a normalized value.


def default_candidate_requirements() -> dict:
    return _CandidateRequirements().model_dump()


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_quotable(value: str, raw_norm: str) -> bool:
    norm = _normalize_for_match(value)[:80]
    return bool(norm) and norm in raw_norm


def validate_and_score(
    structured: dict[str, Any], raw_text: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate ``structured`` against :class:`JDExtractionSchema` and derive a
    per-field ``needs_review`` signal. Absent requirement groups default to
    ``not_required``."""

    payload = {k: v for k, v in structured.items() if k in EXPECTED_KEYS}
    try:
        model = JDExtractionSchema.model_validate(payload)
    except ValidationError as exc:
        bad = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
        model = JDExtractionSchema.model_validate(
            {k: v for k, v in payload.items() if k not in bad}
        )

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
    for key in ("education", "nationalities", "gender", "marital_status"):
        if (cr.get(key) or {}).get("mode", "not_required") != "not_required":
            return True
    if (cr.get("age") or {}).get("mode", "not_required") != "not_required":
        return True
    if cr.get("languages") or cr.get("certifications") or cr.get("note"):
        return True
    return False
