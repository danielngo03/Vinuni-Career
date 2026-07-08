"""Message-request responses — accept / decline / block (Messaging V2).

The RECIPIENT party of a still-``pending`` request decides whether the conversation
opens. Only a member of the recipient party may act (a user party = that user; an org
party = a staff member with the ``messaging`` capability). Non-recipient / non-member
callers get ``404`` (anti-enumeration). Every transition is audited (PII-safe).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.messaging.application import _shared, capability, party_service
from app.modules.messaging.application.errors import RequestNotActionableError
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import (
    MessageThread,
    MessageThreadParticipant,
    MessageThreadParty,
)
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal

_ACTIONS = {
    "accept": rules.REQUEST_ACCEPTED,
    "decline": rules.REQUEST_DECLINED,
    "block": rules.REQUEST_BLOCKED,
}


async def _recipient_party(
    session: AsyncSession, thread: MessageThread
) -> MessageThreadParty | None:
    party_list = await party_service.list_parties(session, thread_id=thread.id)
    return next(
        (p for p in party_list if p.id != thread.initiator_party_id), None
    )


async def _actor_on_party(
    session: AsyncSession, *, principal: Principal, party: MessageThreadParty
) -> bool:
    if party.party_kind == rules.PARTY_USER:
        return party.user_id == principal.user_id
    if party.party_kind == rules.PARTY_ORG and party.org_id is not None:
        return (
            principal.org_id == party.org_id
            and capability.can_send_as_org(principal, party.org_id)
        )
    return False


async def respond(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    action: str,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    if action not in _ACTIONS:
        raise ValidationFailedError(details={"field": "action"})

    thread = await _shared.load_thread(session, thread_id=thread_id, lock=True)
    if thread.request_state != rules.REQUEST_PENDING:
        raise RequestNotActionableError()

    recipient = await _recipient_party(session, thread)
    if recipient is None or not await _actor_on_party(
        session, principal=principal, party=recipient
    ):
        raise ResourceNotFoundError()

    new_state = _ACTIONS[action]
    thread.request_state = new_state
    thread.version += 1

    # On accept by an org Page, register the acting staff as a participant so the
    # thread shows in their personal list + read-state; other staff use the inbox.
    if action == "accept" and recipient.party_kind == rules.PARTY_ORG:
        existing = await _shared.get_participant(
            session, thread_id=thread_id, user_id=principal.user_id
        )
        if existing is None:
            session.add(
                MessageThreadParticipant(
                    thread_id=thread_id, user_id=principal.user_id,
                    party_id=recipient.id, role_in_thread="member", can_reply=True,
                )
            )

    await session.flush()
    await write_audit(
        session,
        action=f"messaging.request.{action}",
        resource_type="message_thread",
        resource_id=thread.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "thread_id": str(thread.id),
            "request_state": new_state,
            "actor_id": str(principal.user_id),
        },
    )
    await session.commit()
    return {"status": "ok", "thread_id": str(thread.id), "request_state": new_state}
