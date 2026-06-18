from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user, get_registration_user
from app.modules.access.api.identity import get_active_identity
from app.modules.access.api.rbac import require_permission
from app.modules.registrations.schemas import (
    PendingRegistrationView,
    RegistrationQueueItem,
    RegistrationResubmitRequest,
    RegistrationReviewRequest,
    RegistrationView,
    StudentRegistrationCreate,
    VerificationPolicyUpdate,
    VerificationPolicyView,
)
from app.modules.registrations.service import (
    get_or_create_verification_policy,
    pending_registration_for_user,
    registration_queue,
    resubmit_registration,
    review_registration,
    submit_partner_registration,
    submit_student_registration,
    update_verification_policy,
)
from app.platform.database.models import RegistrationApplication, User, UserOrgRole
from app.platform.database.session import get_db
from app.shared.enum import OrgType, RegistrationStatus, RegistrationType
from app.shared.errors import AppError, ErrorCode

router = APIRouter()


@router.get("/me", response_model=PendingRegistrationView)
def my_registration(
    current_user: User = Depends(get_registration_user),
    db: Session = Depends(get_db),
) -> PendingRegistrationView:
    return pending_registration_for_user(db, current_user.id)


@router.post("/me/resubmit", response_model=RegistrationView)
def resubmit_my_registration(
    payload: RegistrationResubmitRequest,
    current_user: User = Depends(get_registration_user),
    db: Session = Depends(get_db),
) -> RegistrationApplication:
    return resubmit_registration(db, user_id=current_user.id, payload=payload)


@router.post("/student", response_model=RegistrationView, status_code=201)
def register_student(
    payload: StudentRegistrationCreate,
    db: Session = Depends(get_db),
) -> RegistrationApplication:
    return submit_student_registration(db, payload)


@router.post("/partner", response_model=RegistrationView, status_code=201)
async def register_partner(
    university_org_id: str = Form(...),
    full_name: str = Form(..., min_length=2, max_length=255),
    email: str = Form(...),
    password: str = Form(..., min_length=8, max_length=128),
    company_name: str = Form(..., min_length=2, max_length=255),
    tax_code: str = Form(..., min_length=5, max_length=80),
    website: str | None = Form(default=None),
    company_size: str = Form(...),
    founded_year: int | None = Form(default=None),
    headquarters_address: str = Form(...),
    company_description: str = Form(..., min_length=20),
    representative_name: str = Form(...),
    representative_title: str = Form(...),
    representative_phone: str = Form(...),
    representative_email: str = Form(...),
    industry_ids_json: str = Form(...),
    primary_industry_id: str = Form(...),
    logo: UploadFile = File(...),
    business_license: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> RegistrationApplication:
    try:
        industry_ids = json.loads(industry_ids_json)
    except json.JSONDecodeError as exc:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="industry_ids_json must be valid JSON",
            status_code=400,
        ) from exc
    if not isinstance(industry_ids, list) or not industry_ids:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="At least one industry is required",
            status_code=400,
        )
    return submit_partner_registration(
        db,
        university_org_id=university_org_id,
        full_name=full_name,
        email=email,
        password=password,
        company_name=company_name,
        tax_code=tax_code,
        website=website,
        company_size=company_size,
        founded_year=founded_year,
        headquarters_address=headquarters_address,
        company_description=company_description,
        representative_name=representative_name,
        representative_title=representative_title,
        representative_phone=representative_phone,
        representative_email=representative_email,
        industry_ids=[str(item) for item in industry_ids],
        primary_industry_id=primary_industry_id,
        logo_name=logo.filename or "company-logo",
        logo_type=logo.content_type or "application/octet-stream",
        logo_content=await logo.read(),
        license_name=business_license.filename or "business-license",
        license_type=business_license.content_type or "application/octet-stream",
        license_content=await business_license.read(),
    )


@router.get("/review-queue", response_model=list[RegistrationQueueItem])
def get_review_queue(
    status: RegistrationStatus | None = Query(default=None),
    identity: UserOrgRole = Depends(get_active_identity),
    _: User = Depends(require_permission("registration", "review")),
    db: Session = Depends(get_db),
) -> list[RegistrationQueueItem]:
    if identity.org.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="University identity required",
            status_code=403,
        )
    return registration_queue(db, university_org_id=identity.org_id, status=status)


@router.get(
    "/verification-policy/{registration_type}",
    response_model=VerificationPolicyView,
)
def get_verification_policy(
    registration_type: RegistrationType,
    identity: UserOrgRole = Depends(get_active_identity),
    _: User = Depends(require_permission("registration", "review")),
    db: Session = Depends(get_db),
):
    if identity.org.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="University identity required",
            status_code=403,
        )
    policy = get_or_create_verification_policy(
        db,
        university_org_id=identity.org_id,
        registration_type=registration_type,
    )
    db.commit()
    db.refresh(policy)
    return policy


@router.put(
    "/verification-policy/{registration_type}",
    response_model=VerificationPolicyView,
)
def put_verification_policy(
    registration_type: RegistrationType,
    payload: VerificationPolicyUpdate,
    identity: UserOrgRole = Depends(get_active_identity),
    _: User = Depends(require_permission("registration", "review")),
    db: Session = Depends(get_db),
):
    if identity.org.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="University identity required",
            status_code=403,
        )
    return update_verification_policy(
        db,
        university_org_id=identity.org_id,
        registration_type=registration_type,
        payload=payload,
    )


@router.post("/{application_id}/review", response_model=RegistrationView)
def review(
    application_id: str,
    payload: RegistrationReviewRequest,
    identity: UserOrgRole = Depends(get_active_identity),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_permission("registration", "review")),
    db: Session = Depends(get_db),
) -> RegistrationApplication:
    if identity.org.type != OrgType.UNIVERSITY:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="University identity required",
            status_code=403,
        )
    return review_registration(
        db,
        application_id=application_id,
        university_org_id=identity.org_id,
        reviewer_id=current_user.id,
        payload=payload,
    )
