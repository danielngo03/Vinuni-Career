"""CV-to-job review service with LLM and deterministic fallback modes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from backend.src.models.schemas import JobRequirementProfile, MatchThresholds, StudentProfile, match_result_to_dict
from backend.src.provider import LLMProvider, get_llm_provider
from backend.src.services.matching import match_students_for_job


TECH_KEYWORDS = [
    "Python",
    "SQL",
    "Docker",
    "JavaScript",
    "TypeScript",
    "React",
    "FastAPI",
    "Streamlit",
    "Pandas",
    "Excel",
    "Machine Learning",
    "LLM",
    "RAG",
    "API",
    "Git",
    "Dashboard",
    "Data Analysis",
    "Communication",
    "Documentation",
    "Testing",
    "REST",
    "Database",
    "Cloud",
]


REVIEW_FIELDS = [
    "overall_assessment",
    "match_level",
    "strengths",
    "missing_skills",
    "missing_keywords",
    "improvement_suggestions",
    "cv_improvements",
    "priority_actions",
]


@dataclass(frozen=True)
class ReviewMetadata:
    reviewer_mode: str
    model: str
    api_key_configured: bool
    used_llm: bool
    fallback_used: bool
    error: str | None = None


def review_metadata_to_dict(metadata: ReviewMetadata) -> dict[str, Any]:
    return {
        "reviewer_mode": metadata.reviewer_mode,
        "model": metadata.model,
        "api_key_configured": metadata.api_key_configured,
        "used_llm": metadata.used_llm,
        "fallback_used": metadata.fallback_used,
        "error": metadata.error,
    }


def review_student_against_job(
    student: StudentProfile,
    job: JobRequirementProfile,
    thresholds: MatchThresholds | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Return a structured review of one saved student profile against one open job."""
    thresholds = thresholds or MatchThresholds()
    match_result = match_students_for_job(job, [student], thresholds)[0]
    fallback = _fallback_review(student, job, match_result)

    try:
        provider = get_llm_provider()
    except Exception as exc:
        fallback["_reviewer"] = review_metadata_to_dict(
            ReviewMetadata(
                reviewer_mode="fallback",
                model="unknown",
                api_key_configured=False,
                used_llm=False,
                fallback_used=True,
                error=str(exc) if use_llm else "LLM review disabled for this call.",
            )
        )
        return fallback

    if use_llm and provider.is_configured:
        try:
            llm_review = _review_with_provider(provider, student, job, fallback)
            llm_review["_reviewer"] = review_metadata_to_dict(
                ReviewMetadata(
                    reviewer_mode=provider.name,
                    model=provider.model,
                    api_key_configured=True,
                    used_llm=True,
                    fallback_used=False,
                )
            )
            return llm_review
        except Exception as exc:
            fallback["_reviewer"] = review_metadata_to_dict(
                ReviewMetadata(
                    reviewer_mode="fallback",
                    model=provider.model,
                    api_key_configured=True,
                    used_llm=False,
                    fallback_used=True,
                    error=str(exc),
                )
            )
            return fallback

    fallback["_reviewer"] = review_metadata_to_dict(
        ReviewMetadata(
            reviewer_mode="fallback",
            model=provider.model,
            api_key_configured=provider.is_configured,
            used_llm=False,
            fallback_used=True,
            error=None if use_llm else "LLM review disabled for this call.",
        )
    )
    return fallback


