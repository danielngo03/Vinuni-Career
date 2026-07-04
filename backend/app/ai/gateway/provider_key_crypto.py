"""Encryption-at-rest for admin-managed AI provider API keys.

Provider keys are symmetric credentials and must never be stored or returned in
plaintext. Admin APIs accept a plaintext key only on create/update, encrypt it
immediately, and responses expose presence only (``has_api_key``).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    configured = get_settings().ai_provider_key_encryption_key.strip()
    if configured and configured != "replace-with-fernet-key":
        key = configured.encode()
    else:
        digest = hashlib.sha256(
            f"ai-provider-key:{get_settings().jwt_secret_key}".encode()
        ).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_provider_api_key(plaintext: str) -> str:
    """Return Fernet ciphertext for a provider API key."""

    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_provider_api_key(ciphertext: str | None) -> str:
    """Return the plaintext provider key or an empty string on invalid input."""

    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return ""
