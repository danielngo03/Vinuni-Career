"""Tests for E36 B-542/B-543: resend/forgot-password throttling and OAuth
account linking (Google/Facebook).

Rate-limit tests exercise the HTTP layer (anti-enumeration must hold at the
API boundary). OAuth tests exercise ``oauth_service`` directly with a fake
provider injected via ``mock.patch.object`` (this codebase has no
respx/httpx-mock infra — see ``tests/unit/test_ai_judge.py`` for the
established pattern).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from app.main import app
from app.modules.auth.application import errors, oauth_service
from app.modules.auth.application.context import RequestContext
from app.modules.auth.domain.models import AuthThrottle, OidcAccount
from app.modules.auth.infrastructure.oauth_providers import OAuthUserInfo
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.users.application import user_service
from app.modules.users.application.user_write_facade import create_identity, create_user
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.auth_utils import register_verified

CTX = RequestContext(ip="203.0.113.11", user_agent="Mozilla/5.0 (Macintosh) Chrome/120")


def _email() -> str:
    return f"rl_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


# --------------------------------------------------------------------------- #
# Resend cooldown / hourly cap                                                 #
# --------------------------------------------------------------------------- #


async def test_resend_verification_cooldown_applies_identically_known_and_unknown(
    client, db_session
) -> None:
    known_email = _email()
    reg = await client.post(
        "/auth/register", json={"email": known_email, "password": "Sup3rSecret!"}
    )
    assert reg.status_code == 202

    unknown_email = _email()

    known_first = await client.post(
        "/auth/verify-email/resend", json={"email": known_email}
    )
    unknown_first = await client.post(
        "/auth/verify-email/resend", json={"email": unknown_email}
    )
    assert known_first.status_code == unknown_first.status_code == 200
    assert (
        known_first.json()["data"]["status"]
        == unknown_first.json()["data"]["status"]
        == "verification_sent"
    )

    known_second = await client.post(
        "/auth/verify-email/resend", json={"email": known_email}
    )
    unknown_second = await client.post(
        "/auth/verify-email/resend", json={"email": unknown_email}
    )
    assert known_second.status_code == unknown_second.status_code == 429
    assert (
        known_second.json()["error"]["details"]["reason"]
        == unknown_second.json()["error"]["details"]["reason"]
        == "resend_cooldown"
    )
    assert known_second.json()["error"]["code"] == "RATE_LIMITED"


async def test_forgot_password_cooldown_applies_identically_known_and_unknown(
    client, db_session
) -> None:
    known_email = _email()
    await client.post(
        "/auth/register", json={"email": known_email, "password": "Sup3rSecret!"}
    )
    unknown_email = _email()

    known_first = await client.post(
        "/auth/forgot-password", json={"email": known_email}
    )
    unknown_first = await client.post(
        "/auth/forgot-password", json={"email": unknown_email}
    )
    assert known_first.status_code == unknown_first.status_code == 200

    known_second = await client.post(
        "/auth/forgot-password", json={"email": known_email}
    )
    unknown_second = await client.post(
        "/auth/forgot-password", json={"email": unknown_email}
    )
    assert known_second.status_code == unknown_second.status_code == 429
    assert (
        known_second.json()["error"]["details"]["reason"]
        == unknown_second.json()["error"]["details"]["reason"]
        == "resend_cooldown"
    )


async def test_hourly_cap_returns_rate_limited_reason(client, db_session) -> None:
    email = _email()
    await client.post(
        "/auth/register", json={"email": email, "password": "Sup3rSecret!"}
    )

    # Simulate having already made auth_email_request_rate_limit_per_hour (5)
    # attempts earlier in the current rolling window (each past its own
    # cooldown) by writing the AuthThrottle row directly, then send the request
    # that pushes past the cap.
    from app.modules.auth.infrastructure.rate_limit import _key_hash

    now = datetime.now(tz=UTC)
    row = AuthThrottle(
        scope="resend_verification",
        key_hash=_key_hash(email),
        window_started_at=now - timedelta(minutes=30),
        attempt_count=5,
        last_attempt_at=now - timedelta(minutes=5),
    )
    db_session.add(row)
    await db_session.commit()

    resp = await client.post("/auth/verify-email/resend", json={"email": email})
    assert resp.status_code == 429
    assert resp.json()["error"]["details"]["reason"] == "rate_limited"
    assert resp.json()["error"]["details"]["retry_after_seconds"] > 0


# --------------------------------------------------------------------------- #
# OAuth account linking                                                       #
# --------------------------------------------------------------------------- #


class _FakeOAuthProvider:
    def __init__(self, *, user_info: OAuthUserInfo) -> None:
        self.user_info = user_info

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        return f"https://provider.example/authorize?state={state}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthUserInfo:
        return self.user_info


def _patched(fake_provider: _FakeOAuthProvider):
    return mock.patch.object(
        oauth_service, "get_oauth_provider", lambda _name: fake_provider
    ), mock.patch.object(oauth_service, "is_provider_configured", lambda _name: True)


async def test_oauth_new_verified_user_creates_account_and_logs_in(db_session) -> None:
    email = _email()
    fake = _FakeOAuthProvider(
        user_info=OAuthUserInfo(
            provider_user_id="google-sub-1",
            email=email,
            email_verified=True,
            name="New OAuth User",
        )
    )
    p1, p2 = _patched(fake)
    with p1, p2:
        result = await oauth_service.handle_callback(
            db_session,
            provider="google",
            code="fake-code",
            redirect_uri="http://localhost:8000/api/v1/auth/oauth/google/callback",
            ctx=CTX,
        )
    assert isinstance(result, oauth_service.OAuthLoggedIn)

    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    assert user.is_email_verified
    assert user.password_hash is None

    link = (
        await db_session.execute(
            select(OidcAccount).where(OidcAccount.user_id == user.id)
        )
    ).scalar_one()
    assert link.provider == "google"

    login_result = await oauth_service.exchange_ticket(
        db_session, ticket=result.ticket, ctx=CTX
    )
    assert login_result.user.id == user.id
    assert login_result.tokens.access_token


async def test_oauth_auto_links_passwordless_existing_account(db_session) -> None:
    email = _email()
    user = await create_user(
        db_session, email=email, password_hash=None, full_name="SSO Only"
    )
    await create_identity(db_session, user_id=user.id, persona="student", is_primary=True)
    await db_session.commit()

    fake = _FakeOAuthProvider(
        user_info=OAuthUserInfo(
            provider_user_id="google-sub-2",
            email=email,
            email_verified=True,
            name="SSO Only",
        )
    )
    p1, p2 = _patched(fake)
    with p1, p2:
        result = await oauth_service.handle_callback(
            db_session,
            provider="google",
            code="fake-code",
            redirect_uri="http://localhost:8000/api/v1/auth/oauth/google/callback",
            ctx=CTX,
        )
    assert isinstance(result, oauth_service.OAuthLoggedIn)

    link = (
        await db_session.execute(
            select(OidcAccount).where(OidcAccount.user_id == user.id)
        )
    ).scalar_one()
    assert link.provider == "google"

    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.oauth_linked",
            )
        )
    ).scalars().all()
    assert len(outbox) == 1


async def test_oauth_conflict_requires_password_confirm(db_session) -> None:
    email = _email()
    verified_user = await register_verified(db_session, email=email, password="Sup3rSecret!")

    fake = _FakeOAuthProvider(
        user_info=OAuthUserInfo(
            provider_user_id="google-sub-3",
            email=email,
            email_verified=True,
            name="Conflict User",
        )
    )
    p1, p2 = _patched(fake)
    with p1, p2:
        result = await oauth_service.handle_callback(
            db_session,
            provider="google",
            code="fake-code",
            redirect_uri="http://localhost:8000/api/v1/auth/oauth/google/callback",
            ctx=CTX,
        )
    assert isinstance(result, oauth_service.OAuthLinkConflict)
    assert result.email == email

    # No OidcAccount created yet.
    link = (
        await db_session.execute(
            select(OidcAccount).where(OidcAccount.provider_user_id == "google-sub-3")
        )
    ).scalar_one_or_none()
    assert link is None

    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == verified_user.id,
                NotificationOutbox.template_key == "account.oauth_conflict",
            )
        )
    ).scalars().all()
    assert len(outbox) == 1

    # Wrong password -> uniform 401, no account created.
    with pytest.raises(errors.InvalidCredentialsError):
        await oauth_service.confirm_link(
            db_session, ticket=result.ticket, password="WrongPassword!", ctx=CTX
        )
    link_after_bad = (
        await db_session.execute(
            select(OidcAccount).where(OidcAccount.provider_user_id == "google-sub-3")
        )
    ).scalar_one_or_none()
    assert link_after_bad is None

    # Correct password -> creates the OidcAccount + logs in.
    login_result = await oauth_service.confirm_link(
        db_session, ticket=result.ticket, password="Sup3rSecret!", ctx=CTX
    )
    assert login_result.user.id == verified_user.id
    link_after_ok = (
        await db_session.execute(
            select(OidcAccount).where(OidcAccount.provider_user_id == "google-sub-3")
        )
    ).scalar_one()
    assert link_after_ok.user_id == verified_user.id


async def test_oauth_unverified_provider_email_is_rejected(db_session) -> None:
    email = _email()
    fake = _FakeOAuthProvider(
        user_info=OAuthUserInfo(
            provider_user_id="google-sub-4",
            email=email,
            email_verified=False,
            name="Unverified",
        )
    )
    p1, p2 = _patched(fake)
    with p1, p2, pytest.raises(errors.InvalidTokenError):
        await oauth_service.handle_callback(
            db_session,
            provider="google",
            code="fake-code",
            redirect_uri="http://localhost:8000/api/v1/auth/oauth/google/callback",
            ctx=CTX,
        )

    user = await user_service.get_by_email(db_session, email)
    assert user is None
