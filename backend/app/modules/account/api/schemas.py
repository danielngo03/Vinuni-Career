"""Account API request schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PreferencesPatch(BaseModel):
    locale: str | None = Field(default=None, pattern="^(vi|en)$")
    timezone: str | None = Field(default=None, max_length=100)
    theme: str | None = Field(default=None, pattern="^(system|light|dark)$")
    quiet_hours: dict[str, Any] | None = None
    categories: dict[str, dict[str, Any]] | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)
