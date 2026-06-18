from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if "@" not in email or "." not in email.rsplit("@", maxsplit=1)[-1]:
            raise ValueError("Invalid email address")
        return email


class LoginRequest(BaseModel):
    email: str
    password: str
    device_info: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    is_active: bool


class IdentityView(BaseModel):
    id: str
    org_id: str
    org_name: str
    org_type: str
    role_id: str
    role_name: str
    dept_id: str | None = None
    dept_name: str | None = None
    portal: str
    redirect_path: str


class SessionView(BaseModel):
    user: UserView
    identities: list[IdentityView]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserView | None = None
    identities: list[IdentityView] = Field(default_factory=list)
    access_scope: str = "workspace"
    pending_registration_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)
    device_info: str | None = Field(default=None, max_length=255)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)


class IdentitySelectionRequest(BaseModel):
    identity_id: str


class OIDCExchangeRequest(BaseModel):
    ticket: str = Field(min_length=32, max_length=4096)
    device_info: str | None = Field(default=None, max_length=255)


class OIDCProviderStatus(BaseModel):
    google: bool
    microsoft: bool
