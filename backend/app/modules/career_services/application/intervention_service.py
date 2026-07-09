"""Intervention history: logged counselor actions + outcome tracking (B-554).

RBAC resource: ``career_services_interventions``. An intervention may optionally
link a prior appointment and/or at-risk flag (both must belong to the same org
and are validated on create so a counselor cannot link cross-tenant rows).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.career_services.application.common import audit_ctx, require_org
from app.modules.career_services.domain import catalog
from app.modules.career_services.domain.models import (
    Appointment,
    AtRiskFlag,
    InterventionRecord,
)
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "career_services_interventions"


def _presenter(rec: InterventionRecord, *, locale: str = "vi") -> dict:
    return {
        "id": str(rec.id),
        "student_id": str(rec.student_id),
        "counselor_id": str(rec.counselor_id),
        "intervention_type": rec.intervention_type,
        "intervention_type_label": catalog.intervention_type_label(
            rec.intervention_type, locale=locale
        ),
        "description": rec.description,
        "outcome": rec.outcome,
        "outcome_label": catalog.intervention_outcome_label(rec.outcome, locale=locale),
        "linked_appointment_id": (
            str(rec.linked_appointment_id) if rec.linked_appointment_id else None
        ),
        "linked_at_risk_flag_id": (
            str(rec.linked_at_risk_flag_id) if rec.linked_at_risk_flag_id else None
        ),
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


async def _get_record(
    session: AsyncSession, *, org_id: uuid.UUID, record_id: uuid.UUID
) -> InterventionRecord | None:
    stmt = select(InterventionRecord).where(
        InterventionRecord.id == record_id, InterventionRecord.org_id == org_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_intervention(
    session: AsyncSession,
    *,
    principal: Principal,
    student_id: uuid.UUID,
    intervention_type: str,
    description: str,
    linked_appointment_id: uuid.UUID | None,
    linked_at_risk_flag_id: uuid.UUID | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "create", resource_org_id=org_id)
    if intervention_type not in catalog.INTERVENTION_TYPES:
        raise ValidationFailedError(details={"reason": "invalid_intervention_type"})
    if not description or not description.strip():
        raise ValidationFailedError(details={"reason": "description_required"})

    if linked_appointment_id is not None:
        appt = (
            await session.execute(
                select(Appointment.id).where(
                    Appointment.id == linked_appointment_id,
                    Appointment.org_id == org_id,
                )
            )
        ).first()
        if appt is None:
            raise ValidationFailedError(details={"reason": "appointment_not_found"})

    if linked_at_risk_flag_id is not None:
        flag = (
            await session.execute(
                select(AtRiskFlag.id).where(
                    AtRiskFlag.id == linked_at_risk_flag_id,
                    AtRiskFlag.org_id == org_id,
                )
            )
        ).first()
        if flag is None:
            raise ValidationFailedError(details={"reason": "at_risk_flag_not_found"})

    rec = InterventionRecord(
        org_id=org_id,
        student_id=student_id,
        counselor_id=principal.user_id,
        intervention_type=intervention_type,
        description=description.strip(),
        outcome=catalog.INTERVENTION_OUTCOME_PENDING,
        linked_appointment_id=linked_appointment_id,
        linked_at_risk_flag_id=linked_at_risk_flag_id,
    )
    session.add(rec)
    await session.flush()
    await write_audit(
        session,
        action="career_services.intervention.created",
        resource_type="career_services_intervention",
        resource_id=rec.id,
        context=audit_ctx(principal, ctx),
        after={"student_id": str(student_id), "type": intervention_type},
    )
    await session.commit()
    return _presenter(rec, locale=locale)


async def list_interventions(
    session: AsyncSession,
    *,
    principal: Principal,
    student_id: uuid.UUID | None = None,
    locale: str = "vi",
) -> list[dict]:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=org_id)
    stmt = select(InterventionRecord).where(InterventionRecord.org_id == org_id)
    if student_id is not None:
        stmt = stmt.where(InterventionRecord.student_id == student_id)
    stmt = stmt.order_by(InterventionRecord.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [_presenter(r, locale=locale) for r in rows]


async def update_outcome(
    session: AsyncSession,
    *,
    principal: Principal,
    record_id: uuid.UUID,
    outcome: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "update", resource_org_id=org_id)
    rec = await _get_record(session, org_id=org_id, record_id=record_id)
    if rec is None:
        raise ResourceNotFoundError()
    if outcome not in catalog.INTERVENTION_OUTCOMES:
        raise ValidationFailedError(details={"reason": "invalid_outcome"})
    rec.outcome = outcome
    await session.flush()
    await session.refresh(rec)
    await write_audit(
        session,
        action="career_services.intervention.outcome_updated",
        resource_type="career_services_intervention",
        resource_id=rec.id,
        context=audit_ctx(principal, ctx),
        after={"outcome": outcome},
    )
    await session.commit()
    return _presenter(rec, locale=locale)
