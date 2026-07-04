"""Pydantic request schemas for the student-profile API.

HTTP validation only; vocabulary, ownership, RBAC, optimistic-locking, and
business rules live in the services. All update bodies are sparse (only provided
fields are touched), so fields default to ``None``/unset.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UpdateProfileRequest(BaseModel):
    headline: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)
    phone: str | None = Field(default=None, max_length=30)
    location_city: str | None = Field(default=None, max_length=100)
    location_country: str | None = Field(default=None, max_length=100)
    major: str | None = Field(default=None, max_length=200)
    degree_level: str | None = Field(default=None, max_length=30)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    profile_visibility: str | None = Field(default=None, max_length=20)
    show_email: str | None = Field(default=None, max_length=20)
    show_phone: str | None = Field(default=None, max_length=20)
    is_open_to_work: bool | None = None
    open_to_work_types: list[str] | None = None
    expected_version: int | None = None

    model_config = {"extra": "forbid"}


class EducationRequest(BaseModel):
    institution: str | None = Field(default=None, max_length=255)
    degree: str | None = Field(default=None, max_length=100)
    field_of_study: str | None = Field(default=None, max_length=200)
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool | None = None
    gpa: float | None = Field(default=None, ge=0, le=4)
    description: str | None = Field(default=None, max_length=5000)
    sort_order: int | None = None
    expected_version: int | None = None

    model_config = {"extra": "forbid"}


class ExperienceRequest(BaseModel):
    company_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    employment_type: str | None = Field(default=None, max_length=30)
    location: str | None = Field(default=None, max_length=200)
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool | None = None
    description: str | None = Field(default=None, max_length=5000)
    skills_used: list[str] | None = None
    sort_order: int | None = None
    expected_version: int | None = None

    model_config = {"extra": "forbid"}


class SkillRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=50)
    proficiency: int | None = Field(default=None, ge=1, le=5)
    sort_order: int | None = None
    expected_version: int | None = None

    model_config = {"extra": "forbid"}


class LinkRequest(BaseModel):
    label: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None
    expected_version: int | None = None

    model_config = {"extra": "forbid"}
