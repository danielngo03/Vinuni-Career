from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enum import ApplicationStatus, JobStatus


class JobCreate(BaseModel):
    org_id: str
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=20, max_length=50_000)
    dept_id: str | None = None


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
