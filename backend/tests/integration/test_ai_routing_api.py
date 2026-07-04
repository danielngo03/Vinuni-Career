from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.gateway.provider_models import AiModelAlias, AiProviderConfig
from app.main import app
from tests.org_utils import make_org_with_admin


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.mark.asyncio
async def test_create_and_activate_routing_graph_via_api(db_session, client) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    provider = AiProviderConfig(name="provider-a", provider_type="openai_compatible", base_url="https://a.example.com", is_active=True)
    db_session.add(provider)
    await db_session.flush()
    # Seed a model alias for "chat" tied to this provider so the routing-canvas
    # read view (which surfaces providers backing an active alias for the task
    # family) has something to show — mirrors test_ai_routing_read_service.py.
    alias = AiModelAlias(
        alias_name="chat_cheap", model_id="chat-cheap-v1", provider_id=provider.id,
        task_families="chat", is_active=True,
    )
    db_session.add(alias)
    await db_session.commit()

    login = await client.post(
        "/auth/login",
        json={"email": _user.email, "password": "Sup3rSecret!"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]

    # A brand-new user's primary identity is the default student persona, not
    # the university-admin identity created by make_org_with_admin — switch to
    # the org-scoped identity so the ai_settings:manage/read grants apply.
    identities = await client.get(
        "/auth/identity", headers={"Authorization": f"Bearer {token}"}
    )
    assert identities.status_code == 200
    org_identity = next(
        item for item in identities.json()["data"] if item["org_id"] == str(org.id)
    )
    switch_resp = await client.post(
        "/auth/identity",
        headers={"Authorization": f"Bearer {token}"},
        json={"identity_id": org_identity["id"]},
    )
    assert switch_resp.status_code == 200
    token = switch_resp.json()["data"]["access_token"]

    create_resp = await client.post(
        "/admin/ai-settings/routing-graphs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "task_family": "chat",
            "graph": {"nodes": [{"id": "p1", "type": "provider", "data": {"provider_id": str(provider.id), "order": 0}}], "edges": []},
        },
    )
    assert create_resp.status_code == 200
    graph_id = create_resp.json()["data"]["id"]
    assert graph_id

    canvas_resp = await client.get(
        "/admin/ai-settings/routing-canvas/chat",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert canvas_resp.status_code == 200
    assert "vendor_label" in canvas_resp.json()["data"]["providers"][0]
