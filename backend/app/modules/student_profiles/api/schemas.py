"""Pydantic request schemas for the identity-only student-profile API.

HTTP validation only; vocabulary, ownership, RBAC, optimistic-locking, and
business rules live in the service. The update body is sparse (only provided
fields are touched), so fields default to ``None``/unset.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UpdateProfileRequest(BaseModel):
    phone: str | None = Field(default=None, max_length=30)
    location_city: str | None = Field(default=None, max_length=100)
    location_country: str | None = Field(default=None, max_length=100)
    profile_visibility: str | None = Field(default=None, max_length=20)
    show_email: str | None = Field(default=None, max_length=20)
    show_phone: str | None = Field(default=None, max_length=20)
    is_open_to_work: bool | None = None
    expected_version: int | None = None

    model_config = {"extra": "forbid"}
