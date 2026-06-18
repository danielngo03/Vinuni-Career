from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enum import DegreeLevel, StudentStatus


class StudentProfileCreate(BaseModel):
    user_id: str
    org_id: str
    student_code: str = Field(min_length=2, max_length=80)
    major_id: str | None = None
    enrollment_year: int | None = None
    graduation_year: int | None = None
    date_of_birth: datetime | None = None
    phone_number: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    bio: str | None = None
    current_status: StudentStatus | None = None
    degree_level: DegreeLevel | None = None
    gpa_overall: float | None = Field(default=None, ge=0, le=4)
    attendance_overall: float | None = Field(default=None, ge=0, le=100)
    social_links: dict[str, Any] = Field(default_factory=dict)
    skills: list[str] | None = None
    privacy_settings: dict[str, Any] = Field(default_factory=dict)


class StudentProfileView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    student_code: str
    major_id: str | None
    enrollment_year: int | None
    graduation_year: int | None
    date_of_birth: datetime | None
    phone_number: str | None
    address: str | None
    bio: str | None
    current_status: StudentStatus | None
    degree_level: DegreeLevel | None
    gpa_overall: float | None
    attendance_overall: float | None
    social_links: dict[str, Any]
    skills: list[str] | None
    privacy_settings: dict[str, Any]
    profile_completeness: int

class UniversityMajorCreate(BaseModel):
    major_code: str
    major_name: str
    description: str | None = None

class UniversityMajorView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    major_code: str
    major_name: str
    description: str | None
    is_active: bool
