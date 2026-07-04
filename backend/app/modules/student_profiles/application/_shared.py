"""Internal helpers shared across the student-profile services.

RBAC + ownership follow the project pattern: a cross-owner access returns ``404``
(never ``403``) so resources are not enumerable. The owning student holds
``profile:*``; the partner/community read is gated by privacy, not by a write
grant.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.student_profiles.domain.models import StudentProfile
from app.shared.audit import AuditContext
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal

RESOURCE = "profile"

# Personas considered part of the VinUni community for ``vinuni_only`` visibility.
VINUNI_PERSONAS = frozenset({"student", "alumni", "university_staff"})


def now() -> datetime:
    return datetime.now(tz=UTC)


def to_uuid(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def parse_date(value: object, *, field: str) -> date | None:
    """Coerce an ISO ``YYYY-MM-DD`` string (or ``date``) into a ``date``."""

    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationFailedError("Ngày không hợp lệ (định dạng YYYY-MM-DD).") from exc
    raise ValidationFailedError(f"Giá trị '{field}' không hợp lệ.")


def audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


async def load_owned_profile(
    session: AsyncSession, *, principal: Principal, lock: bool = False
) -> StudentProfile:
    """Load the acting user's own profile, creating it lazily if absent."""

    assert principal.user_id is not None
    stmt = select(StudentProfile).where(
        StudentProfile.user_id == principal.user_id,
        StudentProfile.deleted_at.is_(None),
    )
    if lock and use_for_update():
        stmt = stmt.with_for_update()
    profile = (await session.execute(stmt)).scalar_one_or_none()
    if profile is None:
        profile = StudentProfile(user_id=principal.user_id)
        session.add(profile)
        await session.flush()
    return profile


async def load_profile_by_id(
    session: AsyncSession, *, profile_id: uuid.UUID
) -> StudentProfile:
    profile = (
        await session.execute(
            select(StudentProfile).where(
                StudentProfile.id == profile_id,
                StudentProfile.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        raise ResourceNotFoundError()
    return profile


async def load_profile_by_user(
    session: AsyncSession, *, user_id: uuid.UUID
) -> StudentProfile | None:
    return (
        await session.execute(
            select(StudentProfile).where(
                StudentProfile.user_id == user_id,
                StudentProfile.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
