"""Shared schemas and validation helpers for jobs, students, and matches."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


JobStatus = Literal["draft", "open", "closed"]
MatchStatus = Literal["strong_match", "partial_match", "not_match"]


class ValidationError(ValueError):
    """Raised when incoming JSON does not match the expected demo schema."""


@dataclass
class StudentSkill:
    score: float
    confidence: float = 1.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class StudentProfile:
    student_id: str
    name: str
    skills: dict[str, StudentSkill]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobSkillRequirement:
    required_level: float
    importance: float
    required: bool = True


@dataclass
class JobRequirementProfile:
    job_id: str
    company_id: str
    title: str
    status: JobStatus
    employment_type: str
    location: str
    salary_range: str
    benefits: list[str]
    skills: dict[str, JobSkillRequirement]
    raw_text: str | None = None


@dataclass
class MatchThresholds:
    strong_match: float = 0.8
    partial_match: float = 0.6

    def validate(self) -> None:
        if not 0 <= self.partial_match <= self.strong_match <= 1:
            raise ValidationError("Thresholds must satisfy 0 <= partial_match <= strong_match <= 1.")


@dataclass
class SkillGap:
    user_score: float
    required_level: float
    gap: float
    importance: float
    required: bool


@dataclass
class MatchResult:
    job_id: str
    student_id: str
    student_name: str
    match_score: float
    match_status: MatchStatus
    matched_skills: list[str]
    missing_or_weak_skills: dict[str, SkillGap]
    explanation: str


def normalize_skill_name(name: str) -> str:
    aliases = {
        "js": "JavaScript",
        "javascript": "JavaScript",
        "python programming": "Python",
        "postgres": "SQL",
        "postgresql": "SQL",
        "mysql": "SQL",
        "machine learning": "Machine Learning",
        "ml": "Machine Learning",
        "llms": "LLM",
        "large language models": "LLM",
    }
    stripped = " ".join(str(name).strip().split())
    return aliases.get(stripped.lower(), stripped)


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Missing or invalid string field: {key}")
    return value.strip()


def _number_between(data: dict[str, Any], key: str, minimum: float, maximum: float) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)) or not minimum <= float(value) <= maximum:
        raise ValidationError(f"Field {key} must be a number between {minimum} and {maximum}.")
    return float(value)


def student_from_dict(data: dict[str, Any]) -> StudentProfile:
    student_id = _required_str(data, "student_id")
    name = _required_str(data, "name")
    raw_skills = data.get("skills")
    if not isinstance(raw_skills, dict) or not raw_skills:
        raise ValidationError("Student profile must include non-empty skills.")

    skills: dict[str, StudentSkill] = {}
    for raw_name, raw_skill in raw_skills.items():
        if not isinstance(raw_skill, dict):
            raise ValidationError(f"Invalid skill object for {raw_name}.")
        skill_name = normalize_skill_name(raw_name)
        skills[skill_name] = StudentSkill(
            score=_number_between(raw_skill, "score", 0, 10),
            confidence=_number_between(raw_skill, "confidence", 0, 1),
            evidence=list(raw_skill.get("evidence", [])),
        )

    metadata = data.get("metadata", {})
    return StudentProfile(
        student_id=student_id,
        name=name,
        skills=skills,
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def job_from_dict(data: dict[str, Any]) -> JobRequirementProfile:
    status = data.get("status", "draft")
    if status not in {"draft", "open", "closed"}:
        raise ValidationError("Job status must be one of: draft, open, closed.")

    raw_skills = data.get("skills")
    if not isinstance(raw_skills, dict) or not raw_skills:
        raise ValidationError("Job requirement must include non-empty skills.")

    skills: dict[str, JobSkillRequirement] = {}
    for raw_name, raw_req in raw_skills.items():
        if not isinstance(raw_req, dict):
            raise ValidationError(f"Invalid requirement object for {raw_name}.")
        skill_name = normalize_skill_name(raw_name)
        skills[skill_name] = JobSkillRequirement(
            required_level=_number_between(raw_req, "required_level", 1, 10),
            importance=_number_between(raw_req, "importance", 0, 1),
            required=bool(raw_req.get("required", True)),
        )

    benefits = data.get("benefits", [])
    if isinstance(benefits, str):
        benefits = [benefits]
    if not isinstance(benefits, list):
        raise ValidationError("benefits must be a list of strings.")

    return JobRequirementProfile(
        job_id=_required_str(data, "job_id"),
        company_id=_required_str(data, "company_id"),
        title=_required_str(data, "title"),
        status=status,
        employment_type=str(data.get("employment_type", "unspecified")),
        location=str(data.get("location", "unspecified")),
        salary_range=str(data.get("salary_range", "unspecified")),
        benefits=[str(item) for item in benefits],
        skills=skills,
        raw_text=data.get("raw_text") if isinstance(data.get("raw_text"), str) else None,
    )


def skill_to_dict(skill: StudentSkill) -> dict[str, Any]:
    return {
        "score": skill.score,
        "confidence": skill.confidence,
        "evidence": skill.evidence,
    }


def requirement_to_dict(requirement: JobSkillRequirement) -> dict[str, Any]:
    return {
        "required_level": requirement.required_level,
        "importance": requirement.importance,
        "required": requirement.required,
    }


def job_to_dict(job: JobRequirementProfile) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "company_id": job.company_id,
        "title": job.title,
        "status": job.status,
        "employment_type": job.employment_type,
        "location": job.location,
        "salary_range": job.salary_range,
        "benefits": job.benefits,
        "skills": {name: requirement_to_dict(req) for name, req in job.skills.items()},
        "raw_text": job.raw_text,
    }


def student_to_dict(student: StudentProfile) -> dict[str, Any]:
    return {
        "student_id": student.student_id,
        "name": student.name,
        "skills": {name: skill_to_dict(skill) for name, skill in student.skills.items()},
        "metadata": student.metadata,
    }


def match_result_to_dict(result: MatchResult) -> dict[str, Any]:
    return {
        "job_id": result.job_id,
        "student_id": result.student_id,
        "student_name": result.student_name,
        "match_score": result.match_score,
        "match_status": result.match_status,
        "matched_skills": result.matched_skills,
        "missing_or_weak_skills": {
            name: {
                "user_score": gap.user_score,
                "required_level": gap.required_level,
                "gap": gap.gap,
                "importance": gap.importance,
                "required": gap.required,
            }
            for name, gap in result.missing_or_weak_skills.items()
        },
        "explanation": result.explanation,
    }
