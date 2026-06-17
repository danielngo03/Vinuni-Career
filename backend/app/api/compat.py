from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.schemas.matching import (
    MatchingJobInput,
    MatchingSkillRequirement,
    MatchingStudentInput,
    MatchingStudentSkill,
)
from app.services.ai_service import extract_skills
from app.services.cv_service import parse_cv_raw_text
from app.services.job_service import parse_jd_raw_text
from app.services.matching_service import score_match

router = APIRouter(tags=["frontend-compat"])

DATA_ROOT = Path(__file__).resolve().parents[2] / ".data" / "demo"
JOBS_DIR = DATA_ROOT / "jobs"
STUDENTS_DIR = DATA_ROOT / "students"
COMPANIES_DIR = DATA_ROOT / "companies"


class RawTextPayload(BaseModel):
    raw_text: str = Field(default="")
    company_id: str = Field(default="company_demo")


class MatchThresholds(BaseModel):
    strong_match: float = 0.8
    partial_match: float = 0.6


class CvPayload(BaseModel):
    raw_text: str


def _ensure_dirs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    STUDENTS_DIR.mkdir(parents=True, exist_ok=True)
    COMPANIES_DIR.mkdir(parents=True, exist_ok=True)
    if not any(COMPANIES_DIR.glob("*.json")):
        _write_json(
            COMPANIES_DIR / "company_demo.json",
            {
                "company_id": "company_demo",
                "name": "Demo Company",
                "industry": "Education technology",
                "metadata": {"source": "compat_api"},
            },
        )
    if not any(JOBS_DIR.glob("*.json")):
        _write_json(
            JOBS_DIR / "mock-frontend-intern-001.json",
            _job_from_text(
                (
                    "Frontend Intern. Required skills: JavaScript, React, TypeScript, "
                    "documentation, communication."
                ),
                company_id="company_demo",
                job_id="mock-frontend-intern-001",
                status="open",
            ),
        )
    if not any(STUDENTS_DIR.glob("*.json")):
        _write_json(
            STUDENTS_DIR / "mock-student-frontend-001.json",
            _student_from_text(
                (
                    "Chi Le\nComputer Science student. Projects with JavaScript, React, "
                    "TypeScript, Python and dashboards."
                ),
                student_id="mock-student-frontend-001",
            ),
        )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _skill_level(skill: str, text: str, base: float) -> float:
    count = len(re.findall(re.escape(skill), text, flags=re.IGNORECASE))
    return min(10.0, round(base + count * 0.8, 1))


def _skill_requirements(text: str) -> dict[str, dict[str, Any]]:
    skills = extract_skills(text)
    if not skills:
        skills = ["communication", "documentation", "python"]
    return {
        skill: {
            "required_level": _skill_level(skill, text, 6.0),
            "importance": 1.0,
            "required": index < 5,
        }
        for index, skill in enumerate(skills)
    }


def _student_skills(text: str) -> dict[str, dict[str, Any]]:
    skills = extract_skills(text)
    if not skills:
        skills = ["communication", "documentation", "python"]
    return {
        skill: {
            "score": _skill_level(skill, text, 6.5),
            "confidence": 0.82,
            "evidence": [f"Detected from CV text: {skill}"],
        }
        for skill in skills
    }


def _title_from_text(text: str) -> str:
    first = next((line.strip(" .") for line in text.splitlines() if line.strip()), "")
    if first:
        return first[:80]
    lowered = text.lower()
    if "backend" in lowered:
        return "Backend Intern"
    if "data" in lowered:
        return "Data Analyst Intern"
    return "Frontend Intern"


