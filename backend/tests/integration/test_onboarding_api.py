"""Onboarding wizard service-level tests (previously zero coverage).

Covers: initial state, role selection (both branches), seeker-type branching,
seeker-profile completion, student email-OTP verify + confirm, employer info +
docs submission reaching ``pending``, resuming a draft mid-flow, and completion
leaving prior verification/audit rows intact.
"""

from __future__ import annotations

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.onboarding.application import onboarding_service as svc
from app.modules.onboarding.domain.models import StudentVerification
from app.modules.organization.domain.models import PartnerRegistrationRequest
from app.modules.users.application.user_write_facade import update_identity_persona
from app.shared.models import AuditLog
from sqlalchemy import select

from tests.auth_utils import register_verified

CTX = RequestContext(ip="203.0.113.9", user_agent="Mozilla/5.0 (Macintosh) Chrome/120")


async def _fetch_student_email_otp(session, user_id) -> str:
    rows = (
        await session.execute(
            select(NotificationOutbox)
            .where(NotificationOutbox.recipient_id == user_id)
            .order_by(NotificationOutbox.created_at.desc())
        )
    ).scalars().all()
    for row in rows:
        if row.template_key == "account.student_email_verification":
            return str(row.variables["otp_code"])
    raise AssertionError("no student email OTP enqueued")


async def test_get_or_create_initial_state_starts_at_role_select(db_session) -> None:
    user = await register_verified(db_session, email="onb_init@vinuni.edu.vn")
    state = await svc.get_or_create_onboarding_state(db_session, user_id=user.id)
    assert state.current_step == "role_select"
    assert state.role is None
    assert not state.is_complete

    # Idempotent: fetching again returns the SAME row, not a fresh reset one.
    again = await svc.get_or_create_onboarding_state(db_session, user_id=user.id)
    assert again.user_id == state.user_id
    await db_session.commit()


async def test_org_scoped_identity_without_state_does_not_get_stuck(db_session) -> None:
    user = await register_verified(db_session, email="onb_invited_partner@vinuni.edu.vn")
    await update_identity_persona(db_session, user_id=user.id, persona="partner_member")
    await db_session.flush()

    status = await svc.get_status(db_session, user_id=user.id)
    assert status["current_step"] == "complete"
    assert status["is_complete"] is True
    assert status["role"] is None
    await db_session.commit()


async def test_set_role_job_seeker_advances_to_seeker_type(db_session) -> None:
    user = await register_verified(db_session, email="onb_seeker@vinuni.edu.vn")
    state = await svc.set_role(
        db_session, user_id=user.id, role=svc.ROLE_JOB_SEEKER, ctx=CTX
    )
    assert state.role == svc.ROLE_JOB_SEEKER
    assert state.current_step == "seeker_type"
    await db_session.commit()


async def test_set_role_employer_advances_to_employer_info(db_session) -> None:
    user = await register_verified(db_session, email="onb_employer@vinuni.edu.vn")
    state = await svc.set_role(
        db_session, user_id=user.id, role=svc.ROLE_EMPLOYER, ctx=CTX
    )
    assert state.role == svc.ROLE_EMPLOYER
    assert state.current_step == "employer_info"
    await db_session.commit()


