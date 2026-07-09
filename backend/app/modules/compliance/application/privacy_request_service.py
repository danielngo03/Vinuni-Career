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
    REQUEST_TYPES,
    STATUS_FULFILLED,
    STATUS_PENDING,
    STATUS_REJECTED,
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


def _present(row: PrivacyRequest) -> dict:
    return {
        "id": str(row.id),
        "request_type": row.request_type,
        "status": row.status,
        "requested_by": str(row.requested_by),
        "processed_by": str(row.processed_by) if row.processed_by else None,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
        "fulfilled_at": row.fulfilled_at.isoformat() if row.fulfilled_at else None,
    }


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


async def list_mine(session: AsyncSession, *, principal: Principal, limit: int = 20) -> list[dict]:
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
    stmt = stmt.limit(clamp_limit(limit))
    rows = (await session.execute(stmt)).scalars().all()
    return [_present(r) for r in rows]


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
        await session.execute(select(PrivacyRequest).where(PrivacyRequest.id == request_id))
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError()

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
