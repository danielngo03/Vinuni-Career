"""
Jobs Router - Endpoints for job listings and matching scores
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.matcher import match_all_jobs
from services.session_store import get_profile

router = APIRouter()

# Load jobs from JSON file
JOBS_FILE = Path(__file__).parent.parent / "data" / "jobs.json"


def load_jobs() -> list[dict]:
    """Load job listings from JSON file."""
    if not JOBS_FILE.exists():
        return []
    with open(JOBS_FILE, encoding="utf-8") as f:
        return json.load(f)


@router.get("/")
async def list_jobs(
    title: str = Query(None, description="Filter by job title (case-insensitive)"),
    location: str = Query(None, description="Filter by location"),
    type: str = Query(None, description="Filter by job type (Full-time/Internship)"),
):
    """
    Get all job listings with optional filters.
    """
    jobs = load_jobs()

    if title:
        jobs = [j for j in jobs if title.lower() in j["title"].lower()]
    if location:
        jobs = [j for j in jobs if location.lower() in j["location"].lower()]
    if type:
        jobs = [j for j in jobs if type.lower() in j.get("type", "").lower()]

    return {
        "total": len(jobs),
        "jobs": jobs
    }


@router.get("/{job_id}")
async def get_job(job_id: str):
    """
    Get a specific job by ID.
    """
    jobs = load_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy job '{job_id}'")
    return job


class MatchRequest(BaseModel):
    session_id: str


@router.post("/match")
async def match_jobs(request: MatchRequest):
    """
    Calculate matching scores between student's CV profile and all jobs.

    Requires a session_id from a previous CV upload.
    Returns jobs sorted by matching score (highest first).
    """
    profile = get_profile(request.session_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy CV cho session '{request.session_id}'. Hãy upload CV trước."
        )

    jobs = load_jobs()
    if not jobs:
        raise HTTPException(status_code=500, detail="Không tìm thấy dữ liệu job.")

    results = match_all_jobs(profile, jobs)

    return {
        "session_id": request.session_id,
        "student_name": profile.get("name", "Unknown"),
        "student_skills": profile.get("skills", []),
        "total_jobs": len(results),
        "results": results,
    }


@router.post("/match/{job_id}")
async def match_single_job(job_id: str, request: MatchRequest):
    """
    Calculate matching score for a single job.
    """
    profile = get_profile(request.session_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy CV cho session '{request.session_id}'."
        )

    jobs = load_jobs()
    job = next((j for j in jobs if j["id"] == job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy job '{job_id}'")

    from services.matcher import calculate_matching_score
    result = calculate_matching_score(profile, job)

    return {
        "session_id": request.session_id,
        "student_name": profile.get("name", "Unknown"),
        **result,
        "job_details": job,
    }