async def test_set_seeker_type_student_routes_to_student_verify(db_session) -> None:
    user = await register_verified(db_session, email="onb_seeker_student@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_JOB_SEEKER, ctx=CTX)
    state = await svc.set_seeker_type(
        db_session, user_id=user.id, seeker_type=svc.SEEKER_STUDENT, ctx=CTX
    )
    assert state.current_step == "student_verify"
    await db_session.commit()


async def test_set_seeker_type_professional_routes_to_seeker_profile(db_session) -> None:
    user = await register_verified(db_session, email="onb_seeker_prof@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_JOB_SEEKER, ctx=CTX)
    state = await svc.set_seeker_type(
        db_session, user_id=user.id, seeker_type=svc.SEEKER_PROFESSIONAL, ctx=CTX
    )
    assert state.current_step == "seeker_profile"
    await db_session.commit()


async def test_save_seeker_profile_completes_onboarding(db_session) -> None:
    user = await register_verified(db_session, email="onb_seeker_complete@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_JOB_SEEKER, ctx=CTX)
    await svc.set_seeker_type(
        db_session, user_id=user.id, seeker_type=svc.SEEKER_PROFESSIONAL, ctx=CTX
    )
    state = await svc.save_seeker_profile(
        db_session, user_id=user.id, profile_data={}, ctx=CTX
    )
    assert state.current_step == "complete"
    assert state.completed_at is not None
    assert state.is_complete
    await db_session.commit()


async def test_student_can_skip_optional_verification_and_complete(db_session) -> None:
    user = await register_verified(db_session, email="onb_student_skip@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_JOB_SEEKER, ctx=CTX)
    await svc.set_seeker_type(
        db_session, user_id=user.id, seeker_type=svc.SEEKER_STUDENT, ctx=CTX
    )

    state = await svc.save_seeker_profile(
        db_session, user_id=user.id, profile_data={}, ctx=CTX
    )
    assert state.current_step == "complete"
    assert state.is_complete

    status = await svc.get_status(db_session, user_id=user.id)
    assert status["current_step"] == "complete"
    assert status["is_complete"] is True
    assert status["student_verification_status"] is None
    await db_session.commit()


async def test_student_verify_request_and_confirm(db_session) -> None:
    user = await register_verified(db_session, email="onb_student@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_JOB_SEEKER, ctx=CTX)
    await svc.set_seeker_type(
        db_session, user_id=user.id, seeker_type=svc.SEEKER_STUDENT, ctx=CTX
    )

    result = await svc.request_student_verify(
        db_session,
        user_id=user.id,
        university_name="VinUniversity",
        student_id_number="V2024001",
        student_email="student.v2024001@vinuni.edu.vn",
        ctx=CTX,
    )
    assert result["status"] == "otp_sent"
    await db_session.commit()

    otp = await _fetch_student_email_otp(db_session, user.id)

    state = await svc.confirm_student_verify(
        db_session,
        user_id=user.id,
        otp_code=otp,
        id_card_file_path=None,
        ctx=CTX,
    )
    assert state.current_step == "seeker_profile"
    await db_session.commit()

    verif = (
        await db_session.execute(
            select(StudentVerification).where(StudentVerification.user_id == user.id)
        )
    ).scalar_one()
    assert verif.student_email_verified_at is not None
    assert verif.verified_at is not None
    assert verif.status == "verified"
    assert verif.university_name == "VinUniversity"


async def test_employer_info_and_docs_reach_pending(db_session) -> None:
    user = await register_verified(db_session, email="onb_employer_docs@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_EMPLOYER, ctx=CTX)

    state = await svc.save_employer_info(
        db_session,
        user_id=user.id,
        company_name="Acme Corp",
        industry="Technology",
        company_size="51-200",
        address="Hanoi, Vietnam",
        registrant_role="HR Manager",
        ctx=CTX,
    )
    assert state.current_step == "employer_docs"
    await db_session.commit()

    result = await svc.submit_employer_docs(
        db_session,
        user_id=user.id,
        document_path=".dev/storage/employer_docs/fake.pdf",
        tax_id="0101234567",
        ctx=CTX,
    )
    assert result["status"] == "submitted"
    assert result["ai_doc_status"] == "pending"
    await db_session.commit()

    final_state = await svc.get_or_create_onboarding_state(db_session, user_id=user.id)
    assert final_state.current_step == "pending"

    req = (
        await db_session.execute(
            select(PartnerRegistrationRequest).where(
                PartnerRegistrationRequest.submitted_by_user_id == user.id
            )
        )
    ).scalar_one()
    assert req.ai_doc_status == "pending"
    assert req.tax_id == "0101234567"

    # Persona is updated to partner_member once docs are submitted.
    from app.modules.users.application import user_service

    identity = await user_service.primary_identity(db_session, user.id)
    assert identity is not None
    assert identity.persona == "partner_member"


async def test_get_status_treats_approved_employer_request_as_complete(db_session) -> None:
    user = await register_verified(db_session, email="onb_employer_approved@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_EMPLOYER, ctx=CTX)
    await svc.save_employer_info(
        db_session,
        user_id=user.id,
        company_name="Approved Corp",
        industry="Technology",
        company_size="51-200",
        address="Hanoi, Vietnam",
        registrant_role="HR Manager",
        ctx=CTX,
    )
    await svc.submit_employer_docs(
        db_session,
        user_id=user.id,
        document_path=".dev/storage/employer_docs/approved.pdf",
        tax_id="0101111222",
        ctx=CTX,
    )

    req = (
        await db_session.execute(
            select(PartnerRegistrationRequest).where(
                PartnerRegistrationRequest.submitted_by_user_id == user.id
            )
        )
    ).scalar_one()
    req.status = "approved"
    req.ai_doc_status = "passed"
    await db_session.flush()

    status = await svc.get_status(db_session, user_id=user.id)
    assert status["current_step"] == "complete"
    assert status["is_complete"] is True
    assert status["employer_request_status"] == "approved"
    await db_session.commit()


async def test_get_status_routes_rejected_employer_back_to_docs(db_session) -> None:
    user = await register_verified(db_session, email="onb_employer_rejected@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_EMPLOYER, ctx=CTX)
    await svc.save_employer_info(
        db_session,
        user_id=user.id,
        company_name="Rejected Corp",
        industry="Technology",
        company_size="11-50",
        address="Ho Chi Minh City, Vietnam",
        registrant_role="Founder",
        ctx=CTX,
    )
    await svc.submit_employer_docs(
        db_session,
        user_id=user.id,
        document_path=".dev/storage/employer_docs/rejected.pdf",
        tax_id="0103333444",
        ctx=CTX,
    )

    req = (
        await db_session.execute(
            select(PartnerRegistrationRequest).where(
                PartnerRegistrationRequest.submitted_by_user_id == user.id
            )
        )
    ).scalar_one()
    req.status = "rejected"
    req.ai_doc_status = "tampered"
    await db_session.flush()

    status = await svc.get_status(db_session, user_id=user.id)
    assert status["current_step"] == "employer_docs"
    assert status["is_complete"] is False
    assert status["employer_request_status"] == "rejected"
    await db_session.commit()


async def test_get_status_resumes_mid_flow_not_reset(db_session) -> None:
    user = await register_verified(db_session, email="onb_resume@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_JOB_SEEKER, ctx=CTX)
    await svc.set_seeker_type(
        db_session, user_id=user.id, seeker_type=svc.SEEKER_PROFESSIONAL, ctx=CTX
    )
    await db_session.commit()

    # Re-fetching status mid-wizard must return the in-progress step, not reset
    # back to role_select.
    status = await svc.get_status(db_session, user_id=user.id)
    assert status["current_step"] == "seeker_profile"
    assert status["role"] == svc.ROLE_JOB_SEEKER
    assert status["seeker_type"] == svc.SEEKER_PROFESSIONAL
    assert not status["is_complete"]


async def test_completion_preserves_prior_verification_and_audit_rows(db_session) -> None:
    user = await register_verified(db_session, email="onb_preserve@vinuni.edu.vn")
    await svc.set_role(db_session, user_id=user.id, role=svc.ROLE_JOB_SEEKER, ctx=CTX)
    await svc.set_seeker_type(
        db_session, user_id=user.id, seeker_type=svc.SEEKER_STUDENT, ctx=CTX
    )
    await svc.request_student_verify(
        db_session,
        user_id=user.id,
        university_name="VinUniversity",
        student_id_number="V2024099",
        student_email="student.v2024099@vinuni.edu.vn",
        ctx=CTX,
    )
    await db_session.commit()
    otp = await _fetch_student_email_otp(db_session, user.id)
    await svc.confirm_student_verify(
        db_session, user_id=user.id, otp_code=otp, id_card_file_path=None, ctx=CTX
    )
    await db_session.commit()

    audit_count_before = len(
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.actor_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert audit_count_before > 0

    state = await svc.save_seeker_profile(
        db_session, user_id=user.id, profile_data={}, ctx=CTX
    )
    await db_session.commit()
    assert state.completed_at is not None

    # Re-fetch: prior StudentVerification + audit rows must still exist.
    verif = (
        await db_session.execute(
            select(StudentVerification).where(StudentVerification.user_id == user.id)
        )
    ).scalar_one()
    assert verif.student_email_verified_at is not None

    audit_count_after = len(
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.actor_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert audit_count_after >= audit_count_before
