from __future__ import annotations

from fastapi.testclient import TestClient

from app.platform.database.models import CV
from app.platform.database.session import SessionLocal
from scripts.init_db import seed_demo_product_data


def test_health(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_me(client: TestClient, auth_headers: dict[str, str]):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "owner@example.com"


def test_seeded_role_dashboards(client: TestClient):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()

    accounts = [
        ("student@vinuni.edu.vn", "student", "recommended_jobs"),
        ("hr@partner.vn", "partner", "candidates"),
        ("career.center@vinuni.edu.vn", "university", "moderation_queue"),
    ]
    for email, portal, expected_key in accounts:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert login.status_code == 200
        body = login.json()
        identity = next(item for item in body["identities"] if item["portal"] == portal)
        dashboard = client.get(
            f"/api/v1/dashboard/{portal}",
            headers={
                "Authorization": f"Bearer {body['access_token']}",
                "X-Identity-Id": identity["id"],
            },
        )
        assert dashboard.status_code == 200
        assert expected_key in dashboard.json()


def test_student_dashboard_accepts_structured_cv_skills(client: TestClient):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        cv = db.query(CV).filter(CV.is_primary.is_(True)).first()
        assert cv is not None
        cv.skills = ["Python", "SQL"]
        cv.parsed_data = {
            "skills": [
                {"name": "python", "evidence": "CV skills", "proficiency": "unknown"},
                {"name": "machine learning", "evidence": "summary", "proficiency": "unknown"},
            ],
            "gemini_extraction": {
                "skills": [
                    {"name": "PyTorch", "evidence": "technical skills"},
                ],
            },
        }
        db.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "student@vinuni.edu.vn", "password": "password123"},
    )
    assert login.status_code == 200
    body = login.json()
    identity = next(item for item in body["identities"] if item["portal"] == "student")
    dashboard = client.get(
        "/api/v1/dashboard/student",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            "X-Identity-Id": identity["id"],
        },
    )
    assert dashboard.status_code == 200
    skills = {skill for cv in dashboard.json()["cvs"] for skill in cv["skills"]}
    assert {"Python", "SQL", "machine learning", "PyTorch"}.issubset(skills)


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
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "student@vinuni.edu.vn", "password": "password123"},
    ).json()
    identity = next(item for item in login["identities"] if item["portal"] == "student")
    scoped_headers = {
        "Authorization": f"Bearer {login['access_token']}",
        "X-Identity-Id": identity["id"],
    }
    providers = client.get("/api/v1/ai/providers", headers=scoped_headers)
    assert providers.status_code == 200
    assert "offline" in providers.json()["chat_chain"]

    chat = client.post(
        "/api/v1/ai/chat",
        headers=scoped_headers,
        json={"messages": [{"role": "user", "content": "Summarize FastAPI"}]},
    )
    assert chat.status_code == 200
    assert chat.json()["provider"] == "offline"

    embedding = client.post(
        "/api/v1/ai/embed",
        headers=scoped_headers,
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


def test_refresh_rotation_detects_reuse(client: TestClient):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "rotation@example.com",
            "password": "StrongPass123!",
            "full_name": "Rotation Test",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "rotation@example.com", "password": "StrongPass123!"},
    ).json()
    original = login["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != original

    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": original})
    assert reuse.status_code == 401
    assert "reuse detected" in reuse.json()["error"]["message"].lower()
