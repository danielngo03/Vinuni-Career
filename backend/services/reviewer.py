"""
CV Reviewer Service - AI review of CV against a specific Job Description
"""
import json
import os
import re
from typing import Any

from openai import OpenAI

CV_REVIEW_PROMPT = """Bạn là một chuyên gia tuyển dụng và career coach. 
Hãy phân tích CV của ứng viên so với Job Description (JD) và đưa ra feedback chi tiết.

=== THÔNG TIN ỨNG VIÊN (từ CV) ===
Họ tên: {name}
Skills: {skills}
Kinh nghiệm: {experience}
Học vấn: {education}
Dự án: {projects}

=== JOB DESCRIPTION ===
Vị trí: {job_title} tại {company}
Yêu cầu kỹ năng: {required_skills}
Kỹ năng nice-to-have: {nice_to_have}
Kinh nghiệm yêu cầu: {required_experience}
Mô tả công việc: {job_description}

=== YÊU CẦU PHÂN TÍCH ===
Hãy trả về JSON (không markdown, chỉ JSON thuần):
{{
  "overall_assessment": "Đánh giá tổng quan ngắn gọn (2-3 câu)",
  "match_level": "Excellent | Good | Fair | Poor",
  "strengths": [
    "Điểm mạnh 1 của ứng viên phù hợp với JD",
    "Điểm mạnh 2",
    "..."
  ],
  "missing_skills": [
    "Kỹ năng còn thiếu 1 (có trong JD, không có trong CV)",
    "Kỹ năng còn thiếu 2",
    "..."
  ],
  "missing_keywords": [
    "Từ khóa quan trọng trong JD nhưng không xuất hiện trong CV 1",
    "Từ khóa 2",
    "..."
  ],
  "improvement_suggestions": [
    "Gợi ý cụ thể 1 để cải thiện CV hoặc bản thân",
    "Gợi ý 2",
    "Gợi ý 3",
    "..."
  ],
  "cv_improvements": [
    "Cách cải thiện phần viết CV cụ thể 1 (thêm keyword, rewording, ...)",
    "Cách cải thiện 2"
  ],
  "priority_actions": [
    "Hành động ưu tiên cao nhất cần làm ngay",
    "Hành động thứ 2"
  ]
}}

Hãy đưa ra feedback cụ thể, thực tế, hữu ích. Chỉ trả về JSON."""


def format_experience(experience_list: list[dict]) -> str:
    """Format experience list to readable string."""
    if not experience_list:
        return "Chưa có kinh nghiệm"
    parts = []
    for exp in experience_list[:5]:  # Max 5 items
        parts.append(f"- {exp.get('title', '')} tại {exp.get('company', '')} ({exp.get('duration', '')}): {exp.get('description', '')[:100]}")
    return "\n".join(parts)


def format_education(education_list: list[dict]) -> str:
    """Format education list to readable string."""
    if not education_list:
        return "Không có thông tin"
    parts = []
    for edu in education_list:
        gpa = f", GPA: {edu.get('gpa')}" if edu.get('gpa') else ""
        parts.append(f"- {edu.get('degree', '')} {edu.get('major', '')} tại {edu.get('school', '')} ({edu.get('year', '')}){gpa}")
    return "\n".join(parts)


def format_projects(projects_list: list[dict]) -> str:
    """Format projects to readable string."""
    if not projects_list:
        return "Không có dự án"
    parts = []
    for proj in projects_list[:5]:
        techs = ", ".join(proj.get('technologies', []))
        parts.append(f"- {proj.get('name', '')}: {proj.get('description', '')[:100]} [Tech: {techs}]")
    return "\n".join(parts)


def review_cv_against_job(student_profile: dict[str, Any], job: dict[str, Any]) -> dict:
    """
    Use LLM to review CV against a specific job description.

    Args:
        student_profile: Parsed CV data
        job: Job data from jobs.json

    Returns:
        Structured review with strengths, missing skills, suggestions
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or not openai_key.startswith("sk-"):
        raise ValueError("OPENAI_API_KEY không hợp lệ.")

    client = OpenAI(api_key=openai_key)
    model = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")

    prompt = CV_REVIEW_PROMPT.format(
        name=student_profile.get("name", "Ứng viên"),
        skills=", ".join(student_profile.get("skills", [])),
        experience=format_experience(student_profile.get("experience", [])),
        education=format_education(student_profile.get("education", [])),
        projects=format_projects(student_profile.get("projects", [])),
        job_title=job.get("title", ""),
        company=job.get("company", ""),
        required_skills=", ".join(job.get("required_skills", [])),
        nice_to_have=", ".join(job.get("nice_to_have", [])),
        required_experience=job.get("required_experience", ""),
        job_description=job.get("description", ""),
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Bạn là career coach chuyên nghiệp. Luôn trả về JSON hợp lệ."
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"LLM trả về format không hợp lệ: {raw[:200]}")
