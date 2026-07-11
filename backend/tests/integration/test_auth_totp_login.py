"""TOTP enforcement at login + encrypted-at-rest secrets (P2 auth hardening).

Covers ``docs/SECURITY_PRIVACY.md`` §8 and ``.claude/rules/backend.md``:

- A confirmed-TOTP account cannot obtain tokens with password alone — login
  returns a ``totp_required`` challenge and NO refresh cookie.
- ``/auth/login/totp`` with the correct code issues tokens + sets the cookie;
  a wrong/expired code is rejected with the uniform invalid-credentials error.
- The stored TOTP secret is Fernet ciphertext (never plaintext) and round-trips;
  legacy plaintext rows are tolerated and re-encrypted.
"""

from __future__ import annotations

import uuid

import pyotp
import pytest
from app.main import app
from app.modules.account.application import account_service
from app.modules.auth.application import auth_service, errors
from app.modules.auth.application.auth_service import LoginChallenge, LoginResult
from app.modules.auth.domain import security_events as ev
from app.modules.auth.domain.models import SecurityEvent, UserTotp
from app.modules.auth.domain.personas import permissions_for
from app.modules.auth.infrastructure import jwt as jwt_infra
from app.modules.auth.infrastructure.totp_crypto import (
    decrypt_totp_secret,
    encrypt_totp_secret,
)
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.auth_utils import CTX, fetch_verification_token, register_verified


def _email() -> str:
    return f"totp_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


def _principal(user_id: uuid.UUID) -> Principal:
    return Principal(user_id=user_id, persona="student", permissions=permissions_for("student"))


async def _enroll_confirmed_totp(db_session, user_id: uuid.UUID) -> str:
    """Enrol + confirm TOTP via the account service. Returns the base32 secret."""

    principal = _principal(user_id)
    setup = await account_service.totp_setup(db_session, principal=principal, ctx=CTX)
    secret = setup["secret"]
    code = pyotp.TOTP(secret).now()
    await account_service.totp_verify(db_session, principal=principal, code=code, ctx=CTX)
    return secret


# --------------------------------------------------------------------------- #
# Encryption at rest                                                          #
# --------------------------------------------------------------------------- #


def test_encrypt_round_trips_and_is_not_plaintext() -> None:
    secret = pyotp.random_base32()
    ciphertext = encrypt_totp_secret(secret)
    assert ciphertext != secret
    assert secret not in ciphertext
    decrypted, was_plaintext = decrypt_totp_secret(ciphertext)
    assert decrypted == secret
    assert was_plaintext is False


def test_decrypt_tolerates_legacy_plaintext() -> None:
    secret = pyotp.random_base32()
    decrypted, was_plaintext = decrypt_totp_secret(secret)
    assert decrypted == secret
    assert was_plaintext is True


