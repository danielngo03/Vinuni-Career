"""Register hardening (email/password only) + no-name email + register throttle.

Covers the owner-flagged auth gaps:
- Register succeeds with NO name (identity is email/password only; a name belongs
  to onboarding / profile / CV confirmation).
- Verification and password-reset emails never assume a name exists — the greeting
  falls back to the account email so nothing renders an empty ``Hi ,``.
- Register has a service-layer rate limit (shared enumeration-safe throttle infra).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.main import app
from app.modules.auth.application import auth_service
from app.modules.auth.domain.models import AuthThrottle
from app.modules.auth.infrastructure.rate_limit import _key_hash
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.users.application import user_service
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.auth_utils import CTX, fetch_verification_token


def _email() -> str:
    return f"reghard_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


async def _outbox_vars(session, *, user_id: uuid.UUID, template_key: str) -> dict:
    rows = (
        (
            await session.execute(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.recipient_id == user_id,
                    NotificationOutbox.template_key == template_key,
                )
                .order_by(NotificationOutbox.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    assert rows, f"no outbox row for {template_key}"
    return dict(rows[0].variables)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


# --------------------------------------------------------------------------- #
# Register is email/password only                                             #
# --------------------------------------------------------------------------- #


async def test_register_without_name_succeeds(db_session) -> None:
    email = _email()
    result = await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name=None, ctx=CTX
    )
    assert result == {"status": "verification_sent", "email": email}
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    assert user.full_name is None  # no name captured at register
    assert user.is_email_verified is False


async def test_register_without_name_over_http(client, db_session) -> None:
    email = _email()
    reg = await client.post("/auth/register", json={"email": email, "password": "Sup3rSecret!"})
    assert reg.status_code == 202
    assert reg.json()["data"]["status"] == "verification_sent"
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    assert user.full_name is None


# --------------------------------------------------------------------------- #
# Verification / reset emails never assume a name                             #
# --------------------------------------------------------------------------- #


async def test_verification_email_greeting_falls_back_to_email(db_session) -> None:
    email = _email()
    await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name=None, ctx=CTX
    )
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    variables = await _outbox_vars(
        db_session, user_id=user.id, template_key="account.email_verification"
    )
    # A never-empty greeting token — the account email, not "".
    assert variables["name"] == email
    assert str(variables["name"]).strip() != ""


async def test_password_reset_and_changed_emails_have_nonempty_greeting(db_session) -> None:
    email = _email()
    # Register + verify WITHOUT a name.
    await auth_service.register(
        db_session, email=email, password="Sup3rSecret!", full_name=None, ctx=CTX
    )
    user = await user_service.get_by_email(db_session, email)
    assert user is not None
    token = await fetch_verification_token(db_session, user.id)
    await auth_service.verify_email(db_session, token=token, ctx=CTX)

    # Request + complete a password reset (no name anywhere in the account).
    await auth_service.forgot_password(db_session, email=email, ctx=CTX)
    reset_vars = await _outbox_vars(
        db_session, user_id=user.id, template_key="account.password_reset"
    )
    assert reset_vars["name"] == email

    reset_row = (
        (
            await db_session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.recipient_id == user.id,
                    NotificationOutbox.template_key == "account.password_reset",
                )
            )
        )
        .scalars()
        .first()
    )
    assert reset_row is not None
    otp = str(reset_row.variables["otp_code"])

    await auth_service.reset_password_otp(
        db_session, email=email, otp_code=otp, password="BrandNewPass1!", ctx=CTX
    )
    changed_vars = await _outbox_vars(
        db_session, user_id=user.id, template_key="account.password_changed"
    )
    assert changed_vars["name"] == email
    assert str(changed_vars["name"]).strip() != ""


# --------------------------------------------------------------------------- #
# Register rate limit                                                          #
# --------------------------------------------------------------------------- #


async def test_register_is_rate_limited_when_hourly_cap_reached(client, db_session) -> None:
    """A brand-new email whose ``register`` throttle already sits at the hourly
    cap is rejected with a 429 (no account created)."""

    email = _email()
    now = datetime.now(tz=UTC)
    db_session.add(
        AuthThrottle(
            scope="register",
            key_hash=_key_hash(email),
            window_started_at=now - timedelta(minutes=30),
            attempt_count=5,  # == auth_email_request_rate_limit_per_hour default
            last_attempt_at=now - timedelta(minutes=5),  # past the cooldown
        )
    )
    await db_session.commit()

    resp = await client.post("/auth/register", json={"email": email, "password": "Sup3rSecret!"})
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"
    assert resp.json()["error"]["details"]["reason"] == "rate_limited"

    # No account was created by the throttled attempt.
    assert await user_service.get_by_email(db_session, email) is None


async def test_register_cooldown_blocks_rapid_new_account_retry(client, db_session) -> None:
    """Two brand-new-account attempts for the same email inside the cooldown
    window: the second is 429'd. (The first creates a pending account; a genuine
    re-register would instead take the resume path — this exercises the throttle
    directly via a pre-seeded recent attempt.)"""

    email = _email()
    now = datetime.now(tz=UTC)
    db_session.add(
        AuthThrottle(
            scope="register",
            key_hash=_key_hash(email),
            window_started_at=now,
            attempt_count=1,
            last_attempt_at=now,  # within cooldown
        )
    )
    await db_session.commit()

    resp = await client.post("/auth/register", json={"email": email, "password": "Sup3rSecret!"})
    assert resp.status_code == 429
    assert resp.json()["error"]["details"]["reason"] == "resend_cooldown"
    assert resp.json()["error"]["details"]["retry_after_seconds"] > 0
