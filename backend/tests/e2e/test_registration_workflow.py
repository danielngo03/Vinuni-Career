from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.platform.database.models import Industry, Organization, StudentProfile
from app.platform.database.session import SessionLocal
from app.shared.config import settings
from app.shared.enum import RegistrationStatus
from scripts.init_db import seed_demo_product_data


def _university_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "career.center@vinuni.edu.vn",
            "password": "password123",
        },
    )
    body = response.json()
    identity = next(item for item in body["identities"] if item["portal"] == "university")
    return {
        "Authorization": f"Bearer {body['access_token']}",
        "X-Identity-Id": identity["id"],
    }


def test_student_registration_requires_university_approval(client: TestClient):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()
        university = db.scalar(
            select(Organization).where(Organization.name == "VinUniversity")
        )
        major_id = university and university.id
        major = (
            db.execute(
                select(StudentProfile.major_id)
                .where(StudentProfile.org_id == university.id)
                .limit(1)
            ).scalar_one()
            if university
            else None
        )
    assert university and major and major_id

    response = client.post(
        "/api/v1/registrations/student",
        json={
            "university_org_id": university.id,
            "full_name": "Pending Student",
            "email": "pending.student@vinuni.edu.vn",
            "password": "StrongPass123!",
            "student_code": "SE2026-099",
            "major_id": major,
            "degree_level": "BACHELOR",
            "enrollment_year": 2023,
            "expected_graduation_year": 2027,
            "phone_number": "0912345678",
        },
    )
    assert response.status_code == 201
    application = response.json()
    assert application["status"] == RegistrationStatus.SUBMITTED
    assert application["version"] == 1
    assert application["assessment"]["outcome"] == "APPROVE"
    assert application["policy_snapshot"]["mode"] == "SHADOW"

    before_approval = client.post(
        "/api/v1/auth/login",
        json={
            "email": "pending.student@vinuni.edu.vn",
            "password": "StrongPass123!",
        },
    )
    assert before_approval.status_code == 200
    pending_session = before_approval.json()
    assert pending_session["access_scope"] == "registration:pending"
    assert pending_session["identities"] == []

    pending_status = client.get(
        "/api/v1/registrations/me",
        headers={"Authorization": f"Bearer {pending_session['access_token']}"},
    )
    assert pending_status.status_code == 200
    assert pending_status.json()["allowed_actions"] == ["view_status", "withdraw"]

    previous = settings.enforce_rbac
    settings.enforce_rbac = True
    try:
        review = client.post(
            f"/api/v1/registrations/{application['id']}/review",
            headers=_university_headers(client),
            json={"decision": "APPROVE", "note": "Student record verified"},
        )
        assert review.status_code == 200
        assert review.json()["status"] == RegistrationStatus.APPROVED
    finally:
        settings.enforce_rbac = previous

    after_approval = client.post(
        "/api/v1/auth/login",
        json={
            "email": "pending.student@vinuni.edu.vn",
            "password": "StrongPass123!",
        },
    )
    assert after_approval.status_code == 200
    assert after_approval.json()["identities"][0]["portal"] == "student"


