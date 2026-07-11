"""OAuth/OIDC provider adapters (Google / Facebook).

Self-contained ``httpx.AsyncClient`` calls, matching the inline-client style
used elsewhere in this codebase (``app/ai/gateway/openai_compatible.py``,
``app/modules/onboarding/application/doc_verification.py``) — no shared HTTP
wrapper exists and none is introduced here. Real network calls only happen
against Google/Facebook's OAuth endpoints; tests inject a ``FakeOAuthProvider``
implementing the same :class:`OAuthProvider` protocol via
``mock.patch.object`` (this codebase has no respx/httpx-mock infra).
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.shared.exceptions import ValidationFailedError

_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

_FACEBOOK_AUTHORIZE_URL = "https://www.facebook.com/v18.0/dialog/oauth"
_FACEBOOK_TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"
_FACEBOOK_USERINFO_URL = "https://graph.facebook.com/v18.0/me"


@dataclass(slots=True)
class OAuthUserInfo:
    provider_user_id: str
    email: str | None
    email_verified: bool
    name: str | None


class OAuthProvider(Protocol):
    def authorize_url(self, *, state: str, redirect_uri: str) -> str: ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthUserInfo: ...


class GoogleOAuthProvider:
    def __init__(self, *, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{_GOOGLE_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            userinfo_resp = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_resp.raise_for_status()
            claims = userinfo_resp.json()

        return OAuthUserInfo(
            provider_user_id=str(claims["sub"]),
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name"),
        )


class FacebookOAuthProvider:
    def __init__(self, *, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "email public_profile",
            "state": state,
        }
        return f"{_FACEBOOK_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=10) as client:
            token_resp = await client.get(
                _FACEBOOK_TOKEN_URL,
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            userinfo_resp = await client.get(
                _FACEBOOK_USERINFO_URL,
                params={
                    "fields": "id,name,email",
                    "access_token": access_token,
                },
            )
            userinfo_resp.raise_for_status()
            claims = userinfo_resp.json()

        # Facebook's Graph API only returns an email when the user has one AND
        # granted the "email" scope; it does not expose a separate verified
        # flag — a returned email from the Graph API is treated as verified
        # (Facebook only ever returns verified emails here).
        email = claims.get("email")
        return OAuthUserInfo(
            provider_user_id=str(claims["id"]),
            email=email,
            email_verified=bool(email),
            name=claims.get("name"),
        )


def get_oauth_provider(name: str) -> OAuthProvider:
    settings = get_settings()
    if name == "google":
        return GoogleOAuthProvider(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
        )
    if name == "facebook":
        return FacebookOAuthProvider(
            client_id=settings.facebook_oauth_client_id,
            client_secret=settings.facebook_oauth_client_secret,
        )
    raise ValidationFailedError(details={"reason": "unsupported_oauth_provider"})


def is_provider_configured(name: str) -> bool:
    settings = get_settings()
    if name == "google":
        return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)
    if name == "facebook":
        return bool(settings.facebook_oauth_client_id and settings.facebook_oauth_client_secret)
    return False
