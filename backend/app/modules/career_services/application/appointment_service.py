"""Counselor <-> student appointments (B-554).

RBAC resource: ``career_services_appointments``. Concurrency/edge case: two
simultaneous booking requests for the same counselor + timeslot must not both
succeed (``docs/EDGE_CASES_FAILURE_MODES.md`` concurrent-write class). This is
enforced two ways:

1. A pre-check query inside the same transaction (fast-path, catches the common
   sequential case and gives a clean ``409`` before touching the DB row).
2. ``UniqueConstraint(counselor_id, conflict_key)`` on the table (belt-and-
   suspenders for a true race — two requests committing concurrently) — an
   ``IntegrityError`` on flush is translated to the same ``409 CONFLICT``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.career_services.application.common import audit_ctx, require_org
from app.modules.career_services.domain import catalog
from app.modules.career_services.domain.models import Appointment
from app.shared.audit import write_audit
from app.shared.exceptions import ConflictError, ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "career_services_appointments"


def _conflict_key(status: str, scheduled_at: datetime) -> datetime | None:
    return scheduled_at if status in catalog.APPT_ACTIVE_STATUSES else None


def _presenter(appt: Appointment, *, locale: str = "vi") -> dict:
    return {
        "id": str(appt.id),
        "student_id": str(appt.student_id),
        "counselor_id": str(appt.counselor_id),
        "scheduled_at": appt.scheduled_at.isoformat() if appt.scheduled_at else None,
        "duration_minutes": appt.duration_minutes,
        "mode": appt.mode,
        "mode_label": catalog.appointment_mode_label(appt.mode, locale=locale),
        "location": appt.location,
        "status": appt.status,
        "status_label": catalog.appointment_status_label(appt.status, locale=locale),
        "notes": appt.notes,
        "cancel_reason": appt.cancel_reason,
        "created_at": appt.created_at.isoformat() if appt.created_at else None,
        "updated_at": appt.updated_at.isoformat() if appt.updated_at else None,
    }


async def _get_appt(
    session: AsyncSession, *, org_id: uuid.UUID, appt_id: uuid.UUID
) -> Appointment | None:
    stmt = select(Appointment).where(
        Appointment.id == appt_id, Appointment.org_id == org_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def book_appointment(
    session: AsyncSession,
    *,
    principal: Principal,
    student_id: uuid.UUID,
    counselor_id: uuid.UUID,
    scheduled_at: datetime,
    duration_minutes: int,
    mode: str,
    location: str | None,
    notes: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(
        principal, _RESOURCE, "create", resource_org_id=org_id
    )
    if mode not in catalog.APPT_MODES:
        raise ValidationFailedError(details={"reason": "invalid_mode"})
    if duration_minutes < 5 or duration_minutes > 240:
        raise ValidationFailedError(details={"reason": "invalid_duration"})

    # Fast-path conflict check (sequential race, no DB round-trip needed on error).
    existing = (
        await session.execute(
            select(Appointment.id).where(
                Appointment.counselor_id == counselor_id,
                Appointment.scheduled_at == scheduled_at,
                Appointment.status.in_(catalog.APPT_ACTIVE_STATUSES),
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(details={"reason": "counselor_slot_taken"})

    appt = Appointment(
        org_id=org_id,
        student_id=student_id,
        counselor_id=counselor_id,
        scheduled_at=scheduled_at,
        conflict_key=_conflict_key(catalog.APPT_REQUESTED, scheduled_at),
        duration_minutes=duration_minutes,
        mode=mode,
        location=location,
        status=catalog.APPT_REQUESTED,
        notes=notes,
        created_by=principal.user_id,
    )
    session.add(appt)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(details={"reason": "counselor_slot_taken"}) from exc

    await write_audit(
        session,
        action="career_services.appointment.booked",
        resource_type="career_services_appointment",
        resource_id=appt.id,
        context=audit_ctx(principal, ctx),
        after={
            "student_id": str(student_id),
            "counselor_id": str(counselor_id),
            "scheduled_at": scheduled_at.isoformat(),
        },
    )
    await session.commit()
    return _presenter(appt, locale=locale)


async def list_appointments(
    session: AsyncSession,
    *,
    principal: Principal,
    counselor_id: uuid.UUID | None = None,
    student_id: uuid.UUID | None = None,
    status: str | None = None,
    locale: str = "vi",
) -> list[dict]:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=org_id)
    stmt = select(Appointment).where(Appointment.org_id == org_id)
    if counselor_id is not None:
        stmt = stmt.where(Appointment.counselor_id == counselor_id)
    if student_id is not None:
        stmt = stmt.where(Appointment.student_id == student_id)
    if status is not None:
        if status not in catalog.APPT_STATUSES:
            raise ValidationFailedError(details={"reason": "invalid_status"})
        stmt = stmt.where(Appointment.status == status)
    stmt = stmt.order_by(Appointment.scheduled_at)
    rows = (await session.execute(stmt)).scalars().all()
    return [_presenter(a, locale=locale) for a in rows]


async def update_status(
    session: AsyncSession,
    *,
    principal: Principal,
    appointment_id: uuid.UUID,
    status: str,
    cancel_reason: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(
        principal, _RESOURCE, "cancel" if status == catalog.APPT_CANCELLED else "update",
        resource_org_id=org_id,
    )
    appt = await _get_appt(session, org_id=org_id, appt_id=appointment_id)
    if appt is None:
        raise ResourceNotFoundError()
    if status not in catalog.APPT_STATUSES:
        raise ValidationFailedError(details={"reason": "invalid_status"})
    if status == catalog.APPT_CANCELLED and (
        not cancel_reason or not cancel_reason.strip()
    ):
        raise ValidationFailedError(details={"reason": "cancel_reason_required"})

    appt.status = status
    appt.conflict_key = _conflict_key(status, appt.scheduled_at)
    if status == catalog.APPT_CANCELLED:
        appt.cancel_reason = cancel_reason.strip()

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(details={"reason": "counselor_slot_taken"}) from exc
    await session.refresh(appt)

    await write_audit(
        session,
        action="career_services.appointment.status_changed",
        resource_type="career_services_appointment",
        resource_id=appt.id,
        context=audit_ctx(principal, ctx),
        after={"status": status},
    )
    await session.commit()
    return _presenter(appt, locale=locale)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)
