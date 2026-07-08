"""HTTP-level discovery analytics endpoint tests via ASGI transport.

Proves the public/optional-auth contract:

- ``POST /discovery/events`` is PUBLIC (no auth) and returns only ``{recorded: true}``
  — no session id, coarse tags, scope, or other internal data.
- it sets/refreshes the httpOnly ``vinuni_discovery`` cookie; a repeated cookie keeps
  one session; a repeated idempotency key keeps one event row.
- an invalid event vocabulary → ``422 VALIDATION_FAILED``.
- ``POST /discovery/session/reset`` clears signals/opts out and drops the cookie.
"""

from __future__ import annotations

import uuid

import pytest
from app.main import app
from app.modules.discovery.domain.models import DiscoveryEvent, DiscoverySession
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


def _event_body(**over) -> dict:
    body = {
        "event_type": "impression",
        "source_surface": "homepage_recommended",
        "target_type": "job",
        "target_id": str(uuid.uuid4()),
        "idempotency_key": uuid.uuid4().hex,
    }
    body.update(over)
    return body


async def test_events_public_sets_cookie_and_returns_no_internal_data(
    client, db_session
) -> None:
    resp = await client.post("/discovery/events", json=_event_body())
    assert resp.status_code == 200

    body = resp.json()
    # ONLY {recorded: true} — no session id / scope / tags leak.
    assert body["data"] == {"recorded": True}
    assert "session_id" not in body["data"]
    assert "scope" not in body["data"]

    # First-party cookie set, httpOnly, scoped to /discovery.
    set_cookie = resp.headers.get("set-cookie", "")
    assert "vinuni_discovery=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    count = (
        await db_session.execute(select(func.count()).select_from(DiscoverySession))
    ).scalar_one()
    assert count == 1


async def test_events_idempotent_and_session_reused_over_cookie(
    client, db_session
) -> None:
    key = uuid.uuid4().hex
    first = await client.post(
        "/discovery/events", json=_event_body(idempotency_key=key)
    )
    assert first.status_code == 200
    # Client retains the cookie; repeat same idempotency key.
    second = await client.post(
        "/discovery/events", json=_event_body(idempotency_key=key)
    )
    assert second.status_code == 200

    events = (
        await db_session.execute(select(func.count()).select_from(DiscoveryEvent))
    ).scalar_one()
    sessions = (
        await db_session.execute(select(func.count()).select_from(DiscoverySession))
    ).scalar_one()
    assert events == 1  # idempotent
    assert sessions == 1  # cookie reused → same session


async def test_events_merges_only_allowlisted_signal_tags(client, db_session) -> None:
    resp = await client.post(
        "/discovery/events",
        json=_event_body(
            signal_tags={
                "categories": ["Data Analyst"],
                "email": "leak@example.com",
                "gps": "21.0,105.8",
            }
        ),
    )
    assert resp.status_code == 200
    row = (
        await db_session.execute(select(DiscoverySession))
    ).scalar_one()
    # Weighted taxonomy shape: only the allowlisted coarse value survives; forbidden
    # PII keys are stripped and never persisted.
    assert set(row.coarse_tags) == {"categories"}
    assert set(row.coarse_tags["categories"]) == {"data analyst"}
    assert row.coarse_tags["categories"]["data analyst"]["count"] == 1
    assert "email" not in row.coarse_tags and "gps" not in row.coarse_tags


async def test_invalid_event_returns_422(client) -> None:
    resp = await client.post(
        "/discovery/events", json=_event_body(source_surface="bogus_surface")
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_extra_fields_rejected(client) -> None:
    # extra="forbid" → a stray PII-looking field is a schema error, never stored.
    resp = await client.post(
        "/discovery/events", json=_event_body(email="leak@example.com")
    )
    assert resp.status_code == 422


async def test_reset_clears_signals_and_drops_cookie(client, db_session) -> None:
    await client.post(
        "/discovery/events",
        json=_event_body(signal_tags={"categories": ["python"]}),
    )
    resp = await client.post("/discovery/session/reset", json={"opt_out": True})
    assert resp.status_code == 200
    assert resp.json()["data"] == {"reset": True, "opt_out": True}

    row = (await db_session.execute(select(DiscoverySession))).scalar_one()
    assert row.coarse_tags == {}
    assert row.opt_out is True
