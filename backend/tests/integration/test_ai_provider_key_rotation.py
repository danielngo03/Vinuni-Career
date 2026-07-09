"""Rotation routine re-encrypts stored keys under the newest key (P2.4)."""

from __future__ import annotations

import pytest
from app.ai.gateway import provider_registry
from app.ai.gateway.provider_key_crypto import decrypt_provider_api_key
from app.ai.gateway.provider_models import AiProviderConfig
from app.core.config import get_settings
from cryptography.fernet import Fernet
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _clean_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_reencrypt_rotates_key_version(db_session, monkeypatch) -> None:
    key_a = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_PROVIDER_KEY_ENCRYPTION_KEYS", key_a)
    get_settings.cache_clear()

    created = await provider_registry.create_provider(
        db_session,
        payload={"name": "rot-x", "base_url": "https://x/v1", "api_key": "sk-rotate-7777"},
    )
    version_a = created["key_version"]
    old_cipher = (
        await db_session.execute(
            select(AiProviderConfig.api_key_ciphertext).where(AiProviderConfig.name == "rot-x")
        )
    ).scalar_one()

    # Rotate: prepend a new key (newest first) and re-encrypt.
    key_b = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_PROVIDER_KEY_ENCRYPTION_KEYS", f"{key_b},{key_a}")
    get_settings.cache_clear()

    result = await provider_registry.reencrypt_all_provider_keys(db_session)
    assert result["rotated"] >= 1
    assert result["key_version"] != version_a

    row = (
        await db_session.execute(select(AiProviderConfig).where(AiProviderConfig.name == "rot-x"))
    ).scalar_one()
    assert row.key_version == result["key_version"]
    assert row.api_key_ciphertext != old_cipher  # re-wrapped under the new key
    assert row.api_key_last4 == "7777"
    assert decrypt_provider_api_key(row.api_key_ciphertext) == "sk-rotate-7777"


@pytest.mark.asyncio
async def test_reencrypt_is_idempotent(db_session, monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AI_PROVIDER_KEY_ENCRYPTION_KEYS", key)
    get_settings.cache_clear()
    await provider_registry.create_provider(
        db_session,
        payload={"name": "rot-y", "base_url": "https://y/v1", "api_key": "sk-y-1234"},
    )
    first = await provider_registry.reencrypt_all_provider_keys(db_session)
    # Already at the current version → second pass rotates nothing.
    second = await provider_registry.reencrypt_all_provider_keys(db_session)
    assert second["rotated"] == 0
    assert second["skipped"] >= 1
    assert first["key_version"] == second["key_version"]
