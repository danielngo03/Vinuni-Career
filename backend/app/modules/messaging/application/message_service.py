"""Message send / read / delete / report service (ADR-0012 §1.2, §2, §4, §5).

The send path is the heart of the slice and honors every non-negotiable in ONE
transaction:

    re-check permission (every send) -> rate limit -> PERSIST the message ->
    bump the thread -> audit (PII-safe) -> notify each other participant
    (in-app feed + preference-gated outbox) -> COMMIT.

There is NO delivery path before the commit (persist-before-deliver). The send is
idempotent on ``client_dedupe_key``. Audit + notifications are PII-safe: the audit
``after`` snapshot carries ids/status only (never body/name/email) and the
notification carries a MASKED sender label + a neutral "new message" + a deep link,
never the body and never the anonymous student's identity.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.messaging.api import presenters
from app.modules.messaging.application import _shared, thread_view
from app.modules.messaging.application.errors import (
    BlankMessageError,
    MessageDeleteNotAllowedError,
    MessageRateLimitedError,
    MessagingNotAllowedError,
    StudentToStudentBlockedError,
    ThreadClosedError,
)
from app.modules.messaging.application.recruitment_relationship import (
    ApplicationRelationship,
    load_relationship,
)
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import (
    Message,
    MessageThread,
)
from app.modules.notifications.application import feed_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.users.application import user_read_facade
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal

_MESSAGE_NOTIF = "message.received"
_FLAGGED_NOTIF = "message.flagged"


# --------------------------------------------------------------------------- #
# Internal persist + notify (no commit) — the persist-before-deliver core      #
# --------------------------------------------------------------------------- #


async def _existing_dedupe(
    session: AsyncSession,
    *,
    thread_id: uuid.UUID,
    sender_id: uuid.UUID,
    client_dedupe_key: str | None,
) -> Message | None:
    if client_dedupe_key is None:
        return None
    return (
        (
            await session.execute(
                select(Message).where(
                    Message.thread_id == thread_id,
                    Message.sender_id == sender_id,
                    Message.client_dedupe_key == client_dedupe_key,
                )
            )
        )
        .scalars()
        .first()
    )


async def _participant_personas(session: AsyncSession, user_ids: list[uuid.UUID]) -> list[str]:
    """Effective persona per participant (for the send-time student↔student block).

    Institutional identities win, so a university staffer / partner who also holds
    the baseline ``student`` identity is NOT treated as student-side.
    """

    resolved, _orgs = await _shared.resolve_effective_personas(session, user_ids)
    return [resolved[u] for u in user_ids if u in resolved]


async def _recipient_view_principal(
    session: AsyncSession, *, recipient_id: uuid.UUID, thread: MessageThread
) -> Principal:
    """Synthesize how the RECIPIENT perceives the thread (for masking the sender).

    If the recipient is a member of the thread's org they are the org/partner/uni
    side; otherwise they are the student/alumni side. This drives ``render_*`` so a
    partner's notification stays anonymous and a student's notification names the org.
    """

    persona = await user_read_facade.get_identity_persona_in_org(
        session, user_id=recipient_id, org_id=thread.org_id
    )
    if persona is not None:
        return Principal(user_id=recipient_id, persona=persona, org_id=thread.org_id)
    return Principal(user_id=recipient_id, persona=rules.STUDENT, org_id=None)


async def deliver_message(
    session: AsyncSession,
    *,
    thread: MessageThread,
    sender_principal: Principal,
    body: str,
    reply_to_id: uuid.UUID | None,
    client_dedupe_key: str | None,
    relationship: ApplicationRelationship | None,
    ctx: RequestContext,
    is_system: bool = False,
    locale: str = "vi",
) -> Message:
    """Persist a message + bump thread + audit + notify — all WITHOUT commit.

    The caller owns the transaction/commit so this composes inside ``create_thread``
    (first message) and ``send_message`` (single tx, persist-before-deliver).
    """

    sender_id = None if is_system else sender_principal.user_id
    message = Message(
        thread_id=thread.id,
        sender_id=sender_id,
        body=body.strip(),
        is_system=is_system,
        reply_to_id=reply_to_id,
        client_dedupe_key=client_dedupe_key,
    )
    session.add(message)
    thread.last_message_at = _shared.now()
    thread.version += 1
    await session.flush()

    # Audit is PII-safe: ids + status only, NEVER the body / name / email.
    await write_audit(
        session,
        action="messaging.message.send",
        resource_type="message",
        resource_id=message.id,
        context=_shared.audit_ctx(sender_principal, ctx),
        after={
            "message_id": str(message.id),
            "thread_id": str(thread.id),
            "sender_id": str(sender_id) if sender_id else None,
            "is_system": is_system,
        },
    )

    await _notify_participants(
        session,
        thread=thread,
        message=message,
        sender_id=sender_id,
        relationship=relationship,
        locale=locale,
    )
    return message


async def _notify_participants(
    session: AsyncSession,
    *,
    thread: MessageThread,
    message: Message,
    sender_id: uuid.UUID | None,
    relationship: ApplicationRelationship | None,
    locale: str,
) -> None:
    participants = await _shared.list_participants(session, thread_id=thread.id)
    action_url = f"/messages/{thread.id}"
    for p in participants:
        if sender_id is not None and p.user_id == sender_id:
            continue
        if p.muted:
            # Mute suppresses notifications (and stops refreshing the partner cap).
            continue
        recipient_principal = await _recipient_view_principal(
            session, recipient_id=p.user_id, thread=thread
        )
        # MASKED sender label as THIS recipient perceives the sender.
        if sender_id is None:
            sender_label = ""
        else:
            sender_label = await thread_view.render_participant_label(
                session,
                viewer=recipient_principal,
                thread=thread,
                other_user_id=sender_id,
                relationship=relationship,
                is_moderator=False,
                locale=locale,
            )
        # In-app feed — dedupe (recipient + type + action_url) coalesces a burst into
        # one unread row per thread until read. NEVER carries the message body.
        await feed_service.create_in_app(
            session,
            recipient_id=p.user_id,
            notif_type=_MESSAGE_NOTIF,
            action_url=action_url,
            variables={"sender_label": sender_label},
            locale=locale,
        )
        # Preference-gated email via the shipped outbox (drained later). No body.
        recipient = await user_read_facade.get_user_contact(session, p.user_id)
        if recipient is not None:
            await enqueue_notification(
                session,
                recipient_id=p.user_id,
                template_key=_MESSAGE_NOTIF,
                channel="email",
                locale=locale,
                variables={
                    "email": recipient.email,
                    "name": recipient.full_name or "",
                    "sender_label": sender_label,
                    "action_url": action_url,
                },
                dedupe_key=f"{_MESSAGE_NOTIF}:{thread.id}:{p.user_id}",
            )


# --------------------------------------------------------------------------- #
# Public send                                                                  #
# --------------------------------------------------------------------------- #


async def _relationship_for(
    session: AsyncSession, thread: MessageThread
) -> ApplicationRelationship | None:
    if thread.context_type == rules.CONTEXT_APPLICATION and thread.context_id:
        return await load_relationship(session, application_id=thread.context_id)
    return None


async def _enforce_send_rate_limit(
    session: AsyncSession,
    *,
    sender_id: uuid.UUID,
    thread: MessageThread,
    relationship: ApplicationRelationship | None,
) -> None:
    settings = get_settings()
    start = _shared.start_of_utc_day()
    # Global per-sender ceiling.
    global_count = (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.sender_id == sender_id, Message.created_at >= start)
        )
    ).scalar_one()
    if global_count >= settings.messaging_max_messages_per_sender_per_day:
        raise MessageRateLimitedError(
            reset_at=_shared.next_utc_midnight().isoformat(), scope="messages_per_day"
        )
    # Inactive-application taper (BUSINESS_LOGIC §14.1): a terminal/inactive bound
    # application caps the partner at N messages/day into THAT thread.
    if (
        thread.context_type == rules.CONTEXT_APPLICATION
        and relationship is not None
        and not rules.application_relationship_active(relationship.status)
    ):
        in_thread = (
            await session.execute(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.thread_id == thread.id,
                    Message.sender_id == sender_id,
                    Message.created_at >= start,
                )
            )
        ).scalar_one()
        if in_thread >= settings.messaging_inactive_application_daily_cap:
            raise MessageRateLimitedError(
                reset_at=_shared.next_utc_midnight().isoformat(),
                scope="inactive_application",
            )


async def send_message(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    body: str,
    reply_to_id: uuid.UUID | None = None,
    client_dedupe_key: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    sender_id = principal.user_id
    if not body or not body.strip():
        raise BlankMessageError()

    thread = await _shared.load_thread(session, thread_id=thread_id, lock=True)

    # Non-participant (or cross-tenant) is indistinguishable from missing -> 404.
    participant = await _shared.get_participant(session, thread_id=thread_id, user_id=sender_id)
    is_author = thread.created_by == sender_id
    if participant is None and not is_author:
        raise ResourceNotFoundError()

    # STUDENT↔STUDENT HARD BLOCK — the SECOND enforcement layer (re-checked on every
    # send, never cached at create). Even a thread that somehow contains two students
    # can never carry a student↔student message.
    all_participants = await _shared.list_participants(session, thread_id=thread_id)
    other_personas = await _participant_personas(
        session, [p.user_id for p in all_participants if p.user_id != sender_id]
    )
    if rules.student_to_student_blocked(principal.persona, other_personas):
        raise StudentToStudentBlockedError()

    relationship = await _relationship_for(session, thread)

    # RE-CHECK permission on EVERY send (ADR-0012 §1.2) — never cached at create.
    reason = rules.evaluate_send(
        is_participant=participant is not None or is_author,
        can_reply=bool(participant and participant.can_reply),
        is_author=is_author,
        thread_status=thread.status,
        thread_deleted=thread.deleted_at is not None,
        relationship_ok=(
            relationship is not None if thread.context_type == rules.CONTEXT_APPLICATION else True
        ),
    )
    if reason == rules.REASON_THREAD_NOT_ACTIVE:
        raise ThreadClosedError()
    if reason is not None:
        raise MessagingNotAllowedError(details={"reason": reason})

    # Idempotent re-send: same key -> the original message, no new row / notify.
    existing = await _existing_dedupe(
        session,
        thread_id=thread_id,
        sender_id=sender_id,
        client_dedupe_key=client_dedupe_key,
    )
    if existing is not None:
        return presenters.message_item(existing, sender_label="", is_mine=True, locale=locale)

    await _enforce_send_rate_limit(
        session, sender_id=sender_id, thread=thread, relationship=relationship
    )

    message = await deliver_message(
        session,
        thread=thread,
        sender_principal=principal,
        body=body,
        reply_to_id=reply_to_id,
        client_dedupe_key=client_dedupe_key,
        relationship=relationship,
        ctx=ctx,
        locale=locale,
    )
    await session.commit()
    await session.refresh(message)
    return presenters.message_item(message, sender_label="", is_mine=True, locale=locale)


# --------------------------------------------------------------------------- #
# Read / list                                                                  #
# --------------------------------------------------------------------------- #


async def list_messages(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    after: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    from app.modules.messaging.application.thread_service import _load_readable

    thread, is_mod = await _load_readable(session, principal=principal, thread_id=thread_id)
    relationship = await _relationship_for(session, thread)
    page_limit = clamp_limit(limit)

    stmt = select(Message).where(Message.thread_id == thread_id)
    decoded = decode_cursor(after)
    if decoded is not None:
        anchor_created = datetime.fromisoformat(decoded["created_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                Message.created_at > anchor_created,
                (Message.created_at == anchor_created) & (Message.id > anchor_id),
            )
        )
    stmt = stmt.order_by(Message.created_at.asc(), Message.id.asc()).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda m: {
            "created_at": _shared.as_aware(m.created_at).isoformat(),
            "id": str(m.id),
        },
    )
    items: list[dict] = []
    for m in page.items:
        if m.sender_id is None or m.sender_id == principal.user_id:
            sender_label = ""
        else:
            sender_label = await thread_view.render_participant_label(
                session,
                viewer=principal,
                thread=thread,
                other_user_id=m.sender_id,
                relationship=relationship,
                is_moderator=is_mod,
                locale=locale,
            )
        items.append(
            presenters.message_item(
                m,
                sender_label=sender_label,
                is_mine=m.sender_id == principal.user_id,
                locale=locale,
            )
        )
    return items, page.next_cursor, page.limit


async def mark_read(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    await _shared.load_thread(session, thread_id=thread_id)
    participant = await _shared.get_participant(
        session, thread_id=thread_id, user_id=principal.user_id
    )
    if participant is None:
        raise ResourceNotFoundError()
    participant.last_read_at = _shared.now()
    await session.flush()
    await session.commit()
    return {"status": "ok", "thread_id": str(thread_id), "unread": 0}


async def unread_count(session: AsyncSession, *, principal: Principal) -> int:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    return await thread_view.unread_count_total(session, principal=principal)


# --------------------------------------------------------------------------- #
# Delete / mute / report                                                       #
# --------------------------------------------------------------------------- #


async def delete_message(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    message_id: uuid.UUID,
    ctx: RequestContext,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    thread = await _shared.load_thread(session, thread_id=thread_id, lock=True)
    is_mod = await _shared.is_university_moderator(session, principal)
    participant = await _shared.get_participant(
        session, thread_id=thread_id, user_id=principal.user_id
    )
    if participant is None and not is_mod:
        raise ResourceNotFoundError()

    message = (
        await session.execute(
            select(Message).where(Message.id == message_id, Message.thread_id == thread_id)
        )
    ).scalar_one_or_none()
    if message is None:
        raise ResourceNotFoundError()

    is_owner = message.sender_id is not None and message.sender_id == principal.user_id
    owner_is_partner_to_student = (
        is_owner
        and principal.persona == rules.PARTNER_MEMBER
        and thread.context_type == rules.CONTEXT_APPLICATION
    )
    settings = get_settings()
    allowed = rules.can_delete_message(
        now=_shared.now(),
        created_at=_shared.as_aware(message.created_at),
        is_system=message.is_system,
        is_owner=is_owner,
        is_university_moderator=is_mod,
        owner_is_partner_to_student=owner_is_partner_to_student,
        window_minutes=settings.messaging_delete_window_minutes,
    )
    if not allowed:
        raise MessageDeleteNotAllowedError()
    if message.deleted_at is None:
        message.deleted_at = _shared.now()
        await session.flush()
        await write_audit(
            session,
            action="messaging.message.delete",
            resource_type="message",
            resource_id=message.id,
            context=_shared.audit_ctx(principal, ctx),
            after={
                "message_id": str(message.id),
                "thread_id": str(thread_id),
                "by_moderator": is_mod and not is_owner,
            },
        )
    await session.commit()
    return {"status": "deleted", "id": str(message_id)}


async def set_mute(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    muted: bool,
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    await _shared.load_thread(session, thread_id=thread_id)
    participant = await _shared.get_participant(
        session, thread_id=thread_id, user_id=principal.user_id
    )
    if participant is None:
        raise ResourceNotFoundError()
    participant.muted = muted
    await session.flush()
    await session.commit()
    return {"status": "ok", "thread_id": str(thread_id), "muted": muted}


async def report_thread(
    session: AsyncSession,
    *,
    principal: Principal,
    thread_id: uuid.UUID,
    reason: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    if not principal.is_authenticated or principal.user_id is None:
        raise ResourceNotFoundError()
    thread = await _shared.load_thread(session, thread_id=thread_id)
    participant = await _shared.get_participant(
        session, thread_id=thread_id, user_id=principal.user_id
    )
    is_mod = await _shared.is_university_moderator(session, principal)
    if participant is None and not is_mod:
        raise ResourceNotFoundError()

    await write_audit(
        session,
        action="messaging.report",
        resource_type="message_thread",
        resource_id=thread.id,
        context=_shared.audit_ctx(principal, ctx),
        # PII-safe: ids + a coded reason only, never message content.
        after={
            "thread_id": str(thread.id),
            "reported_by": str(principal.user_id),
            "reason_code": (reason or "unspecified")[:50],
        },
    )

    # Notify university moderators (the "reported to university admin" rule).
    staff_ids = await user_read_facade.get_user_ids_by_persona(session, rules.UNIVERSITY_STAFF)
    for staff_id in staff_ids[:20]:
        await feed_service.create_in_app(
            session,
            recipient_id=staff_id,
            notif_type=_FLAGGED_NOTIF,
            action_url=f"/admin/messaging/threads/{thread.id}",
            variables={},
            locale=locale,
        )
    await session.commit()
    return {"status": "reported", "thread_id": str(thread.id)}
