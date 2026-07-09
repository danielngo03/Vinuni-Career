"""Messaging (ADR-0012) service-level tests.

Covers the institutional permission matrix (student↔student hard block at BOTH
create and send; partner↔student application-bound; partner↔partner same-org vs.
cross-org; student initiate-support vs. reply-only-to-partner; university↔anyone),
anonymity masking + PII-safe notification, persist-before-deliver, notification
dedupe coalescing, idempotent send, rate limits (global + inactive-application
taper), delete rules, mute/report, cross-tenant isolation, unread/mark-read, and
PII-safe audit.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import get_settings
from app.modules.messaging.application import message_service, thread_service
from app.modules.messaging.application.errors import (
    MessageDeleteNotAllowedError,
    MessageRateLimitedError,
    MessagingNotAllowedError,
    StudentToStudentBlockedError,
)
from app.modules.messaging.domain.models import (
    Message,
    MessageThread,
    MessageThreadParticipant,
)
from app.modules.notifications.domain.models import Notification
from app.modules.recruitment.domain.models import Application
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.messaging_utils import (
    make_partner,
    make_second_student,
    make_student,
    make_university,
    seed_application,
)
from tests.org_utils import add_member

# --------------------------------------------------------------------------- #
# Student ↔ student hard block (BOTH create AND send)                          #
# --------------------------------------------------------------------------- #


async def test_student_to_student_create_blocked(db_session) -> None:
    _su1, student1 = await make_student(db_session)
    student2_user, _student2 = await make_second_student(db_session)
    with pytest.raises(StudentToStudentBlockedError):
        await thread_service.create_thread(
            db_session,
            principal=student1,
            kind="direct",
            context_type="support",
            context_id=None,
            recipient_ids=[student2_user.id],
            first_message="hi",
            ctx=CTX,
        )
    # Nothing persisted.
    count = (await db_session.execute(select(func.count()).select_from(MessageThread))).scalar_one()
    assert count == 0


async def test_student_to_student_send_blocked(db_session) -> None:
    """Even a thread that contains two students can never carry a student message."""

    _su1, student1 = await make_student(db_session)
    student2_user, _student2 = await make_second_student(db_session)
    _uu, uorg, _uni = await make_university(db_session)

    thread = MessageThread(
        kind="direct",
        context_type="support",
        org_id=uorg.id,
        created_by=student1.user_id,
        status="active",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add_all(
        [
            MessageThreadParticipant(thread_id=thread.id, user_id=student1.user_id),
            MessageThreadParticipant(thread_id=thread.id, user_id=student2_user.id),
        ]
    )
    await db_session.commit()

    with pytest.raises(StudentToStudentBlockedError):
        await message_service.send_message(
            db_session, principal=student1, thread_id=thread.id, body="hi", ctx=CTX
        )
    msgs = (await db_session.execute(select(func.count()).select_from(Message))).scalar_one()
    assert msgs == 0


# --------------------------------------------------------------------------- #
# University may initiate to anyone                                            #
# --------------------------------------------------------------------------- #


async def test_university_initiates_to_student_and_partner(db_session) -> None:
    _uu, _uorg, uni = await make_university(db_session)
    student_user, _student = await make_student(db_session)
    partner_user, _porg, _partner = await make_partner(db_session)

    to_student = await thread_service.create_thread(
        db_session,
        principal=uni,
        kind="direct",
        context_type="support",
        context_id=None,
        recipient_ids=[student_user.id],
        first_message="Welcome",
        ctx=CTX,
    )
    assert to_student["status"] == "active"

    to_partner = await thread_service.create_thread(
        db_session,
        principal=uni,
        kind="direct",
        context_type=None,
        context_id=None,
        recipient_ids=[partner_user.id],
        first_message="Hello",
        ctx=CTX,
    )
    assert to_partner["id"]


# --------------------------------------------------------------------------- #
# Partner ↔ student requires an application relationship                        #
# --------------------------------------------------------------------------- #


async def test_partner_to_student_without_application_blocked(db_session) -> None:
    _pu, porg, partner = await make_partner(db_session)
    student_user, _student = await make_student(db_session)
    # A context_id that does not bind this org/applicant -> 404 (masked).
    with pytest.raises(ResourceNotFoundError):
        await thread_service.create_thread(
            db_session,
            principal=partner,
            kind="direct",
            context_type="application",
            context_id=uuid.uuid4(),
            recipient_ids=[student_user.id],
            first_message="hi",
            ctx=CTX,
        )


async def test_partner_to_student_missing_context_rejected(db_session) -> None:
    _pu, porg, partner = await make_partner(db_session)
    student_user, _student = await make_student(db_session)
    with pytest.raises(ValidationFailedError):
        await thread_service.create_thread(
            db_session,
            principal=partner,
            kind="direct",
            context_type=None,
            context_id=None,
            recipient_ids=[student_user.id],
            ctx=CTX,
        )


async def test_partner_to_student_with_application_ok(db_session) -> None:
    _pu, porg, partner = await make_partner(db_session)
    student_user, _student = await make_student(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    out = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="We reviewed your application.",
        ctx=CTX,
    )
    assert out["context_type"] == "application"
    assert out["is_anonymous"] is False
    thread = (
        await db_session.execute(
            select(MessageThread).where(MessageThread.id == uuid.UUID(out["id"]))
        )
    ).scalar_one()
    assert thread.context_id == app_id
    assert thread.org_id == porg.id


# --------------------------------------------------------------------------- #
# Partner opens an ANONYMOUS-applicant thread WITHOUT the student's user id     #
# (recipient resolved server-side from the application — ADR-0012 §3/§8)        #
# --------------------------------------------------------------------------- #


async def test_partner_opens_anonymous_thread_without_recipient_ids(db_session) -> None:
    """A partner has no student user id while the application is anonymous; it opens
    the masked thread by passing ONLY the application context, and the service
    resolves the applicant. The response must stay masked (no name/email)."""

    student_user, _student = await make_student(db_session)
    student_user.full_name = "Mai Tran Unique"
    await db_session.commit()
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(
        db_session, org_id=porg.id, applicant_id=student_user.id, is_anonymous=True
    )

    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[],  # partner does NOT know / pass the student's user id
        first_message="We would like to talk.",
        ctx=CTX,
    )

    # Recipient was resolved to the bound applicant.
    thread_id = uuid.UUID(created["id"])
    parts = (
        (
            await db_session.execute(
                select(MessageThreadParticipant.user_id).where(
                    MessageThreadParticipant.thread_id == thread_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert student_user.id in parts
    assert partner.user_id in parts

    # Response is anonymity-masked: no name, no email, just the masked handle.
    assert created["is_anonymous"] is True
    assert created["counterpart_label"].startswith("Ứng viên ẩn danh")
    serialized = json.dumps(created, ensure_ascii=False)
    assert "Mai Tran Unique" not in serialized
    assert student_user.email not in serialized

    # Audit stores ids/codes only, never the student identity.
    audit_rows = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "messaging.thread.create")
            )
        )
        .scalars()
        .all()
    )
    assert audit_rows
    for row in audit_rows:
        blob = json.dumps(row.after_snapshot or {}, ensure_ascii=False)
        assert "Mai Tran Unique" not in blob
        assert student_user.email not in blob


async def test_partner_open_anonymous_thread_idempotent(db_session) -> None:
    """Re-opening the same (application, org) returns the existing thread."""

    student_user, _student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(
        db_session, org_id=porg.id, applicant_id=student_user.id, is_anonymous=True
    )
    first = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[],
        ctx=CTX,
    )
    second = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[],
        ctx=CTX,
    )
    assert first["id"] == second["id"]
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(MessageThread)
            .where(MessageThread.context_id == app_id)
        )
    ).scalar_one()
    assert count == 1


async def test_partner_open_anonymous_thread_other_org_404(db_session) -> None:
    """A partner cannot open a context thread on another org's application."""

    student_user, _student = await make_student(db_session)
    _pu, porg, _partner = await make_partner(db_session)
    app_id = await seed_application(
        db_session, org_id=porg.id, applicant_id=student_user.id, is_anonymous=True
    )
    _ou, _oorg, other_partner = await make_partner(db_session, display_name="Other Co")
    with pytest.raises(ResourceNotFoundError):
        await thread_service.create_thread(
            db_session,
            principal=other_partner,
            kind="direct",
            context_type="application",
            context_id=app_id,
            recipient_ids=[],
            ctx=CTX,
        )


