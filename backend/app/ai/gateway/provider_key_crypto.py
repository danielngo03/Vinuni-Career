"""Encryption-at-rest for admin-managed AI provider API keys.

Provider keys are symmetric credentials and must never be stored or returned in
plaintext. Admin APIs accept a plaintext key only on create/update, encrypt it
immediately, and responses expose presence + a masked last-4 hint only.

Key management (large-system posture):

- ``AI_PROVIDER_KEY_ENCRYPTION_KEYS`` is a comma-separated list of Fernet keys,
  **newest key first**. We build a :class:`MultiFernet`: new ciphertexts are
  written with the first (newest) key, decryption tries every key. This gives
  **zero-downtime key rotation** — prepend a fresh key, re-encrypt stored rows
  in the background, then drop the retired key.
- Production (``app_env != local``) MUST configure a real key; otherwise
  :func:`_keys` raises so the misconfiguration fails loudly instead of silently
  falling back to a secret derived from the JWT signing key.
- Local dev with no configured key derives one from ``jwt_secret_key`` (with a
  one-time warning) purely for developer convenience.

``current_key_version`` returns a short, non-secret fingerprint of the primary
key so ``ai_provider_configs.key_version`` can record which key generation
encrypted each row (used by the rotation routine to find stale rows). It never
reveals key material.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings

logger = logging.getLogger("ai.provider_key_crypto")

# Values that mean "no real key configured".
_PLACEHOLDER_KEYS = frozenset({"", "replace-with-fernet-key", "replace-with-local-secret"})

_warned_local_derivation = False


def _configured_keys() -> list[str]:
    """Return admin-configured Fernet keys, newest first (plural CSV preferred)."""

    s = get_settings()
    plural = (getattr(s, "ai_provider_key_encryption_keys", "") or "").strip()
    if plural:
        keys = [k.strip() for k in plural.split(",")]
        return [k for k in keys if k and k not in _PLACEHOLDER_KEYS]
    singular = (s.ai_provider_key_encryption_key or "").strip()
    if singular and singular not in _PLACEHOLDER_KEYS:
        return [singular]
    return []


def _derived_local_key() -> str:
    """Deterministic dev-only key derived from the JWT secret (never for prod)."""

    digest = hashlib.sha256(
        f"ai-provider-key:{get_settings().jwt_secret_key}".encode()
    ).digest()
    return base64.urlsafe_b64encode(digest).decode()


def _keys() -> list[str]:
    """Resolve the active Fernet key list, newest first.

    Raises ``RuntimeError`` in non-local environments when no key is configured,
    so a production deployment can never silently encrypt provider secrets under
    a key derived from the JWT signing secret.
    """

    keys = _configured_keys()
    if keys:
        return keys
    if get_settings().app_env.lower() != "local":
        raise RuntimeError(
            "AI_PROVIDER_KEY_ENCRYPTION_KEYS is required outside local dev to "
            "encrypt admin AI provider API keys. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    global _warned_local_derivation
    if not _warned_local_derivation:
        logger.warning(
            "ai_provider_key_encryption_derived_from_jwt_secret",
            extra={"hint": "set AI_PROVIDER_KEY_ENCRYPTION_KEYS for production"},
        )
        _warned_local_derivation = True
    return [_derived_local_key()]


def _multifernet() -> MultiFernet:
    return MultiFernet([Fernet(k.encode()) for k in _keys()])


def encrypt_provider_api_key(plaintext: str) -> str:
    """Return MultiFernet ciphertext (written with the newest key)."""

    return _multifernet().encrypt(plaintext.encode()).decode()


def decrypt_provider_api_key(ciphertext: str | None) -> str:
    """Return the plaintext provider key, or an empty string on invalid input.

    Tries every configured key so ciphertexts written under a now-retired key
    keep decrypting until the rotation routine re-encrypts them.
    """

    if not ciphertext:
        return ""
    try:
        return _multifernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def mask_last4(plaintext: str) -> str:
    """Return the last 4 characters of a key for a safe UI hint (never the key)."""

    if not plaintext:
        return ""
    return plaintext[-4:]


def current_key_version() -> str:
    """Short, non-secret fingerprint of the PRIMARY (newest) key.

    Stored on ``ai_provider_configs.key_version`` so the rotation routine can
    identify rows still encrypted under an older key. Never reveals key material.
    """

    primary = _keys()[0]
    return hashlib.sha256(primary.encode()).hexdigest()[:12]
