"""Unit tests for auth security primitives: passwords, token hashing, JWT."""

from __future__ import annotations

import uuid

import pytest
from app.modules.auth.infrastructure import jwt as jwt_infra
from app.modules.auth.infrastructure.passwords import hash_password, verify_password
from app.modules.auth.infrastructure.tokens import generate_token, hash_token


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    hashed = hash_password("Sup3rSecret!")
    assert hashed != "Sup3rSecret!"
    assert "Sup3rSecret!" not in hashed
    assert verify_password("Sup3rSecret!", hashed) is True
    assert verify_password("wrong", hashed) is False
    assert verify_password("anything", None) is False


def test_token_hash_is_deterministic_and_opaque() -> None:
    raw = generate_token()
    assert hash_token(raw) == hash_token(raw)
    assert hash_token(raw) != raw
    assert len(hash_token(raw)) == 64


def test_jwt_round_trip_carries_claims() -> None:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    identity_id = uuid.uuid4()
    token, jti, _exp = jwt_infra.issue_access_token(
        user_id=user_id,
        session_id=session_id,
        identity_id=identity_id,
        persona="student",
        org_id=None,
    )
    claims = jwt_infra.decode_access_token(token)
    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert claims.identity_id == identity_id
    assert claims.persona == "student"
    assert claims.org_id is None
    assert claims.jti == jti


def test_jwt_rejects_tampered_token() -> None:
    token, _jti, _exp = jwt_infra.issue_access_token(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        identity_id=uuid.uuid4(),
        persona="student",
        org_id=None,
    )
    with pytest.raises(jwt_infra.InvalidTokenError):
        jwt_infra.decode_access_token(token + "tamper")
