from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.api.identity import get_optional_active_identity
from app.modules.access.api.rbac import require_permission
from app.modules.opportunities.infrastructure.models import Job
from app.modules.recruitment.application.application_service import (
    apply_to_job,
    update_application_status,
)
from app.modules.recruitment.infrastructure.models import JobApplication
from app.modules.recruitment.schemas import ConsentUpdate, JobApplicationCreate, JobApplicationView
from app.platform.database.models import User, UserOrgRole
from app.platform.database.session import get_db
from app.shared.enum import ApplicationStatus, OrgType
from app.shared.errors import AppError, ErrorCode

router = APIRouter()


@router.get("/applications/me", response_model=list[JobApplicationView])
def get_my_applications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JobApplication]:
    return list(
        db.scalars(
            select(JobApplication)
            .where(JobApplication.student_id == current_user.id)
            .order_by(JobApplication.applied_at.desc())
        )
    )


@router.get("/{job_id}/applications", response_model=list[JobApplicationView])
def get_job_applications(
    job_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> list[JobApplication]:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    if identity and identity.org.type == OrgType.PARTNER and job.org_id != identity.org_id:
        raise AppError(
            code=ErrorCode.FORBIDDEN, message="Job belongs to another organization", status_code=403
        )
    return list(
        db.scalars(
            select(JobApplication)
            .where(JobApplication.job_id == job_id)
            .order_by(JobApplication.applied_at.desc())
        )
    )


@router.post("/{job_id}/applications", response_model=JobApplicationView, status_code=201)
def apply(
    job_id: str,
    payload: JobApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobApplication:
    payload.student_id = current_user.id
    return apply_to_job(db, job_id, payload, actor_id=current_user.id)


@router.put("/applications/{application_id}/status", response_model=JobApplicationView)
def update_app_status(
    application_id: str,
    new_status: ApplicationStatus = Query(...),
    note: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job_application", "update")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> JobApplication:
    application = db.get(JobApplication, application_id)
    job = db.get(Job, application.job_id) if application else None
    if not application or not job:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Application not found", status_code=404)
    if identity and identity.org.type == OrgType.PARTNER and job.org_id != identity.org_id:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="Application belongs to another organization",
            status_code=403,
        )
    return update_application_status(
        db,
        application_id,
        new_status,
        actor_id=current_user.id,
        note=note,
    )


@router.put("/applications/{application_id}/consent", response_model=JobApplicationView)
def update_consent(
    application_id: str,
    payload: ConsentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobApplication:
    application = db.get(JobApplication, application_id)
    if not application or application.student_id != current_user.id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Application not found", status_code=404)
    application.consent_to_unmask = payload.consent_to_unmask
    db.commit()
    db.refresh(application)
    return application
