"""Encryption-at-rest for interview meeting links (Fernet / AES-128-CBC + HMAC).

A meeting link (Zoom/Meet/Teams URL) is a sensitive attendee-only artifact: it must
be encrypted at rest and revealed only to attendees (the candidate + assigned
interviewers) — ``docs/SECURITY_PRIVACY.md`` / ``docs/DATA_MODEL.md`` §9, ADR-0006
§4. This mirrors the TOTP-secret at-rest pattern
(:mod:`app.modules.auth.infrastructure.totp_crypto`).

Key sourcing (``docs/ENVIRONMENT.md``): the Fernet key comes from
``TOTP_ENCRYPTION_KEY`` (the platform's at-rest field key, urlsafe base64, 32
bytes); when unset — local dev only — it is derived deterministically from
``JWT_SECRET_KEY`` with a distinct purpose label so the suite/dev runs without an
extra secret while production sets a real, rotated key.

Decryption is legacy-tolerant: a value that is not a valid Fernet token is returned
as-is (treated as a pre-existing/plaintext link) so callers never crash on dev data.
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
        # Local-dev fallback: derive a stable 32-byte key from the JWT secret with a
        # purpose label distinct from the TOTP derivation.
        digest = hashlib.sha256(
            f"interview-meeting-link:{get_settings().jwt_secret_key}".encode()
        ).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_meeting_link(plaintext: str) -> str:
    """Return the Fernet ciphertext (urlsafe str) for a meeting-link URL."""

    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_meeting_link(stored_value: str | None) -> str | None:
    """Return the plaintext meeting link, or ``None`` when nothing is stored.

    A value that fails to decrypt as a Fernet token is returned unchanged (treated
    as a legacy/plaintext link) so dev data written before encryption never crashes.
    """

    if stored_value is None:
        return None
    try:
        return _fernet().decrypt(stored_value.encode()).decode()
    except (InvalidToken, ValueError):
        return stored_value
