"""Party construction + resolution (Messaging V2, owner decision 2026-07-09).

A thread has one or two PARTIES. This module builds them at create time and resolves
them at read time. An ``org`` party is a partner/university acting as a single Page
(shared team inbox) — it carries NO per-user participant rows for the whole staff;
access is computed from RBAC + department scope, and read-state is a shared cursor on
the party row. A ``user`` party is a single individual with a normal participant row.

Only the INITIATING staff member of an org-initiated thread gets a participant row
(so the thread shows in their personal list + for audit); every other staff member
reaches the thread through the org inbox (``inbox_service``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.messaging.domain import parties, rules
from app.modules.messaging.domain.models import (
    MessageThread,
    MessageThreadParticipant,
    MessageThreadParty,
)


@dataclass(frozen=True, slots=True)
class RecipientUser:
    user_id: uuid.UUID
    persona: str


async def list_parties(
    session: AsyncSession, *, thread_id: uuid.UUID
) -> list[MessageThreadParty]:
    return list(
        (
            await session.execute(
                select(MessageThreadParty).where(
                    MessageThreadParty.thread_id == thread_id
                )
            )
        )
        .scalars()
        .all()
    )


async def get_party(
    session: AsyncSession, *, party_id: uuid.UUID | None
) -> MessageThreadParty | None:
    if party_id is None:
        return None
    return (
        await session.execute(
            select(MessageThreadParty).where(MessageThreadParty.id == party_id)
        )
    ).scalar_one_or_none()


def _sender_party_kind(*, sender_persona: str, thread_kind: str) -> tuple[str, str]:
    """(party_kind, identity_mode) for the sender given the resolved thread kind."""

    # Internal colleague/department DMs never mask — the sender is a person.
    if thread_kind == rules.TK_INTERNAL:
        return rules.PARTY_USER, rules.IDENTITY_PERSON
    if parties.is_org_side(sender_persona):
        return rules.PARTY_ORG, rules.IDENTITY_ORG
    return rules.PARTY_USER, rules.IDENTITY_PERSON


async def build_parties(
    session: AsyncSession,
    *,
    thread: MessageThread,
    sender_id: uuid.UUID,
    sender_persona: str,
    sender_org_id: uuid.UUID | None,
    thread_kind: str,
    recipient_users: list[RecipientUser],
    target_org_id: uuid.UUID | None,
    target_department_id: uuid.UUID | None,
) -> MessageThreadParty:
    """Create party rows for a freshly-inserted thread and stamp participant.party_id.

    Returns the INITIATOR (sender) party. Assumes ``thread`` + its participant rows are
    already flushed (the legacy create path builds participants); this only adds the
    party layer and links participants to their party.
    """

    # --- sender party -----------------------------------------------------------
    s_kind, s_mode = _sender_party_kind(
        sender_persona=sender_persona, thread_kind=thread_kind
    )
    sender_party = MessageThreadParty(
        thread_id=thread.id,
        party_kind=s_kind,
        user_id=sender_id if s_kind == rules.PARTY_USER else None,
        org_id=sender_org_id if s_kind == rules.PARTY_ORG else None,
        identity_mode=s_mode,
    )
    session.add(sender_party)

    # --- recipient party/parties ------------------------------------------------
    recipient_parties: list[MessageThreadParty] = []
    if target_org_id is not None:
        # Individual/Page → an org Page (student→org, partner→university).
        recipient_parties.append(
            MessageThreadParty(
                thread_id=thread.id,
                party_kind=rules.PARTY_ORG,
                org_id=target_org_id,
                identity_mode=rules.IDENTITY_ORG,
            )
        )
    elif target_department_id is not None:
        # Internal department channel (shared inbox, names visible).
        recipient_parties.append(
            MessageThreadParty(
                thread_id=thread.id,
                party_kind=rules.PARTY_ORG,
                org_id=sender_org_id,
                identity_mode=rules.IDENTITY_PERSON,
                assigned_department_id=target_department_id,
                assignment_state=rules.ASSIGN_ASSIGNED,
            )
        )
    else:
        # User recipients. Org-side recipients (an application's owning partner, or a
        # university staffer being addressed as their Page) collapse into ONE org
        # party per org; individuals become user parties.
        org_parties: dict[uuid.UUID, MessageThreadParty] = {}
        for r in recipient_users:
            if parties.is_org_side(r.persona) and thread_kind != rules.TK_INTERNAL:
                # Resolve their org via the thread's org scope (application/support)
                # — a partner recipient belongs to thread.org_id.
                key = thread.org_id
                if key not in org_parties:
                    org_parties[key] = MessageThreadParty(
                        thread_id=thread.id,
                        party_kind=rules.PARTY_ORG,
                        org_id=key,
                        identity_mode=rules.IDENTITY_ORG,
                    )
                    recipient_parties.append(org_parties[key])
            else:
                recipient_parties.append(
                    MessageThreadParty(
                        thread_id=thread.id,
                        party_kind=rules.PARTY_USER,
                        user_id=r.user_id,
                        identity_mode=rules.IDENTITY_PERSON,
                    )
                )

    for p in recipient_parties:
        session.add(p)
    await session.flush()

    # --- link participant rows to their party ----------------------------------
    participants = list(
        (
            await session.execute(
                select(MessageThreadParticipant).where(
                    MessageThreadParticipant.thread_id == thread.id
                )
            )
        )
        .scalars()
        .all()
    )
    # user_id -> recipient party
    user_party_by_uid = {
        p.user_id: p for p in recipient_parties if p.party_kind == rules.PARTY_USER
    }
    for part in participants:
        if part.user_id == sender_id:
            part.party_id = sender_party.id
        elif part.user_id in user_party_by_uid:
            part.party_id = user_party_by_uid[part.user_id].id
    await session.flush()
    return sender_party


async def party_for_user(
    session: AsyncSession,
    *,
    thread_id: uuid.UUID,
    user_id: uuid.UUID,
    user_org_ids: set[uuid.UUID],
) -> MessageThreadParty | None:
    """Which party a user acts within: their user party, else the org party of an
    org they are an active member of (staff acting for the org Page)."""

    party_list = await list_parties(session, thread_id=thread_id)
    for p in party_list:
        if p.party_kind == rules.PARTY_USER and p.user_id == user_id:
            return p
    for p in party_list:
        if p.party_kind == rules.PARTY_ORG and p.org_id in user_org_ids:
            return p
    return None
