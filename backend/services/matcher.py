"""
Matching Score Service - Calculate how well a student profile matches job requirements
"""
from typing import Any


def normalize_skill(skill: str) -> str:
    """Normalize skill name for comparison (lowercase, strip)."""
    return skill.lower().strip()


def calculate_skill_overlap(student_skills: list[str], job_skills: list[str]) -> tuple[float, list[str], list[str]]:
    """
    Calculate skill overlap between student and job.

    Returns:
        (score_0_to_1, matched_skills, missing_skills)
    """
    if not job_skills:
        return 1.0, [], []

    # Normalize
    student_set = {normalize_skill(s) for s in student_skills}
    job_set = {normalize_skill(s) for s in job_skills}

    # Exact matches
    matched = job_set & student_set
    missing = job_set - student_set

    # Partial matches (e.g., "react.js" matches "react")
    for s_skill in student_set:
        for j_skill in list(missing):
            if s_skill in j_skill or j_skill in s_skill:
                matched.add(j_skill)
                missing.discard(j_skill)

    score = len(matched) / len(job_set) if job_set else 0.0

    # Get original casing from job_skills for display
    matched_display = [s for s in job_skills if normalize_skill(s) in matched]
    missing_display = [s for s in job_skills if normalize_skill(s) in missing]

    return score, matched_display, missing_display


def parse_experience_years(experience_str: str) -> float:
    """Parse experience requirement string to years."""
    if not experience_str:
        return 0.0

    s = experience_str.lower()
    
    # "0-1 năm" -> 0
    # "1-3 năm" -> 1
    # "sinh viên" -> 0
    if "sinh viên" in s or "intern" in s:
        return 0.0

    import re
    numbers = re.findall(r'\d+(?:\.\d+)?', s)
    if numbers:
        return float(numbers[0])  # Lấy số nhỏ nhất (min requirement)
    return 0.0


def calculate_experience_score(student_years: float, required_years: float) -> float:
    """Score 0-1 based on experience match."""
    if required_years == 0:
        return 1.0
    if student_years >= required_years:
        return 1.0
    # Partial credit nếu gần đủ
    ratio = student_years / required_years
    return min(ratio, 1.0)


def calculate_matching_score(student_profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """
    Calculate comprehensive matching score between student and job.

    Weights:
    - Skills: 70% (most important)
    - Experience: 30%

    Returns dict with score, matched_skills, missing_skills, breakdown
    """
    student_skills = student_profile.get("skills", [])
    student_exp_years = student_profile.get("total_experience_years", 0) or 0

    required_skills = job.get("required_skills", [])
    required_exp_str = job.get("required_experience", "")
    required_exp_years = parse_experience_years(required_exp_str)

    # --- Skill Score (70%) ---
    skill_score, matched_skills, missing_skills = calculate_skill_overlap(
        student_skills, required_skills
    )

    # --- Experience Score (30%) ---
    exp_score = calculate_experience_score(student_exp_years, required_exp_years)

    # --- Weighted Total ---
    SKILL_WEIGHT = 0.70
    EXP_WEIGHT = 0.30

    total_score = (skill_score * SKILL_WEIGHT) + (exp_score * EXP_WEIGHT)
    total_percent = round(total_score * 100, 1)

    return {
        "job_id": job["id"],
        "job_title": job["title"],
        "company": job["company"],
        "location": job.get("location", ""),
        "type": job.get("type", ""),
        "salary": job.get("salary", ""),
        "matching_score": total_percent,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "breakdown": {
            "skill_score": round(skill_score * 100, 1),
            "skill_weight": f"{int(SKILL_WEIGHT * 100)}%",
            "experience_score": round(exp_score * 100, 1),
            "experience_weight": f"{int(EXP_WEIGHT * 100)}%",
        }
    }


def match_all_jobs(student_profile: dict[str, Any], jobs: list[dict]) -> list[dict]:
    """
    Calculate matching score for all jobs and return sorted list.

    Returns list sorted by matching_score descending.
    """
    results = []
    for job in jobs:
        match_result = calculate_matching_score(student_profile, job)
        results.append(match_result)

    # Sort by matching score (highest first)
    results.sort(key=lambda x: x["matching_score"], reverse=True)
    return results
