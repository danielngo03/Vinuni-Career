"""Pydantic request/response schemas for the onboarding API."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SetRoleRequest(BaseModel):
    role: str = Field(pattern="^(job_seeker|employer)$")


class SetSeekerTypeRequest(BaseModel):
    seeker_type: str = Field(pattern="^(student|professional|fresh_graduate)$")


class SeekerProfileRequest(BaseModel):
    # Professional sub-type fields
    title: str | None = Field(default=None, max_length=150)
    company: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    years_experience: int | None = Field(default=None, ge=0, le=60)
    # Fresh graduate sub-type field. Career facts (major / graduation year) were
    # removed with the identity-only profile cleanup (owner decision 2026-07-06):
    # they belong in the student's CV, not onboarding/profile. Onboarding sets only
    # identity/basics that still exist.
    university: str | None = Field(default=None, max_length=255)


class StudentVerifyRequestBody(BaseModel):
    university_name: str = Field(min_length=2, max_length=255)
    student_id_number: str = Field(min_length=2, max_length=50)
    student_email: str = Field(max_length=320)
    # Which student persona is being asserted. Defaults to ``vinuni_student`` for
    # backward-compat when the client omits it. The institution-domain rule for
    # vinuni_student / vinuni_alumni is enforced in the service, not just here.
    student_kind: Literal["vinuni_student", "vinuni_alumni", "external"] = (
        "vinuni_student"
    )

    @field_validator("student_email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("invalid email")
        return v.strip()


class StudentVerifyConfirmBody(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class EmployerInfoRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    company_size: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
    registrant_role: str | None = Field(default=None, max_length=150)


class OnboardingStatusResponse(BaseModel):
    current_step: str
    role: str | None
    seeker_type: str | None
    is_complete: bool
    email_verified: bool
    student_verification_status: str | None
    employer_doc_status: str | None
    employer_request_status: str | None


class EmployerDocStatusResponse(BaseModel):
    ai_doc_status: str
    request_status: str
    tax_id_verified: bool
