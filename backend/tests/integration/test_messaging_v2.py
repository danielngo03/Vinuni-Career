"""Messaging V2 (owner decision 2026-07-09) service-level tests.

Covers the new cross-persona interaction model layered on ADR-0012:
the message-request gate (initiate → 3 intro messages → accept/decline/block),
organization-as-Page identity masking (outsiders see the org, never the staff
member), the shared org inbox + RBAC, and the recipient picker's student↔student
discovery block. The ADR-0012 institutional invariants are still exercised by
``test_messaging.py``.
"""

from __future__ import annotations

import io
import uuid

import pytest
from app.core.config import get_settings
from app.modules.messaging.application import (
    assignment_service,
    inbox_service,
    message_service,
    recipient_service,
    request_service,
    thread_service,
)
from app.modules.messaging.application.errors import (
    RequestNotActionableError,
    RequestPendingError,
)
from app.modules.messaging.domain.models import MessageThread
from app.modules.notifications.domain.models import Notification, NotificationOutbox
from app.shared.exceptions import ResourceNotFoundError
from sqlalchemy import select
from starlette.datastructures import Headers, UploadFile

from tests.auth_utils import CTX
from tests.messaging_utils import (
    make_partner,
    make_student,
    make_university,
)
from tests.org_utils import add_member, email


async def _thread(db_session, thread_id: uuid.UUID) -> MessageThread:
    return (
        await db_session.execute(
            select(MessageThread).where(MessageThread.id == thread_id)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Message-request gate: student initiates → partner accepts                    #
# --------------------------------------------------------------------------- #


async def test_student_request_then_partner_accepts(db_session) -> None:
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)

    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id],
        first_message="Hi, I'm interested in your roles.", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    assert out["request_state"] == "pending"

    # Student may send up to the intro cap (default 3, incl. the first message).
    limit = get_settings().messaging_request_message_limit
    for i in range(limit - 1):
        await message_service.send_message(
            db_session, principal=student, thread_id=tid, body=f"follow up {i}",
            ctx=CTX,
        )
    # The next one is blocked — waiting for acceptance.
    with pytest.raises(RequestPendingError):
        await message_service.send_message(
            db_session, principal=student, thread_id=tid, body="one too many",
            ctx=CTX,
        )

    # Partner accepts (org Page member with the messaging capability).
    res = await request_service.respond(
        db_session, principal=partner, thread_id=tid, action="accept", ctx=CTX,
    )
    assert res["request_state"] == "accepted"

    # Now both sides can message freely.
    await message_service.send_message(
        db_session, principal=partner, thread_id=tid, body="Thanks for reaching out!",
        ctx=CTX,
    )
    await message_service.send_message(
        db_session, principal=student, thread_id=tid, body="Great, here are details.",
        ctx=CTX,
    )
    assert (await _thread(db_session, tid)).request_state == "accepted"


async def test_accept_notifies_initiator_masked(db_session) -> None:
    """Accepting a request notifies ONLY the initiator, with an org-Page label and
    never the message body; the accepting staff member is not surfaced."""
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)

    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id],
        first_message="Hi, I'd love to learn about your internships.", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])

    await request_service.respond(
        db_session, principal=partner, thread_id=tid, action="accept", ctx=CTX,
    )

    # The student (initiator) gets exactly one in-app "request accepted" row.
    student_rows = (
        await db_session.execute(
            select(Notification).where(
                Notification.recipient_id == student_user.id,
                Notification.notif_type == "message.request_accepted",
            )
        )
    ).scalars().all()
    assert len(student_rows) == 1
    note = student_rows[0]
    # Org-Page masking: names the org, never the message body.
    assert "Partner Co" in note.body
    assert "internships" not in note.body
    assert note.action_url == f"/messages/{tid}"

    # The acceptor (partner staff) is NOT notified about their own accept.
    partner_rows = (
        await db_session.execute(
            select(Notification).where(
                Notification.recipient_id == partner_user.id,
                Notification.notif_type == "message.request_accepted",
            )
        )
    ).scalars().all()
    assert partner_rows == []

    # A preference-gated email is also enqueued to the initiator (drained later).
    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == student_user.id,
                NotificationOutbox.template_key == "message.request_accepted",
            )
        )
    ).scalars().all()
    assert len(outbox) == 1