async def test_partner_context_overrides_recipient_to_applicant(db_session) -> None:
    """Even if a partner passes some OTHER user id, an application context resolves
    the recipient to the bound applicant — never the smuggled non-applicant."""

    student_user, _student = await make_student(db_session)
    decoy_user, _decoy = await make_second_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[decoy_user.id],
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    parts = set(
        (
            await db_session.execute(
                select(MessageThreadParticipant.user_id).where(
                    MessageThreadParticipant.thread_id == thread_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert student_user.id in parts  # the bound applicant
    assert decoy_user.id not in parts  # the smuggled non-applicant is ignored


async def test_partner_open_thread_reveal_flips_to_real_name(db_session) -> None:
    """After reveal, the projection on a context-resolved thread shows the real name."""

    student_user, _student = await make_student(db_session)
    student_user.full_name = "Khanh Le Unique"
    await db_session.commit()
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(
        db_session, org_id=porg.id, applicant_id=student_user.id, is_anonymous=True
    )
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[],
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    masked = await thread_service.get_thread(db_session, principal=partner, thread_id=thread_id)
    assert masked["counterpart_label"].startswith("Ứng viên ẩn danh")

    app_row = (
        await db_session.execute(select(Application).where(Application.id == app_id))
    ).scalar_one()
    app_row.reveal_approved_at = datetime.now(tz=UTC)
    await db_session.commit()

    revealed = await thread_service.get_thread(db_session, principal=partner, thread_id=thread_id)
    assert revealed["counterpart_label"] == "Khanh Le Unique"


# --------------------------------------------------------------------------- #
# Partner ↔ partner: same org ok, cross org 404                                #
# --------------------------------------------------------------------------- #


async def test_partner_partner_same_org_ok_cross_org_404(db_session) -> None:
    _pu, porg, partner = await make_partner(db_session)
    teammate_user, _m, _teammate = await add_member(
        db_session, org=porg, permissions=[("jobs", "read")]
    )
    same = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="team",
        context_id=None,
        recipient_ids=[teammate_user.id],
        first_message="standup",
        ctx=CTX,
    )
    assert same["id"]

    other_user, _porg2, _partner2 = await make_partner(db_session, display_name="Other Co")
    with pytest.raises(ResourceNotFoundError):
        await thread_service.create_thread(
            db_session,
            principal=partner,
            kind="direct",
            context_type="team",
            context_id=None,
            recipient_ids=[other_user.id],
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Student initiate-support ok; initiate-to-partner refused; reply-only ok      #
# --------------------------------------------------------------------------- #


async def test_student_initiates_support_ok(db_session) -> None:
    _su, student = await make_student(db_session)
    uni_user, _uorg, _uni = await make_university(db_session)
    out = await thread_service.create_thread(
        db_session,
        principal=student,
        kind="direct",
        context_type="support",
        context_id=None,
        recipient_ids=[uni_user.id],
        first_message="I need help",
        ctx=CTX,
    )
    assert out["id"]


async def test_student_cannot_initiate_partner_thread(db_session) -> None:
    _su, student = await make_student(db_session)
    partner_user, _porg, _partner = await make_partner(db_session)
    with pytest.raises(MessagingNotAllowedError):
        await thread_service.create_thread(
            db_session,
            principal=student,
            kind="direct",
            context_type=None,
            context_id=None,
            recipient_ids=[partner_user.id],
            ctx=CTX,
        )


async def test_student_replies_into_partner_thread(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="Are you available?",
        ctx=CTX,
    )
    reply = await message_service.send_message(
        db_session,
        principal=student,
        thread_id=uuid.UUID(created["id"]),
        body="Yes, I am.",
        ctx=CTX,
    )
    assert reply["is_mine"] is True


# --------------------------------------------------------------------------- #
# Anonymity masking + PII-safe notification                                    #
# --------------------------------------------------------------------------- #


async def test_anonymous_masking_until_reveal(db_session) -> None:
    student_user, student = await make_student(db_session)
    # Distinct, recognizable name so we can prove it is masked then revealed.
    student_user.full_name = "Linh Nguyen Unique"
    await db_session.commit()
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(
        db_session, org_id=porg.id, applicant_id=student_user.id, is_anonymous=True
    )
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="Hello candidate",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])

    # Student replies -> partner gets a PII-safe, anonymous notification.
    await message_service.send_message(
        db_session,
        principal=student,
        thread_id=thread_id,
        body="Hi there",
        ctx=CTX,
    )

    # Partner's thread view masks the student.
    detail = await thread_service.get_thread(db_session, principal=partner, thread_id=thread_id)
    assert detail["counterpart_label"].startswith("Ứng viên ẩn danh")
    serialized = json.dumps(detail, ensure_ascii=False)
    assert student_user.email not in serialized
    assert "Linh Nguyen Unique" not in serialized

    # Partner's NEW-MESSAGE notification stays anonymous (no name/email/body).
    notif = (
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.recipient_id == partner.user_id,
                    Notification.notif_type == "message.received",
                )
            )
        )
        .scalars()
        .first()
    )
    assert notif is not None
    blob = f"{notif.title} {notif.body}"
    assert "Ứng viên ẩn danh" in notif.body
    assert student_user.email not in blob
    assert "Hi there" not in blob  # never the message body

    # After reveal, the same projection flips to the real name.
    app_row = (
        await db_session.execute(select(Application).where(Application.id == app_id))
    ).scalar_one()
    app_row.reveal_approved_at = datetime.now(tz=UTC)
    await db_session.commit()

    detail2 = await thread_service.get_thread(db_session, principal=partner, thread_id=thread_id)
    assert detail2["counterpart_label"] == "Linh Nguyen Unique"


