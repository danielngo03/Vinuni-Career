from __future__ import annotations

from fastapi.testclient import TestClient


def test_parse_cv_raw_endpoint(client: TestClient):
    response = client.post(
        "/api/v1/cvs/parse/raw",
        json={
            "student_id": "mock-student-frontend-001",
            "raw_text": (
                "Chi Le\nComputer Science student. Projects with JavaScript, React, "
                "TypeScript, Python and dashboards."
            ),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["student_id"] == "mock-student-frontend-001"
    assert data["name"] == "Chi Le"
    assert "python" in data["skills"]
    assert data["metadata"]["source"] == "raw_text"


def test_parse_cv_upload_endpoint(client: TestClient):
    response = client.post(
        "/api/v1/cvs/parse/upload",
        files={
            "file": (
                "cv.txt",
                b"Chi Le\nJavaScript React TypeScript Python",
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Chi Le"
    assert data["metadata"]["source"] == "upload"