async def test_decline_notifies_nobody(db_session) -> None:
    """Declining a request stays silent — no rejection notification anywhere."""
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)

    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id],
        first_message="Hello there.", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    await request_service.respond(
        db_session, principal=partner, thread_id=tid, action="decline", ctx=CTX,
    )

    rows = (
        await db_session.execute(
            select(Notification).where(
                Notification.notif_type == "message.request_accepted",
            )
        )
    ).scalars().all()
    assert rows == []


async def test_message_email_honors_mute_preference(db_session) -> None:
    """A user who turns OFF the 'message' email category still gets the in-app feed
    row but no email outbox row (the outbox is preference-gated as documented)."""
    from app.modules.users.domain.models import NotificationPreference

    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)
    db_session.add(
        NotificationPreference(
            user_id=student_user.id, category="message", email_setting="off",
        )
    )
    await db_session.commit()

    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id], first_message="Hi", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    await request_service.respond(
        db_session, principal=partner, thread_id=tid, action="accept", ctx=CTX
    )
    await message_service.send_message(
        db_session, principal=partner, thread_id=tid, body="Reply", ctx=CTX
    )

    feed = (
        await db_session.execute(
            select(Notification).where(
                Notification.recipient_id == student_user.id,
                Notification.notif_type == "message.received",
            )
        )
    ).scalars().all()
    assert len(feed) >= 1  # in-app still delivered
    emails = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.recipient_id == student_user.id,
                NotificationOutbox.template_key == "message.received",
            )
        )
    ).scalars().all()
    assert emails == []  # email muted


async def test_partner_decline_blocks_further_sends(db_session) -> None:
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)
    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id], first_message="Hello",
        ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    await request_service.respond(
        db_session, principal=partner, thread_id=tid, action="decline", ctx=CTX
    )
    with pytest.raises(RequestPendingError):
        await message_service.send_message(
            db_session, principal=student, thread_id=tid, body="please?", ctx=CTX
        )
    # Re-responding to a settled request is a no-op error.
    with pytest.raises(RequestNotActionableError):
        await request_service.respond(
            db_session, principal=partner, thread_id=tid, action="accept", ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Organization-as-Page identity masking                                        #
# --------------------------------------------------------------------------- #


async def test_student_sees_org_page_not_staff(db_session) -> None:
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session, display_name="Acme Co")
    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id], first_message="Hi",
        ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    await request_service.respond(
        db_session, principal=partner, thread_id=tid, action="accept", ctx=CTX
    )
    await message_service.send_message(
        db_session, principal=partner, thread_id=tid, body="We reply as the company",
        ctx=CTX,
    )
    # Student's thread view: the counterpart is the ORG Page, never the recruiter.
    detail = await thread_service.get_thread(
        db_session, principal=student, thread_id=tid
    )
    assert detail["counterpart_label"] == "Acme Co"
    msgs, _cur, _lim = await message_service.list_messages(
        db_session, principal=student, thread_id=tid
    )
    partner_msg = [m for m in msgs if not m["is_mine"]][-1]
    assert partner_msg["sender_label"] == "Acme Co"


