"""
Review Router - AI-powered CV review against specific Job Descriptions
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.reviewer import review_cv_against_job
from services.session_store import get_profile

router = APIRouter()

JOBS_FILE = Path(__file__).parent.parent / "data" / "jobs.json"


def load_jobs() -> list[dict]:
    with open(JOBS_FILE, encoding="utf-8") as f:
        return json.load(f)


class ReviewRequest(BaseModel):
    session_id: str
    job_id: str


@router.post("/")
async def review_cv(request: ReviewRequest):
    """
    AI review of student's CV against a specific Job Description.

    Returns:
    - overall_assessment: Đánh giá tổng quan
    - match_level: Excellent | Good | Fair | Poor
    - strengths: Điểm mạnh phù hợp với JD
    - missing_skills: Kỹ năng còn thiếu
    - missing_keywords: Từ khóa thiếu trong CV
    - improvement_suggestions: Gợi ý cải thiện bản thân
    - cv_improvements: Gợi ý cải thiện cách viết CV
    - priority_actions: Hành động ưu tiên cần làm ngay
    """
    # Get student profile
    profile = get_profile(request.session_id)
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy CV cho session '{request.session_id}'. Hãy upload CV trước."
        )

    # Get job details
    jobs = load_jobs()
    job = next((j for j in jobs if j["id"] == request.job_id), None)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy job '{request.job_id}'."
        )

    # Call AI review service
    try:
        review_result = review_cv_against_job(profile, job)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi khi gọi AI review: {str(e)}"
        )

    return {
        "session_id": request.session_id,
        "student_name": profile.get("name", "Ứng viên"),
        "job_id": request.job_id,
        "job_title": job["title"],
        "company": job["company"],
        "review": review_result,
    }
