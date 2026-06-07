"""Deterministic rule-based matching for one open job against students."""

from __future__ import annotations

from backend.src.models.schemas import (
    JobRequirementProfile,
    MatchResult,
    MatchThresholds,
    SkillGap,
    StudentProfile,
    ValidationError,
)


def match_students_for_job(
    job: JobRequirementProfile,
    students: list[StudentProfile],
    thresholds: MatchThresholds | None = None,
) -> list[MatchResult]:
    if job.status != "open":
        raise ValidationError("Matching is only allowed for jobs with status = open.")

    thresholds = thresholds or MatchThresholds()
    thresholds.validate()

    results = [_match_student(job, student, thresholds) for student in students]
    return sorted(results, key=lambda item: item.match_score, reverse=True)


def _match_student(
    job: JobRequirementProfile,
    student: StudentProfile,
    thresholds: MatchThresholds,
) -> MatchResult:
    total_importance = sum(req.importance for req in job.skills.values())
    if total_importance <= 0:
        raise ValidationError("Job skill importance sum must be greater than zero.")

    weighted_score = 0.0
    matched_skills: list[str] = []
    missing_or_weak: dict[str, SkillGap] = {}
    blocks_strong_match = False

    for skill_name, requirement in job.skills.items():
        student_skill = student.skills.get(skill_name)
        user_score = student_skill.score if student_skill else 0.0
        ratio = min(user_score / requirement.required_level, 1.0)
        weighted_score += ratio * requirement.importance

        if user_score >= requirement.required_level:
            matched_skills.append(skill_name)
        else:
            gap = round(requirement.required_level - user_score, 2)
            missing_or_weak[skill_name] = SkillGap(
                user_score=user_score,
                required_level=requirement.required_level,
                gap=gap,
                importance=requirement.importance,
                required=requirement.required,
            )
            if requirement.required and requirement.importance >= 0.8:
                blocks_strong_match = True

    score = round(weighted_score / total_importance, 4)
    status = _label_score(score, blocks_strong_match, thresholds)
    explanation = _explain(student.name, status, matched_skills, missing_or_weak)

    return MatchResult(
        job_id=job.job_id,
        student_id=student.student_id,
        student_name=student.name,
        match_score=score,
        match_status=status,
        matched_skills=matched_skills,
        missing_or_weak_skills=missing_or_weak,
        explanation=explanation,
    )


def _label_score(score: float, blocks_strong_match: bool, thresholds: MatchThresholds) -> str:
    if score >= thresholds.strong_match and not blocks_strong_match:
        return "strong_match"
    if score >= thresholds.partial_match:
        return "partial_match"
    return "not_match"


def _explain(
    student_name: str,
    status: str,
    matched_skills: list[str],
    missing_or_weak: dict[str, SkillGap],
) -> str:
    matched = ", ".join(matched_skills) if matched_skills else "no required skills"
    if not missing_or_weak:
        return f"{student_name} is a {status} because all required skills meet the requested levels."

    gaps = ", ".join(
        f"{name} gap {gap.gap:g} (has {gap.user_score:g}, needs {gap.required_level:g})"
        for name, gap in missing_or_weak.items()
    )
    return f"{student_name} is a {status}. Matched: {matched}. Missing or weak: {gaps}."