async def test_partner_cold_request_masks_student(db_session) -> None:
    # A partner-INITIATED cold request keeps the student masked to the partner until
    # the student accepts (the student did not choose to reach out).
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)
    out = await thread_service.create_thread(
        db_session, principal=partner, kind="direct", context_type=None,
        context_id=None, recipient_ids=[student_user.id], first_message="We're hiring",
        ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    assert out["request_state"] == "pending"
    # From the partner org inbox, the student is a masked handle (no real name).
    items, _c, _l = await inbox_service.list_org_inbox(
        db_session, principal=partner, scope="all"
    )
    row = next(i for i in items if i["id"] == str(tid))
    assert "ẩn danh" in row["counterpart_label"].lower() or "anonymous" in (
        row["counterpart_label"].lower()
    )


def _is_masked(label: str) -> bool:
    lo = label.lower()
    return "ẩn danh" in lo or "anonymous" in lo


async def test_cold_requested_student_stays_masked_after_decline_and_block(db_session) -> None:
    """A student who rejects a partner's cold outreach must NOT have their identity
    exposed to the partner — the mask lifts only on accept, never on decline/block."""
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)
    out = await thread_service.create_thread(
        db_session, principal=partner, kind="direct", context_type=None,
        context_id=None, recipient_ids=[student_user.id], first_message="We're hiring",
        ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    # Decline → still masked to the partner.
    await request_service.respond(
        db_session, principal=student, thread_id=tid, action="decline", ctx=CTX
    )
    detail = await thread_service.get_thread(db_session, principal=partner, thread_id=tid)
    assert _is_masked(detail["counterpart_label"])

    # A fresh cold request that gets BLOCKED → also still masked.
    out2 = await thread_service.create_thread(
        db_session, principal=partner, kind="direct", context_type=None,
        context_id=None, recipient_ids=[student_user.id], first_message="Second try",
        ctx=CTX,
    )
    tid2 = uuid.UUID(out2["id"])
    await request_service.respond(
        db_session, principal=student, thread_id=tid2, action="block", ctx=CTX
    )
    detail2 = await thread_service.get_thread(db_session, principal=partner, thread_id=tid2)
    assert _is_masked(detail2["counterpart_label"])


async def test_partner_cannot_colocate_two_students_in_one_thread(db_session) -> None:
    """A partner must not create a thread with two student recipients — they would
    read each other's real names (a student-discovery / de-anonymization channel)."""
    from app.modules.messaging.application.errors import StudentToStudentBlockedError

    from tests.messaging_utils import make_second_student

    _su1, s1 = await make_student(db_session)
    student2_user, _s2 = await make_second_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)
    _su1_user = _su1

    with pytest.raises(StudentToStudentBlockedError):
        await thread_service.create_thread(
            db_session, principal=partner, kind="direct", context_type=None,
            context_id=None, recipient_ids=[_su1_user.id, student2_user.id],
            first_message="Hi both", ctx=CTX,
        )


async def test_idempotent_intro_retry_at_cap_returns_original(db_session) -> None:
    """Retrying the last intro message (same dedupe key) at the request cap must
    return the already-persisted message, not a spurious 409 request-pending error."""
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)
    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id], first_message="intro 1",
        ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    limit = get_settings().messaging_request_message_limit
    # Send up to the cap; the last one carries a dedupe key.
    for i in range(limit - 2):
        await message_service.send_message(
            db_session, principal=student, thread_id=tid, body=f"intro {i + 2}", ctx=CTX,
        )
    last = await message_service.send_message(
        db_session, principal=student, thread_id=tid, body="final intro",
        client_dedupe_key="K-final", ctx=CTX,
    )
    # Retrying that exact send at the cap returns the SAME message (idempotent),
    # never RequestPendingError.
    retry = await message_service.send_message(
        db_session, principal=student, thread_id=tid, body="final intro",
        client_dedupe_key="K-final", ctx=CTX,
    )
    assert retry["id"] == last["id"]


