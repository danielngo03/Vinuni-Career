from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
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
    JobDeleteResponse,
    JobFormParseRequest,
    JobManagementCreate,
    JobManagementView,
    JobModerationRequest,
    JobParseResponse,
    JobRawParseRequest,
    JobStatusUpdateRequest,
    JobView,
)
from app.services.job_service import (
    apply_to_job,
    create_managed_job,
    create_job,
    delete_managed_job,
    list_jobs,
    list_managed_jobs,
    moderate_job,
    parse_jd_form,
    parse_jd_raw_text,
    update_managed_job_status,
)

router = APIRouter()


@router.post("/parse/raw", response_model=JobParseResponse)
def parse_job_from_raw_text(payload: JobRawParseRequest) -> JobParseResponse:
    return parse_jd_raw_text(
        payload.raw_text,
        job_id=payload.job_id,
        company_id=payload.company_id,
    )


@router.post("/parse/form", response_model=JobParseResponse)
def parse_job_from_form(payload: JobFormParseRequest) -> JobParseResponse:
    return parse_jd_form(payload)


@router.post("/parse/upload", response_model=JobParseResponse)
async def parse_job_from_upload(
    file: UploadFile = File(...),
    job_id: str | None = None,
    company_id: str | None = None,
) -> JobParseResponse:
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")
    return parse_jd_raw_text(text, job_id=job_id, company_id=company_id, source="upload")


@router.post("", response_model=JobView, status_code=201)
def post_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
) -> Job:
    return create_job(db, payload, actor_id=current_user.id)


@router.post("/manage", response_model=JobManagementView, status_code=201)
def create_job_for_management(
    payload: JobManagementCreate,
    db: Session = Depends(get_db),
) -> JobManagementView:
    return create_managed_job(db, payload)


@router.get("/manage", response_model=list[JobManagementView])
def get_managed_jobs(
    page: PageParams = Depends(),
    org_id: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
    db: Session = Depends(get_db),
) -> list[JobManagementView]:
    return list_managed_jobs(
        db,
        org_id=org_id,
        status_filter=status,
        limit=page.limit,
        offset=page.offset,
    )


@router.patch("/{job_id}/status", response_model=JobManagementView)
def update_job_status(
    job_id: str,
    payload: JobStatusUpdateRequest,
    db: Session = Depends(get_db),
) -> JobManagementView:
    return update_managed_job_status(db, job_id, payload)


@router.delete("/{job_id}", response_model=JobDeleteResponse)
def delete_job(
    job_id: str,
    db: Session = Depends(get_db),
) -> JobDeleteResponse:
    return delete_managed_job(db, job_id)


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
