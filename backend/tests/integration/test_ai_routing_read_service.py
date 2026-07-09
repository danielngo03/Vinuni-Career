from __future__ import annotations

import pytest
from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import routing_read_service
from app.shared.audit import AuditLog
from app.shared.exceptions import PermissionDeniedError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


async def _seed_provider_and_alias(db_session):
    provider = AiProviderConfig(
        name="provider-a",
        provider_type="openai_compatible",
        base_url="https://a.example.com",
        is_active=True,
    )
    db_session.add(provider)
    await db_session.flush()
    alias = AiModelAlias(
        alias_name="chat_cheap",
        model_id="chat-cheap-v1",
        provider_id=provider.id,
        task_families="chat",
        is_active=True,
    )
    db_session.add(alias)
    await db_session.commit()
    return provider, alias


@pytest.mark.asyncio
async def test_university_reader_cannot_access_routing_canvas(db_session) -> None:
    _user, _org, admin = await make_org_with_admin(db_session, org_type="university")
    await _seed_provider_and_alias(db_session)

    with pytest.raises(PermissionDeniedError):
        await routing_read_service.get_routing_canvas_view(
            db_session, principal=admin, task_family="chat", ctx=CTX
        )


@pytest.mark.asyncio
async def test_superadmin_sees_raw_identity_and_is_audited(
    db_session,
) -> None:
    _user, _org, admin = await make_org_with_admin(db_session, org_type="university")
    admin.is_superadmin = True
    await _seed_provider_and_alias(db_session)

    view = await routing_read_service.get_routing_canvas_view(
        db_session, principal=admin, task_family="chat", ctx=CTX
    )

    provider_entry = view["providers"][0]
    assert provider_entry["provider_internal"] == "provider-a"
    assert provider_entry["model_id"] == "chat-cheap-v1"

    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "ai_settings.provider_identity_viewed")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
