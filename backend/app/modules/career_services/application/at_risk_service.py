"""At-risk student flags: raise, triage, and resolve (B-554).

RBAC resource: ``career_services_at_risk``. Lifecycle: ``open`` ->
``in_progress`` -> ``resolved``/``dismissed`` (a resolution requires
``resolution_notes`` — an unexplained close is not accepted, mirroring the
partner-moderation "reason + explanation" convention).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.career_services.application.common import audit_ctx, require_org
from app.modules.career_services.domain import catalog
from app.modules.career_services.domain.models import AtRiskFlag
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "career_services_at_risk"


def _presenter(flag: AtRiskFlag, *, locale: str = "vi") -> dict:
    return {
        "id": str(flag.id),
        "student_id": str(flag.student_id),
        "cohort_id": str(flag.cohort_id) if flag.cohort_id else None,
        "reason": flag.reason_code,
        "reason_label": catalog.risk_reason_label(flag.reason_code, locale=locale),
        "severity": flag.severity,
        "severity_label": catalog.risk_severity_label(flag.severity, locale=locale),
        "status": flag.status,
        "status_label": catalog.risk_status_label(flag.status, locale=locale),
        "notes": flag.notes,
        "flagged_by": str(flag.flagged_by),
        "resolved_by": str(flag.resolved_by) if flag.resolved_by else None,
        "resolution_notes": flag.resolution_notes,
        "resolved_at": flag.resolved_at.isoformat() if flag.resolved_at else None,
        "created_at": flag.created_at.isoformat() if flag.created_at else None,
        "updated_at": flag.updated_at.isoformat() if flag.updated_at else None,
    }


async def _get_flag(
    session: AsyncSession, *, org_id: uuid.UUID, flag_id: uuid.UUID
) -> AtRiskFlag | None:
    stmt = select(AtRiskFlag).where(AtRiskFlag.id == flag_id, AtRiskFlag.org_id == org_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_flag(
    session: AsyncSession,
    *,
    principal: Principal,
    student_id: uuid.UUID,
    reason: str,
    severity: str,
    notes: str | None,
    cohort_id: uuid.UUID | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "create", resource_org_id=org_id)
    if reason not in catalog.RISK_REASONS:
        raise ValidationFailedError(details={"reason": "invalid_reason"})
    if severity not in catalog.RISK_SEVERITIES:
        raise ValidationFailedError(details={"reason": "invalid_severity"})

    flag = AtRiskFlag(
        org_id=org_id,
        student_id=student_id,
        cohort_id=cohort_id,
        reason_code=reason,
        severity=severity,
        notes=notes,
        status=catalog.RISK_OPEN,
        flagged_by=principal.user_id,
    )
    session.add(flag)
    await session.flush()
    await write_audit(
        session,
        action="career_services.at_risk_flag.created",
        resource_type="career_services_at_risk_flag",
        resource_id=flag.id,
        context=audit_ctx(principal, ctx),
        after={"student_id": str(student_id), "reason": reason, "severity": severity},
    )
    await session.commit()
    return _presenter(flag, locale=locale)


async def list_flags(
    session: AsyncSession,
    *,
    principal: Principal,
    student_id: uuid.UUID | None = None,
    status: str | None = None,
    locale: str = "vi",
) -> list[dict]:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=org_id)
    stmt = select(AtRiskFlag).where(AtRiskFlag.org_id == org_id)
    if student_id is not None:
        stmt = stmt.where(AtRiskFlag.student_id == student_id)
    if status is not None:
        if status not in catalog.RISK_STATUSES:
            raise ValidationFailedError(details={"reason": "invalid_status"})
        stmt = stmt.where(AtRiskFlag.status == status)
    stmt = stmt.order_by(AtRiskFlag.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [_presenter(f, locale=locale) for f in rows]


async def update_flag_status(
    session: AsyncSession,
    *,
    principal: Principal,
    flag_id: uuid.UUID,
    status: str,
    resolution_notes: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "update", resource_org_id=org_id)
    flag = await _get_flag(session, org_id=org_id, flag_id=flag_id)
    if flag is None:
        raise ResourceNotFoundError()
    if status not in catalog.RISK_STATUSES:
        raise ValidationFailedError(details={"reason": "invalid_status"})
    if status in (catalog.RISK_RESOLVED, catalog.RISK_DISMISSED):
        if not resolution_notes or not resolution_notes.strip():
            raise ValidationFailedError(details={"reason": "resolution_notes_required"})
        flag.resolution_notes = resolution_notes.strip()
        flag.resolved_by = principal.user_id
        flag.resolved_at = datetime.now(tz=UTC)
    flag.status = status
    await session.flush()
    # ``updated_at`` (onupdate=func.now()) is server-computed and expired after
    # this UPDATE; refresh explicitly so the sync presenter below never triggers
    # an implicit lazy-load outside the async greenlet bridge.
    await session.refresh(flag)
    await write_audit(
        session,
        action="career_services.at_risk_flag.status_changed",
        resource_type="career_services_at_risk_flag",
        resource_id=flag.id,
        context=audit_ctx(principal, ctx),
        after={"status": status},
    )
    await session.commit()
    return _presenter(flag, locale=locale)
