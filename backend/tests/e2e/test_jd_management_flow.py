from __future__ import annotations

from fastapi.testclient import TestClient


def test_manage_jd_open_close_delete(client: TestClient, auth_headers: dict[str, str]):
    org = client.post(
        "/api/v1/orgs",
        headers=auth_headers,
        json={"name": "Demo Company", "type": "COMPANY", "metadata": {"country": "VN"}},
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    created = client.post(
        "/api/v1/jobs/manage",
        headers=auth_headers,
        json={
            "org_id": org_id,
            "title": "Frontend Intern",
            "description": "Build React TypeScript UI and write documentation.",
            "status": "open",
        },
    )
    assert created.status_code == 201
    data = created.json()
    assert data["status"] == "open"

    closed = client.patch(
        f"/api/v1/jobs/{data['id']}/status",
        headers=auth_headers,
        json={"status": "closed"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    listed = client.get(
        "/api/v1/jobs/manage?status=closed",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert any(job["id"] == data["id"] for job in listed.json())

    deleted = client.delete(f"/api/v1/jobs/{data['id']}", headers=auth_headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted", "job_id": data["id"]}

    listed_again = client.get("/api/v1/jobs/manage", headers=auth_headers)
    assert listed_again.status_code == 200
    assert all(job["id"] != data["id"] for job in listed_again.json())
