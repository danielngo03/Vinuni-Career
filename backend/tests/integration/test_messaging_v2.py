"""Messaging V2 (owner decision 2026-07-09) service-level tests.

Covers the new cross-persona interaction model layered on ADR-0012:
the message-request gate (initiate → 3 intro messages → accept/decline/block),
organization-as-Page identity masking (outsiders see the org, never the staff
member), the shared org inbox + RBAC, and the recipient picker's student↔student
discovery block. The ADR-0012 institutional invariants are still exercised by
``test_messaging.py``.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.modules.messaging.application import (
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
from app.shared.exceptions import ResourceNotFoundError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.messaging_utils import (
    make_partner,
    make_student,
    make_university,
)


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
