from __future__ import annotations

from fastapi.testclient import TestClient


def test_openapi_exposes_v2_operational_contracts(client: TestClient):
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    required = {
        "/api/v1/auth/login",
        "/api/v1/organizations/registration-reference",
        "/api/v1/registrations/me",
        "/api/v1/documents/upload-session",
        "/api/v1/ai/runs/",
        "/api/v1/ai/runs/capabilities",
        "/api/v1/ai/interviews/sessions",
        "/api/v1/ai/interviews/sessions/{session_id}",
        "/api/v1/ai/interviews/sessions/{session_id}/answers",
        "/api/v1/dashboard/student",
    }
    assert required.issubset(paths)
    assert "/api/v1/orgs/registration-reference" not in paths


def test_candidate_interview_response_does_not_expose_internal_fields(client: TestClient):
    schema = client.get("/openapi.json").json()
    properties = schema["components"]["schemas"]["CandidateInterviewResponse"]["properties"]

    assert set(properties) == {
        "session_id",
        "question",
        "current_phase",
        "should_end_interview",
        "report",
    }
    assert not {
        "internal_reason",
        "expected_signals",
        "previous_answer_evaluation",
        "score",
    } & set(properties)


def test_organization_compatibility_alias_remains_callable(client: TestClient):
    canonical = client.get("/api/v1/organizations/registration-reference")
    compatibility = client.get("/api/v1/orgs/registration-reference")
    assert canonical.status_code == 200
    assert compatibility.status_code == 200
    assert canonical.json() == compatibility.json()


def test_tenant_scoped_endpoints_require_identity(
    client: TestClient,
    auth_headers: dict[str, str],
):
    document = client.post(
        "/api/v1/documents/upload-session",
        headers=auth_headers,
        json={
            "category": "cv",
            "file_name": "cv.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
        },
    )
    assert document.status_code == 400

    ai_run = client.post(
        "/api/v1/ai/runs/",
        headers=auth_headers,
        json={"run_type": "career_coaching"},
    )
    assert ai_run.status_code == 400
