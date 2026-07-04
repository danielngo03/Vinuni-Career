"""HTTP-level auth/account flow via ASGI transport (no real network/email)."""

from __future__ import annotations

import uuid

import pytest
from app.main import app
from app.modules.users.application import user_service
from httpx import ASGITransport, AsyncClient

from tests.auth_utils import fetch_verification_token


def _email() -> str:
    return f"api_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


async def test_unauthenticated_request_returns_401(client) -> None:
    resp = await client.get("/account/preferences")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


async def test_full_register_verify_login_me_refresh_sessions(client, db_session) -> None:
    email = _email()
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh) Chrome/120"}

    reg = await client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!", "full_name": "API User"},
        headers=headers,
    )
    assert reg.status_code == 202
    assert reg.json()["data"]["status"] == "verification_sent"

    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    token = await fetch_verification_token(db_session, user.id)

    verify = await client.post("/auth/verify-email", json={"token": token})
    assert verify.status_code == 200
    assert verify.json()["data"]["email_verified"] is True

    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "Sup3rSecret!"},
        headers=headers,
    )
    assert login.status_code == 200
    body = login.json()["data"]
    access = body["access_token"]
    # Refresh token is delivered ONLY as an httpOnly cookie, never in the body.
    assert "refresh_token" not in body
    set_cookie = login.headers.get("set-cookie", "")
    assert "vinuni_refresh=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "path=/api/v1/auth" in set_cookie.lower()
    assert client.cookies.get("vinuni_refresh")
    assert body["user"]["email"] == email
    assert "password_hash" not in str(body)

    auth_headers = {"Authorization": f"Bearer {access}", **headers}
    me = await client.get("/auth/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["data"]["email"] == email
    assert me.json()["data"]["active_identity"]["persona"] == "student"

    # Refresh reads the cookie (no body), rotates, and sets a fresh cookie.
    old_cookie = client.cookies.get("vinuni_refresh")
    refreshed = await client.post("/auth/refresh", headers=headers)
    assert refreshed.status_code == 200
    new_access = refreshed.json()["data"]["access_token"]
    assert new_access != access
    assert "refresh_token" not in refreshed.json()["data"]
    assert "vinuni_refresh=" in refreshed.headers.get("set-cookie", "")
    assert client.cookies.get("vinuni_refresh") != old_cookie

    sessions = await client.get(
        "/account/sessions",
        headers={"Authorization": f"Bearer {new_access}", **headers},
    )
    assert sessions.status_code == 200
    items = sessions.json()["data"]
    assert len(items) == 1
    assert items[0]["current"] is True
    # No raw IP / user-agent / refresh token leaked in device metadata.
    blob = str(items)
    assert "Mozilla" not in blob
    assert "refresh" not in blob


async def test_register_pending_unverified_email_resumes(client, db_session) -> None:
    """A duplicate register against a still-unverified (pending/abandoned)
    account resumes in place: 202, same shape, NOT a 409 (E36 B-542)."""

    email = _email()
    first = await client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!"},
    )
    assert first.status_code == 202

    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    first_token = await fetch_verification_token(db_session, user.id)

    duplicate = await client.post(
        "/auth/register",
        json={"email": email.upper(), "password": "OtherSecret2026!", "full_name": "Resumed"},
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["data"]["status"] == "verification_sent"
    assert duplicate.json()["data"]["email"] == email

    # A fresh verification token was issued (a second distinct outbox row now
    # exists) and the ORIGINAL token is no longer usable.
    from app.modules.notifications.domain.models import NotificationOutbox
    from sqlalchemy import select

    rows = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.email_verification",
            )
        )
    ).scalars().all()
    tokens = {str(row.variables["token"]) for row in rows}
    assert len(tokens) == 2
    second_token = next(iter(tokens - {first_token}))

    stale_verify = await client.post("/auth/verify-email", json={"token": first_token})
    assert stale_verify.status_code == 400

    verify = await client.post("/auth/verify-email", json={"token": second_token})
    assert verify.status_code == 200

    login_new = await client.post(
        "/auth/login", json={"email": email, "password": "OtherSecret2026!"}
    )
    assert login_new.status_code == 200

    login_old = await client.post(
        "/auth/login", json={"email": email, "password": "Sup3rSecret!"}
    )
    assert login_old.status_code == 401


