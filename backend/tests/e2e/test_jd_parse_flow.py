from __future__ import annotations

from fastapi.testclient import TestClient


def test_parse_jd_raw_endpoint(client: TestClient):
    response = client.post(
        "/api/v1/jobs/parse/raw",
        json={
            "job_id": "mock-frontend-intern-001",
            "company_id": "company_demo",
            "raw_text": (
                "Frontend Intern. Required skills: JavaScript, React, TypeScript, "
                "documentation, communication."
            ),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "mock-frontend-intern-001"
    assert data["company_id"] == "company_demo"
    assert "react" in data["skills"]
    assert data["metadata"]["source"] == "raw_text"
    assert "llm_used" in data["metadata"]
    assert "fallback_used" in data["metadata"]


def test_parse_jd_upload_endpoint(client: TestClient):
    response = client.post(
        "/api/v1/jobs/parse/upload",
        files={
            "file": (
                "jd.txt",
                b"Backend Intern\nRequired skills: Python FastAPI Docker",
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Backend Intern"
    assert data["metadata"]["source"] == "upload"