def test_request_changes_requires_checklist_and_resubmit_creates_version(
    client: TestClient,
):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()
        university = db.scalar(
            select(Organization).where(Organization.name == "VinUniversity")
        )
        major = db.execute(
            select(StudentProfile.major_id)
            .where(StudentProfile.org_id == university.id)
            .limit(1)
        ).scalar_one()

    response = client.post(
        "/api/v1/registrations/student",
        json={
            "university_org_id": university.id,
            "full_name": "Needs Changes Student",
            "email": "changes.student@vinuni.edu.vn",
            "password": "StrongPass123!",
            "student_code": "SE2026-088",
            "major_id": major,
            "degree_level": "BACHELOR",
            "enrollment_year": 2023,
            "expected_graduation_year": 2027,
            "phone_number": "0912345678",
        },
    )
    application_id = response.json()["id"]

    previous = settings.enforce_rbac
    settings.enforce_rbac = True
    try:
        without_checklist = client.post(
            f"/api/v1/registrations/{application_id}/review",
            headers=_university_headers(client),
            json={"decision": "REQUEST_CHANGES", "note": "Confirm phone number"},
        )
        assert without_checklist.status_code == 400

        review = client.post(
            f"/api/v1/registrations/{application_id}/review",
            headers=_university_headers(client),
            json={
                "decision": "REQUEST_CHANGES",
                "note": "Confirm phone number",
                "checklist": [
                    {
                        "code": "phone",
                        "label": "Confirm the current phone number",
                        "field": "phone_number",
                    }
                ],
            },
        )
        assert review.status_code == 200
        assert review.json()["status"] == RegistrationStatus.CHANGES_REQUESTED
    finally:
        settings.enforce_rbac = previous

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "changes.student@vinuni.edu.vn",
            "password": "StrongPass123!",
        },
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    pending = client.get("/api/v1/registrations/me", headers=headers)
    assert pending.json()["allowed_actions"] == ["view_status", "resubmit", "withdraw"]

    incomplete = client.post(
        "/api/v1/registrations/me/resubmit",
        headers=headers,
        json={"checklist_codes": []},
    )
    assert incomplete.status_code == 400

    resubmitted = client.post(
        "/api/v1/registrations/me/resubmit",
        headers=headers,
        json={
            "checklist_codes": ["phone"],
            "note": "Phone number confirmed against my student record.",
        },
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["status"] == RegistrationStatus.RESUBMITTED
    assert resubmitted.json()["version"] == 2


def test_partner_registration_creates_verified_org_after_approval(client: TestClient):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()
        university = db.scalar(
            select(Organization).where(Organization.name == "VinUniversity")
        )
        industries = list(
            db.scalars(
                select(Industry)
                .where(Industry.university_org_id == university.id)
                .limit(2)
            )
        )
    assert university and len(industries) == 2

    response = client.post(
        "/api/v1/registrations/partner",
        data={
            "university_org_id": university.id,
            "full_name": "Partner Representative",
            "email": "representative@newpartner.vn",
            "password": "StrongPass123!",
            "company_name": "New Partner Vietnam",
            "tax_code": "0109999999",
            "website": "https://newpartner.vn",
            "company_size": "51-200",
            "founded_year": "2020",
            "headquarters_address": "Hanoi, Vietnam",
            "company_description": "Technology company building reliable products for education.",
            "representative_name": "Partner Representative",
            "representative_title": "Head of Talent",
            "representative_phone": "0987654321",
            "representative_email": "representative@newpartner.vn",
            "industry_ids_json": f'["{industries[0].id}","{industries[1].id}"]',
            "primary_industry_id": industries[0].id,
        },
        files={
            "logo": ("logo.png", BytesIO(b"fake-png"), "image/png"),
            "business_license": (
                "business-license.pdf",
                BytesIO(b"%PDF-1.4 registration"),
                "application/pdf",
            ),
        },
    )
    assert response.status_code == 201, response.json()
    assert response.json()["status"] == RegistrationStatus.SUBMITTED
    assert response.json()["assessment"]["outcome"] == "MANUAL_REVIEW"
    assert "unavailable" in str(response.json()["assessment"]).lower()

    previous = settings.enforce_rbac
    settings.enforce_rbac = True
    try:
        review = client.post(
            f"/api/v1/registrations/{response.json()['id']}/review",
            headers=_university_headers(client),
            json={"decision": "APPROVE", "note": "Legal documents verified"},
        )
        assert review.status_code == 200, review.json()
    finally:
        settings.enforce_rbac = previous

    with SessionLocal() as db:
        organization = db.scalar(
            select(Organization).where(Organization.name == "New Partner Vietnam")
        )
        assert organization and organization.is_verified_partner


def test_auto_low_risk_approves_student_but_kill_switch_prevents_it(
    client: TestClient,
):
    with SessionLocal() as db:
        seed_demo_product_data(db)
        db.commit()
        university = db.scalar(
            select(Organization).where(Organization.name == "VinUniversity")
        )
        major = db.execute(
            select(StudentProfile.major_id)
            .where(StudentProfile.org_id == university.id)
            .limit(1)
        ).scalar_one()

    headers = _university_headers(client)
    previous = settings.enforce_rbac
    settings.enforce_rbac = True
    try:
        policy = client.put(
            "/api/v1/registrations/verification-policy/STUDENT",
            headers=headers,
            json={
                "mode": "AUTO_LOW_RISK",
                "global_kill_switch": False,
                "confidence_threshold": 90,
                "required_providers": ["student_roster"],
                "required_documents": [],
                "sample_rate": 100,
                "model_version": "deterministic-v1",
            },
        )
        assert policy.status_code == 200

        approved = client.post(
            "/api/v1/registrations/student",
            json={
                "university_org_id": university.id,
                "full_name": "Auto Approved",
                "email": "auto.approved@vinuni.edu.vn",
                "password": "StrongPass123!",
                "student_code": "SE2026-701",
                "major_id": major,
                "degree_level": "BACHELOR",
                "enrollment_year": 2023,
                "expected_graduation_year": 2027,
                "phone_number": "0912345678",
            },
        )
        assert approved.status_code == 201
        assert approved.json()["status"] == RegistrationStatus.APPROVED

        kill_switch = client.put(
            "/api/v1/registrations/verification-policy/STUDENT",
            headers=headers,
            json={
                "mode": "AUTO_LOW_RISK",
                "global_kill_switch": True,
                "confidence_threshold": 90,
                "required_providers": ["student_roster"],
                "required_documents": [],
                "sample_rate": 100,
                "model_version": "deterministic-v1",
            },
        )
        assert kill_switch.status_code == 200

        held = client.post(
            "/api/v1/registrations/student",
            json={
                "university_org_id": university.id,
                "full_name": "Kill Switch Held",
                "email": "kill.switch@vinuni.edu.vn",
                "password": "StrongPass123!",
                "student_code": "SE2026-702",
                "major_id": major,
                "degree_level": "BACHELOR",
                "enrollment_year": 2023,
                "expected_graduation_year": 2027,
                "phone_number": "0912345678",
            },
        )
        assert held.status_code == 201
        assert held.json()["status"] == RegistrationStatus.SUBMITTED
    finally:
        settings.enforce_rbac = previous
