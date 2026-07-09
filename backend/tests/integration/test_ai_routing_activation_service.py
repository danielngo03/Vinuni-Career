from __future__ import annotations

import pytest
from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.modules.ai_settings.application import routing_activation_service, routing_service
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


async def _seed_two_providers_and_alias(db_session):
    provider_a = AiProviderConfig(
        name="provider-a",
        provider_type="openai_compatible",
        base_url="https://a.example.com",
        is_active=True,
    )
    provider_b = AiProviderConfig(
        name="provider-b",
        provider_type="openai_compatible",
        base_url="https://b.example.com",
        is_active=True,
    )
    db_session.add_all([provider_a, provider_b])
    await db_session.flush()

    alias = AiModelAlias(
        alias_name="chat_cheap",
        model_id="chat-cheap-v1",
        provider_id=provider_a.id,
        task_families="chat",
        is_active=True,
    )
    db_session.add(alias)
    await db_session.flush()
    await db_session.commit()
    return provider_a, provider_b, alias


@pytest.mark.asyncio
async def test_activate_compiles_graph_into_model_alias(db_session) -> None:
    _user, _org, admin = await make_org_with_admin(db_session, org_type="university")
    admin.is_superadmin = True
    provider_a, provider_b, alias = await _seed_two_providers_and_alias(db_session)

    # AiSettings singleton must point chat_model_alias at "chat_cheap" for the
    # compile step to find it — reuse the settings resolver's get_or_create.
    from app.modules.ai_settings.infrastructure import repository as ai_settings_repo

    settings_row = await ai_settings_repo.get_or_create_platform(db_session)
    settings_row.chat_model_alias = "chat_cheap"
    await db_session.commit()

    graph = await routing_service.create_draft_graph(
        db_session,
        principal=admin,
        task_family="chat",
        graph={
            "nodes": [
                {
                    "id": "p1",
                    "type": "provider",
                    "data": {"provider_id": str(provider_b.id), "order": 0},
                },
                {
                    "id": "p2",
                    "type": "provider",
                    "data": {"provider_id": str(provider_a.id), "order": 1},
                },
            ],
            "edges": [{"source": "p1", "target": "p2", "kind": "fallback"}],
        },
        ctx=CTX,
    )

    activated = await routing_activation_service.activate_routing_graph(
        db_session,
        principal=admin,
        graph_id=graph.id,
        ctx=CTX,
    )

    assert activated.status == "ACTIVE"
    refreshed_alias = await db_session.get(AiModelAlias, alias.id)
    assert refreshed_alias.provider_id == provider_b.id
    assert refreshed_alias.fallback_provider_names == "provider-a"


@pytest.mark.asyncio
async def test_activation_writes_activation_audit_row(db_session) -> None:
    _user, _org, admin = await make_org_with_admin(db_session, org_type="university")
    admin.is_superadmin = True
    provider_a, _provider_b, _alias = await _seed_two_providers_and_alias(db_session)

    from app.modules.ai_settings.infrastructure import repository as ai_settings_repo

    settings_row = await ai_settings_repo.get_or_create_platform(db_session)
    settings_row.chat_model_alias = "chat_cheap"
    await db_session.commit()

    graph = await routing_service.create_draft_graph(
        db_session,
        principal=admin,
        task_family="chat",
        graph={
            "nodes": [
                {
                    "id": "p1",
                    "type": "provider",
                    "data": {"provider_id": str(provider_a.id), "order": 0},
                }
            ],
            "edges": [],
        },
        ctx=CTX,
    )
    await routing_activation_service.activate_routing_graph(
        db_session, principal=admin, graph_id=graph.id, ctx=CTX
    )

    from app.modules.ai_settings.domain.routing_models import AiRoutingGraphActivation

    rows = (
        (
            await db_session.execute(
                select(AiRoutingGraphActivation).where(
                    AiRoutingGraphActivation.graph_id == graph.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].graph_version == graph.version
