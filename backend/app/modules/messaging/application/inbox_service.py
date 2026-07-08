"""Organization shared inbox (Messaging V2, owner decision 2026-07-09).

Partner/University threads belong to the ORG, not one recruiter. A member with the
``messaging:read`` capability sees the org's inbox; a member who can also ``assign``
(effectively an admin/lead) sees ALL of it, while a plain member is scoped to their
department(s) + unassigned + assigned-to-them. Read-state is shared on the org party
(``last_read_at``). Filters: unassigned / mine / all / resolved, department, search.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.messaging.api import presenters
from app.modules.messaging.application import _shared, capability, thread_view
from app.modules.messaging.application.recruitment_relationship import load_relationship
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import (
    Message,
    MessageThread,
    MessageThreadParty,
)
from app.modules.organization.application import org_reporting_facade
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


async def _org_unread(
    session: AsyncSession, *, thread_id: uuid.UUID, party: MessageThreadParty
) -> int:
    anchor = _shared.as_aware(party.last_read_at) if party.last_read_at else _EPOCH
    return (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.thread_id == thread_id,
                Message.created_at > anchor,
                or_(
                    Message.sender_party_id.is_(None),
                    Message.sender_party_id != party.id,
                ),
                Message.deleted_at.is_(None),
            )
        )
    ).scalar_one()


async def list_org_inbox(
    session: AsyncSession,
    *,
    principal: Principal,
    scope: str = "all",
    department_id: uuid.UUID | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    org_id = principal.org_id
    if org_id is None or not capability.can_read_org_inbox(principal, org_id):
        raise PermissionDeniedError()

    page_limit = clamp_limit(limit)
    sees_all = capability.can_assign(principal, org_id) or principal.is_superadmin
    my_departments: set[uuid.UUID] = set()
    if not sees_all:
        my_departments = await org_reporting_facade.department_ids_for_user_in_org(
            session, org_id=org_id, user_id=principal.user_id
        )

    P = MessageThreadParty
    conds = [
        P.party_kind == rules.PARTY_ORG,
        P.org_id == org_id,
        MessageThread.deleted_at.is_(None),
    ]
    # Scope filter.
    if scope == "unassigned":
        conds.append(P.assignment_state == rules.ASSIGN_UNASSIGNED)
    elif scope == "mine":
        conds.append(P.assigned_user_id == principal.user_id)
    elif scope == "resolved":
        conds.append(P.assignment_state == rules.ASSIGN_RESOLVED)
    else:  # all — hide resolved from the default view
        conds.append(P.assignment_state != rules.ASSIGN_RESOLVED)
    # Department filter (explicit).
    if department_id is not None:
        conds.append(P.assigned_department_id == department_id)
    # Non-admin visibility: their departments + unassigned + assigned-to-them.
    if not sees_all:
        visibility = [
            P.assigned_user_id == principal.user_id,
            P.assigned_department_id.is_(None),
        ]
        if my_departments:
            visibility.append(P.assigned_department_id.in_(my_departments))
        conds.append(or_(*visibility))
    # Text search on subject.
    if q:
        conds.append(func.lower(MessageThread.subject).like(f"%{q.strip().lower()}%"))

    stmt = (
        select(MessageThread, P)
        .join(P, P.thread_id == MessageThread.id)
        .where(and_(*conds))
    )
    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_sort = datetime.fromisoformat(decoded["sort"])
        anchor_id = uuid.UUID(decoded["id"])
        sort_expr = func.coalesce(
            MessageThread.last_message_at, MessageThread.created_at
        )
        stmt = stmt.where(
            or_(
                sort_expr < anchor_sort,
                and_(sort_expr == anchor_sort, MessageThread.id < anchor_id),
            )
        )
    stmt = stmt.order_by(
        func.coalesce(MessageThread.last_message_at, MessageThread.created_at).desc(),
        MessageThread.id.desc(),
    ).limit(page_limit + 1)

    rows = list((await session.execute(stmt)).all())
    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda r: {
            "sort": _shared.as_aware(
                r[0].last_message_at or r[0].created_at
            ).isoformat(),
            "id": str(r[0].id),
        },
    )
    is_mod = await _shared.is_university_moderator(session, principal)
    items: list[dict] = []
    for thread, party in page.items:
        relationship = None
        if thread.context_type == rules.CONTEXT_APPLICATION and thread.context_id:
            relationship = await load_relationship(
                session, application_id=thread.context_id
            )
        counterpart = await thread_view.counterpart_label(
            session,
            viewer=principal,
            thread=thread,
            participants=[],
            relationship=relationship,
            is_moderator=is_mod,
            locale=locale,
        )
        unread = await _org_unread(session, thread_id=thread.id, party=party)
        item = presenters.thread_summary(
            thread,
            counterpart=counterpart,
            unread=unread,
            can_reply=capability.can_send_as_org(principal, org_id),
            muted=party.muted,
            locale=locale,
        )
        item.update(presenters.assignment_block(party))
        items.append(item)
    return items, page.next_cursor, page.limit


async def mark_org_read(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    ctx: RequestContext | None = None,
) -> dict:
    """Set the shared org-party read cursor (team-level 'seen')."""

    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    org_id = principal.org_id
    if org_id is None or not capability.can_read_org_inbox(principal, org_id):
        raise PermissionDeniedError()
    party = (
        await session.execute(
            select(MessageThreadParty).where(
                MessageThreadParty.thread_id == thread_id,
                MessageThreadParty.party_kind == rules.PARTY_ORG,
                MessageThreadParty.org_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if party is None:
        raise ResourceNotFoundError()
    party.last_read_at = _shared.now()
    await session.flush()
    await session.commit()
    return {"status": "ok", "thread_id": str(thread_id), "unread": 0}
