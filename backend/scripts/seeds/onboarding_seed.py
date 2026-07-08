"""Seed realistic onboarding state for development accounts.

The main dev seed creates ready-to-use accounts (students, alumni, university
staff, partner admins/recruiters) rather than asking every demo user to walk
through the post-registration wizard. This module keeps those accounts aligned
with the production onboarding state machine so the frontend guard, partner
approval screens, and demo dashboards all see coherent data after a reset.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.modules.onboarding.domain.models import OnboardingState, StudentVerification
from app.modules.organization.domain.models import Organization, PartnerRegistrationRequest
from app.modules.users.domain.models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

NOW = datetime.now(tz=UTC)


async def _complete_state(
    session: AsyncSession,
    *,
    user: User,
    role: str | None,
    seeker_type: str | None = None,
) -> OnboardingState:
    state = (
        await session.execute(
            select(OnboardingState).where(OnboardingState.user_id == user.id)
        )
    ).scalar_one_or_none()
    if state is None:
        state = OnboardingState(user_id=user.id)
        session.add(state)
    state.role = role
    state.seeker_type = seeker_type
    state.current_step = "complete"
    state.completed_at = state.completed_at or NOW
    state.updated_at = NOW
    await session.flush()
    return state


async def _student_verification(
    session: AsyncSession,
    *,
    user: User,
    student_id_number: str,
) -> None:
    row = (
        await session.execute(
            select(StudentVerification).where(StudentVerification.user_id == user.id)
        )
    ).scalar_one_or_none()
    student_email = user.email if user.email.endswith("@vinuni.edu.vn") else user.email
    if row is None:
        row = StudentVerification(
            id=uuid.uuid4(),
            user_id=user.id,
            university_name="VinUniversity",
            student_id_number=student_id_number,
            student_email=student_email,
        )
        session.add(row)
    row.student_email = student_email
    row.student_email_verified_at = row.student_email_verified_at or NOW
    row.verified_at = row.verified_at or NOW
    row.status = "verified"
    row.ai_check_status = "passed"
    row.ai_check_result = {
        "source": "dev_seed",
        "decision": "passed",
        "confidence": 0.98,
    }
    row.updated_at = NOW
    await session.flush()


async def _approved_partner_request(
    session: AsyncSession,
    *,
    user: User,
    org: Organization,
    reviewed_by: User,
) -> None:
    row = (
        await session.execute(
            select(PartnerRegistrationRequest).where(
                PartnerRegistrationRequest.submitted_by_user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = PartnerRegistrationRequest(
            id=uuid.uuid4(),
            company_name=org.display_name,
            company_website=org.website_url,
            company_size=org.company_size,
            industry=org.industry,
            description=org.description,
            contact_name=user.full_name or user.email,
            contact_email=user.email,
            contact_title="Partner Admin",
            submitted_by_user_id=user.id,
        )
        session.add(row)

    row.company_name = org.display_name
    row.company_website = org.website_url
    row.company_size = org.company_size
    row.industry = org.industry
    row.description = org.description
    row.contact_name = user.full_name or user.email
    row.contact_email = user.email
    row.contact_title = row.contact_title or "Partner Admin"
    row.status = "approved"
    row.review_note = "Seeded approved partner account for local development."
    row.reviewed_by = reviewed_by.id
    row.reviewed_at = row.reviewed_at or NOW
    row.created_org_id = org.id
    row.tax_id = row.tax_id or "0101248141"
    row.tax_code = row.tax_code or row.tax_id
    row.tax_id_verified = True
    row.tax_id_api_result = {
        "source": "dev_seed",
        "status": "verified",
        "company_name": org.display_name,
    }
    row.document_path = row.document_path or ".dev/storage/employer_docs/fpt-software.pdf"
    row.ai_doc_status = "passed"
    row.ai_doc_result = {
        "source": "dev_seed",
        "decision": "passed",
        "confidence": 0.97,
    }
    row.updated_at = NOW
    await session.flush()


async def seed_onboarding_state(
    session: AsyncSession,
    *,
    users: dict[str, User],
    orgs: dict[str, Organization],
) -> None:
    """Make seeded accounts immediately usable after login.

    Real newly-registered accounts still start at ``role_select``. These rows
    only affect the curated dev accounts that already represent approved
    students, staff, alumni, and partner members.
    """

    print("\n[onboarding]")

    student_specs = {
        "vinuni_student": "V2024001",
        "vinuni_student_data": "V2024002",
        "vinuni_student_business": "V2024003",
    }
    for key, student_id in student_specs.items():
        await _complete_state(
            session,
            user=users[key],
            role="job_seeker",
            seeker_type="student",
        )
        await _student_verification(
            session,
            user=users[key],
            student_id_number=student_id,
        )

    await _complete_state(
        session,
        user=users["external_student"],
        role="job_seeker",
        seeker_type="student",
    )
    await _complete_state(
        session,
        user=users["alumni"],
        role="job_seeker",
        seeker_type="professional",
    )

    for key in (
        "partner",
        "fpt_recruiter",
        "fpt_hiring_manager",
        "fpt_finance",
        "vcb_recruiter",
        "momo_recruiter",
    ):
        await _complete_state(session, user=users[key], role="employer")

    await _approved_partner_request(
        session,
        user=users["partner"],
        org=orgs["fpt-software"],
        reviewed_by=users["admin"],
    )

    for key in ("career_admin", "career_coach", "moderator", "ai_ops", "admin"):
        await _complete_state(session, user=users[key], role=None)

    print("  [ok] onboarding states aligned with seeded personas")
