from __future__ import annotations

import pytest

from app.modules.ai_settings.application import routing_service
from app.modules.ai_settings.application.routing_errors import InvalidRoutingGraphError
from app.shared.exceptions import PermissionDeniedError
from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin

VALID_GRAPH = {
    "nodes": [
        {"id": "p1", "type": "provider", "data": {"provider_id": "11111111-1111-1111-1111-111111111111", "order": 0}},
    ],
    "edges": [],
}


@pytest.mark.asyncio
async def test_university_admin_can_create_and_read_draft_graph(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    graph = await routing_service.create_draft_graph(
        db_session, principal=admin, task_family="chat", graph=VALID_GRAPH, ctx=CTX,
    )

    assert graph.status == "DRAFT"
    fetched = await routing_service.get_graph(db_session, principal=admin, graph_id=graph.id)
    assert fetched.id == graph.id


@pytest.mark.asyncio
async def test_create_graph_rejects_invalid_structure(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    with pytest.raises(InvalidRoutingGraphError):
        await routing_service.create_draft_graph(
            db_session, principal=admin, task_family="chat", graph={"nodes": [], "edges": []}, ctx=CTX,
        )


@pytest.mark.asyncio
async def test_member_without_ai_settings_manage_is_denied(db_session) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")
    _member_user, _membership, member = await add_member(
        db_session, org=org, permissions=[("ai_settings", "read")]
    )

    with pytest.raises(PermissionDeniedError):
        await routing_service.create_draft_graph(
            db_session, principal=member, task_family="chat", graph=VALID_GRAPH, ctx=CTX,
        )
