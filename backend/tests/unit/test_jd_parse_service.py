from __future__ import annotations

from app.ai_engines.jd_parser import parse_jd_form, parse_jd_raw_text
from app.schemas.jobs import JobFormParseRequest


def test_parse_jd_raw_text_returns_frontend_ready_json():
    result = parse_jd_raw_text(
        (
            "Frontend Intern. Required skills: JavaScript, React, TypeScript, "
            "documentation, communication."
        ),
        job_id="mock-frontend-intern-001",
        company_id="company_demo",
    )

    data = result.model_dump()
    assert data["job_id"] == "mock-frontend-intern-001"
    assert data["company_id"] == "company_demo"
    assert data["title"] == "Frontend Intern"
    assert {"javascript", "react", "typescript"}.issubset(data["skills"])
    assert data["skills"]["react"]["required"] is True
    assert data["metadata"]["source"] == "raw_text"
    assert data["metadata"]["prompt_version"] == "parse_jd_v1"


def test_parse_jd_form_uses_structured_skills():
    result = parse_jd_form(
        JobFormParseRequest(
            job_id="job-form-001",
            company_id="company_demo",
            title="Backend Intern",
            employment_type="Internship",
            location="Hybrid",
            salary_range="Competitive",
            benefits=["Mentorship"],
            required_skills=["Python", "FastAPI"],
            preferred_skills=["Docker"],
        )
    )

    data = result.model_dump()
    assert data["job_id"] == "job-form-001"
    assert set(data["skills"]) == {"docker", "fastapi", "python"}
    assert data["skills"]["docker"]["required"] is False
    assert data["metadata"]["source"] == "form"
