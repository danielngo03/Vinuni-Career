from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StudentProfileCreate(BaseModel):
    user_id: str
    org_id: str
    student_code: str = Field(min_length=2, max_length=80)
    gpa_overall: float | None = Field(default=None, ge=0, le=4)
    attendance_overall: float | None = Field(default=None, ge=0, le=100)
    privacy_settings: dict[str, Any] = Field(default_factory=dict)


class StudentProfileView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    student_code: str
    gpa_overall: float | None
    attendance_overall: float | None
    privacy_settings: dict[str, Any]
