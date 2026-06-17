from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_me(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"


def test_job_cv_application_flow(client: TestClient, auth_headers: dict[str, str]):
    owner = client.get("/api/v1/auth/me", headers=auth_headers).json()

    org = client.post(
        "/api/v1/orgs",
        headers=auth_headers,
        json={"name": "Demo University", "type": "UNIVERSITY", "metadata": {"country": "VN"}},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    profile = client.post(
        "/api/v1/students",
        headers=auth_headers,
        json={
            "user_id": owner["id"],
            "org_id": org_id,
            "student_code": "S001",
            "gpa_overall": 3.6,
            "attendance_overall": 95,
        },
    )
    assert profile.status_code == 201

    cv = client.post(
        "/api/v1/cvs",
        headers=auth_headers,
        json={
            "student_id": owner["id"],
            "raw_text": "Owner Student\nowner@example.com\nPython FastAPI PostgreSQL Docker",
            "parsed_data": {"summary": "Backend intern"},
        },
    )
    assert cv.status_code == 201
    assert "[REDACTED_EMAIL]" in cv.json()["masked_data"]["text"]

    job = client.post(
        "/api/v1/jobs",
        headers=auth_headers,
        json={
            "org_id": org_id,
            "title": "Backend AI Intern",
            "description": (
                "Build production FastAPI services with Python, PostgreSQL, Redis, "
                "Docker and reliable AI observability for student recruitment workflows."
            ),
        },
    )
    assert job.status_code == 201
    assert job.json()["status"] == "APPROVED"

    application = client.post(
        f"/api/v1/jobs/{job.json()['id']}/applications",
        headers=auth_headers,
        json={"student_id": owner["id"], "cv_id": cv.json()["id"], "consent_to_unmask": False},
    )
    assert application.status_code == 201
    assert application.json()["ai_match_score"] > 0

    search = client.post(
        "/api/v1/search",
        headers=auth_headers,
        json={"query": "FastAPI PostgreSQL", "entity_type": "job"},
    )
    assert search.status_code == 200
    assert search.json()["results"]


def test_ai_gateway_offline_endpoints(client: TestClient, auth_headers: dict[str, str]):
    providers = client.get("/api/v1/ai/providers", headers=auth_headers)
    assert providers.status_code == 200
    assert "offline" in providers.json()["chat_chain"]

    chat = client.post(
        "/api/v1/ai/chat?org_id=test-org",
        headers=auth_headers,
        json={"messages": [{"role": "user", "content": "Summarize FastAPI"}]},
    )
    assert chat.status_code == 200
    assert chat.json()["provider"] == "offline"

    embedding = client.post(
        "/api/v1/ai/embed",
        headers=auth_headers,
        json={"text": "Python FastAPI PostgreSQL"},
    )
    assert embedding.status_code == 200
    assert embedding.json()["embedding"]


def test_file_upload_local_storage(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/api/v1/files/upload",
        headers=auth_headers,
        files={"upload": ("cv.txt", b"Python FastAPI", "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["file_name"] == "cv.txt"
