"""Opaque secret tokens (refresh + email verification) and their hashing.

Raw tokens are returned to the client exactly once; only a salted SHA-256 hash is
persisted (``docs/SECURITY_PRIVACY.md``). The salt is the JWT secret so hashes are
not portable across deployments.
"""

from __future__ import annotations

import hashlib
import secrets

from app.core.config import get_settings


def generate_token(nbytes: int = 32) -> str:
    """Return a URL-safe, high-entropy opaque token."""

    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Return a salted SHA-256 hex digest of an opaque token."""

    salt = get_settings().jwt_secret_key
    return hashlib.sha256(f"{salt}:token:{token}".encode()).hexdigest()


def generate_otp() -> str:
    """Return a 6-digit numeric OTP code."""

    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    """Return a salted SHA-256 hex digest of an OTP code. Plain code never persisted."""

    salt = get_settings().jwt_secret_key
    return hashlib.sha256(f"{salt}:otp:{code}".encode()).hexdigest()
