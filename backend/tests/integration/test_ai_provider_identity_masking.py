"""Provider/model registry LIST endpoints must not leak real identity.

Findings 1 & 2 (leakage audit): ``GET /admin/ai-settings/providers`` and
``/model-aliases`` returned real provider names, ``base_url``, key last-4, and
model-revealing descriptions to any ``ai_settings:read`` holder — a grantable
university-staff permission, NOT superadmin. This verifies:

- an ``ai_settings:read`` holder without ``view_provider_identity`` gets masked
  vendor labels + status only;
- a holder WITH ``view_provider_identity`` (or superadmin) gets real identity —
  but ``base_url`` is NEVER returned at any privilege level.
"""

from __future__ import annotations

import pytest
from app.ai.gateway import provider_registry
from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import settings_service

from tests.org_utils import add_member, make_org_with_admin, principal_for


async def _seed(db_session) -> None:
    provider = AiProviderConfig(
        name="provider-a",
        provider_type="openai_compatible",
        base_url="https://secret-endpoint.example.com/v1",
        api_key_last4="9876",
        description="Real vendor — GPT-4o, GPT-4o-mini",
        is_active=True,
    )
    db_session.add(provider)
    await db_session.flush()
    alias = AiModelAlias(
        alias_name="chat_default",
        model_id="gpt-4o",
        provider_id=provider.id,
        task_families="chat",
        description="GPT-4o direct",
        is_active=True,
    )
    db_session.add(alias)
    await db_session.commit()


@pytest.mark.asyncio
async def test_provider_list_masks_identity_for_read_only_holder(db_session) -> None:
    await _seed(db_session)
    data = await provider_registry.list_providers(db_session, reveal_identity=False)
    p = data[0]
    # Real identity is hidden.
    assert "name" not in p
    assert "provider_type" not in p
    assert "description" not in p
    assert "api_key_last4" not in p
    # base_url is NEVER present — at any level.
    assert "base_url" not in p
    # A curated, non-identifying label + status is still useful.
    assert p["vendor_label"]
    assert "has_api_key" in p


@pytest.mark.asyncio
async def test_provider_list_reveals_identity_but_never_base_url(db_session) -> None:
    await _seed(db_session)
    data = await provider_registry.list_providers(db_session, reveal_identity=True)
    p = data[0]
    assert p["name"] == "provider-a"
    assert p["api_key_last4"] == "9876"
    # Even with full reveal, base_url must never be returned.
    assert "base_url" not in p


@pytest.mark.asyncio
async def test_alias_list_masks_provider_identity_for_read_only(db_session) -> None:
    await _seed(db_session)
    data = await provider_registry.list_aliases(db_session, reveal_identity=False)
    a = data[0]
    assert a["alias_name"] == "chat_default"  # internal handle, safe
    assert "provider_name" not in a
    assert "fallback_provider_names" not in a
    assert "description" not in a
    assert "model_id" not in a  # never exposed


@pytest.mark.asyncio
async def test_alias_list_reveals_provider_name_when_permitted(db_session) -> None:
    await _seed(db_session)
    data = await provider_registry.list_aliases(db_session, reveal_identity=True)
    a = data[0]
    assert a["provider_name"] == "provider-a"
    assert "model_id" not in a  # still never exposed on GET


@pytest.mark.asyncio
async def test_identity_permission_gating(db_session) -> None:
    user, org, admin = await make_org_with_admin(db_session, org_type="university")
    _reader_user, _m1, reader = await add_member(
        db_session, org=org, permissions=[("ai_settings", "read")]
    )
    _priv_user, _m2, privileged = await add_member(
        db_session,
        org=org,
        permissions=[("ai_settings", "read"), ("ai_settings", "view_provider_identity")],
    )
    superadmin = await principal_for(db_session, user=user, org_id=org.id, superadmin=True)

    # Ordinary ai_settings:read university staff must NOT see raw identity.
    assert settings_service.can_view_provider_identity(reader) is False
    assert settings_service.can_view_provider_identity(privileged) is True
    assert settings_service.can_view_provider_identity(superadmin) is True
