from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction.gemini_document_jd import (
    GeminiJDExtractionError,
    extract_jd_from_pdf,
    extract_jd_from_text,
)
from app.ai.extraction.schemas import JDExtraction
from app.ai.ingestion import inspect_upload
from app.ai.ingestion.gatekeeper import extract_text_for_gatekeeping
from app.modules.access.api.auth import get_current_user
from app.modules.access.api.identity import get_optional_active_identity
from app.modules.access.api.rbac import require_permission
from app.modules.opportunities.application.job_service import (
    apply_job_action,
    cancel_job_scheduled_action,
    count_jobs,
    create_blank_job,
    create_job,
    list_jobs,
    list_job_scheduled_actions,
    moderate_job,
    reanalyze_job,
    run_due_job_scheduled_actions,
    schedule_job_action,
    update_job,
)
from app.modules.opportunities.infrastructure.models import Bookmark, Job
from app.modules.opportunities.schemas import (
    JobActionRequest,
    JobCreate,
    JobModerationRequest,
    JobPage,
    JobScheduleCreate,
    JobScheduleView,
    JobUpdate,
    JobView,
)
from app.platform.database.models import User, UserOrgRole
from app.platform.database.models.student import StudentProfile
from app.platform.database.session import get_db
from app.shared.config import settings
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


@router.post("/analyze-upload", response_model=JDExtraction)
async def analyze_job_upload(
    upload: UploadFile = File(..., alias="file"),
    _: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> JDExtraction:
    if not identity or identity.org.type != OrgType.PARTNER:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="Partner identity required",
            status_code=403,
        )
    content = await upload.read()
    decision = inspect_upload(
        content,
        declared_content_type=upload.content_type,
        filename=upload.filename,
    )
    if decision.route == "reject":
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="; ".join(decision.reasons),
            status_code=400,
        )
    try:
        if decision.detected_kind == "pdf":
            return extract_jd_from_pdf(content)
        text = extract_text_for_gatekeeping(content, decision.detected_kind)
        if not text.strip():
            raise AppError(
                code=ErrorCode.BAD_REQUEST,
                message="Unable to extract text from this JD file.",
                status_code=400,
            )
        return extract_jd_from_text(text)
    except GeminiJDExtractionError as exc:
        raise AppError(
            code=ErrorCode.UPSTREAM_UNAVAILABLE,
            message=f"Unable to analyze this JD with Gemini right now: {exc}",
            status_code=502,
        ) from exc


@router.get("/schedules/clock")
def get_schedule_clock(
    _: User = Depends(require_permission("job", "create")),
) -> dict:
    timezone = _app_timezone()
    return {
        "timezone": getattr(timezone, "key", "UTC"),
        "now": datetime.now(timezone).isoformat(),
    }


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


@router.post("/{job_id}/actions", response_model=JobView)
def run_job_action(
    job_id: str,
    payload: JobActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
) -> Job:
    job = _require_partner_job(db, job_id, identity)
    return apply_job_action(db, job.id, payload, actor_id=current_user.id)


@router.get("/{job_id}/schedules", response_model=list[JobScheduleView])
def list_schedules(
    job_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
):
    job = _require_partner_job(db, job_id, identity)
    return list_job_scheduled_actions(db, job.id)


@router.post("/{job_id}/schedules", response_model=JobScheduleView, status_code=201)
def create_schedule(
    job_id: str,
    payload: JobScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
):
    job = _require_partner_job(db, job_id, identity)
    return schedule_job_action(db, job.id, payload, actor_id=current_user.id)


@router.delete("/{job_id}/schedules/{schedule_id}", response_model=JobScheduleView)
def cancel_schedule(
    job_id: str,
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("job", "create")),
    identity: UserOrgRole | None = Depends(get_optional_active_identity),
):
    job = _require_partner_job(db, job_id, identity)
    return cancel_job_scheduled_action(db, job.id, schedule_id, actor_id=current_user.id)


@router.post("/schedules/run-due")
def run_due_schedules(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("job", "moderate")),
) -> dict:
    return {"executed": run_due_job_scheduled_actions(db)}


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


def _require_partner_job(
    db: Session,
    job_id: str,
    identity: UserOrgRole | None,
) -> Job:
    job = db.get(Job, job_id)
    if not job or job.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Job not found", status_code=404)
    if identity:
        if identity.org.type != OrgType.PARTNER:
            raise AppError(
                code=ErrorCode.FORBIDDEN,
                message="Partner identity required",
                status_code=403,
            )
        if job.org_id != identity.org_id:
            raise AppError(code=ErrorCode.FORBIDDEN, message="Organization mismatch", status_code=403)
    return job


def _app_timezone():
    try:
        return ZoneInfo(settings.app_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")