async def test_respond_returns_404_not_409_for_nonrecipient(db_session) -> None:
    """A settled thread must not reveal its existence via a 409-vs-404 difference:
    a non-recipient always gets 404 whatever the request state."""
    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)
    _ou, _oorg, outsider = await make_partner(db_session, display_name="Other Co")
    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id], first_message="Hi", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    await request_service.respond(
        db_session, principal=partner, thread_id=tid, action="accept", ctx=CTX
    )
    # The thread is now settled (accepted). An unrelated org gets 404, NOT 409.
    with pytest.raises(ResourceNotFoundError):
        await request_service.respond(
            db_session, principal=outsider, thread_id=tid, action="accept", ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Shared org inbox + RBAC                                                       #
# --------------------------------------------------------------------------- #


async def test_org_inbox_lists_incoming_and_scopes_by_org(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    _pu2, _porg2, other_partner = await make_partner(db_session, display_name="Other Co")

    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[_pu.id], first_message="Hi", ctx=CTX,
    )
    tid = out["id"]
    # The owning partner sees it in their inbox.
    items, _c, _l = await inbox_service.list_org_inbox(
        db_session, principal=partner, scope="all"
    )
    assert any(i["id"] == tid for i in items)
    # A different partner org does NOT.
    other_items, _c2, _l2 = await inbox_service.list_org_inbox(
        db_session, principal=other_partner, scope="all"
    )
    assert all(i["id"] != tid for i in other_items)


async def test_org_new_inbound_raises_team_badge_and_clears_on_read(db_session) -> None:
    """A brand-new inbound lead raises the header badge for the whole org team even
    with no participant rows yet, is scoped to the owning org, and clears when read in
    the inbox — including after a staffer accepts (personal + team cursors sync)."""
    student_user, student = await make_student(db_session)
    admin_user, porg, admin = await make_partner(db_session, display_name="Acme Co")
    _ou, _oorg, other = await make_partner(db_session, display_name="Other Co")

    assert await message_service.unread_count(db_session, principal=admin) == 0

    # Address the org PAGE directly (the real inbound flow): an org party with NO
    # staff participant rows — the whole team relies on the shared cursor.
    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[], target_org_id=porg.id,
        first_message="Hi, a question for your team.", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])

    # New inbound lead raises the shared team badge (no participant row on the org side).
    assert await message_service.unread_count(db_session, principal=admin) >= 1
    # A different org never sees it in their badge.
    assert await message_service.unread_count(db_session, principal=other) == 0

    # Reading it in the inbox clears the team badge.
    await inbox_service.mark_org_read(db_session, principal=admin, thread_id=tid, ctx=CTX)
    assert await message_service.unread_count(db_session, principal=admin) == 0

    # After the admin accepts (gains a participant row) a new student message raises the
    # badge again, and reading in the inbox still clears it (the two cursors stay in sync).
    await request_service.respond(
        db_session, principal=admin, thread_id=tid, action="accept", ctx=CTX
    )
    await message_service.send_message(
        db_session, principal=student, thread_id=tid, body="one more thing", ctx=CTX
    )
    assert await message_service.unread_count(db_session, principal=admin) >= 1
    await inbox_service.mark_org_read(db_session, principal=admin, thread_id=tid, ctx=CTX)
    assert await message_service.unread_count(db_session, principal=admin) == 0


async def test_assignment_notifies_new_assignee_not_self(db_session) -> None:
    """Routing a thread to a specific member alerts that member (deep link, no body);
    picking up your own thread never pings yourself."""
    student_user, student = await make_student(db_session)
    admin_user, porg, admin = await make_partner(db_session, display_name="Acme Co")
    member_user, _m, _mp = await add_member(
        db_session, org=porg, member_email=email("rep"),
        permissions=[("messaging", "read"), ("messaging", "send")],
    )
    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[], target_org_id=porg.id,
        first_message="Hi team", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])

    await assignment_service.assign(
        db_session, principal=admin, thread_id=tid,
        department_id=None, assignee_id=member_user.id, ctx=CTX,
    )
    rep_notes = (
        await db_session.execute(
            select(Notification).where(
                Notification.recipient_id == member_user.id,
                Notification.notif_type == "messaging.thread_assigned",
            )
        )
    ).scalars().all()
    assert len(rep_notes) == 1
    assert rep_notes[0].action_url == f"/messages/{tid}"

    # Self-assign does not ping the caller.
    await assignment_service.assign(
        db_session, principal=admin, thread_id=tid,
        department_id=None, assignee_id=admin_user.id, ctx=CTX,
    )
    admin_notes = (
        await db_session.execute(
            select(Notification).where(
                Notification.recipient_id == admin_user.id,
                Notification.notif_type == "messaging.thread_assigned",
            )
        )
    ).scalars().all()
    assert admin_notes == []


