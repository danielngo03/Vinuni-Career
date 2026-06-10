"""Student profile summary logic for the student profile agent."""

from __future__ import annotations

from typing import Any

from backend.src.models.schemas import StudentProfile


def summarize_student_profile(student: StudentProfile, top_n: int = 3) -> dict[str, Any]:
    ranked_skills = sorted(
        student.skills.items(),
        key=lambda item: (item[1].score, item[1].confidence, item[0]),
        reverse=True,
    )
    top_skills = [
        {
            "name": name,
            "score": skill.score,
            "confidence": skill.confidence,
            "evidence": skill.evidence,
        }
        for name, skill in ranked_skills[:top_n]
    ]

    average_score = 0.0
    if student.skills:
        average_score = round(sum(skill.score for skill in student.skills.values()) / len(student.skills), 2)

    return {
        "student_id": student.student_id,
        "name": student.name,
        "metadata": student.metadata,
        "average_skill_score": average_score,
        "top_skills": top_skills,
        "summary": _build_summary(student, top_skills),
    }


def _build_summary(student: StudentProfile, top_skills: list[dict[str, Any]]) -> str:
    if not top_skills:
        return f"{student.name} does not have skill data yet."

    skill_names = ", ".join(skill["name"] for skill in top_skills)
    major = student.metadata.get("major")
    year = student.metadata.get("year")
    context = f", {major} year {year}" if major and year else ""
    return f"{student.name}{context}, is strongest in {skill_names}."
