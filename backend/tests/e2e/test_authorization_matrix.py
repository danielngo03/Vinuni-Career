from __future__ import annotations

from fastapi.testclient import TestClient

from app.platform.database.session import SessionLocal
from app.shared.config import settings
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


def test_role_permission_matrix(client: TestClient):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()

    previous = settings.enforce_rbac
    settings.enforce_rbac = True
    try:
        student = _login(client, "student@vinuni.edu.vn", "student")
        partner = _login(client, "hr@partner.vn", "partner")
        university = _login(client, "career.center@vinuni.edu.vn", "university")

        student_create_job = client.post(
            "/api/v1/jobs",
            headers=student,
            json={
                "title": "Unauthorized role",
                "description": "This description is deliberately long enough for validation.",
            },
        )
        assert student_create_job.status_code == 403

        partner_create_job = client.post(
            "/api/v1/jobs",
            headers=partner,
            json={
                "title": "Authorized partner role",
                "description": (
                    "Build reliable data products with clear responsibilities, "
                    "requirements, mentoring and transparent compensation."
                ),
            },
        )
        assert partner_create_job.status_code == 201

        partner_moderate = client.post(
            f"/api/v1/jobs/{partner_create_job.json()['id']}/moderate",
            headers=partner,
            json={"approve": True},
        )
        assert partner_moderate.status_code == 403

        university_moderate = client.post(
            f"/api/v1/jobs/{partner_create_job.json()['id']}/moderate",
            headers=university,
            json={"approve": True},
        )
        assert university_moderate.status_code == 200
    finally:
        settings.enforce_rbac = previous
