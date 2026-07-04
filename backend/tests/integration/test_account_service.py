"""Service-level account tests: preferences, sessions, password, RBAC, privacy."""

from __future__ import annotations

import uuid

import pytest
from app.modules.account.application import account_service
from app.modules.auth.application import auth_service
from app.modules.auth.application.errors import InvalidCredentialsError
from app.modules.auth.domain.models import Session
from app.modules.auth.domain.personas import permissions_for
from app.modules.auth.infrastructure.jwt import decode_access_token
from app.modules.auth.infrastructure.passwords import verify_password
from app.modules.users.application import user_service
from app.shared.exceptions import PermissionDeniedError
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import CTX, register_verified


def _email() -> str:
    return f"acct_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


def _principal(user_id: uuid.UUID, persona: str = "student") -> Principal:
    return Principal(
        user_id=user_id, persona=persona, permissions=permissions_for(persona)
    )


async def _login(db_session, email: str):
    return await auth_service.login(
        db_session, email=email, password="Sup3rSecret!", ctx=CTX
    )


async def test_preferences_returns_locked_mandatory_categories(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    principal = _principal(user.id)
    prefs = await account_service.get_preferences(db_session, principal=principal)
    assert prefs["locale"] == "vi"
    sec = prefs["categories"]["security_alert"]
    assert sec["locked"] is True
    assert sec["email"] == "mandatory"
    assert sec["in_app"] is True


async def test_patch_cannot_disable_mandatory_but_updates_optional(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    principal = _principal(user.id)
    updated = await account_service.update_preferences(
        db_session,
        principal=principal,
        ctx=CTX,
        payload={
            "locale": "en",
            "categories": {
                # Attempt to disable a mandatory category -> ignored.
                "security_alert": {"in_app": False, "email": "off"},
                # Optional category -> applied.
                "job_digest": {"in_app": False, "email": "daily", "push": True},
            },
        },
    )
    assert updated["locale"] == "en"
    assert updated["categories"]["security_alert"]["locked"] is True
    assert updated["categories"]["security_alert"]["in_app"] is True
    assert updated["categories"]["security_alert"]["email"] == "mandatory"
    job = updated["categories"]["job_digest"]
    assert job["in_app"] is False
    assert job["email"] == "daily"
    assert job["push"] is True


async def test_sessions_list_exposes_safe_metadata_only(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    login = await _login(db_session, user.email)
    claims = decode_access_token(login.tokens.access_token)
    principal = _principal(user.id)
    sessions = await account_service.list_sessions(
        db_session, principal=principal, current_session_id=claims.session_id
    )
    assert len(sessions) == 1
    s = sessions[0]
    assert s["current"] is True
    assert s["device_hint"]  # coarse hint, e.g. chrome_desktop
    # No raw IP, no user-agent, no refresh token, no ip_hash leaked.
    serialized = str(s)
    assert CTX.ip not in serialized
    assert "Mozilla" not in serialized
    assert "refresh" not in serialized
    assert "ip_hash" not in s


async def test_remote_revoke_session(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    login = await _login(db_session, user.email)
    claims = decode_access_token(login.tokens.access_token)
    principal = _principal(user.id)
    await account_service.revoke_session(
        db_session, principal=principal, session_id=claims.session_id, ctx=CTX
    )
    sess = (
        await db_session.execute(
            select(Session).where(Session.id == claims.session_id)
        )
    ).scalar_one()
    assert sess.revoked_at is not None
    assert sess.revoked_reason == "remote_logout"


async def test_password_change_reauth_and_revokes_other_sessions(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    # Two sessions (two devices).
    first = await _login(db_session, user.email)
    second = await _login(db_session, user.email)
    first_claims = decode_access_token(first.tokens.access_token)
    second_claims = decode_access_token(second.tokens.access_token)
    principal = _principal(user.id)

    # Wrong current password is rejected.
    with pytest.raises(InvalidCredentialsError):
        await account_service.change_password(
            db_session,
            principal=principal,
            current_session_id=first_claims.session_id,
            current_password="wrong",
            new_password="BrandN3wPass!",
            ctx=CTX,
        )

    await account_service.change_password(
        db_session,
        principal=principal,
        current_session_id=first_claims.session_id,
        current_password="Sup3rSecret!",
        new_password="BrandN3wPass!",
        ctx=CTX,
    )
    refreshed = await user_service.get_by_id(db_session, user.id)
    assert refreshed is not None
    assert verify_password("BrandN3wPass!", refreshed.password_hash)

    # Current session stays; the other session is revoked.
    current = (
        await db_session.execute(
            select(Session).where(Session.id == first_claims.session_id)
        )
    ).scalar_one()
    other = (
        await db_session.execute(
            select(Session).where(Session.id == second_claims.session_id)
        )
    ).scalar_one()
    assert current.revoked_at is None
    assert other.revoked_at is not None


async def test_security_events_have_friendly_labels_no_pii(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    await _login(db_session, user.email)
    principal = _principal(user.id)
    events = await account_service.list_events(db_session, principal=principal)
    assert events
    blob = str(events)
    assert CTX.ip not in blob
    assert "Mozilla" not in blob
    # Friendly bilingual labels, never raw enum codes presented as the label.
    login_ev = next(e for e in events if e["type"] == "login_success")
    assert login_ev["label"] == "Đăng nhập thành công"
    assert login_ev["label_en"] == "Signed in"


async def test_rbac_denies_principal_without_account_permission(db_session) -> None:
    user = await register_verified(db_session, email=_email())
    # Authenticated but no account permissions -> 403 PermissionDenied.
    denied = Principal(user_id=user.id, persona="none", permissions=frozenset())
    with pytest.raises(PermissionDeniedError):
        await account_service.get_preferences(db_session, principal=denied)
    # Student persona is allowed.
    allowed = _principal(user.id)
    prefs = await account_service.get_preferences(db_session, principal=allowed)
    assert "categories" in prefs


async def test_totp_setup_verify_disable_scaffold(db_session) -> None:
    import pyotp

    user = await register_verified(db_session, email=_email())
    principal = _principal(user.id)
    setup = await account_service.totp_setup(db_session, principal=principal, ctx=CTX)
    assert setup["confirmed"] is False
    assert setup["secret"]
    code = pyotp.TOTP(setup["secret"]).now()
    verified = await account_service.totp_verify(
        db_session, principal=principal, code=code, ctx=CTX
    )
    assert verified["confirmed"] is True
    code2 = pyotp.TOTP(setup["secret"]).now()
    disabled = await account_service.totp_disable(
        db_session, principal=principal, code=code2, ctx=CTX
    )
    assert disabled["confirmed"] is False
