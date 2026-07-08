"""Access-token (JWT) signing and verification.

Short-lived HS256 access tokens (``ACCESS_TOKEN_TTL_MINUTES``) signed with
``JWT_SECRET_KEY``. Claims carry the acting session and identity so the principal
resolver can rebuild RBAC context and check revocation. No PII beyond ids.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

_ALGORITHM = "HS256"
_ISSUER = "vinuni-career-platform"
_TOTP_CHALLENGE_PURPOSE = "totp_challenge"
_OAUTH_STATE_PURPOSE = "oauth_state"
_OAUTH_TICKET_PURPOSE = "oauth_ticket"
_OAUTH_LINK_PURPOSE = "oauth_link"


@dataclass(slots=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    identity_id: uuid.UUID
    persona: str
    org_id: uuid.UUID | None
    jti: uuid.UUID
    expires_at: datetime


class InvalidTokenError(Exception):
    """Raised when an access token fails signature/format/expiry checks."""


def issue_access_token(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    identity_id: uuid.UUID,
    persona: str,
    org_id: uuid.UUID | None,
) -> tuple[str, uuid.UUID, datetime]:
    """Return ``(token, jti, expires_at)`` for a freshly signed access token."""

    settings = get_settings()
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)
    jti = uuid.uuid4()
    payload = {
        "iss": _ISSUER,
        "sub": str(user_id),
        "sid": str(session_id),
        "iid": str(identity_id),
        "persona": persona,
        "org_id": str(org_id) if org_id else None,
        "jti": str(jti),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)
    return token, jti, expires_at


def issue_totp_challenge_token(*, user_id: uuid.UUID) -> str:
    """Mint a short-lived signed token bridging password verification and the
    TOTP step.

    It is NOT an access token: it carries only ``sub`` (pending user), a random
    nonce, and a distinct ``purpose`` claim, and grants no access on its own. It
    is consumed exactly once by ``/auth/login/totp``.
    """

    settings = get_settings()
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(minutes=settings.totp_challenge_ttl_minutes)
    payload = {
        "iss": _ISSUER,
        "sub": str(user_id),
        "purpose": _TOTP_CHALLENGE_PURPOSE,
        "nonce": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_totp_challenge_token(token: str) -> uuid.UUID:
    """Return the pending user id from a TOTP challenge token, or raise
    :class:`InvalidTokenError` (expired / wrong purpose / bad signature)."""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "sub", "purpose"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("purpose") != _TOTP_CHALLENGE_PURPOSE:
        raise InvalidTokenError("wrong purpose")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("malformed challenge") from exc


@dataclass(slots=True)
class OAuthStateClaims:
    provider: str
    mode: str
    return_to: str | None
    nonce: str


def issue_oauth_state_token(
    *, provider: str, mode: str, return_to: str | None, nonce: str
) -> str:
    """Short-lived signed state token bridging ``/oauth/{provider}/start`` and
    ``/oauth/{provider}/callback`` (CSRF defense). The same ``nonce`` is also set
    as an httpOnly cookie (double-submit) by the router."""

    settings = get_settings()
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(minutes=settings.oauth_state_ttl_minutes)
    payload = {
        "iss": _ISSUER,
        "purpose": _OAUTH_STATE_PURPOSE,
        "provider": provider,
        "mode": mode,
        "return_to": return_to,
        "nonce": nonce,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_oauth_state_token(token: str) -> OAuthStateClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "purpose", "provider", "nonce"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("purpose") != _OAUTH_STATE_PURPOSE:
        raise InvalidTokenError("wrong purpose")
    return OAuthStateClaims(
        provider=payload["provider"],
        mode=payload.get("mode", "login"),
        return_to=payload.get("return_to"),
        nonce=payload["nonce"],
    )


def issue_oauth_ticket_token(*, user_id: uuid.UUID) -> str:
    """One-time, very-short-TTL ticket encoding only ``user_id``. Minted after a
    successful OAuth callback; redeemed exactly once by ``/auth/oauth/exchange``,
    which is where the real session/tokens are actually minted (no session is
    created at callback time)."""

    settings = get_settings()
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(minutes=settings.oauth_ticket_ttl_minutes)
    payload = {
        "iss": _ISSUER,
        "sub": str(user_id),
        "purpose": _OAUTH_TICKET_PURPOSE,
        "nonce": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_oauth_ticket_token(token: str) -> uuid.UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "sub", "purpose"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("purpose") != _OAUTH_TICKET_PURPOSE:
        raise InvalidTokenError("wrong purpose")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("malformed ticket") from exc


@dataclass(slots=True)
class OAuthLinkClaims:
    user_id: uuid.UUID
    provider: str
    provider_user_id: str
    email: str | None
    name: str | None


def issue_oauth_link_ticket_token(
    *,
    user_id: uuid.UUID,
    provider: str,
    provider_user_id: str,
    email: str | None,
    name: str | None,
) -> str:
    """One-time ticket encoding the pending link (existing password account +
    the provider identity that must be confirmed with a password before the
    ``OidcAccount`` row is created)."""

    settings = get_settings()
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(minutes=settings.oauth_ticket_ttl_minutes)
    payload = {
        "iss": _ISSUER,
        "sub": str(user_id),
        "purpose": _OAUTH_LINK_PURPOSE,
        "provider": provider,
        "provider_user_id": provider_user_id,
        "email": email,
        "name": name,
        "nonce": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_oauth_link_ticket_token(token: str) -> OAuthLinkClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "sub", "purpose", "provider", "provider_user_id"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("purpose") != _OAUTH_LINK_PURPOSE:
        raise InvalidTokenError("wrong purpose")
    try:
        return OAuthLinkClaims(
            user_id=uuid.UUID(payload["sub"]),
            provider=payload["provider"],
            provider_user_id=payload["provider_user_id"],
            email=payload.get("email"),
            name=payload.get("name"),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("malformed link ticket") from exc


def decode_access_token(token: str) -> AccessClaims:
    """Decode and validate an access token, raising :class:`InvalidTokenError`."""

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "sub", "sid", "iid", "jti"]},
        )
    except jwt.PyJWTError as exc:  # expired / bad signature / malformed
        raise InvalidTokenError(str(exc)) from exc

    try:
        org_raw = payload.get("org_id")
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
            identity_id=uuid.UUID(payload["iid"]),
            persona=payload.get("persona", "guest"),
            org_id=uuid.UUID(org_raw) if org_raw else None,
            jti=uuid.UUID(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("malformed claims") from exc
