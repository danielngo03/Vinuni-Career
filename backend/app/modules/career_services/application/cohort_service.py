"""Counselor cohorts + cohort membership (B-554).

RBAC resource: ``career_services_cohorts``. Membership add is **idempotent**
(``docs/EDGE_CASES_FAILURE_MODES.md`` duplicate-write class): re-adding a
student who is already a member returns the existing membership instead of
raising a conflict — a counselor re-clicking "add to cohort" is not a bug.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.career_services.application.common import audit_ctx, require_org
from app.modules.career_services.domain import catalog
from app.modules.career_services.domain.models import Cohort, CohortMembership
from app.modules.organization.application import org_lookup_facade
from app.shared.audit import write_audit
from app.shared.exceptions import ConflictError, ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "career_services_cohorts"


def _presenter(cohort: Cohort, *, locale: str = "vi") -> dict:
    return {
        "id": str(cohort.id),
        "name": cohort.name,
        "description": cohort.description,
        "owner_counselor_id": str(cohort.owner_counselor_id),
        # Owning department (P2/WS2.1); NULL = org-wide cohort. Gates cohort
        # writes for department-scoped counselors.
        "department_id": str(cohort.department_id) if cohort.department_id else None,
        "status": cohort.status,
        "status_label": catalog.cohort_status_label(cohort.status, locale=locale),
        "created_at": cohort.created_at.isoformat() if cohort.created_at else None,
        "updated_at": cohort.updated_at.isoformat() if cohort.updated_at else None,
    }


def _membership_presenter(m: CohortMembership) -> dict:
    return {
        "id": str(m.id),
        "cohort_id": str(m.cohort_id),
        "student_id": str(m.student_id),
        "added_by": str(m.added_by),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _get_cohort(
    session: AsyncSession, *, org_id: uuid.UUID, cohort_id: uuid.UUID
) -> Cohort | None:
    stmt = select(Cohort).where(
        Cohort.id == cohort_id, Cohort.org_id == org_id, Cohort.deleted_at.is_(None)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_cohort(
    session: AsyncSession,
    *,
    principal: Principal,
    name: str,
    description: str | None,
    department_id: uuid.UUID | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    # Validate the department scope BEFORE the permission check so a foreign /
    # non-existent department is a clean 404 rather than leaking through the RBAC
    # decision (the department is also the RBAC decision input below).
    if department_id is not None and not await org_lookup_facade.department_belongs_to_org(
        session, org_id=org_id, department_id=department_id
    ):
        raise ResourceNotFoundError()
    # Department-scoped enforcement: a counselor whose ``career_services_cohorts``
    # grant is scoped to ``department_id`` may create a cohort there; an org-wide
    # grant works for any department (incl. ``None`` = org-wide cohort).
    permission_checker.require(
        principal, _RESOURCE, "create",
        resource_org_id=org_id, resource_department_id=department_id,
    )
    if not name or not name.strip():
        raise ValidationFailedError(details={"reason": "name_required"})

    existing = (
        await session.execute(
            select(Cohort.id).where(
                Cohort.org_id == org_id,
                Cohort.name == name,
                Cohort.deleted_at.is_(None),
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(details={"reason": "duplicate_cohort_name"})

    cohort = Cohort(
        org_id=org_id,
        name=name.strip(),
        description=description,
        department_id=department_id,
        owner_counselor_id=principal.user_id,
        status=catalog.COHORT_ACTIVE,
    )
    session.add(cohort)
    await session.flush()
    await write_audit(
        session,
        action="career_services.cohort.created",
        resource_type="career_services_cohort",
        resource_id=cohort.id,
        context=audit_ctx(principal, ctx),
        after={
            "name": cohort.name,
            "department_id": str(department_id) if department_id else None,
        },
    )
    await session.commit()
    return _presenter(cohort, locale=locale)


async def list_cohorts(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> list[dict]:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=org_id)
    rows = (
        await session.execute(
            select(Cohort)
            .where(Cohort.org_id == org_id, Cohort.deleted_at.is_(None))
            .order_by(Cohort.created_at.desc())
        )
    ).scalars().all()
    return [_presenter(c, locale=locale) for c in rows]


async def update_cohort(
    session: AsyncSession,
    *,
    principal: Principal,
    cohort_id: uuid.UUID,
    name: str | None,
    description: str | None,
    status: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    # Load first so the RBAC decision can be scoped to the cohort's department.
    # Tenant isolation is preserved (``_get_cohort`` filters ``org_id``); a
    # missing/foreign cohort is a 404 either way.
    cohort = await _get_cohort(session, org_id=org_id, cohort_id=cohort_id)
    if cohort is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "update",
        resource_org_id=org_id, resource_department_id=cohort.department_id,
    )
    if status is not None:
        if status not in catalog.COHORT_STATUSES:
            raise ValidationFailedError(details={"reason": "invalid_status"})
        cohort.status = status
    if name is not None and name.strip():
        cohort.name = name.strip()
    if description is not None:
        cohort.description = description
    await session.flush()
    # ``updated_at`` (onupdate=func.now()) is expired after this UPDATE; refresh
    # explicitly so the sync presenter never triggers an implicit lazy-load
    # outside the async greenlet bridge.
    await session.refresh(cohort)
    await write_audit(
        session,
        action="career_services.cohort.updated",
        resource_type="career_services_cohort",
        resource_id=cohort.id,
        context=audit_ctx(principal, ctx),
    )
    await session.commit()
    return _presenter(cohort, locale=locale)


async def delete_cohort(
    session: AsyncSession,
    *,
    principal: Principal,
    cohort_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    org_id = require_org(principal)
    cohort = await _get_cohort(session, org_id=org_id, cohort_id=cohort_id)
    if cohort is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "delete",
        resource_org_id=org_id, resource_department_id=cohort.department_id,
    )
    from datetime import UTC, datetime

    cohort.deleted_at = datetime.now(tz=UTC)
    await session.flush()
    await write_audit(
        session,
        action="career_services.cohort.deleted",
        resource_type="career_services_cohort",
        resource_id=cohort.id,
        context=audit_ctx(principal, ctx),
        before={"name": cohort.name},
    )
    await session.commit()


async def add_member(
    session: AsyncSession,
    *,
    principal: Principal,
    cohort_id: uuid.UUID,
    student_id: uuid.UUID,
    ctx: RequestContext,
) -> dict:
    org_id = require_org(principal)
    cohort = await _get_cohort(session, org_id=org_id, cohort_id=cohort_id)
    if cohort is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "update",
        resource_org_id=org_id, resource_department_id=cohort.department_id,
    )

    existing = (
        await session.execute(
            select(CohortMembership).where(
                CohortMembership.cohort_id == cohort_id,
                CohortMembership.student_id == student_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Idempotent: re-adding an existing member is a no-op, not a conflict.
        return _membership_presenter(existing)

    membership = CohortMembership(
        cohort_id=cohort_id, student_id=student_id, added_by=principal.user_id
    )
    session.add(membership)
    await session.flush()
    await write_audit(
        session,
        action="career_services.cohort_membership.added",
        resource_type="career_services_cohort_membership",
        resource_id=membership.id,
        context=audit_ctx(principal, ctx),
        after={"cohort_id": str(cohort_id), "student_id": str(student_id)},
    )
    await session.commit()
    return _membership_presenter(membership)


async def remove_member(
    session: AsyncSession,
    *,
    principal: Principal,
    cohort_id: uuid.UUID,
    student_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    org_id = require_org(principal)
    cohort = await _get_cohort(session, org_id=org_id, cohort_id=cohort_id)
    if cohort is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "update",
        resource_org_id=org_id, resource_department_id=cohort.department_id,
    )

    membership = (
        await session.execute(
            select(CohortMembership).where(
                CohortMembership.cohort_id == cohort_id,
                CohortMembership.student_id == student_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        # Idempotent: removing a non-member is a no-op.
        return
    await session.delete(membership)
    await write_audit(
        session,
        action="career_services.cohort_membership.removed",
        resource_type="career_services_cohort_membership",
        resource_id=membership.id,
        context=audit_ctx(principal, ctx),
        before={"cohort_id": str(cohort_id), "student_id": str(student_id)},
    )
    await session.commit()


async def list_members(
    session: AsyncSession, *, principal: Principal, cohort_id: uuid.UUID
) -> list[dict]:
    org_id = require_org(principal)
    cohort = await _get_cohort(session, org_id=org_id, cohort_id=cohort_id)
    if cohort is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "read",
        resource_org_id=org_id, resource_department_id=cohort.department_id,
    )
    rows = (
        await session.execute(
            select(CohortMembership)
            .where(CohortMembership.cohort_id == cohort_id)
            .order_by(CohortMembership.created_at)
        )
    ).scalars().all()
    return [_membership_presenter(m) for m in rows]
