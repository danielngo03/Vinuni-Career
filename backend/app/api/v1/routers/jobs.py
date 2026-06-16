from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.rbac import require_permission
from app.domain.enum import JobStatus
from app.infra.database.models import Job, JobApplication, User
from app.infra.database.session import get_db
from app.schemas.common import PageParams
from app.schemas.jobs import (
    JobApplicationCreate,
    JobApplicationView,
    JobCreate,
    JobModerationRequest,
    JobView,
)
from app.services.job_service import apply_to_job, create_job, list_jobs, moderate_job

router = APIRouter()


@router.post("", response_model=JobView, status_code=201)
def post_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
) -> Job:
    return create_job(db, payload, actor_id=current_user.id)


@router.get("", response_model=list[JobView])
def get_jobs(
    page: PageParams = Depends(),
    org_id: str | None = Query(default=None),
    status: JobStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Job]:
    return list_jobs(db, org_id=org_id, status_filter=status, limit=page.limit, offset=page.offset)


@router.post("/{job_id}/moderate", response_model=JobView)
def moderate(
    job_id: str,
    payload: JobModerationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "moderate")),
) -> Job:
    return moderate_job(db, job_id, payload, actor_id=current_user.id)


@router.post("/{job_id}/applications", response_model=JobApplicationView, status_code=201)
def apply(
    job_id: str,
    payload: JobApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobApplication:
    return apply_to_job(db, job_id, payload, actor_id=current_user.id)