async def test_org_staff_reads_inbox_thread_without_participant_row(db_session) -> None:
    # The whole team must be able to READ a shared-inbox thread via ``messaging:read``,
    # not only after someone replies (participant rows are created lazily on send/accept).
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[_pu.id], first_message="Hi there",
        ctx=CTX,
    )
    tid = uuid.UUID(out["id"])

    detail = await thread_service.get_thread(
        db_session, principal=partner, thread_id=tid
    )
    assert detail["viewer_is_recipient"] is True  # pending request, partner is recipient
    assert detail["request_message_limit"] >= 1
    msgs, _c, _l = await message_service.list_messages(
        db_session, principal=partner, thread_id=tid
    )
    assert any(m["body"] == "Hi there" for m in msgs)

    # A partner from another org still cannot read it (404).
    _pu2, _porg2, outsider = await make_partner(db_session, display_name="Other Co")
    with pytest.raises(ResourceNotFoundError):
        await thread_service.get_thread(
            db_session, principal=outsider, thread_id=tid
        )


async def _make_department(db_session, org, name: str):
    from app.modules.organization.domain.models import Department

    dept = Department(org_id=org.id, name=name)
    db_session.add(dept)
    await db_session.flush()
    await db_session.commit()
    return dept


async def _dept_scoped_member(db_session, org, dept, prefix: str):
    """A non-admin org member with messaging read+send, scoped to one department."""
    from app.modules.organization.domain.models import MembershipDepartment

    user, membership, principal = await add_member(
        db_session,
        org=org,
        member_email=email(prefix),
        permissions=[("messaging", "read"), ("messaging", "send")],
    )
    db_session.add(
        MembershipDepartment(membership_id=membership.id, department_id=dept.id)
    )
    await db_session.commit()
    return user, principal


async def test_department_scope_is_access_control_not_just_a_filter(db_session) -> None:
    """A thread assigned to department B is unreachable by a department-A staffer via
    a direct deep link (read AND send), while dept B + the admin reach it. Unassigned
    threads stay visible to everyone (shared triage)."""
    student_user, student = await make_student(db_session)
    admin_user, porg, admin = await make_partner(db_session, display_name="Acme Co")

    dept_a = await _make_department(db_session, porg, "Engineering")
    dept_b = await _make_department(db_session, porg, "Finance")
    _ua, member_a = await _dept_scoped_member(db_session, porg, dept_a, "eng")
    _ub, member_b = await _dept_scoped_member(db_session, porg, dept_b, "fin")

    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[admin_user.id],
        first_message="Hello, a question for your team.", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])

    # While UNASSIGNED, either department may triage it (shared inbox).
    for principal in (member_a, member_b):
        detail = await thread_service.get_thread(
            db_session, principal=principal, thread_id=tid
        )
        assert detail["id"] == str(tid)

    # Admin routes it to Finance.
    await assignment_service.assign(
        db_session, principal=admin, thread_id=tid,
        department_id=dept_b.id, assignee_id=None, ctx=CTX,
    )

    # Engineering can no longer read it (deep link crosses a department boundary)...
    with pytest.raises(ResourceNotFoundError):
        await thread_service.get_thread(
            db_session, principal=member_a, thread_id=tid
        )
    # ...nor accept/act on the request...
    with pytest.raises(ResourceNotFoundError):
        await request_service.respond(
            db_session, principal=member_a, thread_id=tid, action="accept", ctx=CTX,
        )
    # ...nor reply as the Page.
    with pytest.raises(ResourceNotFoundError):
        await message_service.send_message(
            db_session, principal=member_a, thread_id=tid, body="sneaking in", ctx=CTX,
        )

    # Finance (the owning department) reads it, accepts the request, and replies.
    detail_b = await thread_service.get_thread(
        db_session, principal=member_b, thread_id=tid
    )
    assert detail_b["id"] == str(tid)
    await request_service.respond(
        db_session, principal=member_b, thread_id=tid, action="accept", ctx=CTX,
    )
    await message_service.send_message(
        db_session, principal=member_b, thread_id=tid, body="Finance here, happy to help.",
        ctx=CTX,
    )
    # The admin (sees-all) always reaches it.
    detail_admin = await thread_service.get_thread(
        db_session, principal=admin, thread_id=tid
    )
    assert detail_admin["id"] == str(tid)


