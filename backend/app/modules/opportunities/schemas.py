from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.enum import (
    EventRegistrationStatus,
    EventStatus,
    EventType,
    ExperienceLevel,
    JobStatus,
    JobType,
    LocationType,
)


class JobCreate(BaseModel):
    org_id: str | None = None
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=20, max_length=50_000)
    requirements: str | None = None
    responsibilities: str | None = None
    benefits_text: str | None = None
    industry: str | None = Field(default=None, max_length=120)
    job_function: str | None = Field(default=None, max_length=120)
    dept_id: str | None = None
    job_type: JobType | None = None
    experience_level: ExperienceLevel | None = None
    location_type: LocationType | None = None
    location_address: str | None = Field(default=None, max_length=500)
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str = "VND"
    skills: list[str] | None = None
    benefits: list[str] | None = None
    contact_email: str | None = Field(default=None, max_length=320)
    contact_name: str | None = Field(default=None, max_length=255)
    application_deadline: datetime | None = None
    is_active: bool = True
    is_featured: bool = False
    max_openings: int | None = Field(default=None, ge=1)
    parsed_requirements: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_logic(self) -> JobCreate:
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_min > self.salary_max:
                raise ValueError("salary_min cannot be greater than salary_max")

        if self.application_deadline is not None:
            now = (
                datetime.now(self.application_deadline.tzinfo)
                if self.application_deadline.tzinfo
                else datetime.now()
            )
            if self.application_deadline < now:
                raise ValueError("application_deadline cannot be in the past")

        return self


class JobUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = Field(default=None, min_length=20, max_length=50_000)
    requirements: str | None = None
    responsibilities: str | None = None
    benefits_text: str | None = None
    location_address: str | None = Field(default=None, max_length=500)
    skills: list[str] | None = None
    benefits: list[str] | None = None
    application_deadline: datetime | None = None
    is_active: bool | None = None
    max_openings: int | None = Field(default=None, ge=1)
    parsed_requirements: dict[str, Any] | None = None


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
    requirements: str | None
    responsibilities: str | None
    benefits_text: str | None
    industry: str | None
    job_function: str | None
    job_type: JobType | None
    experience_level: ExperienceLevel | None
    location_type: LocationType | None
    location_address: str | None
    salary_min: int | None
    salary_max: int | None
    currency: str
    skills: list[str] | None
    benefits: list[str] | None
    contact_email: str | None
    contact_name: str | None
    application_deadline: datetime | None
    is_active: bool
    is_featured: bool
    max_openings: int | None
    parsed_requirements: dict[str, Any]
    status: JobStatus


class JobPage(BaseModel):
    items: list[JobView]
    total: int
    limit: int
    offset: int


class JobScheduleCreate(BaseModel):
    action: str = Field(pattern="^(PUBLISH|OPEN|CLOSE)$")
    run_at: datetime


class JobActionRequest(BaseModel):
    action: str = Field(pattern="^(PUBLISH|OPEN|CLOSE)$")


class JobScheduleView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    action: str
    run_at: datetime
    status: str
    requested_by: str | None
    executed_at: datetime | None
    error_message: str | None


class EventCreate(BaseModel):
    org_id: str
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10)
    event_type: EventType
    start_time: datetime
    end_time: datetime
    location_type: str | None = Field(default=None, max_length=80)
    location_address: str | None = None
    meeting_url: str | None = None
    max_attendees: int | None = None


class EventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    title: str
    description: str
    event_type: EventType
    start_time: datetime
    end_time: datetime
    location_type: str | None
    location_address: str | None
    meeting_url: str | None
    max_attendees: int | None
    status: EventStatus
    approved_by: str | None


class EventRegistrationCreate(BaseModel):
    student_id: str
    event_id: str


class EventRegistrationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    student_id: str
    status: EventRegistrationStatus
    registered_at: datetime


class BookmarkCreate(BaseModel):
    job_id: str


class BookmarkView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    job_id: str
