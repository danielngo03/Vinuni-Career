"""Provider create/update stores last-4 hint + key_version, never plaintext (P2.3)."""

from __future__ import annotations

import uuid

import pytest
from app.ai.gateway import provider_registry


@pytest.mark.asyncio
async def test_create_provider_stores_last4_and_version(db_session) -> None:
    data = await provider_registry.create_provider(
        db_session,
        payload={
            "name": "custom-x",
            "base_url": "https://x.example/v1",
            "api_key": "sk-abcd-9876",
        },
    )
    assert data["has_api_key"] is True
    assert data["api_key_last4"] == "9876"
    assert data["key_version"]  # non-empty fingerprint
    # Plaintext must never appear in the serialized response.
    assert "api_key" not in data
    assert "sk-abcd-9876" not in str(data)


@pytest.mark.asyncio
async def test_clear_key_resets_hint(db_session) -> None:
    created = await provider_registry.create_provider(
        db_session,
        payload={
            "name": "custom-y",
            "base_url": "https://y.example/v1",
            "api_key": "sk-keep-4321",
        },
    )
    updated = await provider_registry.update_provider(
        db_session,
        uuid.UUID(created["id"]),
        payload={"clear_api_key": True},
    )
    assert updated["has_api_key"] is False  # custom name, no env fallback
    assert not updated["api_key_last4"]


@pytest.mark.asyncio
async def test_update_rotates_hint(db_session) -> None:
    created = await provider_registry.create_provider(
        db_session,
        payload={
            "name": "custom-z",
            "base_url": "https://z.example/v1",
            "api_key": "sk-first-1111",
        },
    )
    updated = await provider_registry.update_provider(
        db_session,
        uuid.UUID(created["id"]),
        payload={"api_key": "sk-second-2222"},
    )
    assert updated["api_key_last4"] == "2222"
