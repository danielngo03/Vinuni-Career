"""Org shared-inbox routing — assign / resolve a thread (Messaging V2).

A partner/university thread belongs to the ORG (shared inbox). A member with the
``messaging:assign`` capability routes it to a department and/or a responsible
assignee, and marks it resolved/reopened. Scoped to the caller's own org party;
cross-org callers get ``404`` (anti-enumeration). Audited.
"""

from __future__ import annotations

import uuid

from sqlalchemy import column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.messaging.application import _shared, capability, party_service
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import MessageThread, MessageThreadParty
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

_departments = table("departments", column("id"), column("org_id"))


async def _org_party_for_caller(
    session: AsyncSession, *, thread: MessageThread, principal: Principal
) -> MessageThreadParty:
    """The thread's org party matching the caller's org, or 404."""

    if principal.org_id is None:
        raise ResourceNotFoundError()
    party_list = await party_service.list_parties(session, thread_id=thread.id)
    party = next(
        (
            p
            for p in party_list
            if p.party_kind == rules.PARTY_ORG and p.org_id == principal.org_id
        ),
        None,
    )
    if party is None:
        raise ResourceNotFoundError()
    return party


async def assign(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    department_id: uuid.UUID | None,
    assignee_id: uuid.UUID | None,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    thread = await _shared.load_thread(session, thread_id=thread_id, lock=True)
    party = await _org_party_for_caller(session, thread=thread, principal=principal)
    if not capability.can_assign(principal, party.org_id):  # type: ignore[arg-type]
        raise PermissionDeniedError()

    if department_id is not None:
        row = (
            await session.execute(
                select(_departments.c.id).where(
                    _departments.c.id == department_id,
                    _departments.c.org_id == party.org_id,
                )
            )
        ).first()
        if row is None:
            raise ValidationFailedError(details={"field": "department_id"})
        party.assigned_department_id = department_id

    if assignee_id is not None:
        members = await org_reporting_facade.active_member_ids(
            session, org_id=party.org_id, user_ids=[assignee_id]  # type: ignore[arg-type]
        )
        if assignee_id not in members:
            raise ValidationFailedError(details={"field": "assignee_id"})
        party.assigned_user_id = assignee_id

    if department_id is not None or assignee_id is not None:
        party.assignment_state = rules.ASSIGN_ASSIGNED

    await session.flush()
    await write_audit(
        session,
        action="messaging.thread.assign",
        resource_type="message_thread",
        resource_id=thread.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "thread_id": str(thread.id),
            "department_id": str(department_id) if department_id else None,
            "assignee_id": str(assignee_id) if assignee_id else None,
            "assignment_state": party.assignment_state,
        },
    )
    await session.commit()
    from app.modules.messaging.application.message_service import (
        _publish_thread_signal,
    )

    await _publish_thread_signal(
        session, thread_id=thread.id, event_type="thread.updated"
    )
    return {
        "status": "ok",
        "thread_id": str(thread.id),
        "assignment_state": party.assignment_state,
        "assigned_department_id": (
            str(party.assigned_department_id)
            if party.assigned_department_id
            else None
        ),
        "assigned_user_id": (
            str(party.assigned_user_id) if party.assigned_user_id else None
        ),
    }


async def set_resolution(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    resolved: bool,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    thread = await _shared.load_thread(session, thread_id=thread_id, lock=True)
    party = await _org_party_for_caller(session, thread=thread, principal=principal)
    if not capability.can_assign(principal, party.org_id):  # type: ignore[arg-type]
        raise PermissionDeniedError()
    party.assignment_state = (
        rules.ASSIGN_RESOLVED
        if resolved
        else (
            rules.ASSIGN_ASSIGNED
            if party.assigned_user_id or party.assigned_department_id
            else rules.ASSIGN_UNASSIGNED
        )
    )
    await session.flush()
    await write_audit(
        session,
        action="messaging.thread.resolve" if resolved else "messaging.thread.reopen",
        resource_type="message_thread",
        resource_id=thread.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"thread_id": str(thread.id), "assignment_state": party.assignment_state},
    )
    await session.commit()
    from app.modules.messaging.application.message_service import (
        _publish_thread_signal,
    )

    await _publish_thread_signal(
        session, thread_id=thread.id, event_type="thread.updated"
    )
    return {
        "status": "ok",
        "thread_id": str(thread.id),
        "assignment_state": party.assignment_state,
    }