async def test_student_sees_partner_org_name(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session, display_name="Acme Partner")
    app_id = await seed_application(
        db_session, org_id=porg.id, applicant_id=student_user.id, is_anonymous=True
    )
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="Hi",
        ctx=CTX,
    )
    detail = await thread_service.get_thread(
        db_session, principal=student, thread_id=uuid.UUID(created["id"])
    )
    assert detail["counterpart_label"] == "Acme Partner"


# --------------------------------------------------------------------------- #
# Persist-before-deliver + idempotency + dedupe coalescing                     #
# --------------------------------------------------------------------------- #


async def test_persist_before_deliver(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="hello",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    # The message row is COMMITTED before any delivery is observable.
    msg = (
        (await db_session.execute(select(Message).where(Message.thread_id == thread_id)))
        .scalars()
        .first()
    )
    assert msg is not None
    # The notification feed row exists in the SAME committed transaction.
    notif = (
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.recipient_id == student_user.id,
                    Notification.notif_type == "message.received",
                )
            )
        )
        .scalars()
        .first()
    )
    assert notif is not None
    assert "hello" not in f"{notif.title} {notif.body}"


async def test_notification_dedupe_coalesces_burst(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="1",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    for n in range(3):
        await message_service.send_message(
            db_session,
            principal=partner,
            thread_id=thread_id,
            body=f"msg {n}",
            ctx=CTX,
        )
    feed_rows = (
        await db_session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == student_user.id,
                Notification.notif_type == "message.received",
            )
        )
    ).scalar_one()
    assert feed_rows == 1  # the burst coalesced into one unread feed row


