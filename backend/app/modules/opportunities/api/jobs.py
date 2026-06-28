from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.api.identity import get_optional_active_identity
from app.modules.access.api.rbac import require_permission
from app.modules.opportunities.application.job_service import (
    count_jobs,
    create_blank_job,
    create_job,
    list_jobs,
    moderate_job,
    reanalyze_job,
    update_job,
)
from app.modules.opportunities.infrastructure.models import Bookmark, Job
from app.modules.opportunities.schemas import JobCreate, JobModerationRequest, JobPage, JobUpdate, JobView
from app.platform.database.models import User, UserOrgRole
from app.platform.database.models.student import StudentProfile
from app.platform.database.session import get_db
from app.shared.enum import JobStatus, OrgType
from app.shared.errors import AppError, ErrorCode
from app.shared.schemas import PageParams

router = APIRouter()


@router.post("", response_model=JobView, status_code=201)
def post_job(
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> Job:
    if identity:
        if identity.org.type != OrgType.PARTNER:
            raise AppError(
                code=ErrorCode.FORBIDDEN, message="Partner identity required", status_code=403
            )
        if payload.org_id and payload.org_id != identity.org_id:
            raise AppError(
                code=ErrorCode.FORBIDDEN, message="Organization mismatch", status_code=403
            )
        payload.org_id = identity.org_id
        if identity.dept_id:
            payload.dept_id = identity.dept_id
    if not payload.org_id:
        raise AppError(
            code=ErrorCode.BAD_REQUEST, message="Organization is required", status_code=400
        )
    return create_job(db, payload, actor_id=current_user.id)


@router.post("/blank", response_model=JobView, status_code=201)
def post_blank_job(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> Job:
    if not identity or identity.org.type != OrgType.PARTNER:
        raise AppError(code=ErrorCode.FORBIDDEN, message="Partner identity required", status_code=403)
    return create_blank_job(
        db,
        org_id=identity.org_id,
        dept_id=identity.dept_id,
        actor_id=current_user.id,
    )


@router.get("", response_model=list[JobView])
def get_jobs(
    page: PageParams = Depends(),
    org_id: str | None = Query(default=None),
    status: JobStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Job]:
    return list_jobs(db, org_id=org_id, status_filter=status, limit=page.limit, offset=page.offset)


@router.get("/page", response_model=JobPage)
def get_jobs_page(
    page: PageParams = Depends(),
    org_id: str | None = Query(default=None),
    status: JobStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> JobPage:
    items = list_jobs(
        db,
        org_id=org_id,
        status_filter=status,
        limit=page.limit,
        offset=page.offset,
    )
    return JobPage(
        items=[JobView.model_validate(item) for item in items],
        total=count_jobs(db, org_id=org_id, status_filter=status),
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/saved", response_model=list[JobView])
def get_saved_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Job]:
    stmt = (
        select(Job)
        .join(Bookmark, Bookmark.job_id == Job.id)
        .where(Bookmark.student_id == current_user.id, Job.deleted_at.is_(None))
        .order_by(Bookmark.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.get("/{job_id}", response_model=JobView)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    return job


@router.patch("/{job_id}", response_model=JobView)
def patch_job(
    job_id: str,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    if identity:
        if identity.org.type != OrgType.PARTNER:
            raise AppError(
                code=ErrorCode.FORBIDDEN, message="Partner identity required", status_code=403
            )
        if job.org_id != identity.org_id:
            raise AppError(code=ErrorCode.FORBIDDEN, message="Organization mismatch", status_code=403)
    return update_job(db, job_id, payload, actor_id=current_user.id)


@router.post("/{job_id}/reanalyze", response_model=JobView)
def reanalyze(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    if identity:
        if identity.org.type != OrgType.PARTNER:
            raise AppError(
                code=ErrorCode.FORBIDDEN, message="Partner identity required", status_code=403
            )
        if job.org_id != identity.org_id:
            raise AppError(code=ErrorCode.FORBIDDEN, message="Organization mismatch", status_code=403)
    return reanalyze_job(db, job_id, actor_id=current_user.id)


@router.post("/{job_id}/moderate", response_model=JobView)
def moderate(
    job_id: str,
    payload: JobModerationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "moderate")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> Job:
    if identity and identity.org.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.FORBIDDEN, message="University identity required", status_code=403
        )
    return moderate_job(db, job_id, payload, actor_id=current_user.id)


@router.post("/{job_id}/bookmarks", status_code=201)
def bookmark_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    student = db.get(StudentProfile, current_user.id)
    if not student:
        raise AppError(
            code=ErrorCode.FORBIDDEN, message="Only students can bookmark jobs", status_code=403
        )
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    existing = db.scalar(
        select(Bookmark).where(Bookmark.student_id == student.id, Bookmark.job_id == job_id)
    )
    if not existing:
        db.add(Bookmark(student_id=student.id, job_id=job_id))
        db.commit()
    return {"status": "ok", "message": "Job bookmarked"}


@router.delete("/{job_id}/bookmarks")
def unbookmark_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    bookmark = db.scalar(
        select(Bookmark).where(
            Bookmark.student_id == current_user.id,
            Bookmark.job_id == job_id,
        )
    )
    if bookmark:
        db.delete(bookmark)
        db.commit()
    return {"status": "ok", "message": "Job unbookmarked"}
