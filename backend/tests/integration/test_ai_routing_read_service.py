from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import routing_read_service
from app.shared.audit import AuditLog
from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin


async def _seed_provider_and_alias(db_session):
    provider = AiProviderConfig(name="provider-a", provider_type="openai_compatible", base_url="https://a.example.com", is_active=True)
    db_session.add(provider)
    await db_session.flush()
    alias = AiModelAlias(alias_name="chat_cheap", model_id="chat-cheap-v1", provider_id=provider.id, task_families="chat", is_active=True)
    db_session.add(alias)
    await db_session.commit()
    return provider, alias


@pytest.mark.asyncio
async def test_read_only_holder_sees_curated_labels_not_raw_identity(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, reader = await add_member(db_session, org=org, permissions=[("ai_settings", "read")])
    await _seed_provider_and_alias(db_session)

    view = await routing_read_service.get_routing_canvas_view(db_session, principal=reader, task_family="chat", ctx=CTX)

    provider_entry = view["providers"][0]
    assert provider_entry["vendor_label"]
    assert provider_entry["provider_internal"] is None
    assert provider_entry["model_id"] is None


@pytest.mark.asyncio
async def test_holder_with_view_provider_identity_sees_raw_identity_and_is_audited(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, privileged = await add_member(
        db_session, org=org, permissions=[("ai_settings", "read"), ("ai_settings", "view_provider_identity")]
    )
    await _seed_provider_and_alias(db_session)

    view = await routing_read_service.get_routing_canvas_view(db_session, principal=privileged, task_family="chat", ctx=CTX)

    provider_entry = view["providers"][0]
    assert provider_entry["provider_internal"] == "provider-a"
    assert provider_entry["model_id"] == "chat-cheap-v1"

    rows = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "ai_settings.provider_identity_viewed"))
    ).scalars().all()
    assert len(rows) == 1
