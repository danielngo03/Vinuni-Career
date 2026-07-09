from __future__ import annotations

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient

from tests.org_utils import make_org_with_admin


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.mark.asyncio
async def test_create_and_activate_flow_via_api(db_session, client) -> None:
    _user, org, admin = await make_org_with_admin(db_session, org_type="university")

    login = await client.post(
        "/auth/login",
        json={"email": _user.email, "password": "Sup3rSecret!"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]

    # A brand-new user's primary identity is the default student persona, not
    # the university-admin identity created by make_org_with_admin — switch to
    # the org-scoped identity so the workflow:create/activate grants apply.
    identities = await client.get("/auth/identity", headers={"Authorization": f"Bearer {token}"})
    assert identities.status_code == 200
    org_identity = next(item for item in identities.json()["data"] if item["org_id"] == str(org.id))
    switch_resp = await client.post(
        "/auth/identity",
        headers={"Authorization": f"Bearer {token}"},
        json={"identity_id": org_identity["id"]},
    )
    assert switch_resp.status_code == 200
    token = switch_resp.json()["data"]["access_token"]

    create_resp = await client.post(
        "/workflows",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Student verification",
            "description": None,
            "trigger_type": "system.student_registered",
            "graph": {
                "nodes": [
                    {
                        "id": "n1",
                        "type": "trigger",
                        "data": {"trigger_type": "system.student_registered"},
                    },
                    {"id": "n2", "type": "end", "data": {}},
                ],
                "edges": [{"source": "n1", "target": "n2"}],
            },
        },
    )
    assert create_resp.status_code == 200
    flow_id = create_resp.json()["data"]["id"]

    activate_resp = await client.post(
        f"/workflows/{flow_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert activate_resp.status_code == 200
    assert activate_resp.json()["data"]["status"] == "ACTIVE"
