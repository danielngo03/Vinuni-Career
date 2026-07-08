"""University AI capacity-request workflow (WS1.5).

University energy is DISTRIBUTION, not billing. When a staff member exhausts
their distributed weekly AI allocation they cannot self-serve upgrade — they
submit a capacity request, and a platform superadmin approves (raising the
target's ``AiEnergyAccount`` ceiling) or denies it. Every write is audited and
the requester is notified asynchronously (in-app feed; no synchronous SMTP).

RBAC is enforced here in the service layer (defence-in-depth), not only in the
router. Energy amounts are opaque product credits — never tokens, USD, provider,
or model.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy import distribution
from app.modules.ai_governance.domain.models import (
    REQUEST_SCOPE_DEPARTMENT,
    REQUEST_SCOPE_USER,
    STATUS_APPROVED,
    STATUS_DENIED,
    STATUS_PENDING,
    AiCapacityRequest,
)
from app.modules.notifications.application import feed_service
from app.modules.users.application import user_read_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

# Guard rails on the requested/granted energy amount (opaque credits).
MAX_REQUEST_UNITS = 100_000
MAX_REASON_LEN = 2000

_DECISION_APPROVE = "approve"
_DECISION_DENY = "deny"


def _is_university(principal: Principal) -> bool:
    persona = principal.persona
    return persona == "university_staff" or persona.startswith("university")


def _require_university_member(principal: Principal) -> tuple[uuid.UUID, uuid.UUID]:
    """A university staff member acting from a university org. Returns (user, org)."""

    if not principal.is_authenticated or principal.user_id is None:
        raise PermissionDeniedError()
    if principal.org_id is None or not (_is_university(principal) or principal.is_superadmin):
        raise PermissionDeniedError()
    return principal.user_id, principal.org_id


def _require_superadmin(principal: Principal) -> None:
    if not principal.is_superadmin:
        raise PermissionDeniedError()


def _to_dict(row: AiCapacityRequest) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "org_id": str(row.org_id),
        "requested_by": str(row.requested_by),
        "scope_type": row.scope_type,
        "scope_id": str(row.scope_id),
        "reason": row.reason,
        "requested_units": row.requested_units,
        "status": row.status,
        "decided_by": str(row.decided_by) if row.decided_by else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decision_note": row.decision_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_units(units: int | None) -> int | None:
    if units is None:
        return None
    units = int(units)
    if units <= 0 or units > MAX_REQUEST_UNITS:
        raise ValidationFailedError(
            "Số năng lượng AI yêu cầu không hợp lệ."
        )
    return units


# --------------------------------------------------------------------------- #
# Staff (university member)                                                     #
# --------------------------------------------------------------------------- #


async def submit_request(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    reason: str,
    requested_units: int | None = None,
) -> dict[str, Any]:
    """Create a pending capacity request for the caller's own user allocation.

    One pending request per member — a duplicate raises ``ConflictError``.
    """

    user_id, org_id = _require_university_member(principal)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationFailedError(
            "Vui lòng nhập lý do cho yêu cầu cấp thêm năng lượng AI."
        )
    reason = reason[:MAX_REASON_LEN]
    requested_units = _validate_units(requested_units)

    existing = (
        await session.execute(
            select(AiCapacityRequest.id).where(
                AiCapacityRequest.requested_by == user_id,
                AiCapacityRequest.scope_type == REQUEST_SCOPE_USER,
                AiCapacityRequest.scope_id == user_id,
                AiCapacityRequest.status == STATUS_PENDING,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            "Bạn đã có một yêu cầu cấp thêm năng lượng AI đang chờ duyệt."
        )

    row = AiCapacityRequest(
        org_id=org_id,
        requested_by=user_id,
        scope_type=REQUEST_SCOPE_USER,
        scope_id=user_id,
        reason=reason,
        requested_units=requested_units,
        status=STATUS_PENDING,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    after = _to_dict(row)
    await write_audit(
        session,
        action="ai_capacity_request.created",
        resource_type="ai_capacity_request",
        resource_id=row.id,
        context=ctx,
        before=None,
        after=after,
    )
    await session.commit()
    return after


async def list_my_requests(
    session: AsyncSession, *, principal: Principal
) -> list[dict[str, Any]]:
    """The caller's own capacity requests, newest first."""

    if not principal.is_authenticated or principal.user_id is None:
        raise PermissionDeniedError()
    rows = (
        await session.execute(
            select(AiCapacityRequest)
            .where(AiCapacityRequest.requested_by == principal.user_id)
            .order_by(AiCapacityRequest.created_at.desc())
        )
    ).scalars().all()
    return [_to_dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Superadmin queue + decision                                                  #
# --------------------------------------------------------------------------- #


async def list_requests(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = STATUS_PENDING,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Superadmin queue of capacity requests (oldest first), optional status filter.

    Enriches each row with the requester's email/name (superadmin admin surface)
    so the queue is actionable without a second round-trip. Never exposes energy
    internals beyond the opaque requested-units credit count.
    """

    _require_superadmin(principal)
    stmt = select(AiCapacityRequest)
    if status is not None:
        if status not in (STATUS_PENDING, STATUS_APPROVED, STATUS_DENIED):
            raise ValidationFailedError("Trạng thái lọc không hợp lệ.")
        stmt = stmt.where(AiCapacityRequest.status == status)
    stmt = stmt.order_by(AiCapacityRequest.created_at).limit(max(1, min(limit, 500)))
    rows = (await session.execute(stmt)).scalars().all()

    contacts = await user_read_facade.get_user_contacts(
        session, [r.requested_by for r in rows]
    )
    items: list[dict[str, Any]] = []
    for r in rows:
        item = _to_dict(r)
        contact = contacts.get(r.requested_by)
        item["requested_by_email"] = contact.email if contact else None
        item["requested_by_name"] = contact.full_name if contact else None
        items.append(item)
    return items


async def decide_request(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    request_id: uuid.UUID,
    decision: str,
    granted_units: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Approve (raise the target ceiling) or deny a pending capacity request.

    Approve upserts the target ``AiEnergyAccount`` ceiling to ``granted_units``
    (or the requested amount). The decision is audited and the requester is
    notified in-app. A non-pending request raises ``ConflictError``.
    """

    _require_superadmin(principal)
    if decision not in (_DECISION_APPROVE, _DECISION_DENY):
        raise ValidationFailedError("Quyết định không hợp lệ.")

    row = (
        await session.execute(
            select(AiCapacityRequest).where(AiCapacityRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError("Không tìm thấy yêu cầu.")
    if row.status != STATUS_PENDING:
        raise ConflictError("Yêu cầu này đã được xử lý.")

    before = _to_dict(row)
    granted_units = _validate_units(granted_units)
    note = (note or "").strip() or None

    granted_effective: int | None = None
    if decision == _DECISION_APPROVE:
        granted_effective = granted_units if granted_units is not None else row.requested_units
        if granted_effective is None:
            raise ValidationFailedError(
                "Cần nhập số năng lượng AI muốn cấp để duyệt yêu cầu."
            )
        if row.scope_type not in (REQUEST_SCOPE_USER, REQUEST_SCOPE_DEPARTMENT):
            raise ValidationFailedError("Phạm vi yêu cầu không hợp lệ.")
        await distribution.upsert_allowance(
            session,
            scope_type=row.scope_type,
            scope_id=row.scope_id,
            org_id=row.org_id,
            weekly_allowance_units=granted_effective,
            updated_by=principal.user_id,
        )
        row.status = STATUS_APPROVED
        notif_type = "ai_governance.capacity_approved"
    else:
        row.status = STATUS_DENIED
        notif_type = "ai_governance.capacity_denied"

    row.decided_by = principal.user_id
    row.decided_at = datetime.now(UTC)
    row.decision_note = note
    await session.flush()
    await session.refresh(row)

    after = _to_dict(row)
    after["granted_units"] = granted_effective
    await write_audit(
        session,
        action="ai_capacity_request.decided",
        resource_type="ai_capacity_request",
        resource_id=row.id,
        context=ctx,
        before=before,
        after=after,
    )

    # Non-blocking, always-renders in-app notification to the requester.
    await feed_service.create_in_app(
        session,
        recipient_id=row.requested_by,
        notif_type=notif_type,
        action_url=f"/university/ai/capacity-requests/{row.id}",
        sender_id=principal.user_id,
    )
    await session.commit()
    return after
