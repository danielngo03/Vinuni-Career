"""Pydantic request/response schemas for the auth API.

Email is validated with a minimal pattern (no extra ``email-validator`` dep) and
normalised in the service layer. Responses never echo password or refresh-token
hashes.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    locale: str = Field(default="vi", pattern="^(vi|en)$")

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("invalid email")
        return value.strip()


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=8, max_length=512)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("invalid email")
        return value.strip()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    password: str = Field(min_length=8, max_length=128)


class ResetPasswordOtpRequest(BaseModel):
    email: str = Field(max_length=320)
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("invalid email")
        return value.strip()


class ActivateAccountRequest(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    password: str = Field(min_length=8, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("invalid email")
        return value.strip()


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Refresh body is optional: browsers send the refresh token via the httpOnly
    ``vinuni_refresh`` cookie. The field remains as a fallback for non-browser
    clients only."""

    refresh_token: str | None = Field(default=None, max_length=512)


class LoginTotpRequest(BaseModel):
    challenge_token: str = Field(min_length=8, max_length=1024)
    code: str = Field(min_length=6, max_length=10)


class SwitchIdentityRequest(BaseModel):
    identity_id: uuid.UUID


class OAuthExchangeRequest(BaseModel):
    ticket: str = Field(min_length=8, max_length=2048)


class OAuthLinkConfirmRequest(BaseModel):
    ticket: str = Field(min_length=8, max_length=2048)
    password: str = Field(min_length=1, max_length=128)


class VerifyEmailOtpRequest(BaseModel):
    email: str = Field(max_length=320)
    otp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    purpose: str = Field(default="register", pattern="^(register|student_email)$")

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("invalid email")
        return value.strip()
