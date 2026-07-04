"""The SINGLE projection source for messaging reads (ADR-0012 §2 / §3).

Every per-viewer identity decision and every unread aggregation flows through here,
so anonymity masking can never diverge between the inbox list, the thread detail,
the message echo, and the notification label. Masking is computed at projection
time from ``thread.is_anonymous`` + the recruitment reveal handshake — identity is
never copied into the messaging tables.

Masking decision (for a given viewer rendering another participant):

1. A university moderator (or superadmin) sees real identities.
2. A PARTNER viewing the applicant of an ``application`` thread that is anonymous
   AND not yet revealed sees a stable anonymous handle (never name/email/CV).
   After ``reveal_approved_at`` the same projection flips to the real name.
3. A STUDENT/alumni viewing the org side of an org-bound thread sees the ORG's
   public display name (org identity is not protected).
4. Otherwise: the real display name.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.messaging.application import _shared
from app.modules.messaging.application.recruitment_relationship import (
    ApplicationRelationship,
)
from app.modules.messaging.domain import labels, rules
from app.modules.messaging.domain.models import (
    Message,
    MessageThread,
    MessageThreadParticipant,
)
from app.modules.users.application import user_read_facade
from app.shared.permissions import Principal

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_NEUTRAL_NAME = {"vi": "Người dùng", "en": "User"}


def _short_code(application_id: uuid.UUID | None) -> str:
    if application_id is None:
        return "000000"
    return application_id.hex[:6].upper()


async def _real_name(session: AsyncSession, user_id: uuid.UUID, locale: str) -> str:
    name = await user_read_facade.get_full_name(session, user_id)
    return name or _NEUTRAL_NAME.get(labels.normalize_locale(locale), _NEUTRAL_NAME["vi"])


async def _is_org_member(
    session: AsyncSession, *, user_id: uuid.UUID, org_id: uuid.UUID
) -> bool:
    return await user_read_facade.is_org_member(session, user_id=user_id, org_id=org_id)


async def render_participant_label(
    session: AsyncSession,
    *,
    viewer: Principal,
    thread: MessageThread,
    other_user_id: uuid.UUID,
    relationship: ApplicationRelationship | None,
    is_moderator: bool,
    locale: str = "vi",
) -> str:
    """Render how ``viewer`` should see ``other_user_id`` in ``thread`` (masked or real)."""

    # 1) Moderators see everything.
    if is_moderator:
        return await _real_name(session, other_user_id, locale)

    viewer_is_partner = (
        viewer.persona == rules.PARTNER_MEMBER and viewer.org_id == thread.org_id
    )
    # 2) Partner viewing the masked applicant.
    if (
        viewer_is_partner
        and thread.context_type == rules.CONTEXT_APPLICATION
        and relationship is not None
        and other_user_id == relationship.applicant_id
    ):
        if relationship.is_anonymous and not relationship.is_revealed:
            return labels.anonymous_handle(
                short_code=_short_code(thread.context_id), locale=locale
            )
        return await _real_name(session, other_user_id, locale)

    # 3) Student/alumni viewing the org counterpart -> org name.
    if viewer.persona in (rules.STUDENT, rules.ALUMNI):
        if await _is_org_member(session, user_id=other_user_id, org_id=thread.org_id):
            return await _shared.org_display_name(session, thread.org_id)

    # 4) Default: real name.
    return await _real_name(session, other_user_id, locale)


async def counterpart_label(
    session: AsyncSession,
    *,
    viewer: Principal,
    thread: MessageThread,
    participants: list[MessageThreadParticipant],
    relationship: ApplicationRelationship | None,
    is_moderator: bool,
    locale: str = "vi",
) -> str:
    """A single label summarizing the OTHER side of the thread for ``viewer``."""

    others = [p for p in participants if p.user_id != viewer.user_id]
    if not others:
        return labels.kind_label(thread.kind, locale=locale)
    rendered = []
    for p in others[:3]:
        rendered.append(
            await render_participant_label(
                session,
                viewer=viewer,
                thread=thread,
                other_user_id=p.user_id,
                relationship=relationship,
                is_moderator=is_moderator,
                locale=locale,
            )
        )
    label = ", ".join(rendered)
    if len(others) > 3:
        label += f" +{len(others) - 3}"
    return label


async def thread_unread(
    session: AsyncSession, *, thread_id: uuid.UUID, viewer_id: uuid.UUID
) -> int:
    """Unread = messages newer than my ``last_read_at``, not authored by me, not deleted."""

    participant = await _shared.get_participant(
        session, thread_id=thread_id, user_id=viewer_id
    )
    if participant is None:
        return 0
    anchor = participant.last_read_at or _EPOCH
    return (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.thread_id == thread_id,
                Message.created_at > anchor,
                or_(Message.sender_id.is_(None), Message.sender_id != viewer_id),
                Message.deleted_at.is_(None),
            )
        )
    ).scalar_one()


async def unread_count_total(session: AsyncSession, *, principal: Principal) -> int:
    """Sum of unread across the caller's non-muted, live threads (badge poll)."""

    assert principal.user_id is not None
    rows = list(
        (
            await session.execute(
                select(MessageThreadParticipant.thread_id, MessageThreadParticipant.last_read_at)
                .join(
                    MessageThread,
                    MessageThread.id == MessageThreadParticipant.thread_id,
                )
                .where(
                    MessageThreadParticipant.user_id == principal.user_id,
                    MessageThreadParticipant.removed_at.is_(None),
                    MessageThreadParticipant.muted.is_(False),
                    MessageThread.deleted_at.is_(None),
                )
            )
        ).all()
    )
    total = 0
    for thread_id, _last_read in rows:
        total += await thread_unread(
            session, thread_id=thread_id, viewer_id=principal.user_id
        )
    return total
