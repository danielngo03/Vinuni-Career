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

from sqlalchemy import column, table

from app.modules.messaging.application import _shared, party_service
from app.modules.messaging.application.recruitment_relationship import (
    ApplicationRelationship,
)
from app.modules.messaging.domain import labels, parties, rules
from app.modules.messaging.domain.models import (
    Message,
    MessageThread,
    MessageThreadParticipant,
    MessageThreadParty,
)
from app.modules.users.application import user_read_facade
from app.shared.permissions import Principal

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_NEUTRAL_NAME = {"vi": "Người dùng", "en": "User"}
_departments = table("departments", column("id"), column("name"))


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


async def _department_name(session: AsyncSession, dept_id: uuid.UUID | None) -> str | None:
    if dept_id is None:
        return None
    row = (
        await session.execute(
            select(_departments.c.name).where(_departments.c.id == dept_id)
        )
    ).first()
    return row[0] if row else None


async def _resolve_viewer_party(
    session: AsyncSession,
    *,
    viewer: Principal,
    thread_parties: list[MessageThreadParty],
) -> MessageThreadParty | None:
    for p in thread_parties:
        if p.party_kind == rules.PARTY_USER and p.user_id == viewer.user_id:
            return p
    if viewer.org_id is not None:
        for p in thread_parties:
            if p.party_kind == rules.PARTY_ORG and p.org_id == viewer.org_id:
                # Confirm the viewer is actually an active member of that org.
                if await _is_org_member(
                    session, user_id=viewer.user_id, org_id=p.org_id  # type: ignore[arg-type]
                ):
                    return p
    return None


async def _render_party(
    session: AsyncSession,
    *,
    viewer: Principal,
    viewer_party: MessageThreadParty | None,
    target: MessageThreadParty,
    thread: MessageThread,
    relationship: ApplicationRelationship | None,
    is_moderator: bool,
    locale: str,
) -> str:
    """Render how ``viewer`` sees the ``target`` party (the org-Page masking core)."""

    viewer_on_target = viewer_party is not None and viewer_party.id == target.id

    # --- ORG party ---------------------------------------------------------------
    if target.party_kind == rules.PARTY_ORG:
        # Internal department channel renders as the department (names elsewhere).
        if (
            target.identity_mode == rules.IDENTITY_PERSON
            and target.assigned_department_id is not None
        ):
            dept = await _department_name(session, target.assigned_department_id)
            if dept:
                return dept
        # A Page: outsiders (and everyone, for the header) see the org display name.
        if target.org_id is not None:
            return await _shared.org_display_name(session, target.org_id)
        return labels.kind_label(thread.kind, locale=locale)

    # --- USER party --------------------------------------------------------------
    user_id = target.user_id
    if user_id is None:
        return _NEUTRAL_NAME.get(labels.normalize_locale(locale), _NEUTRAL_NAME["vi"])
    if is_moderator:
        return await _real_name(session, user_id, locale)

    viewer_is_org = viewer_party is not None and viewer_party.party_kind == rules.PARTY_ORG
    org_is_initiator = thread.initiator_party_id != target.id

    # Partner viewing the masked applicant in a recruitment application thread.
    if (
        viewer_is_org
        and thread.context_type == rules.CONTEXT_APPLICATION
        and relationship is not None
        and user_id == relationship.applicant_id
    ):
        if relationship.is_anonymous and not relationship.is_revealed:
            return labels.anonymous_handle(
                short_code=_short_code(thread.context_id), locale=locale
            )
        return await _real_name(session, user_id, locale)

    # A cold partner-INITIATED request keeps the student masked until accepted (the
    # student did not choose to reach out). A student-initiated request does NOT mask.
    if (
        viewer_is_org
        and not viewer_on_target
        and parties.student_masked_to_partner_pending(
            thread_request_state=thread.request_state,
            org_is_initiator=org_is_initiator,
        )
    ):
        return labels.anonymous_handle(short_code=thread.id.hex[:6].upper(), locale=locale)

    return await _real_name(session, user_id, locale)


async def render_participant_label(
    session: AsyncSession,
    *,
    viewer: Principal,
    thread: MessageThread,
    other_user_id: uuid.UUID,
    relationship: ApplicationRelationship | None,
    is_moderator: bool,
    locale: str = "vi",
    sender_party_id: uuid.UUID | None = None,
) -> str:
    """Render how ``viewer`` should see ``other_user_id`` (party-aware, masked/real)."""

    thread_parties = await party_service.list_parties(session, thread_id=thread.id)
    if thread_parties:
        viewer_party = await _resolve_viewer_party(
            session, viewer=viewer, thread_parties=thread_parties
        )
        target: MessageThreadParty | None = None
        if sender_party_id is not None:
            target = next((p for p in thread_parties if p.id == sender_party_id), None)
        if target is None:
            # Resolve the author's party by user id, else the org party they're a
            # member of (staff acting for the Page).
            target = next(
                (
                    p
                    for p in thread_parties
                    if p.party_kind == rules.PARTY_USER and p.user_id == other_user_id
                ),
                None,
            )
            if target is None:
                for p in thread_parties:
                    if p.party_kind == rules.PARTY_ORG and p.org_id is not None:
                        if await _is_org_member(
                            session, user_id=other_user_id, org_id=p.org_id
                        ):
                            target = p
                            break
        if target is not None:
            return await _render_party(
                session,
                viewer=viewer,
                viewer_party=viewer_party,
                target=target,
                thread=thread,
                relationship=relationship,
                is_moderator=is_moderator,
                locale=locale,
            )

    # Legacy fallback (threads created before Messaging V2 have no party rows).
    if is_moderator:
        return await _real_name(session, other_user_id, locale)
    viewer_is_partner = (
        viewer.persona == rules.PARTNER_MEMBER and viewer.org_id == thread.org_id
    )
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
    if viewer.persona in (rules.STUDENT, rules.ALUMNI):
        if await _is_org_member(session, user_id=other_user_id, org_id=thread.org_id):
            return await _shared.org_display_name(session, thread.org_id)
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

    thread_parties = await party_service.list_parties(session, thread_id=thread.id)
    if thread_parties:
        viewer_party = await _resolve_viewer_party(
            session, viewer=viewer, thread_parties=thread_parties
        )
        others = [
            p
            for p in thread_parties
            if viewer_party is None or p.id != viewer_party.id
        ]
        if not others:
            return labels.kind_label(thread.kind, locale=locale)
        rendered = [
            await _render_party(
                session,
                viewer=viewer,
                viewer_party=viewer_party,
                target=p,
                thread=thread,
                relationship=relationship,
                is_moderator=is_moderator,
                locale=locale,
            )
            for p in others[:3]
        ]
        label = ", ".join(rendered)
        if len(others) > 3:
            label += f" +{len(others) - 3}"
        return label

    # Legacy fallback.
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
