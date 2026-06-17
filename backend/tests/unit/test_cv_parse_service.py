from __future__ import annotations

from app.schemas.cvs import CVFormParseRequest
from app.ai_engines.cv_parser import parse_cv_form, parse_cv_raw_text


def test_parse_cv_raw_text_returns_frontend_ready_json():
    result = parse_cv_raw_text(
        "Chi Le\nComputer Science student. Projects with JavaScript, React, TypeScript, "
        "Python and dashboards.",
        student_id="mock-student-frontend-001",
    )

    data = result.model_dump()
    assert data["student_id"] == "mock-student-frontend-001"
    assert data["target_position"] == "Frontend Developer"
    assert data["work_experience"] == []
    assert data["education"] == []
    assert set(data["skills"]) == {"javascript", "python", "react", "typescript"}
    assert data["skills"]["python"]["score"] == 7.3
    assert data["skills"]["python"]["confidence"] == 0.82
    assert data["metadata"]["source"] == "raw_text"


def test_parse_cv_form_uses_structured_skills():
    result = parse_cv_form(
        CVFormParseRequest(
            student_id="student-form-001",
            target_position="Frontend Intern",
            education="Computer Science",
            experience="Built internal dashboard features during internship.",
            projects="Portfolio built with React",
            skills=["Python", "React", "Java"],
        )
    )

    data = result.model_dump()
    assert data["student_id"] == "student-form-001"
    assert data["target_position"] == "Frontend Intern"
    assert data["work_experience"][0]["summary"] == "Built internal dashboard features during internship."
    assert data["work_experience"][0]["score"] == 5.5
    assert data["work_experience"][0]["score_reason"]
    assert data["education"][0]["summary"] == "Computer Science"
    assert data["education"][0]["score"] == 5.5
    assert data["education"][0]["score_reason"]
    assert set(data["skills"]) == {"java", "python", "react"}
    assert data["metadata"]["source"] == "form"
