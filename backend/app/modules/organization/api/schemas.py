"""Pydantic request schemas for the organization / partner API.

HTTP validation only; normalization + business rules live in the services.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PermissionInput(BaseModel):
    resource: str = Field(max_length=100)
    action: str = Field(max_length=50)


class OrganizationPatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    website_url: str | None = Field(default=None, max_length=500)
    description: str | None = None
    industry: str | None = Field(default=None, max_length=100)
    company_size: str | None = Field(default=None, max_length=30)
    founded_year: int | None = Field(default=None, ge=1800, le=2100)
    headquarters_city: str | None = Field(default=None, max_length=100)
    # ``logo_path`` is intentionally NOT settable here: a logo is a validated
    # binary asset set only via ``POST /organizations/{org_id}/logo``. Allowing it
    # on the JSON patch would let a client point ``logo_path`` at an arbitrary
    # storage key, bypassing magic-byte/size validation.
    settings: dict | None = None
    version: int | None = None


class CreateUniversityOrgRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=255)


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permissions: list[PermissionInput] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    permissions: list[PermissionInput] | None = None


class DepartmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    parent_id: uuid.UUID | None = None
    clear_parent: bool = False


class MemberUpdateRequest(BaseModel):
    role_ids: list[uuid.UUID] | None = None
    department_ids: list[uuid.UUID] | None = None
    version: int | None = None


class InvitationCreateRequest(BaseModel):
    email: str = Field(max_length=320)
    role_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("invalid email")
        return value.strip()


class PartnerRegistrationRequestBody(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    tax_code: str | None = Field(default=None, max_length=50)
    company_website: str | None = Field(default=None, max_length=500)
    company_size: str | None = Field(default=None, max_length=30)
    industry: str | None = Field(default=None, max_length=100)
    description: str | None = None
    contact_name: str = Field(min_length=1, max_length=255)
    contact_title: str | None = Field(default=None, max_length=150)
    # Accept both `email`/`phone` (API_CONTRACTS sample) and explicit contact_*.
    contact_email: str = Field(max_length=320, alias="email")
    contact_phone: str | None = Field(default=None, max_length=30, alias="phone")
    logo_upload_id: uuid.UUID | None = None

    model_config = {"populate_by_name": True}

    @field_validator("contact_email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("invalid email")
        return value.strip()


class PermissionPreviewRequest(BaseModel):
    """Hypothetical role/department combination (e.g. before an invite)."""

    role_ids: list[uuid.UUID] = Field(default_factory=list)
    department_ids: list[uuid.UUID] = Field(default_factory=list)


class OwnershipTransferRequest(BaseModel):
    target_membership_id: uuid.UUID
    confirm: bool = False


class MemberDeactivateRequest(BaseModel):
    """Reserved for future notes/reason on suspend; body may be empty."""

    reason: str | None = Field(default=None, max_length=500)


class CampusOwnerSetRequest(BaseModel):
    owner_user_id: uuid.UUID | None = None


class RiskFlagCreateRequest(BaseModel):
    flag_type: str = Field(min_length=1, max_length=50)
    severity: str = Field(default="medium", max_length=20)
    note: str | None = Field(default=None, max_length=2000)


class RiskFlagResolveRequest(BaseModel):
    resolution_note: str | None = Field(default=None, max_length=2000)


class NoteCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CompanyProfileUpdateRequest(BaseModel):
    """Partner company-profile edit.

    Cosmetic fields apply immediately; sensitive legal-identity fields
    (``legal_name``, ``tax_code``, ``registration_number``) create/merge a
    pending university approval request. All optional; only ``exclude_unset``
    fields are considered.
    """

    # Sensitive (approval-gated).
    legal_name: str | None = Field(default=None, max_length=255)
    tax_code: str | None = Field(default=None, max_length=50)
    registration_number: str | None = Field(default=None, max_length=100)
    # Cosmetic (immediate). ``display_name`` matches the legacy PATCH surface.
    display_name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    website_url: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=100)
    company_size: str | None = Field(default=None, max_length=30)
    founded_year: int | None = Field(default=None, ge=1800, le=2100)
    headquarters_city: str | None = Field(default=None, max_length=100)
    headquarters_country: str | None = Field(default=None, max_length=100)
    version: int | None = None


class CompanyApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class CompanyRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    version: int | None = None


class PartnerApproveRequest(BaseModel):
    trust_level: str = Field(default="standard")
    package_id: uuid.UUID | None = None
    note: str | None = None
    version: int | None = None


class PartnerRejectRequest(BaseModel):
    reason: str = Field(min_length=1)
    version: int | None = None
