"""Read-only pointer into the messaging module's application-bound thread.

Mirrors ``messaging.application.recruitment_relationship`` (which reads a
lightweight Core view of ``applications`` without importing recruitment's ORM
class or services): this module reads a lightweight Core view of
``message_threads`` / ``message_thread_participants`` / ``messages`` without
importing ``messaging``'s ORM classes or services, so neither module has a hard
implementation dependency on the other.

Used ONLY to surface ``{thread_id, unread_count}`` on the student's own
application detail (``docs/DATA_MODEL.md`` §32 timeline projection) — never to
read/write message content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, column, func, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

# Lightweight read-model views of messaging-owned tables. NOT the ORM models —
# recruitment stays decoupled from messaging's implementation.
_threads = table(
    "message_threads",
    column("id"),
    column("context_type"),
    column("context_id"),
    column("org_id"),
    column("deleted_at"),
)
_participants = table(
    "message_thread_participants",
    column("thread_id"),
    column("user_id"),
    column("last_read_at"),
    column("removed_at"),
)
_messages = table(
    "messages",
    column("thread_id"),
    column("sender_id"),
    column("created_at"),
    column("deleted_at"),
)

_CONTEXT_APPLICATION = "application"
_EPOCH = "1970-01-01T00:00:00+00:00"


@dataclass(frozen=True, slots=True)
class MessagesPointer:
    thread_id: uuid.UUID
    unread_count: int


async def application_messages_pointer(
    session: AsyncSession, *, application_id: uuid.UUID, viewer_id: uuid.UUID, org_id: uuid.UUID
) -> MessagesPointer | None:
    """The applicant's own ``{thread_id, unread_count}`` for this application.

    ``None`` when no application-bound thread exists yet — the caller must
    return ``messages_pointer: null`` rather than fabricate a thread/count.
    """

    thread_row = (
        await session.execute(
            select(_threads.c.id).where(
                and_(
                    _threads.c.context_type == _CONTEXT_APPLICATION,
                    _threads.c.context_id == application_id,
                    _threads.c.org_id == org_id,
                    _threads.c.deleted_at.is_(None),
                )
            )
        )
    ).first()
    if thread_row is None:
        return None
    thread_id = thread_row[0]
    if not isinstance(thread_id, uuid.UUID):
        thread_id = uuid.UUID(str(thread_id))

    participant_row = (
        await session.execute(
            select(_participants.c.last_read_at).where(
                and_(
                    _participants.c.thread_id == thread_id,
                    _participants.c.user_id == viewer_id,
                    _participants.c.removed_at.is_(None),
                )
            )
        )
    ).first()
    if participant_row is None:
        # Not (or no longer) a participant on the bound thread.
        return None
    last_read_at = participant_row[0]

    unread_stmt = select(func.count()).select_from(_messages).where(
        _messages.c.thread_id == thread_id,
        _messages.c.deleted_at.is_(None),
        or_(_messages.c.sender_id.is_(None), _messages.c.sender_id != viewer_id),
    )
    if last_read_at is not None:
        unread_stmt = unread_stmt.where(_messages.c.created_at > last_read_at)
    unread_count = (await session.execute(unread_stmt)).scalar_one()

    return MessagesPointer(thread_id=thread_id, unread_count=int(unread_count))
