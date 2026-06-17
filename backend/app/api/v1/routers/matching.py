from __future__ import annotations

from fastapi import APIRouter

from app.schemas.matching import (
    CompanyCandidateMatchRequest,
    MatchListResponse,
    MatchingMatrixRequest,
    StudentJobMatchRequest,
)
from app.services.matching_service import (
    match_candidates_to_job,
    match_matrix,
    match_student_to_jobs,
)

router = APIRouter()


@router.post("/student/jobs", response_model=MatchListResponse)
def match_jobs_for_student(payload: StudentJobMatchRequest) -> MatchListResponse:
    return match_student_to_jobs(payload)


@router.post("/company/candidates", response_model=MatchListResponse)
def match_candidates_for_company(payload: CompanyCandidateMatchRequest) -> MatchListResponse:
    return match_candidates_to_job(payload)


@router.post("/matrix", response_model=MatchListResponse)
def match_all_students_and_jobs(payload: MatchingMatrixRequest) -> MatchListResponse:
    return match_matrix(payload)