async def test_org_page_initiate_and_send_require_capability(db_session) -> None:
    """Acting AS the org Page (initiate + send) requires the grantable messaging
    capability — org membership alone must not let an ungranted staffer speak for
    the company; a granted member can."""
    from app.modules.messaging.application.errors import MessagingNotAllowedError

    admin_user, porg, admin = await make_partner(db_session, display_name="Acme Co")
    _uu, uorg, _uni = await make_university(db_session, display_name="VinUni")

    # A member with NO messaging grant cannot initiate as the Page.
    _ng_user, _m, nogrant = await add_member(
        db_session, org=porg, member_email=email("nogrant"), permissions=[],
    )
    with pytest.raises(MessagingNotAllowedError):
        await thread_service.create_thread(
            db_session, principal=nogrant, kind="direct", context_type=None,
            context_id=None, recipient_ids=[], target_org_id=uorg.id,
            first_message="Rogue outreach", ctx=CTX,
        )

    # A member WITH messaging:initiate + send can, and can then send as the Page.
    _ok_user, _m2, ok = await add_member(
        db_session, org=porg, member_email=email("ok"),
        permissions=[("messaging", "initiate"), ("messaging", "send")],
    )
    out = await thread_service.create_thread(
        db_session, principal=ok, kind="direct", context_type=None,
        context_id=None, recipient_ids=[], target_org_id=uorg.id,
        first_message="Official partner outreach", ctx=CTX,
    )
    tid = uuid.UUID(out["id"])
    await message_service.send_message(
        db_session, principal=ok, thread_id=tid, body="Following up as the company",
        ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Recipient discovery: a student can never find another student               #
# --------------------------------------------------------------------------- #


async def test_recipient_search_never_returns_students(db_session) -> None:
    _su, student = await make_student(db_session)
    await make_partner(db_session, display_name="Findable Partner")
    await make_university(db_session, display_name="VinUni")

    results = await recipient_service.search(db_session, principal=student, q=None)
    assert results, "student should be able to find organizations to message"
    assert all(r["kind"] == "org" for r in results)
    assert all(r["org_type"] in ("partner", "university") for r in results)


# --------------------------------------------------------------------------- #
# Realtime: a send publishes a lightweight signal to the org channel           #
# --------------------------------------------------------------------------- #


async def test_realtime_signal_published_to_org_channel(db_session) -> None:
    from app.modules.messaging.application.realtime import connection_manager
    from app.modules.messaging.application.realtime.hub import org_channel

    student_user, student = await make_student(db_session)
    partner_user, porg, partner = await make_partner(db_session)
    out = await thread_service.create_thread(
        db_session, principal=student, kind="direct", context_type=None,
        context_id=None, recipient_ids=[partner_user.id], first_message="Hi",
        ctx=CTX,
    )
    tid = out["id"]

    received: list[dict] = []

    async def _send(evt: dict) -> None:
        received.append(evt)

    conn = await connection_manager.register(
        send=_send, channels=[org_channel(porg.id)]
    )
    try:
        await message_service.send_message(
            db_session, principal=student, thread_id=uuid.UUID(tid),
            body="a follow up", ctx=CTX,
        )
    finally:
        await connection_manager.unregister(conn)

    assert any(
        e.get("type") == "message.created" and e.get("thread_id") == tid
        for e in received
    ), "org inbox socket should receive a lightweight message.created signal (no body)"
    # The signal is a pure notification — it never carries message content.
    assert all("body" not in e for e in received)


# --------------------------------------------------------------------------- #
# Attachments: upload → bind on send → list → gated download + access control  #
# --------------------------------------------------------------------------- #


def _png_upload(name: str = "shot.png") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 64),
        filename=name,
        headers=Headers({"content-type": "image/png"}),
    )


