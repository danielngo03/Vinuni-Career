"""Encryption-at-rest for offer salary figures (Fernet / AES-128-CBC + HMAC).

``offers.salary_amount`` is "recruiter + student only" PII (``docs/DATA_MODEL.md``
§17, ADR-0007 §7): it must be encrypted at rest and decrypted only when rendering a
**recruiter** or the **owning student** surface — never logged, never in a
notification/email body, never in the board glance, never in an analytics/event
payload. This mirrors the interview meeting-link at-rest pattern
(:mod:`app.modules.recruitment.infrastructure.meeting_link_crypto`).

Key sourcing (``docs/ENVIRONMENT.md``): the Fernet key comes from
``TOTP_ENCRYPTION_KEY`` (the platform's at-rest field key, urlsafe base64, 32
bytes); when unset — local dev only — it is derived deterministically from
``JWT_SECRET_KEY`` with a purpose label distinct from the TOTP / meeting-link
derivations so each at-rest field uses an independent key.

Decryption is legacy-tolerant: a value that is not a valid Fernet token is returned
as-is so callers never crash on dev/seed data.
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
        # purpose label distinct from the TOTP / meeting-link derivations.
        digest = hashlib.sha256(f"offer-salary:{get_settings().jwt_secret_key}".encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_salary(plaintext: str) -> str:
    """Return the Fernet ciphertext (urlsafe str) for a salary figure string."""

    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_salary(stored_value: str | None) -> str | None:
    """Return the plaintext salary string, or ``None`` when nothing is stored.

    A value that fails to decrypt as a Fernet token is returned unchanged (treated
    as legacy/plaintext data) so dev data written before encryption never crashes.
    """

    if stored_value is None:
        return None
    try:
        return _fernet().decrypt(stored_value.encode()).decode()
    except (InvalidToken, ValueError):
        return stored_value
