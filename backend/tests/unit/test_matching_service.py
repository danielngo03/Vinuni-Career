from __future__ import annotations

from app.schemas.matching import (
    CompanyCandidateMatchRequest,
    MatchingJobInput,
    MatchingSkillRequirement,
    MatchingStudentInput,
    MatchingStudentSkill,
)
from app.services.matching_service import match_candidates_to_job


def test_rulebase_matching_shortlists_strong_backend_candidate():
    job = MatchingJobInput(
        job_id="mock-backend-intern-002",
        company_id="company_demo",
        title="Backend Intern",
        skills={
            "python": MatchingSkillRequirement(required_level=7.0, importance=1.0, required=True),
            "fastapi": MatchingSkillRequirement(required_level=7.0, importance=1.0, required=True),
            "postgresql": MatchingSkillRequirement(
                required_level=6.5,
                importance=0.85,
                required=True,
            ),
            "docker": MatchingSkillRequirement(required_level=6.0, importance=0.7, required=False),
        },
    )
    student = MatchingStudentInput(
        student_id="mock-student-backend-002",
        name="Minh Nguyen",
        skills={
            "python": MatchingStudentSkill(score=8.1, confidence=0.86, evidence=["Python API"]),
            "fastapi": MatchingStudentSkill(score=7.8, confidence=0.84, evidence=["REST APIs"]),
            "postgresql": MatchingStudentSkill(score=7.2, confidence=0.8, evidence=["Tables"]),
            "docker": MatchingStudentSkill(score=6.9, confidence=0.78, evidence=["Containers"]),
        },
    )

    response = match_candidates_to_job(
        CompanyCandidateMatchRequest(job=job, students=[student])
    )

    result = response.results[0]
    assert result.decision == "shortlist"
    assert result.label == "Strong match"
    assert result.match_score >= 85
    assert result.required_skills["missing"] == []
    assert "docker" in result.optional_skills["matched"]