async def test_idempotent_send_same_dedupe_key(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    key = "retry-key-1"
    first = await message_service.send_message(
        db_session,
        principal=partner,
        thread_id=thread_id,
        body="hi",
        client_dedupe_key=key,
        ctx=CTX,
    )
    second = await message_service.send_message(
        db_session,
        principal=partner,
        thread_id=thread_id,
        body="hi",
        client_dedupe_key=key,
        ctx=CTX,
    )
    assert first["id"] == second["id"]
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.thread_id == thread_id, Message.client_dedupe_key == key)
        )
    ).scalar_one()
    assert count == 1


# --------------------------------------------------------------------------- #
# Rate limits -> 429 + reset_at                                                #
# --------------------------------------------------------------------------- #


async def test_global_rate_limit(db_session, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "messaging_max_messages_per_sender_per_day", 1)
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    await message_service.send_message(
        db_session,
        principal=partner,
        thread_id=thread_id,
        body="one",
        ctx=CTX,
    )
    with pytest.raises(MessageRateLimitedError) as exc:
        await message_service.send_message(
            db_session,
            principal=partner,
            thread_id=thread_id,
            body="two",
            ctx=CTX,
        )
    assert exc.value.details["reset_at"]
    assert exc.value.http_status == 429


async def test_inactive_application_taper(db_session, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "messaging_inactive_application_daily_cap", 1)
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    # Terminal/inactive application.
    app_id = await seed_application(
        db_session, org_id=porg.id, applicant_id=student_user.id, status="rejected"
    )
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    await message_service.send_message(
        db_session,
        principal=partner,
        thread_id=thread_id,
        body="one",
        ctx=CTX,
    )
    with pytest.raises(MessageRateLimitedError) as exc:
        await message_service.send_message(
            db_session,
            principal=partner,
            thread_id=thread_id,
            body="two",
            ctx=CTX,
        )
    assert exc.value.details["scope"] == "inactive_application"


