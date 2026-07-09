"""Student privacy request submit/list + staff list/fulfill (ADR-0014, §35).

Admin fulfillment is a **manual** action (staff has already performed the
export/deletion by querying existing tables outside this service) — there is
no orchestrated auto-purge engine in V1. This service only tracks request
lifecycle state.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.compliance.domain.models import (
    ALL_STATUSES,
    OPEN_STATUSES,
    REQUEST_DELETION,
    REQUEST_TYPES,
    STATUS_FULFILLED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_REJECTED,
    TERMINAL_STATUSES,
    PrivacyRequest,
)
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.moderation import QUEUE_PRIVACY_REQUEST, sla_fields
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _require_privacy_staff(session: AsyncSession, principal: Principal) -> None:
    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.is_superadmin:
        return
    if not permission_checker.can(principal, "privacy", "process"):
        raise PermissionDeniedError()
    if not await org_reporting_facade.is_university_org(session, principal.org_id):
        raise PermissionDeniedError(details={"reason": "university_only"})


def _priority_for(request_type: str) -> str:
    """Deletion carries a legal deadline -> triaged ahead of export."""

    return "high" if request_type == REQUEST_DELETION else "normal"


def _present(row: PrivacyRequest) -> dict:
    data = {
        "id": str(row.id),
        "request_type": row.request_type,
        "status": row.status,
        "priority": _priority_for(row.request_type),
        "requested_by": str(row.requested_by),
        "processed_by": str(row.processed_by) if row.processed_by else None,
        # `processed_by` doubles as the claim/assignee once a staffer starts
        # processing (surfaced under a queue-standard key for the ops UI).
        "assigned_to": str(row.processed_by) if row.processed_by else None,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
        "fulfilled_at": row.fulfilled_at.isoformat() if row.fulfilled_at else None,
    }
    data.update(
        sla_fields(
            submitted_at=row.created_at, kind=QUEUE_PRIVACY_REQUEST, now=_now()
        )
    )
    return data


async def submit(
    session: AsyncSession,
    *,
    principal: Principal,
    request_type: str,
    note: str | None,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()
    if request_type not in REQUEST_TYPES:
        raise ValidationFailedError(details={"field": "request_type"})

    existing = (
        await session.execute(
            select(PrivacyRequest).where(
                PrivacyRequest.requested_by == principal.user_id,
                PrivacyRequest.request_type == request_type,
                PrivacyRequest.status.in_(OPEN_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"status": "request_already_pending", "request": _present(existing)}

    row = PrivacyRequest(
        request_type=request_type,
        status=STATUS_PENDING,
        requested_by=principal.user_id,
        note=(note or "").strip()[:2000] or None,
    )
    session.add(row)
    await session.flush()

    await write_audit(
        session,
        action="compliance.privacy_request_submitted",
        resource_type="privacy_request",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        after={"request_type": request_type},
    )
    await session.commit()
    return {"status": "submitted", "request": _present(row)}


async def list_mine(
    session: AsyncSession, *, principal: Principal, limit: int = 20
) -> list[dict]:
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()
    stmt = (
        select(PrivacyRequest)
        .where(PrivacyRequest.requested_by == principal.user_id)
        .order_by(PrivacyRequest.created_at.desc())
        .limit(clamp_limit(limit))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_present(r) for r in rows]


async def list_staff(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    request_type: str | None = None,
    assigned_to: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    await _require_privacy_staff(session, principal)
    stmt = select(PrivacyRequest).order_by(PrivacyRequest.created_at.desc())
    if status:
        if status not in ALL_STATUSES:
            raise ValidationFailedError(details={"field": "status"})
        stmt = stmt.where(PrivacyRequest.status == status)
    if request_type:
        if request_type not in REQUEST_TYPES:
            raise ValidationFailedError(details={"field": "request_type"})
        stmt = stmt.where(PrivacyRequest.request_type == request_type)
    if assigned_to is not None:
        stmt = stmt.where(PrivacyRequest.processed_by == assigned_to)
    stmt = stmt.limit(clamp_limit(limit))
    rows = (await session.execute(stmt)).scalars().all()
    return [_present(r) for r in rows]


async def start_processing(
    session: AsyncSession,
    *,
    principal: Principal,
    request_id: uuid.UUID,
    ctx: RequestContext,
) -> dict:
    """Claim a pending request and move it to ``processing``.

    Fills the previously-dead ``PROCESSING`` state: a deletion request carries a
    legal deadline, so staff need a visible "in progress / who owns it" state
    between submission and fulfilment. ``processed_by`` records the claimer.
    """

    await _require_privacy_staff(session, principal)
    row = (
        await session.execute(
            select(PrivacyRequest).where(PrivacyRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError()
    if row.status != STATUS_PENDING:
        raise ValidationFailedError(
            details={"field": "status", "reason": "not_pending"}
        )

    before = {"status": row.status}
    row.status = STATUS_PROCESSING
    row.processed_by = principal.user_id
    await session.flush()

    await write_audit(
        session,
        action="compliance.privacy_request_processing_started",
        resource_type="privacy_request",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={"status": STATUS_PROCESSING, "processed_by": str(principal.user_id)},
    )
    await session.commit()
    return _present(row)


async def fulfill(
    session: AsyncSession,
    *,
    principal: Principal,
    request_id: uuid.UUID,
    status: str,
    note: str | None,
    ctx: RequestContext,
) -> dict:
    await _require_privacy_staff(session, principal)
    if status not in (STATUS_FULFILLED, STATUS_REJECTED):
        raise ValidationFailedError(details={"field": "status"})

    row = (
        await session.execute(
            select(PrivacyRequest).where(PrivacyRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError()
    if row.status in TERMINAL_STATUSES:
        raise ValidationFailedError(
            details={"field": "status", "reason": "already_resolved"}
        )

    before = {"status": row.status}
    row.status = status
    row.processed_by = principal.user_id
    row.note = (note or row.note or "").strip()[:2000] or None
    if status == STATUS_FULFILLED:
        row.fulfilled_at = _now()
    await session.flush()

    await write_audit(
        session,
        action="compliance.privacy_request_fulfilled",
        resource_type="privacy_request",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={"status": status},
    )
    await session.commit()
    return _present(row)
