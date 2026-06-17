from __future__ import annotations

from app.schemas.matching import (
    CompanyCandidateMatchRequest,
    MatchingConfig,
    MatchingEducation,
    MatchingEducationRequirement,
    MatchingExperienceRequirement,
    MatchingJobInput,
    MatchingSkillRequirement,
    MatchingStudentInput,
    MatchingStudentSkill,
    MatchingWorkExperience,
)
from app.services.matching_service import match_candidates_to_job, score_match


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


def test_company_weights_can_disable_education_component():
    job = MatchingJobInput(
        job_id="backend-with-degree-001",
        title="Backend Intern",
        skills={
            "python": MatchingSkillRequirement(required_level=7.0, importance=1.0, required=True),
        },
        experience_requirements=MatchingExperienceRequirement(
            required=True,
            min_months=3,
            keywords=["project experience"],
            importance=0.8,
        ),
        education_requirements=MatchingEducationRequirement(
            required=True,
            fields_of_study=["computer science"],
            importance=0.8,
        ),
    )
    student = MatchingStudentInput(
        student_id="student-no-degree-001",
        skills={
            "python": MatchingStudentSkill(score=8.0, confidence=0.9, evidence=["Python API"]),
        },
        work_experience=[
            MatchingWorkExperience(
                title="Backend Project",
                duration="6 months",
                summary="Project experience building APIs.",
                score=8.0,
            )
        ],
        education=[],
    )

    with_education = score_match(student, job)
    without_education = score_match(
        student,
        job,
        MatchingConfig(skill_weight=0.7, experience_weight=0.3, education_weight=0.0),
    )

    assert with_education.breakdown.component_weights["education"] > 0
    assert without_education.breakdown.component_weights["education"] == 0
    assert without_education.match_score > with_education.match_score


def test_company_weights_include_matching_education_when_enabled():
    job = MatchingJobInput(
        job_id="data-education-001",
        title="Data Analyst Intern",
        skills={
            "excel": MatchingSkillRequirement(required_level=6.0, importance=1.0, required=True),
        },
        education_requirements=MatchingEducationRequirement(
            required=True,
            fields_of_study=["computer science"],
            importance=0.8,
        ),
    )
    student = MatchingStudentInput(
        student_id="student-education-001",
        skills={
            "microsoft excel": MatchingStudentSkill(
                score=7.0,
                confidence=0.9,
                evidence=["Excel dashboard"],
            ),
        },
        education=[
            MatchingEducation(
                degree="Bachelor",
                institution="Demo University",
                summary="Computer Science coursework",
                score=8.0,
            )
        ],
    )

    result = score_match(
        student,
        job,
        MatchingConfig(skill_weight=0.5, experience_weight=0.0, education_weight=0.5),
    )

    assert result.breakdown.component_weights == {
        "skill": 0.5,
        "experience": 0.0,
        "education": 0.5,
    }
    assert result.breakdown.education_score > 70
    assert result.match_score > 70