async def test_totp_secret_stored_encrypted(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    secret = await _enroll_confirmed_totp(db_session, user.id)
    row = (
        await db_session.execute(select(UserTotp).where(UserTotp.user_id == user.id))
    ).scalar_one()
    # Persisted value is ciphertext, not the plaintext base32 secret.
    assert row.secret != secret
    assert secret not in row.secret
    decrypted, was_plaintext = decrypt_totp_secret(row.secret)
    assert decrypted == secret
    assert was_plaintext is False


async def test_legacy_plaintext_secret_reencrypted_on_verify(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    secret = pyotp.random_base32()
    # Simulate a pre-encryption dev row: plaintext secret, confirmed.
    db_session.add(UserTotp(user_id=user.id, secret=secret))
    await db_session.commit()
    # A successful TOTP login completes AND re-encrypts opportunistically.
    from datetime import UTC, datetime

    row = (
        await db_session.execute(select(UserTotp).where(UserTotp.user_id == user.id))
    ).scalar_one()
    row.confirmed_at = datetime.now(tz=UTC)
    await db_session.commit()

    challenge = await auth_service.login(
        db_session, email=user.email, password="Sup3rSecret!", ctx=CTX
    )
    assert isinstance(challenge, LoginChallenge)
    result = await auth_service.login_totp(
        db_session,
        challenge_token=challenge.challenge_token,
        code=pyotp.TOTP(secret).now(),
        ctx=CTX,
    )
    assert isinstance(result, LoginResult)
    refreshed = (
        await db_session.execute(select(UserTotp).where(UserTotp.user_id == user.id))
    ).scalar_one()
    assert refreshed.secret != secret  # now ciphertext
    assert decrypt_totp_secret(refreshed.secret) == (secret, False)


# --------------------------------------------------------------------------- #
# Enforcement at login (service level)                                        #
# --------------------------------------------------------------------------- #


async def test_login_without_totp_is_one_step(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    result = await auth_service.login(
        db_session, email=user.email, password="Sup3rSecret!", ctx=CTX
    )
    assert isinstance(result, LoginResult)
    assert result.tokens.access_token
    assert result.tokens.refresh_token


async def test_confirmed_totp_blocks_password_only_login(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    await _enroll_confirmed_totp(db_session, user.id)

    result = await auth_service.login(
        db_session, email=user.email, password="Sup3rSecret!", ctx=CTX
    )
    assert isinstance(result, LoginChallenge)
    assert result.challenge_token
    # The challenge token is not an access token and carries the pending user.
    assert jwt_infra.decode_totp_challenge_token(result.challenge_token) == user.id
    # A challenge security event was recorded.
    events = (
        (
            await db_session.execute(
                select(SecurityEvent).where(
                    SecurityEvent.user_id == user.id,
                    SecurityEvent.event_type == ev.TOTP_CHALLENGE,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1


async def test_login_totp_completes_with_correct_code(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    secret = await _enroll_confirmed_totp(db_session, user.id)
    challenge = await auth_service.login(
        db_session, email=user.email, password="Sup3rSecret!", ctx=CTX
    )
    assert isinstance(challenge, LoginChallenge)
    result = await auth_service.login_totp(
        db_session,
        challenge_token=challenge.challenge_token,
        code=pyotp.TOTP(secret).now(),
        ctx=CTX,
    )
    assert isinstance(result, LoginResult)
    assert result.tokens.access_token
    assert result.tokens.refresh_token
    success_events = (
        (
            await db_session.execute(
                select(SecurityEvent).where(
                    SecurityEvent.user_id == user.id,
                    SecurityEvent.event_type == ev.LOGIN_SUCCESS,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(success_events) == 1


async def test_login_totp_rejects_wrong_code(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    await _enroll_confirmed_totp(db_session, user.id)
    challenge = await auth_service.login(
        db_session, email=user.email, password="Sup3rSecret!", ctx=CTX
    )
    assert isinstance(challenge, LoginChallenge)
    with pytest.raises(errors.InvalidCredentialsError):
        await auth_service.login_totp(
            db_session,
            challenge_token=challenge.challenge_token,
            code="000000",
            ctx=CTX,
        )
    # A failed second-factor attempt accrues a LOGIN_FAILED event (lockout parity).
    failed = (
        (
            await db_session.execute(
                select(SecurityEvent).where(
                    SecurityEvent.user_id == user.id,
                    SecurityEvent.event_type == ev.LOGIN_FAILED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(failed) == 1


async def test_login_totp_rejects_bad_challenge_token(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    secret = await _enroll_confirmed_totp(db_session, user.id)
    with pytest.raises(errors.InvalidCredentialsError):
        await auth_service.login_totp(
            db_session,
            challenge_token="not.a.jwt",
            code=pyotp.TOTP(secret).now(),
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Enforcement at login (HTTP level + cookie)                                  #
# --------------------------------------------------------------------------- #


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


async def test_http_totp_login_flow(client, db_session) -> None:
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/120"}
    email = _email()
    reg = await client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!", "full_name": "TOTP User"},
        headers=headers,
    )
    assert reg.status_code == 202
    from app.modules.users.application import user_service

    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    token = await fetch_verification_token(db_session, user.id)
    await client.post("/auth/verify-email", json={"token": token})

    # One-step login to obtain an access token, then enrol TOTP via account API.
    login = await client.post(
        "/auth/login", json={"email": email, "password": "Sup3rSecret!"}, headers=headers
    )
    access = login.json()["data"]["access_token"]
    auth_headers = {"Authorization": f"Bearer {access}", **headers}
    setup = await client.post("/account/totp/setup", headers=auth_headers)
    secret = setup.json()["data"]["secret"]
    code = pyotp.TOTP(secret).now()
    verify = await client.post("/account/totp/verify", json={"code": code}, headers=auth_headers)
    assert verify.json()["data"]["confirmed"] is True

    client.cookies.clear()
    # Now password-only login must be gated by TOTP: challenge, NO tokens/cookie.
    gated = await client.post(
        "/auth/login", json={"email": email, "password": "Sup3rSecret!"}, headers=headers
    )
    assert gated.status_code == 200
    data = gated.json()["data"]
    assert data["totp_required"] is True
    assert data["challenge_token"]
    assert "access_token" not in data
    assert "vinuni_refresh=" not in gated.headers.get("set-cookie", "")
    assert client.cookies.get("vinuni_refresh") is None

    # Wrong code rejected (uniform invalid-credentials, no enumeration).
    bad = await client.post(
        "/auth/login/totp",
        json={"challenge_token": data["challenge_token"], "code": "000000"},
        headers=headers,
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "AUTH_REQUIRED"

    # Correct code completes login: tokens + httpOnly refresh cookie.
    good = await client.post(
        "/auth/login/totp",
        json={
            "challenge_token": data["challenge_token"],
            "code": pyotp.TOTP(secret).now(),
        },
        headers=headers,
    )
    assert good.status_code == 200
    body = good.json()["data"]
    assert body["access_token"]
    assert "refresh_token" not in body
    set_cookie = good.headers.get("set-cookie", "")
    assert "vinuni_refresh=" in set_cookie
    assert "httponly" in set_cookie.lower()


async def test_http_logout_clears_cookie_and_switch_identity_sets_fresh(client, db_session) -> None:
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/120"}
    user = await register_verified(db_session, email=_email())
    login = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "Sup3rSecret!"},
        headers=headers,
    )
    access = login.json()["data"]["access_token"]
    first_cookie = client.cookies.get("vinuni_refresh")
    assert first_cookie
    auth_headers = {"Authorization": f"Bearer {access}", **headers}

    # switch_identity to the same identity issues a fresh refresh cookie.
    identities = await client.get("/auth/identity", headers=auth_headers)
    identity_id = identities.json()["data"][0]["id"]
    switched = await client.post(
        "/auth/identity", json={"identity_id": identity_id}, headers=auth_headers
    )
    assert switched.status_code == 200
    assert "refresh_token" not in switched.json()["data"]
    assert "vinuni_refresh=" in switched.headers.get("set-cookie", "")
    assert client.cookies.get("vinuni_refresh") != first_cookie

    # logout deletes the cookie.
    new_access = switched.json()["data"]["access_token"]
    logout = await client.post(
        "/auth/logout", headers={"Authorization": f"Bearer {new_access}", **headers}
    )
    assert logout.status_code == 200
    # Delete-cookie emits a Set-Cookie that expires the value.
    assert "vinuni_refresh=" in logout.headers.get("set-cookie", "").lower()
    assert not client.cookies.get("vinuni_refresh")
