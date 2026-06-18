from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.shared.enum import (
    DegreeLevel,
    RegistrationDecision,
    RegistrationStatus,
    RegistrationType,
    VerificationOutcome,
    VerificationPolicyMode,
)


class StudentRegistrationCreate(BaseModel):
    university_org_id: str
    full_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    student_code: str = Field(min_length=4, max_length=80)
    major_id: str
    degree_level: DegreeLevel
    enrollment_year: int = Field(ge=2000, le=2100)
    expected_graduation_year: int = Field(ge=2000, le=2100)
    phone_number: str = Field(min_length=8, max_length=30)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_years(self):
        if self.expected_graduation_year < self.enrollment_year:
            raise ValueError("Expected graduation year must not precede enrollment year")
        return self


class RegistrationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    registration_type: RegistrationType
    status: RegistrationStatus
    university_org_id: str
    submitted_at: datetime
    reviewed_at: datetime | None
    review_note: str | None
    version: int
    checklist: list[dict] = Field(default_factory=list)
    assessment: dict = Field(default_factory=dict)
    policy_snapshot: dict = Field(default_factory=dict)


class RegistrationReviewRequest(BaseModel):
    decision: RegistrationDecision
    note: str | None = Field(default=None, max_length=4000)
    checklist: list[RegistrationChecklistItem] = Field(default_factory=list, max_length=30)


class RegistrationQueueItem(RegistrationView):
    applicant_name: str
    applicant_email: str
    summary: dict
    evidence: list[RegistrationEvidenceView] = Field(default_factory=list)


class RegistrationChecklistItem(BaseModel):
    code: str = Field(min_length=2, max_length=120)
    label: str = Field(min_length=2, max_length=300)
    field: str | None = Field(default=None, max_length=120)
    document: str | None = Field(default=None, max_length=120)
    resolved: bool = False


class RegistrationEvidenceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    provider: str
    field_name: str
    authority: str
    trust_weight: int
    confidence: int
    extracted_value: dict
    provenance: dict
    mismatch: bool
    expires_at: datetime | None


class PendingRegistrationView(RegistrationView):
    registration_type: RegistrationType
    applicant_name: str
    applicant_email: str
    summary: dict
    evidence: list[RegistrationEvidenceView] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class RegistrationResubmitRequest(BaseModel):
    checklist_codes: list[str] = Field(default_factory=list, max_length=30)
    note: str | None = Field(default=None, max_length=2000)


class VerificationPolicyView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    university_org_id: str
    registration_type: RegistrationType
    mode: VerificationPolicyMode
    global_kill_switch: bool
    confidence_threshold: int
    required_providers: list[str]
    required_documents: list[str]
    sample_rate: int
    model_version: str


class VerificationPolicyUpdate(BaseModel):
    mode: VerificationPolicyMode
    global_kill_switch: bool = False
    confidence_threshold: int = Field(default=90, ge=50, le=100)
    required_providers: list[str] = Field(default_factory=list, max_length=20)
    required_documents: list[str] = Field(default_factory=list, max_length=20)
    sample_rate: int = Field(default=100, ge=0, le=100)
    model_version: str = Field(default="deterministic-v1", min_length=2, max_length=120)


class VerificationAssessment(BaseModel):
    outcome: VerificationOutcome
    confidence: int = Field(ge=0, le=100)
    low_risk: bool
    reasons: list[str]
    missing_items: list[RegistrationChecklistItem] = Field(default_factory=list)
