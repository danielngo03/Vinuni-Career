from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enum import ApplicationStatus, InterviewStatus, InterviewType


class JobApplicationCreate(BaseModel):
    student_id: str | None = None
    cv_id: str
    cover_letter: str | None = None
    consent_to_unmask: bool = False


class JobApplicationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    student_id: str
    cv_id: str
    cover_letter: str | None
    status: ApplicationStatus
    ai_match_score: float | None
    ai_reasoning: dict[str, Any]
    consent_to_unmask: bool


class ConsentUpdate(BaseModel):
    consent_to_unmask: bool


class CVMaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=80_000)


class CVMaskResponse(BaseModel):
    masked_text: str
    entities: list[dict[str, str]]


class CVInspectResponse(BaseModel):
    route: str
    detected_kind: str
    declared_content_type: str | None
    byte_size: int
    reasons: list[str]
    needs_vision: bool
    extracted_text_preview: str
    metadata: dict[str, int | str | bool]


class CVCreate(BaseModel):
    student_id: str
    title: str = Field(default="My Resume", max_length=255)
    summary: str | None = None
    experience_years: float | None = Field(default=None, ge=0)
    skills: list[str] | None = None
    education_history: list[dict[str, Any]] | None = None
    work_experience: list[dict[str, Any]] | None = None
    certificates: list[dict[str, Any]] | None = None
    projects: list[dict[str, Any]] | None = None
    awards: list[dict[str, Any]] | None = None
    parsed_data: dict[str, Any] = Field(default_factory=dict)
    raw_text: str | None = Field(default=None, max_length=80_000)
    is_primary: bool = True


class CVUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class CVView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    file_id: str | None
    title: str
    summary: str | None
    experience_years: float | None
    skills: list[str] | None
    education_history: list[dict[str, Any]] | None
    work_experience: list[dict[str, Any]] | None
    certificates: list[dict[str, Any]] | None
    projects: list[dict[str, Any]] | None
    awards: list[dict[str, Any]] | None
    parsed_data: dict[str, Any]
    masked_data: dict[str, Any]
    is_primary: bool
    created_at: datetime


class InterviewCreate(BaseModel):
    application_id: str
    interview_type: InterviewType = InterviewType.HR_ROUND
    start_time: datetime
    end_time: datetime
    meeting_url: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=1000)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_times(self) -> InterviewCreate:
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        now = datetime.now(self.start_time.tzinfo) if self.start_time.tzinfo else datetime.now()
        if self.start_time < now:
            raise ValueError("start_time cannot be in the past")
        return self


class InterviewUpdate(BaseModel):
    status: InterviewStatus | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    meeting_url: str | None = None
    location: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_times(self) -> InterviewUpdate:
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class InterviewView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    interview_type: InterviewType
    status: InterviewStatus
    start_time: datetime
    end_time: datetime
    meeting_url: str | None
    location: str | None
    notes: str | None