def _name_from_text(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first and len(first.split()) <= 5 and not any(char.isdigit() for char in first):
        return first[:80]
    return "Demo Student"


def _job_from_text(
    text: str,
    *,
    company_id: str,
    job_id: str | None = None,
    status: str = "draft",
) -> dict[str, Any]:
    return {
        "job_id": job_id or _slug("job"),
        "company_id": company_id,
        "title": _title_from_text(text),
        "status": status,
        "employment_type": "Internship",
        "location": "Hybrid",
        "salary_range": "Competitive",
        "benefits": ["Mentorship", "Project-based learning"],
        "skills": _skill_requirements(text),
        "raw_text": text,
        "metadata": {"source": "compat_api"},
    }


def _student_from_text(text: str, *, student_id: str | None = None) -> dict[str, Any]:
    return {
        "student_id": student_id or _slug("student"),
        "name": _name_from_text(text),
        "skills": _student_skills(text),
        "metadata": {"source": "compat_api", "cv_text_excerpt": text[:6000]},
    }


def _list_jobs() -> list[dict[str, Any]]:
    _ensure_dirs()
    return [_read_json(path) for path in sorted(JOBS_DIR.glob("*.json"))]


def _list_companies() -> list[dict[str, Any]]:
    _ensure_dirs()
    return [_read_json(path) for path in sorted(COMPANIES_DIR.glob("*.json"))]


def _list_students() -> list[dict[str, Any]]:
    _ensure_dirs()
    return [_read_json(path) for path in sorted(STUDENTS_DIR.glob("*.json"))]


def _get_job(job_id: str) -> dict[str, Any]:
    for job in _list_jobs():
        if job["job_id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="Job not found")


def _get_student(student_id: str) -> dict[str, Any]:
    for student in _list_students():
        if student["student_id"] == student_id:
            return student
    raise HTTPException(status_code=404, detail="Student not found")


def _match(
    job: dict[str, Any],
    student: dict[str, Any],
    thresholds: MatchThresholds,
) -> dict[str, Any]:
    result = score_match(_to_matching_student(student), _to_matching_job(job))
    score = round(result.match_score / 100, 3)
    if score >= thresholds.strong_match:
        status = "strong_match"
    elif score >= thresholds.partial_match:
        status = "partial_match"
    else:
        status = "not_match"
    gaps = {
        item.skill: {
            "user_score": item.student_score or 0,
            "required_level": item.required_level,
            "gap": round(max(item.required_level - (item.student_score or 0), 0), 1),
            "importance": item.importance,
            "required": item.required,
        }
        for item in result.skill_breakdown
        if item.status != "matched"
    }
    return {
        "job_id": job["job_id"],
        "student_id": student["student_id"],
        "student_name": student.get("name") or student["student_id"],
        "match_score": score,
        "match_status": status,
        "matched_skills": result.strengths,
        "missing_or_weak_skills": gaps,
        "explanation": " ".join(result.explanations)
        or f"{student.get('name') or student['student_id']} matches {job['title']}.",
    }


def _to_matching_job(job: dict[str, Any]) -> MatchingJobInput:
    return MatchingJobInput(
        job_id=job["job_id"],
        company_id=job.get("company_id"),
        title=job["title"],
        status=job.get("status"),
        location=job.get("location"),
        skills={
            skill: MatchingSkillRequirement(**detail)
            for skill, detail in job.get("skills", {}).items()
        },
        raw_text=job.get("raw_text"),
        metadata=job.get("metadata", {}),
    )


def _to_matching_student(student: dict[str, Any]) -> MatchingStudentInput:
    return MatchingStudentInput(
        student_id=student["student_id"],
        name=student.get("name"),
        skills={
            skill: MatchingStudentSkill(**detail)
            for skill, detail in student.get("skills", {}).items()
        },
        metadata=student.get("metadata", {}),
    )


async def _upload_text(file: UploadFile) -> str:
    content = await file.read()
    return content.decode("utf-8", errors="ignore")


@router.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "C2 Career Platform",
        "status": "ok",
        "frontend_compat": True,
        "docs": "/docs",
        "api_v1": "/api/v1",
    }


@router.post("/jobs/parse")
def parse_job(payload: RawTextPayload) -> dict[str, Any]:
    return parse_jd_raw_text(payload.raw_text, company_id=payload.company_id).model_dump()


@router.post("/jobs/parse-upload")
async def parse_job_upload(
    company_id: str = Form(default="company_demo"),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    return parse_jd_raw_text(
        await _upload_text(file),
        company_id=company_id,
        source="upload",
    ).model_dump()


@router.post("/jobs")
def save_job(job: dict[str, Any]) -> dict[str, Any]:
    _ensure_dirs()
    if not job.get("job_id"):
        job["job_id"] = _slug("job")
    _write_json(JOBS_DIR / f"{job['job_id']}.json", job)
    return job


@router.get("/jobs")
def list_jobs() -> list[dict[str, Any]]:
    return _list_jobs()


@router.get("/companies")
def list_companies() -> list[dict[str, Any]]:
    return _list_companies()


@router.get("/jobs/open")
def list_open_jobs() -> list[dict[str, Any]]:
    return [job for job in _list_jobs() if job.get("status") == "open"]


@router.post("/jobs/{job_id}/open")
def open_job(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    job["status"] = "open"
    _write_json(JOBS_DIR / f"{job_id}.json", job)
    return job


@router.post("/jobs/{job_id}/close")
def close_job(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    job["status"] = "closed"
    _write_json(JOBS_DIR / f"{job_id}.json", job)
    return job


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, str]:
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    path.unlink()
    return {"status": "deleted", "job_id": job_id}


@router.post("/jobs/{job_id}/match")
def match_job(job_id: str, thresholds: MatchThresholds) -> list[dict[str, Any]]:
    job = _get_job(job_id)
    matches = [_match(job, student, thresholds) for student in _list_students()]
    return sorted(matches, key=lambda item: item["match_score"], reverse=True)


@router.post("/students/cv/parse")
def parse_cv(
    payload: CvPayload,
    demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
) -> dict[str, Any]:
    return parse_cv_raw_text(payload.raw_text, student_id=demo_user_id).model_dump()


@router.post("/students/cv/parse-upload")
async def parse_cv_upload(
    file: UploadFile = File(...),
    demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
) -> dict[str, Any]:
    return parse_cv_raw_text(
        await _upload_text(file),
        student_id=demo_user_id,
        source="upload",
    ).model_dump()


@router.post("/students")
def save_student(student: dict[str, Any]) -> dict[str, Any]:
    _ensure_dirs()
    if not student.get("student_id"):
        student["student_id"] = _slug("student")
    _write_json(STUDENTS_DIR / f"{student['student_id']}.json", student)
    return student


@router.get("/students")
def list_students() -> list[dict[str, Any]]:
    return _list_students()


@router.get("/agents/student-profile/students")
def list_my_students() -> list[dict[str, Any]]:
    return _list_students()


@router.post("/students/{student_id}/match-jobs")
def match_student_jobs(student_id: str, thresholds: MatchThresholds) -> list[dict[str, Any]]:
    student = _get_student(student_id)
    result = [
        {"job": job, "match": _match(job, student, thresholds)}
        for job in _list_jobs()
        if job.get("status") == "open"
    ]
    return sorted(result, key=lambda item: item["match"]["match_score"], reverse=True)


@router.post("/students/{student_id}/jobs/{job_id}/review")
def review_student_job(student_id: str, job_id: str, thresholds: MatchThresholds) -> dict[str, Any]:
    student = _get_student(student_id)
    job = _get_job(job_id)
    match = _match(job, student, thresholds)
    missing = list(match["missing_or_weak_skills"].keys())
    overall_assessment = (
        f"{student['name']} is currently a "
        f"{match['match_status'].replace('_', ' ')} for this role."
    )
    missing_skills = [
        {"skill": skill, **details}
        for skill, details in match["missing_or_weak_skills"].items()
    ]
    return {
        "student_id": student_id,
        "job_id": job_id,
        "job_title": job["title"],
        "company_id": job["company_id"],
        "match": match,
        "overall_assessment": overall_assessment,
        "match_level": match["match_status"],
        "strengths": match["matched_skills"],
        "missing_skills": missing_skills,
        "missing_keywords": missing,
        "improvement_suggestions": [f"Add project evidence for {skill}." for skill in missing[:4]],
        "cv_improvements": [f"Quantify impact related to {skill}." for skill in missing[:4]],
        "priority_actions": [f"Practice and document {skill}." for skill in missing[:4]],
        "_reviewer": {
            "reviewer_mode": "offline_compat",
            "model": "deterministic",
            "api_key_configured": False,
            "used_llm": False,
            "fallback_used": True,
            "error": None,
        },
    }


@router.post("/agents/teacher-rag/detect")
def detect_teacher_source(payload: dict[str, Any]) -> dict[str, str]:
    source_url = str(payload.get("source_url", ""))
    return {"source_type": "playlist" if "list=" in source_url else "video"}


@router.post("/agents/teacher-rag/run")
def run_teacher_rag(payload: dict[str, Any]) -> dict[str, Any]:
    course_title = str(payload.get("course_title") or "Demo course")
    source_type = "playlist" if "list=" in str(payload.get("source_url", "")) else "video"
    run_id = _slug("rag")
    return {
        "run_id": run_id,
        "source_type": source_type,
        "course_title": course_title,
        "videos_found": 1,
        "videos_saved": 1,
        "videos_failed": 0,
        "chunks_created": 3,
        "chunks_output": f"backend/.data/demo/rag/{run_id}.jsonl",
        "report_output": f"backend/.data/demo/rag/{run_id}-report.json",
        "videos": [{"title": course_title, "source_url": payload.get("source_url", "")}],
    }
