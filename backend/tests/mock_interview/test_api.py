"""HTTP wiring tests for the mock-interview router (offline provider).

Proves the router is mounted, the auth gate returns 401 for guests, and the
happy-path endpoints (prep, create, SSE stream, get) return the canonical
``{"data": ...}`` envelope with no internal leak. Auth + DB session are injected
via dependency overrides so we exercise the real router/service stack without a
login round-trip.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from app.core.db import get_db_session, get_sessionmaker
from app.main import app
from app.modules.auth.api.deps import get_current_auth
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv

_INTERNAL_FIELDS = (
    "provider_ref",
    "model_ref",
    "grounding_json",
    "grounding_version",
    "text_redacted",
    "flagged",
)


class _Auth:
    """Minimal stand-in for ``CurrentAuth`` (router reads only ``principal``/``ctx``)."""

    def __init__(self, principal: Principal) -> None:
        self.principal = principal
        self.ctx = CTX
        self.claims = None


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.clear()


async def _override_db() -> AsyncIterator:
    async with get_sessionmaker()() as session:
        yield session


def _authenticate_as(principal: Principal) -> None:
    app.dependency_overrides[get_current_auth] = lambda: _Auth(principal=principal)
    app.dependency_overrides[get_db_session] = _override_db


async def _seed(db) -> tuple[Principal, uuid.UUID]:
    _u, student = await make_student(db)
    await make_strong_cv(db, student)
    job_id = await make_public_job(db)
    return student, job_id


# --------------------------------------------------------------------------- #
# Guest is rejected (401) — router auth gate                                    #
# --------------------------------------------------------------------------- #
async def test_guest_gets_401(client) -> None:
    resp = await client.get("/mock-interview/sessions")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"

    resp2 = await client.post("/mock-interview/sessions", json={"job_id": str(uuid.uuid4())})
    assert resp2.status_code == 401


# --------------------------------------------------------------------------- #
# Happy path via HTTP: prep -> create -> stream -> get                          #
# --------------------------------------------------------------------------- #
async def test_prep_create_stream_get_over_http(client, db_session) -> None:
    student, job_id = await _seed(db_session)
    _authenticate_as(student)

    # prep
    prep = await client.get("/mock-interview/prep", params={"job_id": str(job_id)})
    assert prep.status_code == 200
    prep_data = prep.json()["data"]
    assert prep_data["job"]["id"] == str(job_id)
    assert prep_data["cvs"]  # at least the ready CV

    # create
    created = await client.post(
        "/mock-interview/sessions",
        json={"job_id": str(job_id), "modality": "text", "locale": "en"},
    )
    assert created.status_code == 201
    data = created.json()["data"]
    sid = data["session_id"]
    assert data["opening"]["speaker"] == "interviewer"
    assert data["opening"]["text"]

    # stream a turn (SSE) — AsyncClient buffers the streamed body
    stream = await client.post(
        f"/mock-interview/sessions/{sid}/turns/stream",
        json={"answer": "I built REST APIs with FastAPI in a real internship."},
    )
    assert stream.status_code == 200
    assert "text/event-stream" in stream.headers["content-type"]
    body = stream.text
    assert '"type": "done"' in body or '"type":"done"' in body
    assert "error" not in body.lower()

    # get detail — envelope + no leak
    got = await client.get(f"/mock-interview/sessions/{sid}")
    assert got.status_code == 200
    detail = got.json()["data"]
    assert detail["id"] == sid
    assert len(detail["transcript"]) >= 3  # opening + candidate + interviewer
    blob = json.dumps(got.json(), ensure_ascii=False)
    for field in _INTERNAL_FIELDS:
        assert field not in blob


# --------------------------------------------------------------------------- #
# End + share over HTTP                                                         #
# --------------------------------------------------------------------------- #
async def test_end_and_share_over_http(client, db_session) -> None:
    student, job_id = await _seed(db_session)
    _authenticate_as(student)

    created = await client.post(
        "/mock-interview/sessions", json={"job_id": str(job_id), "modality": "text"}
    )
    sid = created.json()["data"]["session_id"]

    ended = await client.post(f"/mock-interview/sessions/{sid}/end", json={})
    assert ended.status_code == 200
    report = ended.json()["data"]["report"]
    assert report["is_fallback"] is True
    assert "score" not in report and "grade" not in report

    shared = await client.post(
        f"/mock-interview/sessions/{sid}/share", json={"opt_in": True}
    )
    assert shared.status_code == 200
    assert shared.json()["data"]["share_opt_in"] is True
