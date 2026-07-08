"""Provider API-key encryption: MultiFernet rotation, masking, prod fail-fast (P2.1)."""

from __future__ import annotations

import pytest
from app.ai.gateway import provider_key_crypto as crypto
from app.core.config import get_settings
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def _clean_settings_cache():
    """Rebuild settings from the (monkeypatched) env, and restore afterwards."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _use_keys(monkeypatch, value: str) -> None:
    monkeypatch.setenv("AI_PROVIDER_KEY_ENCRYPTION_KEYS", value)
    get_settings.cache_clear()


def test_encrypt_decrypt_round_trip(monkeypatch) -> None:
    _use_keys(monkeypatch, Fernet.generate_key().decode())
    ct = crypto.encrypt_provider_api_key("sk-secret-1234")
    assert ct != "sk-secret-1234"
    assert crypto.decrypt_provider_api_key(ct) == "sk-secret-1234"


def test_rotation_decrypts_old_ciphertext(monkeypatch) -> None:
    old = Fernet.generate_key().decode()
    _use_keys(monkeypatch, old)
    ct_old = crypto.encrypt_provider_api_key("sk-old")

    new = Fernet.generate_key().decode()
    _use_keys(monkeypatch, f"{new},{old}")  # newest first
    # Old ciphertext still decrypts after rotating a new key to the front.
    assert crypto.decrypt_provider_api_key(ct_old) == "sk-old"
    # New writes use the new primary key and round-trip.
    ct_new = crypto.encrypt_provider_api_key("sk-new")
    assert crypto.decrypt_provider_api_key(ct_new) == "sk-new"


def test_decrypt_garbage_returns_empty(monkeypatch) -> None:
    _use_keys(monkeypatch, Fernet.generate_key().decode())
    assert crypto.decrypt_provider_api_key("not-a-token") == ""
    assert crypto.decrypt_provider_api_key(None) == ""


def test_mask_last4() -> None:
    assert crypto.mask_last4("sk-or-v1-abcd1234") == "1234"
    assert crypto.mask_last4("ab") == "ab"
    assert crypto.mask_last4("") == ""


def test_key_version_stable_and_short(monkeypatch) -> None:
    _use_keys(monkeypatch, Fernet.generate_key().decode())
    v1 = crypto.current_key_version()
    v2 = crypto.current_key_version()
    assert v1 == v2
    assert 0 < len(v1) <= 16


def test_prod_fail_fast_without_key(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_KEY_ENCRYPTION_KEYS", "")
    monkeypatch.setenv("AI_PROVIDER_KEY_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        crypto.encrypt_provider_api_key("sk-x")


def test_local_derives_key_without_config(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_KEY_ENCRYPTION_KEYS", "")
    monkeypatch.setenv("AI_PROVIDER_KEY_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()
    ct = crypto.encrypt_provider_api_key("sk-local")
    assert crypto.decrypt_provider_api_key(ct) == "sk-local"