# --------------------------------------------------------------------------- #
# Delete rules                                                                 #
# --------------------------------------------------------------------------- #


async def test_delete_own_within_window_then_too_late(db_session) -> None:
    student_user, student = await make_student(db_session)
    uni_user, _uorg, uni = await make_university(db_session)
    created = await thread_service.create_thread(
        db_session,
        principal=student,
        kind="direct",
        context_type="support",
        context_id=None,
        recipient_ids=[uni_user.id],
        first_message="hello",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    sent = await message_service.send_message(
        db_session,
        principal=student,
        thread_id=thread_id,
        body="oops",
        ctx=CTX,
    )
    msg_id = uuid.UUID(sent["id"])
    out = await message_service.delete_message(
        db_session,
        principal=student,
        thread_id=thread_id,
        message_id=msg_id,
        ctx=CTX,
    )
    assert out["status"] == "deleted"

    # A second message backdated past the window cannot be deleted.
    sent2 = await message_service.send_message(
        db_session,
        principal=student,
        thread_id=thread_id,
        body="late",
        ctx=CTX,
    )
    msg2 = (
        await db_session.execute(select(Message).where(Message.id == uuid.UUID(sent2["id"])))
    ).scalar_one()
    msg2.created_at = datetime.now(tz=UTC) - timedelta(minutes=30)
    await db_session.commit()
    with pytest.raises(MessageDeleteNotAllowedError):
        await message_service.delete_message(
            db_session,
            principal=student,
            thread_id=thread_id,
            message_id=msg2.id,
            ctx=CTX,
        )


async def test_system_message_undeletable_and_university_deletes_any(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    _uu, _uorg, uni = await make_university(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="partner msg",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])

    # University moderator may delete the partner's message.
    partner_msg = (
        (await db_session.execute(select(Message).where(Message.thread_id == thread_id)))
        .scalars()
        .first()
    )
    out = await message_service.delete_message(
        db_session,
        principal=uni,
        thread_id=thread_id,
        message_id=partner_msg.id,
        ctx=CTX,
    )
    assert out["status"] == "deleted"

    # A system message can never be deleted (even by a moderator).
    sysmsg = Message(thread_id=thread_id, sender_id=None, body="System notice", is_system=True)
    db_session.add(sysmsg)
    await db_session.commit()
    with pytest.raises(MessageDeleteNotAllowedError):
        await message_service.delete_message(
            db_session,
            principal=uni,
            thread_id=thread_id,
            message_id=sysmsg.id,
            ctx=CTX,
        )


async def test_partner_cannot_delete_message_to_student(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="hi",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    msg = (
        (await db_session.execute(select(Message).where(Message.thread_id == thread_id)))
        .scalars()
        .first()
    )
    with pytest.raises(MessageDeleteNotAllowedError):
        await message_service.delete_message(
            db_session,
            principal=partner,
            thread_id=thread_id,
            message_id=msg.id,
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Cross-tenant isolation                                                       #
# --------------------------------------------------------------------------- #


async def test_cross_tenant_thread_access_404(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="hi",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])

    _ou, _oorg, other_partner = await make_partner(db_session, display_name="Other")
    with pytest.raises(ResourceNotFoundError):
        await thread_service.get_thread(db_session, principal=other_partner, thread_id=thread_id)
    with pytest.raises(ResourceNotFoundError):
        await message_service.send_message(
            db_session,
            principal=other_partner,
            thread_id=thread_id,
            body="x",
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Mute / report                                                                #
# --------------------------------------------------------------------------- #


async def test_mute_suppresses_notification(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    await message_service.set_mute(db_session, principal=student, thread_id=thread_id, muted=True)
    await message_service.send_message(
        db_session,
        principal=partner,
        thread_id=thread_id,
        body="hello",
        ctx=CTX,
    )
    feed_rows = (
        await db_session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == student_user.id,
                Notification.notif_type == "message.received",
            )
        )
    ).scalar_one()
    assert feed_rows == 0


async def test_report_audits_and_notifies_university(db_session) -> None:
    student_user, student = await make_student(db_session)
    uni_user, _uorg, _uni = await make_university(db_session)
    created = await thread_service.create_thread(
        db_session,
        principal=student,
        kind="direct",
        context_type="support",
        context_id=None,
        recipient_ids=[uni_user.id],
        first_message="help",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    out = await message_service.report_thread(
        db_session,
        principal=student,
        thread_id=thread_id,
        reason="spam",
        ctx=CTX,
    )
    assert out["status"] == "reported"
    audit = (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "messaging.report")
        )
    ).scalar_one()
    assert audit == 1
    flagged = (
        await db_session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == uni_user.id,
                Notification.notif_type == "message.flagged",
            )
        )
    ).scalar_one()
    assert flagged == 1


