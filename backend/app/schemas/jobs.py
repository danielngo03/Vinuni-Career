from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enum import ApplicationStatus, JobStatus


class JobCreate(BaseModel):
    org_id: str
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=20, max_length=50_000)
    dept_id: str | None = None


JDManagementStatus = Literal["open", "closed"]


class JobManagementCreate(BaseModel):
    org_id: str
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=1, max_length=80_000)
    status: JDManagementStatus = "open"
    dept_id: str | None = None
    parsed_requirements: dict[str, Any] = Field(default_factory=dict)


class JobStatusUpdateRequest(BaseModel):
    status: JDManagementStatus


class JobRawParseRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=80_000)
    job_id: str | None = Field(default=None, max_length=120)
    company_id: str | None = Field(default=None, max_length=120)


class JobFormParseRequest(BaseModel):
    job_id: str | None = Field(default=None, max_length=120)
    company_id: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=1, max_length=255)
    employment_type: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=255)
    salary_range: str | None = Field(default=None, max_length=255)
    benefits: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    raw_notes: str | None = Field(default=None, max_length=50_000)


class JobParsedSkill(BaseModel):
    required_level: float = Field(ge=0, le=10)
    importance: float = Field(ge=0, le=1)
    required: bool = True


class JobParseMetadata(BaseModel):
    source: str
    jd_text_excerpt: str
    parser_mode: str
    llm_used: bool = False
    fallback_used: bool = False
    fallback_reason: str | None = None
    provider_chain: list[str] = Field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    error_status_code: int | None = None
    error_code: str | None = None
    error: str | None = None


class JobParseResponse(BaseModel):
    job_id: str
    company_id: str
    title: str
    status: str
    employment_type: str | None = None
    location: str | None = None
    salary_range: str | None = None
    benefits: list[str] = Field(default_factory=list)
    skills: dict[str, JobParsedSkill]
    raw_text: str
    metadata: JobParseMetadata


class JobModerationRequest(BaseModel):
    approve: bool
    reason: str | None = Field(default=None, max_length=1_000)


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    dept_id: str | None
    title: str
    description: str
    parsed_requirements: dict[str, Any]
    status: JobStatus


class JobManagementView(BaseModel):
    id: str
    org_id: str
    dept_id: str | None
    title: str
    description: str
    parsed_requirements: dict[str, Any]
    status: JDManagementStatus


class JobDeleteResponse(BaseModel):
    status: Literal["deleted"]
    job_id: str


class JobApplicationCreate(BaseModel):
    student_id: str
    cv_id: str
    consent_to_unmask: bool = False


class JobApplicationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    student_id: str
    cv_id: str
    status: ApplicationStatus
    ai_match_score: float | None
    ai_reasoning: dict[str, Any]
    consent_to_unmask: bool