async def test_register_verified_duplicate_email_returns_conflict(client, db_session) -> None:
    """A duplicate register against an ALREADY-VERIFIED account stays a stable
    409 (regression: must not have been loosened by the pending-resume path)."""

    email = _email()
    first = await client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!"},
    )
    assert first.status_code == 202
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    token = await fetch_verification_token(db_session, user.id)
    await client.post("/auth/verify-email", json={"token": token})

    duplicate = await client.post(
        "/auth/register",
        json={"email": email.upper(), "password": "OtherSecret2026!"},
    )
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["details"]["reason"] == "email_already_registered"


async def test_forgot_reset_login_flow_over_http(client, db_session) -> None:
    from app.modules.notifications.domain.models import NotificationOutbox
    from sqlalchemy import select

    email = _email()
    reg = await client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!", "full_name": "Reset User"},
    )
    assert reg.status_code == 202
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    token = await fetch_verification_token(db_session, user.id)
    await client.post("/auth/verify-email", json={"token": token})

    # Log in once so there is an active session to revoke on reset. Capture the
    # refresh token from the httpOnly cookie (no longer present in the body).
    login = await client.post(
        "/auth/login", json={"email": email, "password": "Sup3rSecret!"}
    )
    old_refresh = login.cookies.get("vinuni_refresh")
    assert old_refresh

    # Anti-enumeration: same generic response for known + unknown email.
    known = await client.post("/auth/forgot-password", json={"email": email})
    unknown = await client.post(
        "/auth/forgot-password", json={"email": _email()}
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json()["data"] == {**known.json()["data"]}
    assert known.json()["data"]["status"] == unknown.json()["data"]["status"] == "reset_email_sent"

    reset_row = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.password_reset",
            )
        )
    ).scalar_one()
    reset_token = str(reset_row.variables["token"])

    reset = await client.post(
        "/auth/reset-password",
        json={"token": reset_token, "password": "FreshPass2026!"},
    )
    assert reset.status_code == 200
    assert reset.json()["data"]["status"] == "password_reset"

    # New password logs in.
    relog = await client.post(
        "/auth/login", json={"email": email, "password": "FreshPass2026!"}
    )
    assert relog.status_code == 200

    # Old refresh token rejected after reset revoked all sessions. Clear the
    # client cookie (now holding the fresh post-relogin token) and present the
    # stale token via the non-browser body fallback to prove it is rejected.
    client.cookies.clear()
    bad = await client.post(
        "/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert bad.status_code == 401

    # Reusing the reset token is rejected with a friendly validation error.
    reused = await client.post(
        "/auth/reset-password",
        json={"token": reset_token, "password": "FreshPass2026!"},
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_forgot_reset_with_otp_over_http(client, db_session) -> None:
    from app.modules.notifications.domain.models import NotificationOutbox
    from sqlalchemy import select

    email = _email()
    reg = await client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!"},
    )
    assert reg.status_code == 202
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    token = await fetch_verification_token(db_session, user.id)
    await client.post("/auth/verify-email", json={"token": token})

    await client.post("/auth/forgot-password", json={"email": email})
    reset_row = (
        await db_session.execute(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.recipient_id == user.id,
                NotificationOutbox.template_key == "account.password_reset",
            )
            .order_by(NotificationOutbox.created_at.desc())
        )
    ).scalars().first()
    assert reset_row is not None
    otp = str(reset_row.variables["otp_code"])

    reset = await client.post(
        "/auth/reset-password/otp",
        json={"email": email, "otp_code": otp, "password": "FreshOtp2026!"},
    )
    assert reset.status_code == 200
    assert reset.json()["data"]["status"] == "password_reset"

    relog = await client.post(
        "/auth/login", json={"email": email, "password": "FreshOtp2026!"}
    )
    assert relog.status_code == 200


async def test_protected_route_rejects_garbage_token(client) -> None:
    resp = await client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.jwt"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"
