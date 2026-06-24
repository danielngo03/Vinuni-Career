from __future__ import annotations

from fastapi.testclient import TestClient

from app.platform.database.session import SessionLocal
from scripts.init_db import seed_demo_product_data


def _login(client: TestClient, email: str, portal: str) -> dict[str, str]:
    body = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    ).json()
    identity = next(item for item in body["identities"] if item["portal"] == portal)
    return {
        "Authorization": f"Bearer {body['access_token']}",
        "X-Identity-Id": identity["id"],
    }


def test_document_lifecycle_requires_owner_and_internal_scan_auth(
    client: TestClient,
):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()
    student = _login(client, "student@vinuni.edu.vn", "student")

    created = client.post(
        "/api/v1/documents/upload-session",
        headers=student,
        json={
            "category": "cv",
            "file_name": "resume.pdf",
            "content_type": "application/pdf",
            "size_bytes": 4096,
        },
    )
    assert created.status_code == 201, created.json()
    document_id = created.json()["document_id"]
    assert created.json()["upload_method"] == "PUT"

    completed = client.post(
        f"/api/v1/documents/{document_id}/complete",
        headers=student,
        json={"checksum_sha256": "a" * 64},
    )
    assert completed.status_code == 200
    assert completed.json()["scan_status"] == "UPLOADED"

    unauthenticated_scan = client.post(
        f"/api/v1/documents/{document_id}/scan-result",
        json={"scan_result": "CLEAN", "scan_engine": "test-scanner"},
    )
    assert unauthenticated_scan.status_code == 401

    scanned = client.post(
        f"/api/v1/documents/{document_id}/scan-result",
        headers={"X-Internal-Service-Token": "test-internal-service-token"},
        json={"scan_result": "CLEAN", "scan_engine": "test-scanner"},
    )
    assert scanned.status_code == 200, scanned.json()
    assert scanned.json()["scan_status"] == "CLEAN"


def test_ai_runs_are_tenant_scoped_and_asynchronous(client: TestClient):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()
    student = _login(client, "student@vinuni.edu.vn", "student")

    created = client.post(
        "/api/v1/ai/runs",
        headers=student,
        json={
            "run_type": "career_coaching",
            "run_metadata": {"locale": "vi"},
        },
    )
    assert created.status_code == 202, created.json()
    run_id = created.json()["run_id"]
    assert created.json()["org_id"]

    fetched = client.get(f"/api/v1/ai/runs/{run_id}", headers=student)
    assert fetched.status_code == 200
    assert fetched.json()["status"] in {"QUEUED", "RUNNING", "DONE"}
    if fetched.json()["status"] == "DONE":
        assert fetched.json()["result"]["agent"] == "career_coaching_agent"
        assert fetched.json()["result"]["steps"]

    listed = client.get("/api/v1/ai/runs/", headers=student)
    assert listed.status_code == 200
    assert run_id in {item["run_id"] for item in listed.json()}


def test_ai_workforce_capabilities_are_discoverable(client: TestClient):
    response = client.get("/api/v1/ai/runs/capabilities")

    assert response.status_code == 200
    capabilities = {item["task_type"]: item for item in response.json()}
    assert "career_coaching" in capabilities
    assert capabilities["admin_review"]["human_review_policy"]