async def test_attachment_upload_send_list_and_gated_download(db_session) -> None:
    from app.modules.messaging.application import attachment_service

    _uu, _uorg, uni = await make_university(db_session)
    student_user, student = await make_student(db_session)
    # University → student (instant, accepted) so the student can also read.
    out = await thread_service.create_thread(
        db_session, principal=uni, kind="direct", context_type="support",
        context_id=None, recipient_ids=[student_user.id], first_message="Hello",
        ctx=CTX,
    )
    tid = uuid.UUID(out["id"])

    att = await attachment_service.upload(
        db_session, principal=uni, thread_id=tid, file=_png_upload(), ctx=CTX
    )
    assert att["kind"] == "image"
    assert att["url"].startswith("/api/v1/messaging/attachments/")
    assert "storage_key" not in att  # never leak the storage key

    await message_service.send_message(
        db_session, principal=uni, thread_id=tid, body="See attached",
        attachment_ids=[uuid.UUID(att["id"])], ctx=CTX,
    )
    # The student sees the attachment on the message.
    msgs, _c, _l = await message_service.list_messages(
        db_session, principal=student, thread_id=tid
    )
    with_att = [m for m in msgs if m["attachments"]]
    assert with_att and with_att[0]["attachments"][0]["id"] == att["id"]

    # The student (a participant) may download it.
    data, ctype, _fn = await attachment_service.download(
        db_session, principal=student, attachment_id=uuid.UUID(att["id"])
    )
    assert ctype == "image/png" and data

    # An unrelated partner cannot (404, not 403 — anti-enumeration).
    _pu, _porg, outsider = await make_partner(db_session)
    with pytest.raises(ResourceNotFoundError):
        await attachment_service.download(
            db_session, principal=outsider, attachment_id=uuid.UUID(att["id"])
        )


async def test_attachment_only_message_allowed_but_blank_alone_rejected(db_session) -> None:
    from app.modules.messaging.application import attachment_service
    from app.modules.messaging.application.errors import BlankMessageError

    _uu, _uorg, uni = await make_university(db_session)
    student_user, _student = await make_student(db_session)
    out = await thread_service.create_thread(
        db_session, principal=uni, kind="direct", context_type="support",
        context_id=None, recipient_ids=[student_user.id], first_message="Hi",
        ctx=CTX,
    )
    tid = uuid.UUID(out["id"])

    # A blank body with NO attachments is rejected.
    with pytest.raises(BlankMessageError):
        await message_service.send_message(
            db_session, principal=uni, thread_id=tid, body="   ", ctx=CTX
        )

    # A blank body WITH an attachment is allowed (image-only message).
    att = await attachment_service.upload(
        db_session, principal=uni, thread_id=tid, file=_png_upload(), ctx=CTX
    )
    sent = await message_service.send_message(
        db_session, principal=uni, thread_id=tid, body="",
        attachment_ids=[uuid.UUID(att["id"])], ctx=CTX,
    )
    assert sent["attachments"] and sent["attachments"][0]["id"] == att["id"]

