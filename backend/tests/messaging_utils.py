"""Shared helpers for messaging (ADR-0012) service-level tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.modules.auth.domain.personas import permissions_for
from app.modules.recruitment.domain.models import Application
from app.shared.permissions import Principal
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import register_verified
from tests.documents_utils import make_student
from tests.org_utils import email, make_org_with_admin

__all__ = [
    "make_student",
    "make_partner",
    "make_university",
    "make_second_student",
    "seed_application",
]


async def make_partner(session: AsyncSession, *, display_name: str = "Partner Co"):
    """Return (user, org, partner_principal) for a partner org admin."""

    return await make_org_with_admin(
        session, org_type="partner", display_name=display_name
    )


async def make_university(session: AsyncSession, *, display_name: str = "VinUni"):
    """Return (user, org, university_staff_principal)."""

    return await make_org_with_admin(
        session, org_type="university", display_name=display_name
    )


async def make_second_student(session: AsyncSession, *, prefix: str = "student2"):
    user = await register_verified(session, email=email(prefix))
    principal = Principal(
        user_id=user.id,
        persona="student",
        org_id=None,
        is_superadmin=False,
        permissions=permissions_for("student"),
    )
    return user, principal


async def seed_application(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    applicant_id: uuid.UUID,
    is_anonymous: bool = False,
    status: str = "submitted",
    revealed: bool = False,
) -> uuid.UUID:
    """Insert an ``applications`` row binding a partner org to an applicant.

    Mirrors what the recruitment apply-flow produces, without the full job/CV setup
    (SQLite does not enforce the ``job_id`` FK in tests). The messaging relationship
    read-model only reads org_id/applicant_id/status/is_anonymous/reveal_approved_at.
    """

    app = Application(
        job_id=uuid.uuid4(),
        applicant_id=applicant_id,
        org_id=org_id,
        status=status,
        is_anonymous=is_anonymous,
        reveal_approved_at=datetime.now(tz=UTC) if revealed else None,
    )
    session.add(app)
    await session.commit()
    return app.id
