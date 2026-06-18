from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.access.application.service import get_user_by_email, issue_user_session
from app.modules.access.schemas import TokenResponse
from app.platform.database.models import OIDCLoginTicket, User, UserOIDCAccount
from app.shared.config import settings
from app.shared.errors import AppError, ErrorCode
from app.shared.security import hash_password


def configured_providers() -> dict[str, bool]:
    return {
        "google": bool(
            settings.google_oidc_client_id and settings.google_oidc_client_secret
        ),
        "microsoft": bool(
            settings.microsoft_oidc_client_id
            and settings.microsoft_oidc_client_secret
        ),
    }


def authorization_url(provider: str) -> str:
    config = _provider_config(provider)
    discovery = _discovery(config["discovery_url"])
    nonce = uuid4().hex
    state = jwt.encode(
        {
            "type": "oidc_state",
            "provider": provider,
            "nonce": nonce,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    redirect_uri = f"{settings.oidc_backend_callback_base}/{provider}/callback"
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "prompt": "select_account",
        }
    )
    return f"{discovery['authorization_endpoint']}?{query}"


def complete_oidc_login(
    db: Session,
    *,
    provider: str,
    code: str,
    state: str,
) -> str:
    config = _provider_config(provider)
    state_claims = _decode_typed_token(state, "oidc_state")
    if state_claims.get("provider") != provider:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="OIDC provider mismatch",
            status_code=401,
        )
    discovery = _discovery(config["discovery_url"])
    redirect_uri = f"{settings.oidc_backend_callback_base}/{provider}/callback"
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        response = client.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
            },
        )
        response.raise_for_status()
        token_payload = response.json()
    id_token = token_payload.get("id_token")
    if not id_token:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="OIDC provider did not return an ID token",
            status_code=401,
        )
    claims = _verify_id_token(
        provider=provider,
        encoded=id_token,
        discovery=discovery,
        audience=config["client_id"],
        nonce=str(state_claims["nonce"]),
    )
    user = _resolve_oidc_user(db, provider, claims)
    jti = uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(minutes=2)
    db.add(
        OIDCLoginTicket(
            jti=jti,
            user_id=user.id,
            provider=provider,
            expires_at=expires_at,
        )
    )
    db.commit()
    return jwt.encode(
        {
            "type": "oidc_ticket",
            "sub": user.id,
            "provider": provider,
            "jti": jti,
            "iat": datetime.now(UTC),
            "exp": expires_at,
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )


def exchange_login_ticket(
    db: Session,
    ticket: str,
    *,
    device_info: str | None = None,
) -> TokenResponse:
    claims = _decode_typed_token(ticket, "oidc_ticket")
    record = db.scalar(
        select(OIDCLoginTicket).where(OIDCLoginTicket.jti == claims.get("jti"))
    )
    now = datetime.now(UTC)
    if (
        not record
        or record.used_at is not None
        or _as_utc(record.expires_at) <= now
        or record.user_id != claims.get("sub")
    ):
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="OIDC login ticket is invalid or already used",
            status_code=401,
        )
    user = db.get(User, record.user_id)
    if not user or not user.is_active:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="OIDC user is not active",
            status_code=401,
        )
    record.used_at = now
    db.flush()
    return issue_user_session(db, user, device_info=device_info)


def _provider_config(provider: str) -> dict[str, str]:
    if provider == "google":
        values = {
            "client_id": settings.google_oidc_client_id,
            "client_secret": settings.google_oidc_client_secret,
            "discovery_url": settings.google_oidc_discovery_url,
        }
    elif provider == "microsoft":
        values = {
            "client_id": settings.microsoft_oidc_client_id,
            "client_secret": settings.microsoft_oidc_client_secret,
            "discovery_url": (
                "https://login.microsoftonline.com/"
                f"{settings.microsoft_oidc_tenant}/v2.0/"
                ".well-known/openid-configuration"
            ),
        }
    else:
        raise AppError(
            code=ErrorCode.NOT_FOUND,
            message="Unknown OIDC provider",
            status_code=404,
        )
    if not values["client_id"] or not values["client_secret"]:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message=f"{provider.title()} OIDC is not configured",
            status_code=503,
        )
    return {key: str(value) for key, value in values.items()}


def _discovery(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _verify_id_token(
    *,
    provider: str,
    encoded: str,
    discovery: dict[str, Any],
    audience: str,
    nonce: str,
) -> dict[str, Any]:
    signing_key = jwt.PyJWKClient(discovery["jwks_uri"]).get_signing_key_from_jwt(encoded)
    options = {"verify_iss": provider != "microsoft"}
    claims = jwt.decode(
        encoded,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=discovery.get("issuer") if provider != "microsoft" else None,
        options=options,  # type: ignore[arg-type]  # PyJWT's runtime accepts this mapping.
    )
    if claims.get("nonce") != nonce:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="OIDC nonce mismatch",
            status_code=401,
        )
    if provider == "microsoft":
        issuer = str(claims.get("iss") or "")
        if not (
            issuer.startswith("https://login.microsoftonline.com/")
            and issuer.endswith("/v2.0")
        ):
            raise AppError(
                code=ErrorCode.UNAUTHORIZED,
                message="Invalid Microsoft token issuer",
                status_code=401,
            )
    return claims


def _resolve_oidc_user(
    db: Session,
    provider: str,
    claims: dict[str, Any],
) -> User:
    subject = str(claims.get("sub") or "")
    email = str(
        claims.get("email")
        or claims.get("preferred_username")
        or ""
    ).strip().lower()
    if not subject or not email or "@" not in email:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="OIDC account does not expose a verified email",
            status_code=401,
        )
    account = db.scalar(
        select(UserOIDCAccount).where(
            UserOIDCAccount.provider == provider,
            UserOIDCAccount.subject == subject,
        )
    )
    if account:
        user = db.get(User, account.user_id)
        if user:
            account.claims = claims
            account.email = email
            return user

    user = get_user_by_email(db, email)
    if not user:
        user = User(
            email=email,
            full_name=str(claims.get("name") or email.split("@")[0]),
            password_hash=hash_password(uuid4().hex + uuid4().hex),
        )
        db.add(user)
        db.flush()
    db.add(
        UserOIDCAccount(
            user_id=user.id,
            provider=provider,
            subject=subject,
            email=email,
            claims=claims,
        )
    )
    db.flush()
    return user


def _decode_typed_token(encoded: str, token_type: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            encoded,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except jwt.PyJWTError as exc:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="Invalid OIDC state",
            status_code=401,
        ) from exc
    if claims.get("type") != token_type:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="Invalid OIDC token type",
            status_code=401,
        )
    return claims


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
