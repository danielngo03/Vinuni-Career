"""Thread lifecycle service — create / list_mine / get / archive (ADR-0012 §1, §3).

RBAC is enforced HERE (not the router) at the open + read checkpoints, with the
student↔student hard block as the first check. Partner↔student threads are bound to
a recruitment ``application`` and denormalize ``is_anonymous`` from it. Cross-tenant
/ non-participant access returns ``404`` (never ``403``) so threads are not
enumerable. Every create is audited (PII-safe: ids + status only).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.messaging.api import presenters
from app.modules.messaging.application import _shared
from app.modules.messaging.application.errors import (
    ContextRequiredError,
    MessageRateLimitedError,
    MessagingNotAllowedError,
    StudentToStudentBlockedError,
)
from app.modules.messaging.application.recruitment_relationship import (
    ApplicationRelationship,
    load_relationship,
)
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import (
    MessageThread,
    MessageThreadParticipant,
)
from app.modules.users.application import user_read_facade
from app.shared.audit import write_audit
from app.shared.exceptions import (
    AuthRequiredError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal

_RESOURCE = _shared.RESOURCE


async def _recipient_personas(
    session: AsyncSession, *, recipient_ids: list[uuid.UUID]
) -> tuple[list[str], set[uuid.UUID]]:
    """Effective persona per recipient + the set of org_ids they belong to."""

    resolved, org_ids = await _shared.resolve_effective_personas(
        session, recipient_ids
    )
    personas = [resolved[r] for r in recipient_ids if r in resolved]
    return personas, org_ids


async def _require_authenticated(principal: Principal) -> uuid.UUID:
    if not principal.is_authenticated or principal.user_id is None:
        raise AuthRequiredError()
    return principal.user_id


async def _existing_application_thread(
    session: AsyncSession, *, org_id: uuid.UUID, context_id: uuid.UUID
) -> MessageThread | None:
    """One direct thread per (application, partner org) — service-side dedupe guard."""

    return (
        await session.execute(
            select(MessageThread).where(
                MessageThread.context_type == rules.CONTEXT_APPLICATION,
                MessageThread.context_id == context_id,
                MessageThread.org_id == org_id,
                MessageThread.deleted_at.is_(None),
            )
        )
    ).scalars().first()


async def _enforce_thread_rate_limit(
    session: AsyncSession, *, sender_id: uuid.UUID
) -> None:
    settings = get_settings()
    start = _shared.start_of_utc_day()
    count = (
        await session.execute(
            select(func.count())
            .select_from(MessageThread)
            .where(
                MessageThread.created_by == sender_id,
                MessageThread.created_at >= start,
            )
        )
    ).scalar_one()
    if count >= settings.messaging_max_threads_per_sender_per_day:
        raise MessageRateLimitedError(
            reset_at=_shared.next_utc_midnight().isoformat(), scope="threads_per_day"
        )


async def create_thread(
    session: AsyncSession,
    *,
    principal: Principal,
    kind: str,
    context_type: str | None,
    context_id: uuid.UUID | None,
    recipient_ids: list[uuid.UUID],
    subject: str | None = None,
    first_message: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    sender_id = await _require_authenticated(principal)

    if kind not in rules.KINDS:
        raise ValidationFailedError(details={"field": "kind"})
    if context_type is not None and context_type not in rules.CONTEXT_TYPES:
        raise ValidationFailedError(details={"field": "context_type"})

    # Partner opening an application-context thread (ADR-0012 §3/§8): while the
    # application is anonymous the recruitment contract WITHHOLDS the student's
    # user id, so the partner has no ``recipient_ids`` to pass. Resolve the
    # recipient = the application's bound ``applicant_id`` SERVER-SIDE — the partner
    # never passes, nor sees, the student's identity. The application context is
    # authoritative: any client-supplied ``recipient_ids`` are IGNORED in favor of
    # the resolved applicant, so this path can ONLY reach the bound applicant.
    relationship: ApplicationRelationship | None = None
    if (
        principal.persona == rules.PARTNER_MEMBER
        and context_type == rules.CONTEXT_APPLICATION
        and context_id is not None
    ):
        relationship = await load_relationship(session, application_id=context_id)
        # Unknown application, or one owned by another org -> 404 (never 403) so a
        # partner cannot enumerate applications it does not own.
        if relationship is None or relationship.org_id != principal.org_id:
            raise ResourceNotFoundError()
        recipient_ids = [relationship.applicant_id]

    recipient_ids = [r for r in dict.fromkeys(recipient_ids) if r != sender_id]
    if not recipient_ids:
        raise ValidationFailedError(details={"field": "recipient_ids"})

    # Every recipient must be a real user (else indistinguishable from missing).
    known = await user_read_facade.existing_user_ids(session, recipient_ids)
    if known != set(recipient_ids):
        raise ResourceNotFoundError()

    recipient_personas, recipient_org_ids = await _recipient_personas(
        session, recipient_ids=recipient_ids
    )

    # The org that scopes this thread: partner org for application/team (the sender's
    # org), the university org for support/announcement (the sender's org).
    thread_org_id = principal.org_id

    # Partner↔student requires a bound application relationship (and its context).
    is_partner_student = (
        principal.persona == rules.PARTNER_MEMBER
        and any(p in (rules.STUDENT, rules.ALUMNI) for p in recipient_personas)
    )
    if is_partner_student:
        if context_type != rules.CONTEXT_APPLICATION or context_id is None:
            raise ContextRequiredError()
        if relationship is None:
            relationship = await load_relationship(session, application_id=context_id)
        # The relationship must bind THIS partner org to THIS recipient (else 404 —
        # a partner cannot fabricate a thread to an arbitrary student).
        if (
            relationship is None
            or relationship.org_id != principal.org_id
            or relationship.applicant_id not in recipient_ids
        ):
            raise ResourceNotFoundError()
        thread_org_id = relationship.org_id

    same_org = bool(recipient_org_ids) and recipient_org_ids <= {principal.org_id}

    reason = rules.evaluate_open(
        sender_persona=principal.persona,
        recipient_personas=recipient_personas,
        kind=kind,
        context_type=context_type,
        relationship_ok=relationship is not None,
        same_org=same_org,
    )
    if reason == rules.REASON_STUDENT_TO_STUDENT:
        raise StudentToStudentBlockedError()
    if reason == rules.REASON_PARTNER_CROSS_ORG:
        # Cross-org partner↔partner is enumeration-masked as missing (ADR-0012 §5).
        raise ResourceNotFoundError()
    if reason is not None:
        raise MessagingNotAllowedError(details={"reason": reason})

    if thread_org_id is None:
        # Direct threads to a university/partner must carry an org scope.
        if recipient_org_ids:
            thread_org_id = next(iter(recipient_org_ids))
        else:
            raise ValidationFailedError(details={"reason": "missing_org_scope"})

    # Idempotent create for application-bound threads (one per application/org).
    if context_type == rules.CONTEXT_APPLICATION and context_id is not None:
        existing = await _existing_application_thread(
            session, org_id=thread_org_id, context_id=context_id
        )
        if existing is not None:
            return await _present_created(
                session, thread=existing, principal=principal, locale=locale
            )

    await _enforce_thread_rate_limit(session, sender_id=sender_id)

    thread = MessageThread(
        kind=kind,
        context_type=context_type,
        context_id=context_id,
        org_id=thread_org_id,
        subject=subject,
        is_anonymous=bool(relationship.is_anonymous) if relationship else False,
        created_by=sender_id,
        status=rules.STATUS_ACTIVE,
    )
    session.add(thread)
    await session.flush()

    # Author participant (owner).
    session.add(
        MessageThreadParticipant(
            thread_id=thread.id,
            user_id=sender_id,
            role_in_thread="owner",
            can_reply=True,
        )
    )
    # Recipients. Announcement recipients are one-way (can_reply=False).
    recipient_can_reply = kind != rules.KIND_ANNOUNCEMENT
    for rid in recipient_ids:
        session.add(
            MessageThreadParticipant(
                thread_id=thread.id,
                user_id=rid,
                role_in_thread="member",
                can_reply=recipient_can_reply,
            )
        )
    await session.flush()

    await write_audit(
        session,
        action="messaging.thread.create",
        resource_type="message_thread",
        resource_id=thread.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "thread_id": str(thread.id),
            "kind": kind,
            "context_type": context_type,
            "org_id": str(thread_org_id),
            "is_anonymous": thread.is_anonymous,
            "participant_count": len(recipient_ids) + 1,
        },
    )

    if first_message and first_message.strip():
        # Persist-before-deliver in the SAME transaction as the thread create.
        from app.modules.messaging.application import message_service

        await message_service.deliver_message(
            session,
            thread=thread,
            sender_principal=principal,
            body=first_message,
            reply_to_id=None,
            client_dedupe_key=None,
            relationship=relationship,
            ctx=ctx,
            locale=locale,
        )

    await session.commit()
    await session.refresh(thread)
    return await _present_created(
        session, thread=thread, principal=principal, locale=locale
    )


async def _present_created(
    session: AsyncSession,
    *,
    thread: MessageThread,
    principal: Principal,
    locale: str,
) -> dict:
    from app.modules.messaging.application import thread_view

    participants = await _shared.list_participants(session, thread_id=thread.id)
    relationship = None
    if thread.context_type == rules.CONTEXT_APPLICATION and thread.context_id:
        relationship = await load_relationship(
            session, application_id=thread.context_id
        )
    is_mod = await _shared.is_university_moderator(session, principal)
    counterpart = await thread_view.counterpart_label(
        session,
        viewer=principal,
        thread=thread,
        participants=participants,
        relationship=relationship,
        is_moderator=is_mod,
        locale=locale,
    )
    me = next((p for p in participants if p.user_id == principal.user_id), None)
    unread = await thread_view.thread_unread(
        session, thread_id=thread.id, viewer_id=principal.user_id  # type: ignore[arg-type]
    )
    return presenters.thread_summary(
        thread,
        counterpart=counterpart,
        unread=unread,
        can_reply=bool(me and me.can_reply) or thread.created_by == principal.user_id,
        muted=bool(me and me.muted),
        locale=locale,
    )


async def list_mine(
    session: AsyncSession,
    *,
    principal: Principal,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    from app.modules.messaging.application import thread_view

    user_id = await _require_authenticated(principal)
    page_limit = clamp_limit(limit)

    stmt = (
        select(MessageThread)
        .join(
            MessageThreadParticipant,
            MessageThreadParticipant.thread_id == MessageThread.id,
        )
        .where(
            MessageThreadParticipant.user_id == user_id,
            MessageThreadParticipant.removed_at.is_(None),
            MessageThread.deleted_at.is_(None),
        )
    )
    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_sort = datetime.fromisoformat(decoded["sort"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                func.coalesce(MessageThread.last_message_at, MessageThread.created_at)
                < anchor_sort,
                (
                    func.coalesce(
                        MessageThread.last_message_at, MessageThread.created_at
                    )
                    == anchor_sort
                )
                & (MessageThread.id < anchor_id),
            )
        )
    stmt = stmt.order_by(
        func.coalesce(MessageThread.last_message_at, MessageThread.created_at).desc(),
        MessageThread.id.desc(),
    ).limit(page_limit + 1)

    threads = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(
        threads,
        limit=page_limit,
        cursor_builder=lambda t: {
            "sort": _shared.as_aware(t.last_message_at or t.created_at).isoformat(),
            "id": str(t.id),
        },
    )
    is_mod = await _shared.is_university_moderator(session, principal)
    items: list[dict] = []
    for thread in page.items:
        participants = await _shared.list_participants(session, thread_id=thread.id)
        relationship = None
        if thread.context_type == rules.CONTEXT_APPLICATION and thread.context_id:
            relationship = await load_relationship(
                session, application_id=thread.context_id
            )
        counterpart = await thread_view.counterpart_label(
            session,
            viewer=principal,
            thread=thread,
            participants=participants,
            relationship=relationship,
            is_moderator=is_mod,
            locale=locale,
        )
        me = next((p for p in participants if p.user_id == user_id), None)
        unread = await thread_view.thread_unread(
            session, thread_id=thread.id, viewer_id=user_id
        )
        items.append(
            presenters.thread_summary(
                thread,
                counterpart=counterpart,
                unread=unread,
                can_reply=bool(me and me.can_reply),
                muted=bool(me and me.muted),
                locale=locale,
            )
        )
    return items, page.next_cursor, page.limit


async def _load_readable(
    session: AsyncSession, *, principal: Principal, thread_id: uuid.UUID
) -> tuple[MessageThread, bool]:
    """Load a thread the caller may READ, else 404. Returns (thread, is_moderator)."""

    user_id = await _require_authenticated(principal)
    thread = await _shared.load_thread(session, thread_id=thread_id)
    is_mod = await _shared.is_university_moderator(session, principal)
    if is_mod:
        return thread, True
    participant = await _shared.get_participant(
        session, thread_id=thread_id, user_id=user_id
    )
    if participant is None:
        raise ResourceNotFoundError()
    return thread, False


async def get_thread(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    from app.modules.messaging.application import thread_view

    thread, is_mod = await _load_readable(
        session, principal=principal, thread_id=thread_id
    )
    participants = await _shared.list_participants(session, thread_id=thread.id)
    relationship = None
    if thread.context_type == rules.CONTEXT_APPLICATION and thread.context_id:
        relationship = await load_relationship(
            session, application_id=thread.context_id
        )
    counterpart = await thread_view.counterpart_label(
        session,
        viewer=principal,
        thread=thread,
        participants=participants,
        relationship=relationship,
        is_moderator=is_mod,
        locale=locale,
    )
    rendered_participants: list[dict] = []
    for p in participants:
        label = await thread_view.render_participant_label(
            session,
            viewer=principal,
            thread=thread,
            other_user_id=p.user_id,
            relationship=relationship,
            is_moderator=is_mod,
            locale=locale,
        )
        rendered_participants.append(
            presenters.participant_item(
                label=label, can_reply=p.can_reply, role_in_thread=p.role_in_thread
            )
        )
    me = next((p for p in participants if p.user_id == principal.user_id), None)
    unread = await thread_view.thread_unread(
        session, thread_id=thread.id, viewer_id=principal.user_id  # type: ignore[arg-type]
    )
    return presenters.thread_detail(
        thread,
        counterpart=counterpart,
        participants=rendered_participants,
        unread=unread,
        can_reply=bool(me and me.can_reply),
        muted=bool(me and me.muted),
        locale=locale,
    )