# --------------------------------------------------------------------------- #
# Unread / mark-read                                                           #
# --------------------------------------------------------------------------- #


async def test_unread_count_and_mark_read(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    created = await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message="hello",
        ctx=CTX,
    )
    thread_id = uuid.UUID(created["id"])
    assert await message_service.unread_count(db_session, principal=student) == 1
    await message_service.mark_read(db_session, principal=student, thread_id=thread_id)
    assert await message_service.unread_count(db_session, principal=student) == 0


# --------------------------------------------------------------------------- #
# PII-safe audit                                                               #
# --------------------------------------------------------------------------- #


async def test_audit_carries_no_pii(db_session) -> None:
    student_user, student = await make_student(db_session)
    _pu, porg, partner = await make_partner(db_session)
    app_id = await seed_application(db_session, org_id=porg.id, applicant_id=student_user.id)
    secret_body = "My phone is 0900111222 secret"
    await thread_service.create_thread(
        db_session,
        principal=partner,
        kind="direct",
        context_type="application",
        context_id=app_id,
        recipient_ids=[student_user.id],
        first_message=secret_body,
        ctx=CTX,
    )
    rows = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "messaging.message.send")
            )
        )
        .scalars()
        .all()
    )
    assert rows
    for row in rows:
        blob = json.dumps(row.after_snapshot or {}, ensure_ascii=False)
        assert secret_body not in blob
        assert student_user.email not in blob
        assert "body" not in (row.after_snapshot or {})