def _review_with_provider(
    provider: LLMProvider,
    student: StudentProfile,
    job: JobRequirementProfile,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    raw = provider.generate(_build_review_prompt(student, job, fallback))
    parsed = _load_review_json(raw)
    return _merge_with_fallback(parsed, fallback)


def _build_review_prompt(student: StudentProfile, job: JobRequirementProfile, fallback: dict[str, Any]) -> str:
    return f"""
Return only JSON for a student's CV review against a job description.

Required schema:
{{
  "overall_assessment": "2-3 practical sentences",
  "match_level": "Excellent | Good | Fair | Poor",
  "strengths": ["specific strengths relevant to the JD"],
  "missing_skills": [
    {{"skill": "skill name", "student_score": 0, "required_level": 0, "gap": 0, "importance": 0, "required": true}}
  ],
  "missing_keywords": ["keywords present in the JD but weak or absent in the CV"],
  "improvement_suggestions": ["skills or experience the student should build"],
  "cv_improvements": ["how to rewrite or enrich the CV"],
  "priority_actions": ["highest-impact actions first"]
}}

Write every natural-language value in Vietnamese. Keep established skill, tool, framework, and model names unchanged, for example Python, SQL, React, FastAPI, Docker, RAG, LLM. Do not translate JSON keys.

Use this deterministic matching evidence as ground truth:
{json.dumps(fallback, ensure_ascii=False)}

Student profile:
{json.dumps(_student_context(student), ensure_ascii=False)}

Job profile:
{json.dumps(_job_context(job), ensure_ascii=False)}
"""


def _load_review_json(raw: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("LLM did not return a JSON object.")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM review JSON must be an object.")
    return data


def _merge_with_fallback(parsed: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(fallback)
    for field in REVIEW_FIELDS:
        value = parsed.get(field)
        if value:
            merged[field] = value
    merged["match"] = fallback["match"]
    return merged


def _fallback_review(
    student: StudentProfile,
    job: JobRequirementProfile,
    match_result: Any,
) -> dict[str, Any]:
    match_data = match_result_to_dict(match_result)
    missing_skills = [
        {
            "skill": name,
            "student_score": gap.user_score,
            "required_level": gap.required_level,
            "gap": gap.gap,
            "importance": gap.importance,
            "required": gap.required,
        }
        for name, gap in sorted(
            match_result.missing_or_weak_skills.items(),
            key=lambda item: (item[1].required, item[1].importance, item[1].gap),
            reverse=True,
        )
    ]
    missing_keywords = _missing_keywords(student, job, missing_skills)
    strengths = _strengths(student, match_result.matched_skills)
    priority_actions = _priority_actions(missing_skills, missing_keywords)

    return {
        "student_id": student.student_id,
        "job_id": job.job_id,
        "job_title": job.title,
        "company_id": job.company_id,
        "match": match_data,
        "overall_assessment": _overall_assessment(student, job, match_data["match_status"], missing_skills),
        "match_level": _match_level(match_data["match_score"], match_data["match_status"]),
        "strengths": strengths,
        "missing_skills": missing_skills,
        "missing_keywords": missing_keywords,
        "improvement_suggestions": _improvement_suggestions(missing_skills),
        "cv_improvements": _cv_improvements(missing_skills, missing_keywords),
        "priority_actions": priority_actions,
    }


def _overall_assessment(
    student: StudentProfile,
    job: JobRequirementProfile,
    match_status: str,
    missing_skills: list[dict[str, Any]],
) -> str:
    if not missing_skills:
        return (
            f"{student.name} đang ở mức {match_status} cho vị trí {job.title}. "
            "Hồ sơ CV đã bao phủ các kỹ năng bắt buộc của công việc."
        )
    top_missing = ", ".join(item["skill"] for item in missing_skills[:3])
    return (
        f"{student.name} đang ở mức {match_status} cho vị trí {job.title}. "
        f"Các khoảng cách chính cần xử lý là {top_missing}."
    )


def _match_level(score: float, status: str) -> str:
    if status == "strong_match" or score >= 0.85:
        return "Excellent"
    if status == "partial_match" or score >= 0.65:
        return "Good"
    if score >= 0.45:
        return "Fair"
    return "Poor"


def _strengths(student: StudentProfile, matched_skills: list[str]) -> list[str]:
    strengths = []
    for skill_name in matched_skills[:5]:
        skill = student.skills.get(skill_name)
        evidence = ""
        if skill and skill.evidence:
            evidence = f" Bằng chứng: {skill.evidence[0]}"
        strengths.append(f"{skill_name} đáp ứng yêu cầu trong JD.{evidence}")
    return strengths or ["CV chưa thể hiện rõ kỹ năng bắt buộc trong JD; hãy bổ sung bằng chứng cụ thể."]


def _improvement_suggestions(missing_skills: list[dict[str, Any]]) -> list[str]:
    if not missing_skills:
        return ["Tiếp tục bổ sung bằng chứng dự án để chứng minh các kỹ năng đã khớp trong bối cảnh gần với công việc thực tế."]
    return [
        f"Nâng {item['skill']} từ {item['student_score']:g} lên gần mức {item['required_level']:g} bằng dự án, môn học hoặc nhiệm vụ thực tập."
        for item in missing_skills[:5]
    ]


def _cv_improvements(missing_skills: list[dict[str, Any]], missing_keywords: list[str]) -> list[str]:
    suggestions = []
    for item in missing_skills[:3]:
        suggestions.append(f"Thêm một gạch đầu dòng thể hiện kinh nghiệm đo lường được với {item['skill']}.")
    if missing_keywords:
        suggestions.append(f"Dùng các từ khóa liên quan trong JD một cách tự nhiên khi đúng sự thật: {', '.join(missing_keywords[:6])}.")
    return suggestions or ["Giữ bằng chứng trong CV thật cụ thể: tên dự án, công cụ đã dùng, kết quả và tác động."]


def _priority_actions(missing_skills: list[dict[str, Any]], missing_keywords: list[str]) -> list[str]:
    actions = [
        f"Ưu tiên thu hẹp khoảng cách {item['skill']} trước vì kỹ năng này có trọng số cao trong JD."
        for item in missing_skills[:3]
    ]
    if missing_keywords:
        actions.append(f"Kiểm tra xem các thuật ngữ JD này có thể đưa vào CV một cách trung thực không: {', '.join(missing_keywords[:5])}.")
    return actions or ["Chuẩn bị một câu chuyện portfolio ngắn cho từng kỹ năng đã khớp trước khi ứng tuyển."]


def _missing_keywords(student: StudentProfile, job: JobRequirementProfile, missing_skills: list[dict[str, Any]]) -> list[str]:
    student_text = _normal_text(_student_search_text(student))
    job_text = _normal_text(_job_search_text(job))
    candidates = set()

    for skill_name in job.skills:
        candidates.add(skill_name)
    for item in missing_skills:
        candidates.add(str(item["skill"]))
    for keyword in TECH_KEYWORDS:
        if _normal_text(keyword) in job_text:
            candidates.add(keyword)

    missing = []
    for keyword in sorted(candidates, key=lambda value: value.lower()):
        normalized = _normal_text(keyword)
        if normalized and normalized in job_text and normalized not in student_text:
            missing.append(keyword)
    return missing[:12]


def _student_context(student: StudentProfile) -> dict[str, Any]:
    return {
        "student_id": student.student_id,
        "name": student.name,
        "skills": {
            name: {
                "score": skill.score,
                "confidence": skill.confidence,
                "evidence": skill.evidence,
                "self_rating": skill.self_rating,
            }
            for name, skill in student.skills.items()
        },
        "metadata": student.metadata,
    }


def _job_context(job: JobRequirementProfile) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "company_id": job.company_id,
        "title": job.title,
        "employment_type": job.employment_type,
        "location": job.location,
        "skills": {
            name: {
                "required_level": requirement.required_level,
                "importance": requirement.importance,
                "required": requirement.required,
            }
            for name, requirement in job.skills.items()
        },
        "raw_text": job.raw_text,
    }


def _student_search_text(student: StudentProfile) -> str:
    parts = [student.name]
    for name, skill in student.skills.items():
        parts.append(name)
        parts.extend(skill.evidence)
    parts.extend(_flatten_metadata(student.metadata))
    return "\n".join(str(part) for part in parts if part)


def _job_search_text(job: JobRequirementProfile) -> str:
    parts = [job.title, job.employment_type, job.location, job.salary_range, job.raw_text or ""]
    parts.extend(job.benefits)
    parts.extend(job.skills.keys())
    return "\n".join(str(part) for part in parts if part)


def _flatten_metadata(value: Any) -> list[str]:
    if isinstance(value, dict):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_metadata(item))
        return flattened
    if isinstance(value, list):
        flattened = []
        for item in value:
            flattened.extend(_flatten_metadata(item))
        return flattened
    if value is None:
        return []
    return [str(value)]


def _normal_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9.+#-]+", str(value).lower()))
