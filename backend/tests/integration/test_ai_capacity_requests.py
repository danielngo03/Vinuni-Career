"""University AI capacity-request workflow (WS1.5) — service tests.

Covers staff submit (happy / permission / invalid / duplicate), the superadmin
queue gate, and the decide path (approve raises the target ceiling + notifies;
deny; validation; not-found; already-decided). Offline (SQLite), no real LLM.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.energy import service as energy
from app.ai.energy.models import SCOPE_USER
from app.modules.ai_governance.application import capacity_service
from app.modules.ai_governance.domain.models import STATUS_APPROVED, STATUS_DENIED
from app.modules.notifications.domain.models import Notification
from app.shared.audit import AuditContext
from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal
from sqlalchemy import select


def _uni(org_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None) -> Principal:
    return Principal(
        user_id=user_id or uuid.uuid4(),
        persona="university_staff",
        org_id=org_id or uuid.uuid4(),
    )


def _superadmin() -> Principal:
    return Principal(user_id=uuid.uuid4(), persona="university_staff", is_superadmin=True)


def _ctx(principal: Principal) -> AuditContext:
    return AuditContext(actor_id=principal.user_id, actor_org_id=principal.org_id)


# --------------------------------------------------------------------------- #
# Staff submit                                                                  #
# --------------------------------------------------------------------------- #


async def test_submit_request_happy(db_session) -> None:
    p = _uni()
    result = await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="Cần thêm để chấm điểm", requested_units=500
    )
    assert result["status"] == "pending"
    assert result["scope_type"] == "user"
    assert result["scope_id"] == str(p.user_id)
    assert result["requested_units"] == 500

    mine = await capacity_service.list_my_requests(db_session, principal=p)
    assert len(mine) == 1
    assert mine[0]["id"] == result["id"]


async def test_submit_requires_university_member(db_session) -> None:
    # No org context → denied.
    student = Principal(user_id=uuid.uuid4(), persona="student")
    with pytest.raises(PermissionDeniedError):
        await capacity_service.submit_request(
            db_session, principal=student, ctx=_ctx(student), reason="x"
        )


async def test_submit_rejects_empty_reason(db_session) -> None:
    p = _uni()
    with pytest.raises(ValidationFailedError):
        await capacity_service.submit_request(
            db_session, principal=p, ctx=_ctx(p), reason="   "
        )


async def test_submit_rejects_bad_units(db_session) -> None:
    p = _uni()
    with pytest.raises(ValidationFailedError):
        await capacity_service.submit_request(
            db_session, principal=p, ctx=_ctx(p), reason="ok", requested_units=0
        )


async def test_submit_duplicate_pending_conflict(db_session) -> None:
    p = _uni()
    await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="first"
    )
    with pytest.raises(ConflictError):
        await capacity_service.submit_request(
            db_session, principal=p, ctx=_ctx(p), reason="second"
        )


# --------------------------------------------------------------------------- #
# Superadmin queue                                                              #
# --------------------------------------------------------------------------- #


async def test_list_requests_requires_superadmin(db_session) -> None:
    p = _uni()
    with pytest.raises(PermissionDeniedError):
        await capacity_service.list_requests(db_session, principal=p)


async def test_list_requests_pending_queue(db_session) -> None:
    p = _uni()
    await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="need more"
    )
    queue = await capacity_service.list_requests(db_session, principal=_superadmin())
    assert len(queue) == 1
    assert queue[0]["status"] == "pending"
    assert "requested_by_email" in queue[0]


# --------------------------------------------------------------------------- #
# Superadmin decide                                                             #
# --------------------------------------------------------------------------- #


async def test_decide_approve_sets_ceiling_and_notifies(db_session) -> None:
    p = _uni()
    req = await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="need", requested_units=800
    )
    su = _superadmin()
    result = await capacity_service.decide_request(
        db_session,
        principal=su,
        ctx=_ctx(su),
        request_id=uuid.UUID(req["id"]),
        decision="approve",
    )
    assert result["status"] == STATUS_APPROVED
    assert result["granted_units"] == 800

    # The target user's energy ceiling was raised.
    acct = await energy._account(db_session, SCOPE_USER, p.user_id)
    assert acct is not None
    assert acct.weekly_allowance_units == 800

    # The requester was notified (in-app feed row).
    notif = (
        await db_session.execute(
            select(Notification).where(Notification.recipient_id == p.user_id)
        )
    ).scalar_one_or_none()
    assert notif is not None
    assert notif.notif_type == "ai_governance.capacity_approved"


async def test_decide_approve_uses_granted_units_override(db_session) -> None:
    p = _uni()
    req = await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="need", requested_units=800
    )
    su = _superadmin()
    result = await capacity_service.decide_request(
        db_session, principal=su, ctx=_ctx(su),
        request_id=uuid.UUID(req["id"]), decision="approve", granted_units=200,
    )
    assert result["granted_units"] == 200
    acct = await energy._account(db_session, SCOPE_USER, p.user_id)
    assert acct is not None and acct.weekly_allowance_units == 200


async def test_decide_approve_requires_units(db_session) -> None:
    p = _uni()
    req = await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="need"  # no requested_units
    )
    su = _superadmin()
    with pytest.raises(ValidationFailedError):
        await capacity_service.decide_request(
            db_session, principal=su, ctx=_ctx(su),
            request_id=uuid.UUID(req["id"]), decision="approve",
        )


async def test_decide_deny(db_session) -> None:
    p = _uni()
    req = await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="need", requested_units=100
    )
    su = _superadmin()
    result = await capacity_service.decide_request(
        db_session, principal=su, ctx=_ctx(su),
        request_id=uuid.UUID(req["id"]), decision="deny", note="Không đủ ngân sách",
    )
    assert result["status"] == STATUS_DENIED
    # No ceiling was set.
    acct = await energy._account(db_session, SCOPE_USER, p.user_id)
    assert acct is None


async def test_decide_requires_superadmin(db_session) -> None:
    p = _uni()
    req = await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="need", requested_units=100
    )
    with pytest.raises(PermissionDeniedError):
        await capacity_service.decide_request(
            db_session, principal=p, ctx=_ctx(p),
            request_id=uuid.UUID(req["id"]), decision="approve",
        )


async def test_decide_not_found(db_session) -> None:
    su = _superadmin()
    with pytest.raises(ResourceNotFoundError):
        await capacity_service.decide_request(
            db_session, principal=su, ctx=_ctx(su),
            request_id=uuid.uuid4(), decision="deny",
        )


async def test_decide_already_decided_conflict(db_session) -> None:
    p = _uni()
    req = await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="need", requested_units=100
    )
    su = _superadmin()
    await capacity_service.decide_request(
        db_session, principal=su, ctx=_ctx(su),
        request_id=uuid.UUID(req["id"]), decision="deny",
    )
    with pytest.raises(ConflictError):
        await capacity_service.decide_request(
            db_session, principal=su, ctx=_ctx(su),
            request_id=uuid.UUID(req["id"]), decision="approve", granted_units=100,
        )


async def test_decide_invalid_decision(db_session) -> None:
    p = _uni()
    req = await capacity_service.submit_request(
        db_session, principal=p, ctx=_ctx(p), reason="need", requested_units=100
    )
    su = _superadmin()
    with pytest.raises(ValidationFailedError):
        await capacity_service.decide_request(
            db_session, principal=su, ctx=_ctx(su),
            request_id=uuid.UUID(req["id"]), decision="maybe",
        )
