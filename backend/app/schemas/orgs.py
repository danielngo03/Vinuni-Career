from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enum import OrgType


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
