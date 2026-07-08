"""Shared helpers for career-services counselor-workspace tests."""

from __future__ import annotations

import uuid

from app.modules.organization.domain.models import Membership, MembershipRole, Permission, Role
from app.modules.users.application import user_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests.org_utils import email, principal_for


async def add_counselor(
    session: AsyncSession,
    *,
    org,
    permissions: list[tuple[str, str]],
    member_email: str | None = None,
    role_name: str | None = None,
):
    """Add a ``university_staff`` counselor member with a custom-permission role.

    Returns ``(user, membership, principal)`` — mirrors
    ``tests.org_utils.add_member`` but uses the ``university_staff`` persona
    (career-services is a university-only workspace).
    """

    from tests.auth_utils import register_verified

    user = await register_verified(session, email=member_email or email("counselor"))
    role = Role(
        org_id=org.id,
        name=role_name or f"Counselor-{uuid.uuid4().hex[:8]}",
        is_system=False,
    )
    session.add(role)
    await session.flush()
    for resource, action in permissions:
        session.add(Permission(role_id=role.id, resource_type=resource, action=action))
    identity = await user_service.add_identity(
        session, user_id=user.id, persona="university_staff", org_id=org.id
    )
    membership = Membership(
        user_id=user.id, org_id=org.id, identity_id=identity.id, status="active"
    )
    session.add(membership)
    await session.flush()
    session.add(MembershipRole(membership_id=membership.id, role_id=role.id))
    await session.commit()
    principal = await principal_for(session, user=user, org_id=org.id)
    return user, membership, principal


ALL_CAREER_SERVICES_PERMISSIONS: list[tuple[str, str]] = [
    ("career_services_cohorts", "read"),
    ("career_services_cohorts", "create"),
    ("career_services_cohorts", "update"),
    ("career_services_cohorts", "delete"),
    ("career_services_at_risk", "read"),
    ("career_services_at_risk", "create"),
    ("career_services_at_risk", "update"),
    ("career_services_cv_review", "read"),
    ("career_services_cv_review", "create"),
    ("career_services_cv_review", "update"),
    ("career_services_cv_review", "assign"),
    ("career_services_appointments", "read"),
    ("career_services_appointments", "create"),
    ("career_services_appointments", "update"),
    ("career_services_appointments", "cancel"),
    ("career_services_notes", "read"),
    ("career_services_notes", "create"),
    ("career_services_notes", "update"),
    ("career_services_interventions", "read"),
    ("career_services_interventions", "create"),
    ("career_services_interventions", "update"),
    ("career_services_reporting", "read"),
]
