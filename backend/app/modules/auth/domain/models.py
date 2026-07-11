"""Auth ORM models: sessions, refresh tokens, email verifications, security
events, and TOTP enrolment.

Follows ``docs/DATA_MODEL.md`` §4 (``sessions``, ``email_verifications``) and §33
(``security_events``), with privacy rules from ``docs/SECURITY_PRIVACY.md``:

- Refresh tokens are stored **hashed** only and rotated on every use. Rotation
  history lives in ``refresh_tokens`` (one row per issued token) so token reuse
  after rotation is detectable — a capability the single-column design in
  DATA_MODEL cannot express. The ``sessions`` device/metadata fields are kept.
- ``sessions`` never store a raw user-agent (only a coarse ``device_hint``) nor a
  raw IP (only ``ip_hash``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType
from app.shared.models import ensure_aware as ensure_aware  # re-export, back-compat


class Session(Base):
    """A device/login session. Holds safe device metadata only."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("identities.id"), nullable=False)
    device_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city_level_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def is_active(self, *, now: datetime) -> bool:
        return self.revoked_at is None and ensure_aware(self.expires_at) > now


class RefreshToken(Base):
    """A single issued refresh token (hashed). Rotation forms a linked chain."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id"), nullable=True
    )

    def is_active(self, *, now: datetime) -> bool:
        return (
            self.rotated_at is None
            and self.revoked_at is None
            and ensure_aware(self.expires_at) > now
        )


class EmailVerification(Base):
    """Single-use email-verification / password-reset token (hashed).

    Dual-mode: issues both a magic-link token (``token_hash``) and a 6-digit OTP
    (``otp_code_hash``, SHA-256 hashed). Clients may verify via either path; one
    use invalidates both. ``otp_attempts`` counts wrong OTP guesses; exceeding
    ``OTP_MAX_ATTEMPTS`` marks the record used (forces resend).

    purpose: register | change_email | password_reset | student_email
    """

    __tablename__ = "email_verifications"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    otp_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SecurityEvent(Base):
    """A user-facing security event surfaced on the account security screen."""

    __tablename__ = "security_events"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    device_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city_level_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserTotp(Base):
    """TOTP enrolment for a user.

    ``secret`` holds the Fernet ciphertext of the base32 TOTP secret (encrypted at
    rest — ``docs/SECURITY_PRIVACY.md`` §8). The column is widened to hold the
    ciphertext, which is longer than the raw base32 secret.
    """

    __tablename__ = "user_totp"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class AuthThrottle(Base):
    """Rolling cooldown/rate-limit counter for enumeration-sensitive auth flows
    (``forgot_password``, ``resend_verification``, register-resume).

    Keyed by ``(scope, key_hash)`` where ``key_hash`` is a SHA-256 hash of the
    *normalized email string itself* — never the user id — so the same
    cooldown/rate-limit behaviour applies identically whether or not the email
    maps to a real account (anti-enumeration by construction,
    ``docs/SECURITY_PRIVACY.md``).
    """

    __tablename__ = "auth_throttles"
    __table_args__ = (UniqueConstraint("scope", "key_hash", name="uq_auth_throttles_scope_key"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OidcAccount(Base):
    """A linked third-party OAuth/OIDC identity (Google/Facebook) for a user.

    Only non-sensitive claims are persisted: no raw provider access/id tokens are
    stored (nothing downstream needs them after login completes), keeping this
    table lean and avoiding an extra token-encryption module for data the
    platform never re-uses (``docs/DATA_MODEL.md`` §4 ``oidc_accounts``).
    """

    __tablename__ = "oidc_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oidc_accounts_provider_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    extra_claims: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
