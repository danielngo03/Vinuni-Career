"""Onboarding use cases.

Handles the post-registration wizard: role selection, seeker sub-type/profile,
student verification (secondary email OTP + AI card check), and employer info
+ document upload. All writes are guarded by email-verified check.

Step machine:
  job_seeker: role_select → seeker_type → seeker_profile → [student_verify →] complete
  employer:   role_select → employer_info → employer_docs → pending

Persona assignment happens at role selection:
  job_seeker → persona stays 'student' (covers all seeker sub-types)
  employer   → persona updated to 'partner_member' once employer_docs submitted
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.auth_service import (
    PURPOSE_STUDENT_EMAIL,
    _invalidate_outstanding,
    _issue_email_verification,
    verify_email_otp,
)
from app.modules.auth.application.context import RequestContext
from app.modules.onboarding.domain.models import OnboardingState, StudentVerification
from app.modules.organization.application import partner_registration_facade
from app.modules.users.application import user_service
from app.modules.users.application.user_write_facade import update_identity_persona
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ValidationFailedError,
)
from app.shared.exceptions import (
    ResourceNotFoundError as NotFoundError,
)

ROLE_JOB_SEEKER = "job_seeker"
ROLE_EMPLOYER = "employer"

SEEKER_STUDENT = "student"
SEEKER_PROFESSIONAL = "professional"
SEEKER_FRESH_GRADUATE = "fresh_graduate"

VALID_ROLES = {ROLE_JOB_SEEKER, ROLE_EMPLOYER}
VALID_SEEKER_TYPES = {SEEKER_STUDENT, SEEKER_PROFESSIONAL, SEEKER_FRESH_GRADUATE}

# Max employer doc upload: 10 MB
EMPLOYER_DOC_MAX_BYTES = 10 * 1024 * 1024
EMPLOYER_DOC_ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


def _audit_ctx(ctx: RequestContext, *, actor_id: uuid.UUID) -> AuditContext:
    return AuditContext(actor_id=actor_id, ip=ctx.ip, user_agent=ctx.user_agent)


async def get_or_create_onboarding_state(
    session: AsyncSession, *, user_id: uuid.UUID
) -> OnboardingState:
    state = (
        await session.execute(select(OnboardingState).where(OnboardingState.user_id == user_id))
    ).scalar_one_or_none()
    if state is None:
        state = OnboardingState(user_id=user_id, current_step="role_select")
        session.add(state)
        await session.flush()
    return state


async def get_status(session: AsyncSession, *, user_id: uuid.UUID) -> dict:
    """Return current onboarding state for redirect guard / frontend wizard."""
    user = await user_service.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("user_not_found")
    state = await get_or_create_onboarding_state(session, user_id=user_id)
    student_verif = (
        await session.execute(
            select(StudentVerification).where(StudentVerification.user_id == user_id)
        )
    ).scalar_one_or_none()
    employer_req = await partner_registration_facade.get_by_user(session, user_id)
    current_step = state.current_step
    is_complete = state.is_complete

    # Invited/seeded org-scoped accounts can exist without having walked through
    # the self-serve onboarding wizard. New local registrations still start with
    # the default student identity, so this bypass only applies to already
    # provisioned university/partner identities.
    identity = await user_service.primary_identity(session, user_id)
    if (
        state.role is None
        and identity is not None
        and identity.persona in {"partner_member", "university_staff"}
        and user.is_email_verified
    ):
        current_step = "complete"
        is_complete = True

    # Partner registration approval is completed by a university/admin workflow
    # outside the onboarding wizard. Reconcile the effective state here so the
    # frontend guard never keeps an approved partner trapped on `/onboarding`.
    if state.role == ROLE_EMPLOYER and employer_req is not None:
        if employer_req.status == "approved":
            current_step = "complete"
            is_complete = True
        elif employer_req.status == "rejected" and state.current_step == "pending":
            current_step = "employer_docs"
            is_complete = False

    return {
        "current_step": current_step,
        "role": state.role,
        "seeker_type": state.seeker_type,
        "is_complete": is_complete,
        "email_verified": user.is_email_verified,
        "student_verification_status": student_verif.status if student_verif else None,
        "employer_doc_status": employer_req.ai_doc_status if employer_req else None,
        "employer_request_status": employer_req.status if employer_req else None,
    }


async def set_role(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    role: str,
    ctx: RequestContext,
) -> OnboardingState:
    if role not in VALID_ROLES:
        raise ValidationFailedError("invalid_role", details={"role": role})

    user = await user_service.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("user_not_found")
    if not user.is_email_verified:
        raise PermissionDeniedError("email_not_verified")

    state = await get_or_create_onboarding_state(session, user_id=user_id)
    state.role = role
    state.current_step = "seeker_type" if role == ROLE_JOB_SEEKER else "employer_info"
    state.updated_at = datetime.now(tz=UTC)

    await write_audit(
        session,
        action="onboarding.role_selected",
        resource_type="user",
        resource_id=user_id,
        context=_audit_ctx(ctx, actor_id=user_id),
        after={"role": role},
    )
    await session.flush()
    return state


async def set_seeker_type(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    seeker_type: str,
    ctx: RequestContext,
) -> OnboardingState:
    if seeker_type not in VALID_SEEKER_TYPES:
        raise ValidationFailedError("invalid_seeker_type", details={"seeker_type": seeker_type})

    state = await get_or_create_onboarding_state(session, user_id=user_id)
    if state.role != ROLE_JOB_SEEKER:
        raise ValidationFailedError("wrong_role_for_seeker_type")

    state.seeker_type = seeker_type
    state.current_step = "student_verify" if seeker_type == SEEKER_STUDENT else "seeker_profile"
    state.updated_at = datetime.now(tz=UTC)
    await write_audit(
        session,
        action="onboarding.seeker_type_selected",
        resource_type="user",
        resource_id=user_id,
        context=_audit_ctx(ctx, actor_id=user_id),
        after={"seeker_type": seeker_type},
    )
    await session.flush()
    return state


async def save_seeker_profile(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    profile_data: dict,
    ctx: RequestContext,
) -> OnboardingState:
    state = await get_or_create_onboarding_state(session, user_id=user_id)
    if state.role != ROLE_JOB_SEEKER:
        raise ValidationFailedError("wrong_role_for_seeker_profile")

    # Profile data is saved to user_profiles in the student_profiles module.
    # Here we only advance the wizard step.
    state.current_step = "complete"
    state.completed_at = datetime.now(tz=UTC)
    state.updated_at = datetime.now(tz=UTC)
    await write_audit(
        session,
        action="onboarding.seeker_profile_saved",
        resource_type="user",
        resource_id=user_id,
        context=_audit_ctx(ctx, actor_id=user_id),
    )
    await session.flush()
    return state


async def request_student_verify(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    university_name: str,
    student_id_number: str,
    student_email: str,
    ctx: RequestContext,
) -> dict:
    """Start student email verification: create/update StudentVerification row,
    issue OTP to student email address."""

    user = await user_service.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("user_not_found")

    # Upsert StudentVerification row
    existing = (
        await session.execute(
            select(StudentVerification).where(StudentVerification.user_id == user_id)
        )
    ).scalar_one_or_none()

    if existing is None:
        verif = StudentVerification(
            user_id=user_id,
            university_name=university_name,
            student_id_number=student_id_number,
            student_email=student_email,
        )
        session.add(verif)
    else:
        existing.university_name = university_name
        existing.student_id_number = student_id_number
        existing.student_email = student_email
        existing.student_email_verified_at = None
        existing.status = "unverified"
        existing.updated_at = datetime.now(tz=UTC)

    await session.flush()

    # Invalidate any previous student_email OTP for this user
    await _invalidate_outstanding(session, user_id=user_id, purpose=PURPOSE_STUDENT_EMAIL)
    # Issue new OTP to the student email address
    await _issue_email_verification(
        session,
        user=user,
        purpose=PURPOSE_STUDENT_EMAIL,
        override_email=student_email,
    )

    await write_audit(
        session,
        action="onboarding.student_verify_requested",
        resource_type="user",
        resource_id=user_id,
        context=_audit_ctx(ctx, actor_id=user_id),
    )
    await session.flush()
    return {"status": "otp_sent", "student_email": student_email}


async def confirm_student_verify(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    otp_code: str,
    id_card_file_path: str | None,
    ctx: RequestContext,
) -> OnboardingState:
    """Confirm student email OTP and record student ID card path."""
    user = await user_service.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("user_not_found")

    # Verify the student email OTP
    verif = (
        await session.execute(
            select(StudentVerification).where(StudentVerification.user_id == user_id)
        )
    ).scalar_one_or_none()
    if verif is None:
        raise ValidationFailedError("student_verification_not_started")

    # Re-use verify_email_otp but for student_email purpose
    await verify_email_otp(
        session,
        email=user.email,
        otp_code=otp_code,
        purpose=PURPOSE_STUDENT_EMAIL,
        ctx=ctx,
    )

    now = datetime.now(tz=UTC)
    verif.student_email_verified_at = now
    verif.verified_at = now
    verif.status = "verified"
    if id_card_file_path:
        verif.id_card_file_path = id_card_file_path
        verif.ai_check_status = "pending"
    verif.updated_at = now

    state = await get_or_create_onboarding_state(session, user_id=user_id)
    state.current_step = "seeker_profile"
    state.updated_at = now

    await write_audit(
        session,
        action="onboarding.student_email_verified",
        resource_type="user",
        resource_id=user_id,
        context=_audit_ctx(ctx, actor_id=user_id),
    )
    await session.flush()
    return state


async def save_employer_info(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    company_name: str,
    industry: str | None,
    company_size: str | None,
    address: str | None,
    registrant_role: str | None,
    ctx: RequestContext,
) -> OnboardingState:
    """Save company info and advance wizard to employer_docs step."""
    user = await user_service.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("user_not_found")

    state = await get_or_create_onboarding_state(session, user_id=user_id)
    if state.role != ROLE_EMPLOYER:
        raise ValidationFailedError("wrong_role_for_employer_info")

    # Upsert PartnerRegistrationRequest (via the organization facade).
    existing_req = await partner_registration_facade.get_by_user(session, user_id)

    if existing_req is None:
        partner_registration_facade.create(
            session,
            company_name=company_name,
            industry=industry,
            company_size=company_size,
            contact_name=user.full_name or user.email,
            contact_email=user.email,
            contact_title=registrant_role,
            description=address,
            submitted_by_user_id=user_id,
        )
    else:
        existing_req.company_name = company_name
        existing_req.industry = industry
        existing_req.company_size = company_size
        existing_req.contact_title = registrant_role
        existing_req.description = address
        existing_req.updated_at = datetime.now(tz=UTC)

    state.current_step = "employer_docs"
    state.updated_at = datetime.now(tz=UTC)

    await write_audit(
        session,
        action="onboarding.employer_info_saved",
        resource_type="user",
        resource_id=user_id,
        context=_audit_ctx(ctx, actor_id=user_id),
        after={"company_name": company_name},
    )
    await session.flush()
    return state


async def submit_employer_docs(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    document_path: str,
    tax_id: str | None,
    ctx: RequestContext,
) -> dict:
    """Record uploaded business document path, enqueue AI verification task."""
    from app.modules.onboarding.application import doc_verification  # local import

    req = await partner_registration_facade.get_by_user(session, user_id)
    if req is None:
        raise ValidationFailedError("employer_info_not_submitted")

    req.document_path = document_path
    req.tax_id = tax_id
    req.ai_doc_status = "pending"
    req.updated_at = datetime.now(tz=UTC)

    state = await get_or_create_onboarding_state(session, user_id=user_id)
    state.current_step = "pending"
    state.updated_at = datetime.now(tz=UTC)

    # Update user persona to partner_member now that docs are submitted
    await update_identity_persona(session, user_id=user_id, persona="partner_member")

    await write_audit(
        session,
        action="onboarding.employer_docs_submitted",
        resource_type="partner_registration_request",
        resource_id=req.id,
        context=_audit_ctx(ctx, actor_id=user_id),
    )
    await session.flush()

    # Enqueue async AI verification (non-blocking)
    await doc_verification.enqueue_verification(session, request_id=req.id)

    return {"status": "submitted", "ai_doc_status": "pending"}


async def get_employer_doc_status(session: AsyncSession, *, user_id: uuid.UUID) -> dict:
    req = await partner_registration_facade.get_by_user(session, user_id)
    if req is None:
        raise NotFoundError("employer_request_not_found")
    return {
        "ai_doc_status": req.ai_doc_status,
        "request_status": req.status,
        "tax_id_verified": req.tax_id_verified,
    }
