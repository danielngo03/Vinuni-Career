"""Onboarding HTTP routes (``/api/v1/onboarding/*``).

All routes require a valid Bearer token (authenticated user). Role selection
and beyond also require email_verified. The redirect guard on the frontend
reads ``GET /onboarding/status`` to decide which wizard page to show.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import context_from_request
from app.modules.onboarding.api.schemas import (
    EmployerDocStatusResponse,
    EmployerInfoRequest,
    OnboardingStatusResponse,
    SeekerProfileRequest,
    SetRoleRequest,
    SetSeekerTypeRequest,
    StudentVerifyRequestBody,
)
from app.modules.onboarding.application import onboarding_service
from app.shared.exceptions import AuthRequiredError
from app.shared.responses import success
from app.shared.storage import save_upload

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _user_id(auth: CurrentAuth):
    user_id = auth.principal.user_id
    if user_id is None:
        raise AuthRequiredError()
    return user_id


@router.get("/status", summary="Get current onboarding wizard step")
async def get_status(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await onboarding_service.get_status(session, user_id=_user_id(auth))
    return success(OnboardingStatusResponse(**data).model_dump())


@router.post("/role", summary="Select onboarding role (job_seeker | employer)")
async def set_role(
    body: SetRoleRequest,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    state = await onboarding_service.set_role(
        session,
        user_id=_user_id(auth),
        role=body.role,
        ctx=context_from_request(request),
    )
    await session.commit()
    return success({"current_step": state.current_step, "role": state.role})


@router.post(
    "/seeker-type",
    summary="Select seeker sub-type (student | professional | fresh_graduate)",
)
async def set_seeker_type(
    body: SetSeekerTypeRequest,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    state = await onboarding_service.set_seeker_type(
        session,
        user_id=_user_id(auth),
        seeker_type=body.seeker_type,
        ctx=context_from_request(request),
    )
    await session.commit()
    return success({"current_step": state.current_step, "seeker_type": state.seeker_type})


@router.post("/seeker-profile", summary="Save seeker profile info (professional/fresh graduate)")
async def save_seeker_profile(
    body: SeekerProfileRequest,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    state = await onboarding_service.save_seeker_profile(
        session,
        user_id=_user_id(auth),
        profile_data=body.model_dump(exclude_none=True),
        ctx=context_from_request(request),
    )
    await session.commit()
    return success({"current_step": state.current_step, "is_complete": state.is_complete})


@router.post("/student-verify/request", summary="Request student email OTP verification")
async def request_student_verify(
    body: StudentVerifyRequestBody,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await onboarding_service.request_student_verify(
        session,
        user_id=_user_id(auth),
        university_name=body.university_name,
        student_id_number=body.student_id_number,
        student_email=body.student_email,
        ctx=context_from_request(request),
    )
    await session.commit()
    return success(result)


@router.post(
    "/student-verify/confirm",
    summary="Confirm student email OTP + upload student ID card",
)
async def confirm_student_verify(
    request: Request,
    otp_code: str = Form(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    id_card_image: UploadFile | None = File(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    file_path: str | None = None
    if id_card_image is not None:
        file_path = await save_upload(
            file=id_card_image,
            folder=f"student_id_cards/{_user_id(auth)}",
            allowed_mime={"image/jpeg", "image/png", "image/webp"},
            max_bytes=5 * 1024 * 1024,
        )

    state = await onboarding_service.confirm_student_verify(
        session,
        user_id=_user_id(auth),
        otp_code=otp_code,
        id_card_file_path=file_path,
        ctx=context_from_request(request),
    )
    await session.commit()
    return success({"current_step": state.current_step})


@router.post("/employer-info", summary="Save employer company info")
async def save_employer_info(
    body: EmployerInfoRequest,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    state = await onboarding_service.save_employer_info(
        session,
        user_id=_user_id(auth),
        company_name=body.company_name,
        industry=body.industry,
        company_size=body.company_size,
        address=body.address,
        registrant_role=body.registrant_role,
        ctx=context_from_request(request),
    )
    await session.commit()
    return success({"current_step": state.current_step})


@router.post(
    "/employer-docs",
    summary="Upload business registration document; triggers AI verification",
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_employer_docs(
    request: Request,
    document: UploadFile = File(...),
    tax_id: str | None = Form(default=None, max_length=20),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    document_path = await save_upload(
        file=document,
        folder=f"employer_docs/{_user_id(auth)}",
        allowed_mime={"application/pdf", "image/jpeg", "image/png"},
        max_bytes=onboarding_service.EMPLOYER_DOC_MAX_BYTES,
    )
    result = await onboarding_service.submit_employer_docs(
        session,
        user_id=_user_id(auth),
        document_path=document_path,
        tax_id=tax_id,
        ctx=context_from_request(request),
    )
    await session.commit()
    return success(result)


@router.get("/employer-docs/status", summary="Poll AI document verification status")
async def get_employer_doc_status(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await onboarding_service.get_employer_doc_status(session, user_id=_user_id(auth))
    return success(EmployerDocStatusResponse(**data).model_dump())
