"""HTTP-route-level tests for ``GET /jobs/saved`` and ``/jobs/alerts``.

Regression coverage for two shipping-blocker bugs:

1. **Route shadow.** ``GET /jobs/saved`` and ``GET /jobs/alerts`` were declared
   AFTER the dynamic ``GET /jobs/{job_id}`` on the same router, so Starlette
   matched ``/jobs/saved`` against ``/{job_id}`` (``job_id="saved"``) and the
   ``uuid.UUID`` path param 422'd — both list pages were dead end-to-end. The
   pre-existing suite only exercised ``saved_jobs_service`` / ``job_alert_service``
   directly, never the HTTP route, which is why the shadow slipped.

2. **Silent data loss.** ``job_alert_service.create_alert`` / ``delete_alert``
   only ``flush()``-ed; the request-scoped session never commits on success, so
   the alert was discarded when the session closed. These tests create/delete an
   alert and re-read it in a SEPARATE request to prove it persisted.
"""

from __future__ import annotations

import uuid

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient

from tests.documents_utils import make_student


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


async def _student_token(client, db_session) -> str:
    """Register a verified student and log in over HTTP for a real bearer token."""
    user, _ = await make_student(db_session)
    resp = await client.post(
        "/auth/login", json={"email": user.email, "password": "Sup3rSecret!"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


async def test_get_saved_jobs_route_is_not_shadowed(client, db_session) -> None:
    token = await _student_token(client, db_session)
    resp = await client.get("/jobs/saved", headers={"Authorization": f"Bearer {token}"})
    # Before the fix this was 422 (matched GET /jobs/{job_id}, job_id="saved").
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


async def test_get_job_alerts_route_is_not_shadowed(client, db_session) -> None:
    token = await _student_token(client, db_session)
    resp = await client.get("/jobs/alerts", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == []


async def test_job_alert_create_persists_and_is_listed(client, db_session) -> None:
    token = await _student_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/jobs/alerts",
        headers=headers,
        json={"name": "Python internships in Hanoi", "keywords": "python"},
    )
    assert created.status_code == 201, created.text

    # A SEPARATE request (fresh session) must see the alert — proves it committed.
    listed = await client.get("/jobs/alerts", headers=headers)
    assert listed.status_code == 200, listed.text
    names = [a["name"] for a in listed.json()["data"]]
    assert "Python internships in Hanoi" in names


async def test_job_alert_delete_persists(client, db_session) -> None:
    token = await _student_token(client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    created = await client.post(
        "/jobs/alerts", headers=headers, json={"name": "To be deleted"}
    )
    assert created.status_code == 201, created.text
    alert_id = created.json()["data"]["id"]

    deleted = await client.delete(f"/jobs/alerts/{alert_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    listed = await client.get("/jobs/alerts", headers=headers)
    names = [a["name"] for a in listed.json()["data"]]
    assert "To be deleted" not in names


async def test_dynamic_job_detail_route_still_resolves(client, db_session) -> None:
    """Regression: the dynamic GET /jobs/{job_id} still works (random UUID → 404)."""
    token = await _student_token(client, db_session)
    resp = await client.get(
        f"/jobs/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404, resp.text
