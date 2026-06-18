from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enum import OrgType


class IndustryCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_]+$")
    name_vi: str = Field(min_length=2, max_length=255)
    name_en: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: str | None = None


class IndustryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    university_org_id: str
    parent_id: str | None
    code: str
    name_vi: str
    name_en: str
    description: str | None
    is_active: bool


class UniversityReference(BaseModel):
    id: str
    name: str


class MajorReference(BaseModel):
    id: str
    university_org_id: str
    code: str
    name: str


class RegistrationReferenceData(BaseModel):
    universities: list[UniversityReference]
    majors: list[MajorReference]
    industries: list[IndustryView]


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    type: OrgType
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrganizationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: OrgType
    is_verified_partner: bool
    metadata_json: dict[str, Any]


class PartnerVerificationRequest(BaseModel):
    is_verified: bool


class DepartmentCreate(BaseModel):
    org_id: str
    name: str = Field(min_length=2, max_length=255)
    parent_id: str | None = None


class DepartmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    parent_id: str | None
    name: str
