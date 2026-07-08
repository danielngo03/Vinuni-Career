"""Pydantic request schemas for the jobs API.

HTTP validation only; normalization, vocabulary checks against
``domain.lifecycle``, and business rules live in the services.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class JobLocationItem(BaseModel):
    """One worksite entry for a job posting.

    For Vietnamese locations use ``province_code`` (links to ``provinces.code``).
    For non-Vietnam locations or free-text fallback use ``city``.
    ``type`` is one of: onsite | remote | hybrid.
    """

    type: str = Field(max_length=20)
    province_code: str | None = Field(default=None, max_length=10)
    ward_code: str | None = Field(default=None, max_length=20)
    ward_name: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=100)
    country: str = Field(default="Vietnam", max_length=100)


class RequirementGroup(BaseModel):
    """Flexible requirement block for fields with many real-world cases.

    ``not_required`` keeps the rule explicit instead of forcing clients to infer
    meaning from an empty list.
    """

    mode: Literal["not_required", "required", "preferred"] = "not_required"
    values: list[str] = Field(default_factory=list, max_length=50)
    note: str | None = Field(default=None, max_length=1000)


class AgeRequirement(BaseModel):
    mode: Literal["not_required", "at_least", "up_to", "range"] = "not_required"
    min: int | None = Field(default=None, ge=14, le=80)
    max: int | None = Field(default=None, ge=14, le=80)

    @model_validator(mode="after")
    def validate_bounds(self) -> AgeRequirement:
        if self.mode == "not_required":
            return self
        if self.mode == "at_least" and self.min is None:
            raise ValueError("min is required for at_least age requirement")
        if self.mode == "up_to" and self.max is None:
            raise ValueError("max is required for up_to age requirement")
        if self.mode == "range":
            if self.min is None or self.max is None:
                raise ValueError("min and max are required for age range")
            if self.min > self.max:
                raise ValueError("min must be less than or equal to max")
        return self


class LanguageRequirement(BaseModel):
    language: str = Field(min_length=1, max_length=60)
    proficiency: str | None = Field(default=None, max_length=80)
    required: bool = True


class CertificationRequirement(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    required: bool = True


class CandidateRequirements(BaseModel):
    education: RequirementGroup | None = None
    nationalities: RequirementGroup | None = None
    gender: RequirementGroup | None = None
    age: AgeRequirement | None = None
    marital_status: RequirementGroup | None = None
    languages: list[LanguageRequirement] = Field(default_factory=list, max_length=20)
    certifications: list[CertificationRequirement] = Field(default_factory=list, max_length=30)
    note: str | None = Field(default=None, max_length=2000)


# Canonical enum vocabularies for structured salary/experience modes
# (B-544/B-545). Mirrors `docs/DATA_MODEL.md` §8 `jobs` table comments.
SALARY_MODES = ("negotiable", "hidden", "fixed", "range", "from", "to")
SALARY_PERIODS = ("monthly", "yearly")
SALARY_GROSS_NET = ("unspecified", "gross", "net")
EXPERIENCE_MODES = ("no_requirement", "fresher", "range", "min", "max")


def validate_salary_mode(
    *,
    salary_mode: str | None,
    salary_min: int | None,
    salary_max: int | None,
    salary_is_disclosed: bool | None,
) -> tuple[str | None, bool | None]:
    """Validate mode/min/max/disclosed consistency for a **complete** value set.

    ``salary_mode`` is authoritative: when present, ``salary_is_disclosed`` is
    derived from it server-side rather than trusted independently from the
    client (this mirrors how ``status``/``moderation_status`` are always
    service-derived rather than client-set in this module). Returns the
    (possibly overridden) ``salary_is_disclosed`` to persist alongside the mode.
    Raises ``ValueError`` (-> 422) on an inconsistent mode/min/max combination.

    Callers must pass the **effective post-merge** values (not just the fields
    present on a partial PATCH body) — see ``job_service._validate_fields`` for
    the update path, which merges the payload onto the existing job row before
    calling this.
    """

    if salary_mode is None:
        return salary_mode, salary_is_disclosed
    if salary_mode not in SALARY_MODES:
        raise ValueError(f"salary_mode must be one of {SALARY_MODES}")

    if salary_mode == "negotiable":
        if salary_min is not None or salary_max is not None:
            raise ValueError(
                "negotiable salary_mode requires salary_min and salary_max to be empty"
            )
        return salary_mode, False
    if salary_mode == "hidden":
        # Real numbers are optional (partner budget/reporting use) but never
        # publicly disclosed.
        return salary_mode, False
    if salary_mode == "fixed":
        if salary_min is None or salary_max is None or salary_min != salary_max:
            raise ValueError("fixed salary_mode requires salary_min == salary_max, both set")
        return salary_mode, True
    if salary_mode == "range":
        if salary_min is None or salary_max is None or salary_min >= salary_max:
            raise ValueError("range salary_mode requires salary_min < salary_max, both set")
        return salary_mode, True
    if salary_mode == "from":
        if salary_min is None or salary_max is not None:
            raise ValueError("from salary_mode requires salary_min set and salary_max empty")
        return salary_mode, True
    # "to"
    if salary_max is None or salary_min is not None:
        raise ValueError("to salary_mode requires salary_max set and salary_min empty")
    return salary_mode, True


def validate_experience_mode(
    *,
    experience_mode: str | None,
    experience_min_years: int | None,
    experience_max_years: int | None,
) -> str | None:
    if experience_mode is None:
        return experience_mode
    if experience_mode not in EXPERIENCE_MODES:
        raise ValueError(f"experience_mode must be one of {EXPERIENCE_MODES}")

    if experience_mode == "no_requirement":
        if experience_min_years is not None or experience_max_years is not None:
            raise ValueError("no_requirement experience_mode requires both years empty")
    elif experience_mode == "fresher":
        if experience_min_years != 0 or experience_max_years != 0:
            raise ValueError("fresher experience_mode requires both years set to 0")
    elif experience_mode == "range":
        if (
            experience_min_years is None
            or experience_max_years is None
            or experience_min_years >= experience_max_years
        ):
            raise ValueError("range experience_mode requires min < max, both set")
    elif experience_mode == "min":
        if experience_min_years is None or experience_max_years is not None:
            raise ValueError("min experience_mode requires experience_min_years set and max empty")
    else:  # "max"
        if experience_max_years is None or experience_min_years is not None:
            raise ValueError("max experience_mode requires experience_max_years set and min empty")
    return experience_mode


class JobCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10)
    requirements: str | None = None
    benefits: str | None = None
    employment_type: str = Field(max_length=30)
    # Legacy single-location fields kept for backward compat; when `locations` is
    # provided it takes precedence and the first item populates these fields.
    location_type: str = Field(max_length=20)
    location_city: str | None = Field(default=None, max_length=100)
    location_country: str = Field(default="Vietnam", max_length=100)
    # Multi-location: if provided, overrides single-location fields (first item = primary).
    locations: list[JobLocationItem] | None = Field(default=None, max_length=20)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_min_years: int | None = Field(default=None, ge=0, le=60)
    experience_max_years: int | None = Field(default=None, ge=0, le=60)
    experience_mode: str | None = Field(default=None, max_length=20)
    industry_id: uuid.UUID | None = None
    degree_required: str | None = Field(default=None, max_length=30)
    seniority_level: str | None = Field(default=None, max_length=30)
    candidate_requirements: CandidateRequirements | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str = Field(default="VND", max_length=5)
    salary_is_disclosed: bool = False
    salary_mode: str | None = Field(default=None, max_length=20)
    salary_period: str = Field(default="monthly", max_length=10)
    salary_gross_net: str = Field(default="unspecified", max_length=15)
    headcount: int = Field(default=1, ge=1, le=10000)
    application_deadline: datetime | None = None
    visibility: str = Field(default="public", max_length=20)
    cv_language_required: Literal["any", "en", "vi"] = "any"
    # ORIGINAL language of the JD as authored. A HINT only — the server resolves
    # the stored value (AI-extraction ``detected_language`` / manual choice, else
    # a heuristic over the text). Drives the student-side "translate this JD"
    # affordance. Omit to let the backend detect it.
    language_code: Literal["vi", "en", "ja", "ko", "zh"] | None = None

    @model_validator(mode="after")
    def _validate_structured_modes(self) -> JobCreateRequest:
        # Create always submits a complete value set, so full mode/min/max
        # consistency can be enforced here (unlike PATCH, see JobUpdateRequest).
        if self.salary_period not in SALARY_PERIODS:
            raise ValueError(f"salary_period must be one of {SALARY_PERIODS}")
        if self.salary_gross_net not in SALARY_GROSS_NET:
            raise ValueError(f"salary_gross_net must be one of {SALARY_GROSS_NET}")
        _mode, disclosed = validate_salary_mode(
            salary_mode=self.salary_mode,
            salary_min=self.salary_min,
            salary_max=self.salary_max,
            salary_is_disclosed=self.salary_is_disclosed,
        )
        if self.salary_mode is not None:
            self.salary_is_disclosed = bool(disclosed)
        validate_experience_mode(
            experience_mode=self.experience_mode,
            experience_min_years=self.experience_min_years,
            experience_max_years=self.experience_max_years,
        )
        return self


class JobUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=10)
    requirements: str | None = None
    benefits: str | None = None
    employment_type: str | None = Field(default=None, max_length=30)
    location_type: str | None = Field(default=None, max_length=20)
    location_city: str | None = Field(default=None, max_length=100)
    location_country: str | None = Field(default=None, max_length=100)
    locations: list[JobLocationItem] | None = None
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    experience_min_years: int | None = Field(default=None, ge=0, le=60)
    experience_max_years: int | None = Field(default=None, ge=0, le=60)
    experience_mode: str | None = Field(default=None, max_length=20)
    industry_id: uuid.UUID | None = None
    degree_required: str | None = Field(default=None, max_length=30)
    seniority_level: str | None = Field(default=None, max_length=30)
    candidate_requirements: CandidateRequirements | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=5)
    salary_is_disclosed: bool | None = None
    salary_mode: str | None = Field(default=None, max_length=20)
    salary_period: str | None = Field(default=None, max_length=10)
    salary_gross_net: str | None = Field(default=None, max_length=15)
    headcount: int | None = Field(default=None, ge=1, le=10000)
    application_deadline: datetime | None = None
    visibility: str | None = Field(default=None, max_length=20)
    cv_language_required: Literal["any", "en", "vi"] | None = None
    # Hint to re-detect the JD's original language (server resolves; see
    # JobCreateRequest.language_code). Also re-resolved when description changes.
    language_code: Literal["vi", "en", "ja", "ko", "zh"] | None = None
    version: int | None = None

    @model_validator(mode="after")
    def _validate_structured_modes(self) -> JobUpdateRequest:
        # PATCH is partial: a client may send only `salary_mode` (or only
        # `salary_min`) while relying on the job's existing stored values for
        # the rest. Full mode/min/max consistency can only be checked once the
        # payload is merged onto the existing row, so that authoritative check
        # lives in `job_service._validate_fields` (post-merge). Here we only
        # reject values outside the known vocabulary (cheap, always safe).
        if self.salary_mode is not None and self.salary_mode not in SALARY_MODES:
            raise ValueError(f"salary_mode must be one of {SALARY_MODES}")
        if self.salary_period is not None and self.salary_period not in SALARY_PERIODS:
            raise ValueError(f"salary_period must be one of {SALARY_PERIODS}")
        if (
            self.salary_gross_net is not None
            and self.salary_gross_net not in SALARY_GROSS_NET
        ):
            raise ValueError(f"salary_gross_net must be one of {SALARY_GROSS_NET}")
        if self.experience_mode is not None and self.experience_mode not in EXPERIENCE_MODES:
            raise ValueError(f"experience_mode must be one of {EXPERIENCE_MODES}")
        return self


class JobApproveRequest(BaseModel):
    """Approve has no required fields — an empty/absent body is valid (no 422)."""

    note: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class JobModerationRejectRequest(BaseModel):
    reason: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, max_length=30)
    version: int | None = None


class JobCloseRequest(BaseModel):
    version: int | None = None


class JobEscalateRequest(BaseModel):
    """University moderator escalates a job to the shared human review queue."""

    reason_code: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=2000)


class JobBulkApproveRequest(BaseModel):
    job_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class JobBulkRejectItem(BaseModel):
    id: uuid.UUID
    reason: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, max_length=30)


class JobBulkRejectRequest(BaseModel):
    items: list[JobBulkRejectItem] = Field(min_length=1, max_length=100)


class BatchFitScoresRequest(BaseModel):
    """Batch CV-job fit score request.

    The frontend sends the list of job IDs visible on the current page (up to 50).
    The backend returns a score entry for each job the authenticated student has
    an active CV that can be scored against.
    """

    job_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=50,
        description="Job IDs to score (max 50 per request; one page worth).",
    )
