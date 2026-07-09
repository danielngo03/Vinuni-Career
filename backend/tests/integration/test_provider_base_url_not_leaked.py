"""Provider base_url must never be returned by any API (even to superadmin).

CLAUDE.md / .claude/rules/ai.md: "API keys and base URLs are never returned at
any privilege level." base_url is WRITE-ONLY — the admin sets it but the
serializer only signals whether one is configured (``has_base_url``), never the
value. These tests pin that on every provider serialization path.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.gateway import provider_registry


async def _create(db_session, name: str) -> dict:
    return await provider_registry.create_provider(
        db_session,
        payload={
            "name": name,
            "base_url": "https://secret-endpoint.internal.example/v1",
            "api_key": "sk-secret-key-999",
            "provider_type": "openai_compatible",
        },
        created_by=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_create_provider_response_has_no_base_url(db_session) -> None:
    created = await _create(db_session, "leak-check-a")

    assert "base_url" not in created
    assert created["has_base_url"] is True
    # And never any secret material either.
    assert "api_key" not in created
    assert "api_key_ciphertext" not in created


@pytest.mark.asyncio
async def test_list_providers_never_includes_base_url(db_session) -> None:
    await _create(db_session, "leak-check-b")
    providers = await provider_registry.list_providers(db_session)

    assert providers
    for p in providers:
        assert "base_url" not in p, f"base_url leaked for provider {p.get('name')!r}"
        # The value must never appear anywhere in the serialized values.
        assert "secret-endpoint.internal.example" not in str(p)


@pytest.mark.asyncio
async def test_update_provider_response_has_no_base_url(db_session) -> None:
    created = await _create(db_session, "leak-check-c")
    updated = await provider_registry.update_provider(
        db_session,
        provider_id=uuid.UUID(created["id"]),
        payload={"base_url": "https://another-secret.internal/v2"},
    )

    assert "base_url" not in updated
    assert updated["has_base_url"] is True
