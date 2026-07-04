"""Encryption-at-rest for TOTP shared secrets (Fernet / AES-128-CBC + HMAC).

TOTP secrets are symmetric credentials: anyone holding the plaintext can mint
valid one-time codes. They must therefore be encrypted at rest before 2FA is
advertised as active (``docs/SECURITY_PRIVACY.md`` §8, ``.claude/rules/backend.md``).

Key sourcing (``docs/ENVIRONMENT.md``): the Fernet key comes from
``TOTP_ENCRYPTION_KEY`` (urlsafe base64, 32 bytes). When unset — local dev only —
it is derived deterministically from ``JWT_SECRET_KEY`` so the suite/dev runs
without an extra secret, while production sets a real, rotated key.

Decryption is legacy-tolerant: pre-existing dev rows stored the raw base32 secret
in plaintext. :func:`decrypt_totp_secret` returns ``(secret, was_plaintext)`` so
callers can re-encrypt opportunistically instead of crashing.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    configured = get_settings().totp_encryption_key.strip()
    if configured:
        key = configured.encode()
    else:
        # Local-dev fallback: derive a stable 32-byte key from the JWT secret.
        digest = hashlib.sha256(
            f"totp-secret-key:{get_settings().jwt_secret_key}".encode()
        ).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_totp_secret(plaintext_secret: str) -> str:
    """Return the Fernet ciphertext (urlsafe str) for a base32 TOTP secret."""

    return _fernet().encrypt(plaintext_secret.encode()).decode()


def decrypt_totp_secret(stored_value: str) -> tuple[str, bool]:
    """Return ``(plaintext_secret, was_plaintext)``.

    A valid Fernet token decrypts normally. Anything else is treated as a legacy
    plaintext secret (``was_plaintext=True``) so callers can re-encrypt it without
    crashing on dev data written before encryption was introduced.
    """

    try:
        return _fernet().decrypt(stored_value.encode()).decode(), False
    except (InvalidToken, ValueError):
        return stored_value, True
