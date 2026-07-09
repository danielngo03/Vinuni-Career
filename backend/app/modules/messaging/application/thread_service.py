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
from app.modules.messaging.application import _shared, capability, party_service
from app.modules.messaging.application.errors import (
    ContextRequiredError,
    MessageRateLimitedError,
    MessagingNotAllowedError,
    StudentToStudentBlockedError,
)
from app.modules.messaging.application.party_service import RecipientUser
from app.modules.messaging.application.recruitment_relationship import (
    ApplicationRelationship,
    load_relationship,
)
from app.modules.messaging.domain import gate, parties, rules
from app.modules.messaging.domain.models import (
    MessageThread,
    MessageThreadParticipant,
    MessageThreadParty,
)
from app.modules.organization.application import org_reporting_facade
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


async def _org_persona(session: AsyncSession, org_id: uuid.UUID) -> str:
    """The matrix persona an org presents as: university_staff or partner_member."""

    return (
        rules.UNIVERSITY_STAFF
        if await org_reporting_facade.is_university_org(session, org_id)
        else rules.PARTNER_MEMBER
    )


async def _existing_direct_org_thread(
    session: AsyncSession, *, initiator_id: uuid.UUID, target_org_id: uuid.UUID
) -> MessageThread | None:
    """Reuse an existing live 1:1 thread this initiator has with ``target_org_id``
    (prevents duplicate pending requests / re-opening a Page conversation)."""

    stmt = (
        select(MessageThread)
        .join(
            MessageThreadParty, MessageThreadParty.thread_id == MessageThread.id
        )
        .where(
            MessageThread.created_by == initiator_id,
            MessageThread.deleted_at.is_(None),
            MessageThread.context_type.in_(
                [rules.CONTEXT_INQUIRY, rules.CONTEXT_ORG]
            ),
            MessageThreadParty.party_kind == rules.PARTY_ORG,
            MessageThreadParty.org_id == target_org_id,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def create_thread(
    session: AsyncSession,
    *,
    principal: Principal,
    kind: str,
    context_type: str | None,
    context_id: uuid.UUID | None,
    recipient_ids: list[uuid.UUID],
    target_org_id: uuid.UUID | None = None,
    target_department_id: uuid.UUID | None = None,
    subject: str | None = None,
    first_message: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Create a conversation (Messaging V2).

    Four target modes, mutually exclusive by precedence:
      1. ``application`` context (partner→candidate) — recipient resolved server-side
         from the application; masked; no request gate (recruitment consent).
      2. ``target_org_id`` — individual/Page → an org Page (student→partner/uni,
         partner→university). Request-gated unless the initiator is a university Page
         or a prior accepted thread exists.
      3. ``target_department_id`` — internal department channel (same org, shared).
      4. ``recipient_ids`` — user recipients (internal colleagues, university→user).
    """

    sender_id = await _require_authenticated(principal)

    if kind not in rules.KINDS:
        raise ValidationFailedError(details={"field": "kind"})
    if context_type is not None and context_type not in rules.CONTEXT_TYPES:
        raise ValidationFailedError(details={"field": "context_type"})

    relationship: ApplicationRelationship | None = None
    recipient_users: list[RecipientUser] = []
    recipient_personas: list[str] = []
    recipient_org_ids: set[uuid.UUID] = set()
    thread_org_id = principal.org_id
    is_application = False

    # Initiating AS an org Page (partner/university outbound: to another org, an
    # internal department, or a cold outreach) requires the grantable
    # messaging:initiate capability — org membership alone must not let an
    # ungranted staffer speak for the company/university Page. Individual
    # (student/alumni) initiators need no capability; recruitment application
    # threads stay authorized by the application relationship, so they are exempt.
    if (
        parties.is_org_side(principal.persona)
        and context_type != rules.CONTEXT_APPLICATION
        and (
            principal.org_id is None
            or not capability.can_initiate_as_org(principal, principal.org_id)
        )
    ):
        raise MessagingNotAllowedError(details={"reason": rules.REASON_NOT_ALLOWED})

    # -- Mode 1: partner→candidate application thread (existing behavior) ---------
    if (
        principal.persona == rules.PARTNER_MEMBER
        and context_type == rules.CONTEXT_APPLICATION
        and context_id is not None
    ):
        relationship = await load_relationship(session, application_id=context_id)
        if relationship is None or relationship.org_id != principal.org_id:
            raise ResourceNotFoundError()
        recipient_ids = [relationship.applicant_id]

    # -- Mode 2: initiate to an org Page ----------------------------------------
    if target_org_id is not None:
        if not principal.org_id and not principal.is_superadmin:
            pass  # student/alumni have no org — allowed as individual initiators
        target = await org_reporting_facade.summary_for(session, target_org_id)
        if target is None or target.org_type not in ("partner", "university"):
            raise ResourceNotFoundError()
        if target_org_id == principal.org_id:
            # Reaching your own org as a Page makes no sense; use internal instead.
            raise ValidationFailedError(details={"reason": "self_org_target"})
        recipient_personas = [await _org_persona(session, target_org_id)]
        recipient_org_ids = {target_org_id}
        same_org = False
        context_type = context_type or (
            rules.CONTEXT_ORG
            if parties.is_org_side(principal.persona)
            else rules.CONTEXT_INQUIRY
        )
        # Tenant/moderation scope: prefer the university side, else the target org.
        thread_org_id = (
            target_org_id
            if recipient_personas[0] == rules.UNIVERSITY_STAFF
            else target_org_id
        )
        reason = rules.evaluate_open(
            sender_persona=principal.persona,
            recipient_personas=recipient_personas,
            kind=kind,
            context_type=context_type,
            relationship_ok=False,
            same_org=same_org,
        )
        _raise_open_reason(reason)
        existing = await _existing_direct_org_thread(
            session, initiator_id=sender_id, target_org_id=target_org_id
        )
        if existing is not None:
            return await _present_created(
                session, thread=existing, principal=principal, locale=locale
            )
        thread_kind = parties.thread_kind_for(
            sender_persona=principal.persona,
            recipient_personas=recipient_personas,
            kind=kind,
            same_org=False,
            is_application=False,
        )
        return await _persist_thread(
            session,
            principal=principal,
            sender_id=sender_id,
            kind=kind,
            context_type=context_type,
            context_id=None,
            thread_org_id=thread_org_id,
            thread_kind=thread_kind,
            recipient_users=[],
            target_org_id=target_org_id,
            target_department_id=None,
            relationship=None,
            subject=subject,
            first_message=first_message,
            initiator_is_university=(principal.persona == rules.UNIVERSITY_STAFF),
            is_internal=False,
            is_application=False,
            ctx=ctx,
            locale=locale,
        )

    # -- Mode 3: internal department channel ------------------------------------
    if target_department_id is not None:
        if not parties.is_org_side(principal.persona) or principal.org_id is None:
            raise MessagingNotAllowedError(details={"reason": rules.REASON_NOT_ALLOWED})
        # The department must belong to the sender's org (else 404 anti-enumeration).
        exists = await _department_in_org(
            session, org_id=principal.org_id, department_id=target_department_id
        )
        if not exists:
            raise ResourceNotFoundError()
        context_type = rules.CONTEXT_INTERNAL
        thread_org_id = principal.org_id
        return await _persist_thread(
            session,
            principal=principal,
            sender_id=sender_id,
            kind=kind,
            context_type=context_type,
            context_id=None,
            thread_org_id=thread_org_id,
            thread_kind=rules.TK_INTERNAL,
            recipient_users=[],
            target_org_id=None,
            target_department_id=target_department_id,
            relationship=None,
            subject=subject,
            first_message=first_message,
            initiator_is_university=(principal.persona == rules.UNIVERSITY_STAFF),
            is_internal=True,
            is_application=False,
            ctx=ctx,
            locale=locale,
        )

    # -- Mode 4 (and application mode 1): user recipients ------------------------
    recipient_ids = [r for r in dict.fromkeys(recipient_ids) if r != sender_id]
    if not recipient_ids:
        raise ValidationFailedError(details={"field": "recipient_ids"})
    known = await user_read_facade.existing_user_ids(session, recipient_ids)
    if known != set(recipient_ids):
        raise ResourceNotFoundError()

    recipient_personas, recipient_org_ids = await _recipient_personas(
        session, recipient_ids=recipient_ids
    )

    # A thread must NEVER co-locate two student-side individuals. Even as passive
    # co-recipients of a partner, they would read each other's real names in the
    # thread view — a student-discovery / de-anonymization channel. At most one
    # student-side counterpart per thread (student↔student isolation invariant).
    if sum(p in (rules.STUDENT, rules.ALUMNI) for p in recipient_personas) > 1:
        raise StudentToStudentBlockedError()

    is_partner_student = (
        principal.persona == rules.PARTNER_MEMBER
        and any(p in (rules.STUDENT, rules.ALUMNI) for p in recipient_personas)
        and context_type == rules.CONTEXT_APPLICATION
    )
    if is_partner_student:
        if context_id is None:
            raise ContextRequiredError()
        if relationship is None:
            relationship = await load_relationship(session, application_id=context_id)
        if (
            relationship is None
            or relationship.org_id != principal.org_id
            or relationship.applicant_id not in recipient_ids
        ):
            raise ResourceNotFoundError()
        thread_org_id = relationship.org_id
        is_application = True

    same_org = bool(recipient_org_ids) and recipient_org_ids <= {principal.org_id}

    reason = rules.evaluate_open(
        sender_persona=principal.persona,
        recipient_personas=recipient_personas,
        kind=kind,
        context_type=context_type,
        relationship_ok=relationship is not None,
        same_org=same_org,
    )
    _raise_open_reason(reason)

    if thread_org_id is None:
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

    recipient_users = [
        RecipientUser(user_id=r, persona=p)
        for r, p in zip(recipient_ids, recipient_personas, strict=False)
    ]
    thread_kind = parties.thread_kind_for(
        sender_persona=principal.persona,
        recipient_personas=recipient_personas,
        kind=kind,
        same_org=same_org,
        is_application=is_application,
    )
    is_internal = thread_kind == rules.TK_INTERNAL
    return await _persist_thread(
        session,
        principal=principal,
        sender_id=sender_id,
        kind=kind,
        context_type=context_type,
        context_id=context_id,
        thread_org_id=thread_org_id,
        thread_kind=thread_kind,
        recipient_users=recipient_users,
        target_org_id=None,
        target_department_id=None,
        relationship=relationship,
        subject=subject,
        first_message=first_message,
        initiator_is_university=(principal.persona == rules.UNIVERSITY_STAFF),
        is_internal=is_internal,
        is_application=is_application,
        ctx=ctx,
        locale=locale,
    )


def _raise_open_reason(reason: str | None) -> None:
    if reason == rules.REASON_STUDENT_TO_STUDENT:
        raise StudentToStudentBlockedError()
    if reason == rules.REASON_PARTNER_CROSS_ORG:
        # Cross-org partner↔partner is enumeration-masked as missing (ADR-0012 §5).
        raise ResourceNotFoundError()
    if reason is not None:
        raise MessagingNotAllowedError(details={"reason": reason})


async def _department_in_org(
    session: AsyncSession, *, org_id: uuid.UUID, department_id: uuid.UUID
) -> bool:
    from sqlalchemy import column, table

    dept = table("departments", column("id"), column("org_id"))
    row = (
        await session.execute(
            select(dept.c.id).where(
                dept.c.id == department_id, dept.c.org_id == org_id
            )
        )
    ).first()
    return row is not None


async def _persist_thread(
    session: AsyncSession,
    *,
    principal: Principal,
    sender_id: uuid.UUID,
    kind: str,
    context_type: str | None,
    context_id: uuid.UUID | None,
    thread_org_id: uuid.UUID,
    thread_kind: str,
    recipient_users: list[RecipientUser],
    target_org_id: uuid.UUID | None,
    target_department_id: uuid.UUID | None,
    relationship: ApplicationRelationship | None,
    subject: str | None,
    first_message: str | None,
    initiator_is_university: bool,
    is_internal: bool,
    is_application: bool,
    ctx: RequestContext,
    locale: str,
) -> dict:
    """Insert the thread + participants + parties + gate; post first message; commit."""

    await _enforce_thread_rate_limit(session, sender_id=sender_id)

    prior_accepted = False  # dedupe already reused any existing org thread upstream

    request_state = gate.initial_request_state(
        initiator_is_university=initiator_is_university,
        is_internal=is_internal,
        is_application=is_application,
        prior_accepted_exists=prior_accepted,
    )

    thread = MessageThread(
        kind=kind,
        context_type=context_type,
        context_id=context_id,
        org_id=thread_org_id,
        subject=subject,
        is_anonymous=bool(relationship.is_anonymous) if relationship else False,
        thread_kind=thread_kind,
        request_state=request_state,
        request_message_count=0,
        created_by=sender_id,
        status=rules.STATUS_ACTIVE,
    )
    session.add(thread)
    await session.flush()

    # Participant rows: the author always; each USER recipient. Org/department
    # recipients carry NO user participants — access is via the org inbox (RBAC).
    session.add(
        MessageThreadParticipant(
            thread_id=thread.id, user_id=sender_id, role_in_thread="owner",
            can_reply=True,
        )
    )
    recipient_can_reply = kind != rules.KIND_ANNOUNCEMENT
    for r in recipient_users:
        session.add(
            MessageThreadParticipant(
                thread_id=thread.id, user_id=r.user_id, role_in_thread="member",
                can_reply=recipient_can_reply,
            )
        )
    await session.flush()

    sender_party = await party_service.build_parties(
        session,
        thread=thread,
        sender_id=sender_id,
        sender_persona=principal.persona,
        sender_org_id=principal.org_id,
        thread_kind=thread_kind,
        recipient_users=recipient_users,
        target_org_id=target_org_id,
        target_department_id=target_department_id,
    )
    thread.initiator_party_id = sender_party.id
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
            "thread_kind": thread_kind,
            "context_type": context_type,
            "org_id": str(thread_org_id),
            "request_state": request_state,
            "is_anonymous": thread.is_anonymous,
        },
    )

    if first_message and first_message.strip():
        from app.modules.messaging.application import message_service

        await message_service.deliver_message(
            session,
            thread=thread,
            sender_principal=principal,
            sender_party_id=sender_party.id,
            body=first_message,
            reply_to_id=None,
            client_dedupe_key=None,
            relationship=relationship,
            ctx=ctx,
            locale=locale,
        )
        if request_state == rules.REQUEST_PENDING:
            thread.request_message_count += 1
            await session.flush()

    await session.commit()
    await session.refresh(thread)
    from app.modules.messaging.application.message_service import (
        _publish_thread_signal,
    )

    await _publish_thread_signal(
        session, thread_id=thread.id, event_type="thread.created",
        exclude_user_id=sender_id,
    )
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


async def _org_party_in_thread(
    session: AsyncSession, *, thread_id: uuid.UUID, org_id: uuid.UUID
) -> MessageThreadParty | None:
    return (
        await session.execute(
            select(MessageThreadParty).where(
                MessageThreadParty.thread_id == thread_id,
                MessageThreadParty.party_kind == rules.PARTY_ORG,
                MessageThreadParty.org_id == org_id,
            )
        )
    ).scalar_one_or_none()


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
    if participant is not None:
        return thread, False
    # Org shared-inbox read: a staff member with ``messaging:read`` may read a thread
    # that carries their org's Page party WITHOUT a per-user participant row (rows are
    # created lazily only when they send/accept). Without this, an inbox thread 404s
    # until the first reply — the shared inbox must be readable by the whole team.
    if principal.org_id is not None and capability.can_read_org_inbox(
        principal, principal.org_id
    ):
        org_party = await _org_party_in_thread(
            session, thread_id=thread_id, org_id=principal.org_id
        )
        # Department scope is ACCESS CONTROL, not just a list filter: a non-admin
        # staffer may only open a thread that is unassigned, assigned to them, or
        # assigned to one of their departments — a deep link cannot cross depts.
        if org_party is not None and await capability.member_can_access_org_party(
            session, principal=principal, party=org_party
        ):
            return thread, False
    raise ResourceNotFoundError()


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
    # Resolve the viewer's party to expose two facts the composer UX needs exactly:
    # whether the viewer is the request RECIPIENT (→ show Accept/Decline/Block), and
    # whether an org-inbox staff member (no participant row yet) may reply as the Page.
    party_list = await party_service.list_parties(session, thread_id=thread.id)
    viewer_party = None
    for pp in party_list:
        if pp.party_kind == rules.PARTY_USER and pp.user_id == principal.user_id:
            viewer_party = pp
            break
    if viewer_party is None and principal.org_id is not None:
        viewer_party = next(
            (
                pp
                for pp in party_list
                if pp.party_kind == rules.PARTY_ORG and pp.org_id == principal.org_id
            ),
            None,
        )
    viewer_is_recipient = (
        thread.request_state == rules.REQUEST_PENDING
        and viewer_party is not None
        and thread.initiator_party_id is not None
        and viewer_party.id != thread.initiator_party_id
    )
    org_can_send = (
        me is None
        and viewer_party is not None
        and viewer_party.party_kind == rules.PARTY_ORG
        and viewer_party.org_id is not None
        and capability.can_send_as_org(principal, viewer_party.org_id)
    )
    detail = presenters.thread_detail(
        thread,
        counterpart=counterpart,
        participants=rendered_participants,
        unread=unread,
        can_reply=bool(me and me.can_reply) or org_can_send,
        muted=bool(me and me.muted),
        locale=locale,
    )
    detail["viewer_is_recipient"] = viewer_is_recipient
    return detail
