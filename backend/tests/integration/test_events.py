"""Events module tests (ADR-0008 §8/§9 first slice).

Covers: organizer create -> submit -> moderate -> publish; university auto-publish;
public visibility + enumeration hiding; registration (confirmed/waitlist/capacity/
deadline/duplicate/re-register); FIFO inline promotion + waitlist position; guest
401; cross-org 404; check-in (organizer + university, unauthorized 404); attendee
PII rule (email only to organizer, never in audit); moderation reject; marketplace
events integration (real + hide-if-empty); the four scheduler sweeps via tick();
audit-per-write; optimistic version + illegal transitions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.automation.scheduler import runner
from app.modules.marketplace.application import overview_service
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.opportunities.application import (
    event_moderation_service,
    event_service,
    registration_service,
)
from app.modules.opportunities.application.event_errors import (
    EventNotOpenError,
    EventVersionConflictError,
    IllegalEventTransitionError,
    RegistrationClosedError,
)
from app.modules.opportunities.domain import event_lifecycle
from app.modules.opportunities.domain.event_models import Event, EventRegistration
from app.shared.exceptions import (
    AuthRequiredError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.models import AuditLog
from app.shared.permissions import GUEST
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.events_utils import event_payload, publish_event
from tests.org_utils import make_org_with_admin


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _set_event(db, event_id: uuid.UUID, **fields) -> None:
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one()
    for k, v in fields.items():
        setattr(event, k, v)
    db.add(event)
    await db.commit()


# --------------------------------------------------------------------------- #
# Lifecycle + moderation                                                      #
# --------------------------------------------------------------------------- #


async def test_create_submit_moderate_publish(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    created = await event_service.create_event(
        db_session, principal=organizer, payload=event_payload(), ctx=CTX
    )
    assert created["status"] == "draft"
    assert created["status_label"]  # localized, never raw-only

    submitted = await event_service.submit_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert submitted["status"] == "pending_review"

    approved = await event_moderation_service.approve_event(
        db_session, principal=uni, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert approved["status"] == "published"

    # Organizer notified (outbox row to the creator).
    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "event.approved"
            )
        )
    ).scalars().all()
    assert len(outbox) == 1


async def test_university_created_event_auto_publishes(db_session) -> None:
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    created = await event_service.create_event(
        db_session, principal=uni, payload=event_payload(title="VinUni Talk"), ctx=CTX
    )
    submitted = await event_service.submit_event(
        db_session, principal=uni, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    # University submit auto-approves: straight to published.
    assert submitted["status"] == "published"
    assert submitted["moderation_status"] == "approved"
    detail = await event_service.get_event(
        db_session, principal=GUEST, event_id=uuid.UUID(created["id"])
    )
    assert detail["id"] == created["id"]


async def test_public_list_only_visible_events(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    draft = await event_service.create_event(
        db_session, principal=organizer, payload=event_payload("Draft Event"), ctx=CTX
    )
    live_id = await publish_event(db_session, organizer, uni, title="Live Event")
    # A published-but-past event must drop out of discovery.
    past_id = await publish_event(db_session, organizer, uni, title="Past Event")
    await _set_event(
        db_session, past_id,
        starts_at=_now() - timedelta(days=2), ends_at=_now() - timedelta(days=1),
    )

    items, _next, _limit, total = await event_service.list_public_events(
        db_session, principal=GUEST
    )
    assert total == 1
    assert [i["id"] for i in items] == [str(live_id)]

    # Public detail leaks no moderation fields.
    detail = await event_service.get_event(
        db_session, principal=GUEST, event_id=live_id
    )
    assert "moderation_note" not in detail
    assert "moderation_status" not in detail

    # Draft hidden from guests -> 404 (enumeration hiding).
    with pytest.raises(ResourceNotFoundError):
        await event_service.get_event(
            db_session, principal=GUEST, event_id=uuid.UUID(draft["id"])
        )


async def test_moderation_reject_then_resubmit(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    created = await event_service.create_event(
        db_session, principal=organizer, payload=event_payload(), ctx=CTX
    )
    await event_service.submit_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    rejected = await event_moderation_service.reject_event(
        db_session, principal=uni, event_id=uuid.UUID(created["id"]),
        reason="Mô tả sự kiện chưa rõ ràng.", ctx=CTX,
    )
    assert rejected["status"] == "rejected"
    # Editable again, then resubmittable.
    await event_service.update_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]),
        payload={"title": "Career Day 2026 (revised)"}, ctx=CTX,
    )
    resubmitted = await event_service.submit_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert resubmitted["status"] == "pending_review"


async def test_moderation_request_changes_returns_event_to_draft(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    created = await event_service.create_event(
        db_session, principal=organizer, payload=event_payload(), ctx=CTX
    )
    await event_service.submit_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )

    result = await event_moderation_service.request_changes_event(
        db_session, principal=uni, event_id=uuid.UUID(created["id"]),
        reason="Vui lòng bổ sung địa điểm và sức chứa.", ctx=CTX,
    )
    assert result["status"] == "draft"
    assert result["moderation_status"] == "changes_requested"

    # Leaves the moderation queue.
    items, _total = await event_moderation_service.list_moderation_queue(
        db_session, principal=uni
    )
    assert all(row["id"] != created["id"] for row in items)

    # Organizer notified via the changes-requested template.
    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "event.changes_requested"
            )
        )
    ).scalars().all()
    assert len(outbox) == 1

    # Revise + resubmit re-enters review.
    await event_service.update_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]),
        payload={"title": "Career Day 2026 (revised)"}, ctx=CTX,
    )
    resubmitted = await event_service.submit_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert resubmitted["status"] == "pending_review"


async def test_partner_admin_cannot_moderate(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    created = await event_service.create_event(
        db_session, principal=organizer, payload=event_payload(), ctx=CTX
    )
    await event_service.submit_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    with pytest.raises(PermissionDeniedError):
        await event_moderation_service.approve_event(
            db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
        )


async def test_optimistic_version_and_illegal_transition(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    created = await event_service.create_event(
        db_session, principal=organizer, payload=event_payload(), ctx=CTX
    )
    with pytest.raises(EventVersionConflictError):
        await event_service.update_event(
            db_session, principal=organizer, event_id=uuid.UUID(created["id"]),
            payload={"title": "Race", "version": 999}, ctx=CTX,
        )
    # Cancel from draft is illegal.
    with pytest.raises(IllegalEventTransitionError):
        await event_service.cancel_event(
            db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Registration                                                                #
# --------------------------------------------------------------------------- #


async def test_register_confirmed(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _su, student = await make_student(db_session)

    res = await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    assert res["status"] == "confirmed"
    assert res["status_label"]

    # registration_count mirrors confirmed.
    event = (await db_session.execute(select(Event).where(Event.id == event_id))).scalar_one()
    assert event.registration_count == 1


async def test_register_guest_401(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    with pytest.raises(AuthRequiredError):
        await registration_service.register(
            db_session, principal=GUEST, event_id=event_id, ctx=CTX
        )


async def test_register_past_deadline_409(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    # Registration closed in the past, event still upcoming.
    event_id = await publish_event(
        db_session, organizer, uni,
        starts_at=_now() + timedelta(days=3),
        registration_closes_at=_now() - timedelta(hours=1),
    )
    _su, student = await make_student(db_session)
    with pytest.raises(RegistrationClosedError):
        await registration_service.register(
            db_session, principal=student, event_id=event_id, ctx=CTX
        )


async def test_register_cancelled_event_409(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    await event_service.cancel_event(
        db_session, principal=organizer, event_id=event_id, ctx=CTX
    )
    _su, student = await make_student(db_session)
    with pytest.raises(EventNotOpenError):
        await registration_service.register(
            db_session, principal=student, event_id=event_id, ctx=CTX
        )


async def test_duplicate_active_registration_is_idempotent(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _su, student = await make_student(db_session)

    first = await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    second = await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    assert first["registration_id"] == second["registration_id"]
    # No duplicate active row created (partial-unique guarantee on PG; service guard here).
    count = (
        await db_session.execute(
            select(func.count()).select_from(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == student.user_id,
                EventRegistration.status != "cancelled",
            )
        )
    ).scalar_one()
    assert count == 1


async def test_capacity_last_seat_one_confirmed_one_waitlisted(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni, capacity=1)
    _sa, student_a = await make_student(db_session, prefix="a")
    _sb, student_b = await make_student(db_session, prefix="b")

    res_a = await registration_service.register(
        db_session, principal=student_a, event_id=event_id, ctx=CTX
    )
    res_b = await registration_service.register(
        db_session, principal=student_b, event_id=event_id, ctx=CTX
    )
    statuses = {res_a["status"], res_b["status"]}
    assert statuses == {"confirmed", "waitlisted"}
    # Exactly one confirmed — no overbooking (count + capacity guard).
    confirmed_n = (
        await db_session.execute(
            select(func.count()).select_from(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.status == "confirmed",
            )
        )
    ).scalar_one()
    assert confirmed_n == 1
    # Waitlisted row carries a 1-based position.
    waitlisted = res_a if res_a["status"] == "waitlisted" else res_b
    assert waitlisted["waitlist_position"] == 1


async def test_cancel_confirmed_promotes_waitlist_head_fifo(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni, capacity=1)
    _sa, student_a = await make_student(db_session, prefix="a")
    _sb, student_b = await make_student(db_session, prefix="b")
    _sc, student_c = await make_student(db_session, prefix="c")

    await registration_service.register(
        db_session, principal=student_a, event_id=event_id, ctx=CTX
    )  # confirmed
    await registration_service.register(
        db_session, principal=student_b, event_id=event_id, ctx=CTX
    )  # waitlisted (head)
    await registration_service.register(
        db_session, principal=student_c, event_id=event_id, ctx=CTX
    )  # waitlisted

    # Cancelling A frees the seat -> B (FIFO head) is promoted inline.
    await registration_service.cancel_registration(
        db_session, principal=student_a, event_id=event_id, ctx=CTX
    )

    rows = (
        await db_session.execute(
            select(EventRegistration).where(EventRegistration.event_id == event_id)
        )
    ).scalars().all()
    by_user = {r.user_id: r.status for r in rows}
    assert by_user[student_a.user_id] == "cancelled"
    assert by_user[student_b.user_id] == "confirmed"  # promoted
    assert by_user[student_c.user_id] == "waitlisted"  # still waiting

    # Promotion was audited + notified.
    assert await _audit_count(db_session, "event.waitlist_promoted") == 1


async def test_cancelled_then_reregister_allowed(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _su, student = await make_student(db_session)

    await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    await registration_service.cancel_registration(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    # A cancelled row does not block a fresh registration.
    again = await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    assert again["status"] == "confirmed"


async def test_my_registrations_lists_active(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _su, student = await make_student(db_session)
    await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    mine = await registration_service.my_registrations(db_session, principal=student)
    assert len(mine) == 1
    assert mine[0]["event"]["id"] == str(event_id)
    assert mine[0]["status"] == "confirmed"


# --------------------------------------------------------------------------- #
# Check-in + attendee PII                                                      #
# --------------------------------------------------------------------------- #


async def test_check_in_marks_attended_organizer_and_university(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _sa, student_a = await make_student(db_session, prefix="a")
    _sb, student_b = await make_student(db_session, prefix="b")
    reg_a = await registration_service.register(
        db_session, principal=student_a, event_id=event_id, ctx=CTX
    )
    reg_b = await registration_service.register(
        db_session, principal=student_b, event_id=event_id, ctx=CTX
    )

    # Organizer checks one in.
    res = await registration_service.check_in(
        db_session, principal=organizer, event_id=event_id,
        registration_id=uuid.UUID(reg_a["registration_id"]), ctx=CTX,
    )
    assert res["status"] == "attended"
    # Idempotent re-check-in.
    res2 = await registration_service.check_in(
        db_session, principal=organizer, event_id=event_id,
        registration_id=uuid.UUID(reg_a["registration_id"]), ctx=CTX,
    )
    assert res2["status"] == "attended"

    # University moderator can also check in.
    res3 = await registration_service.check_in(
        db_session, principal=uni, event_id=event_id,
        registration_id=uuid.UUID(reg_b["registration_id"]), ctx=CTX,
    )
    assert res3["status"] == "attended"


async def test_check_in_unauthorized_cross_org_404(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _ou, _oorg, other = await make_org_with_admin(db_session, display_name="Other Co")
    event_id = await publish_event(db_session, organizer, uni)
    _su, student = await make_student(db_session)
    reg = await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    # A different partner org -> 404 (enumeration hiding).
    with pytest.raises(ResourceNotFoundError):
        await registration_service.check_in(
            db_session, principal=other, event_id=event_id,
            registration_id=uuid.UUID(reg["registration_id"]), ctx=CTX,
        )
    # A student is not staff -> 404.
    with pytest.raises(ResourceNotFoundError):
        await registration_service.check_in(
            db_session, principal=student, event_id=event_id,
            registration_id=uuid.UUID(reg["registration_id"]), ctx=CTX,
        )


async def test_cross_org_event_and_attendee_list_404(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _ou, _oorg, other = await make_org_with_admin(db_session, display_name="Other Co")
    created = await event_service.create_event(
        db_session, principal=organizer, payload=event_payload(), ctx=CTX
    )
    with pytest.raises(ResourceNotFoundError):
        await event_service.get_event(
            db_session, principal=other, event_id=uuid.UUID(created["id"])
        )
    with pytest.raises(ResourceNotFoundError):
        await registration_service.list_attendees(
            db_session, principal=other, event_id=uuid.UUID(created["id"])
        )


async def test_attendee_list_pii_email_only_for_organizer(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    su, student = await make_student(db_session)
    await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )

    # Organizer sees the email.
    org_view = await registration_service.list_attendees(
        db_session, principal=organizer, event_id=event_id
    )
    assert len(org_view) == 1
    assert org_view[0]["email"] == su.email

    # University staff sees the list but NOT the email.
    uni_view = await registration_service.list_attendees(
        db_session, principal=uni, event_id=event_id
    )
    assert len(uni_view) == 1
    assert "email" not in uni_view[0]

    # No audit/log row for the registration carries an email (PII-safe snapshots).
    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "event.registered")
        )
    ).scalars().all()
    assert rows
    for row in rows:
        snapshot = (row.after_snapshot or {})
        assert su.email not in str(snapshot)
        assert set(snapshot.keys()) <= {"event_id", "user_id", "status"}


# --------------------------------------------------------------------------- #
# Marketplace integration                                                      #
# --------------------------------------------------------------------------- #


async def test_marketplace_overview_includes_events_and_hides_empty(db_session) -> None:
    # Empty: all three event arrays empty (section hides; never fabricated).
    empty = await overview_service.get_overview(db_session)
    assert empty["upcoming_events"] == []
    assert empty["sponsored_events"] == []
    assert empty["featured_events"] == []

    _u, partner, organizer = await make_org_with_admin(db_session, display_name="Acme Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    sponsored_id = await publish_event(db_session, organizer, uni, title="Sponsored Day")
    featured_id = await publish_event(db_session, organizer, uni, title="Featured Day")
    await publish_event(db_session, organizer, uni, title="Plain Day")
    await _set_event(db_session, sponsored_id, is_sponsored=True)
    await _set_event(db_session, featured_id, is_featured=True)

    data = await overview_service.get_overview(db_session)
    assert {e["title"] for e in data["sponsored_events"]} == {"Sponsored Day"}
    assert {e["title"] for e in data["featured_events"]} == {"Featured Day"}
    assert len(data["upcoming_events"]) == 3
    # Each event row carries the organizer company block.
    assert data["upcoming_events"][0]["company"]["slug"] == partner.slug


# --------------------------------------------------------------------------- #
# Scheduler sweeps (driven via tick(), proving they run as scheduled)          #
# --------------------------------------------------------------------------- #


async def test_reminder_sweep_dedupes_no_double_send(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(
        db_session, organizer, uni, starts_at=_now() + timedelta(hours=12)
    )
    _su, student = await make_student(db_session)
    await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )

    await runner.tick(only={"events.reminder_sweep"})
    await runner.tick(only={"events.reminder_sweep"})  # second tick must not re-send

    sent = (
        await db_session.execute(
            select(func.count()).select_from(NotificationOutbox).where(
                NotificationOutbox.template_key == "event.reminder"
            )
        )
    ).scalar_one()
    assert sent == 1


async def test_reminder_sweep_soon_dedupes_no_double_send(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(
        db_session, organizer, uni, starts_at=_now() + timedelta(minutes=30)
    )
    _su, student = await make_student(db_session)
    await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )

    await runner.tick(only={"events.reminder_sweep_soon"})
    await runner.tick(only={"events.reminder_sweep_soon"})  # second tick: no re-send

    sent = (
        await db_session.execute(
            select(func.count()).select_from(NotificationOutbox).where(
                NotificationOutbox.template_key == "event.reminder_soon"
            )
        )
    ).scalar_one()
    assert sent == 1


async def test_reminder_sweep_and_soon_are_independent(db_session) -> None:
    """A registrant inside BOTH windows (T-24h and T-1h) gets exactly one of each."""

    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(
        db_session, organizer, uni, starts_at=_now() + timedelta(minutes=30)
    )
    _su, student = await make_student(db_session)
    await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )

    await runner.tick(only={"events.reminder_sweep", "events.reminder_sweep_soon"})

    counts = {
        key: (
            await db_session.execute(
                select(func.count()).select_from(NotificationOutbox).where(
                    NotificationOutbox.template_key == key
                )
            )
        ).scalar_one()
        for key in ("event.reminder", "event.reminder_soon")
    }
    assert counts == {"event.reminder": 1, "event.reminder_soon": 1}


async def test_waitlist_backfill_sweep_promotes(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni, capacity=1)
    _sa, student_a = await make_student(db_session, prefix="a")
    _sb, student_b = await make_student(db_session, prefix="b")
    await registration_service.register(
        db_session, principal=student_a, event_id=event_id, ctx=CTX
    )
    await registration_service.register(
        db_session, principal=student_b, event_id=event_id, ctx=CTX
    )  # waitlisted

    # Directly free a seat without inline promotion (simulate a crash mid-cancel).
    reg_a = (
        await db_session.execute(
            select(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == student_a.user_id,
            )
        )
    ).scalar_one()
    reg_a.status = "cancelled"
    event = (await db_session.execute(select(Event).where(Event.id == event_id))).scalar_one()
    event.registration_count = 0
    db_session.add_all([reg_a, event])
    await db_session.commit()

    await runner.tick(only={"events.waitlist_backfill"})

    reg_b = (
        await db_session.execute(
            select(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == student_b.user_id,
            )
        )
    ).scalar_one()
    assert reg_b.status == "confirmed"


async def test_auto_complete_and_no_show_sweeps(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _su, student = await make_student(db_session)
    await registration_service.register(
        db_session, principal=student, event_id=event_id, ctx=CTX
    )
    # Move the event entirely into the past (beyond the no-show grace window).
    await _set_event(
        db_session, event_id,
        starts_at=_now() - timedelta(hours=6), ends_at=_now() - timedelta(hours=5),
    )

    await runner.tick(only={"events.auto_complete"})
    event = (await db_session.execute(select(Event).where(Event.id == event_id))).scalar_one()
    assert event.status == "completed"

    await runner.tick(only={"events.no_show_sweep"})
    reg = (
        await db_session.execute(
            select(EventRegistration).where(EventRegistration.event_id == event_id)
        )
    ).scalar_one()
    assert reg.status == "no_show"

    # Idempotent: a second no-show tick changes nothing.
    await runner.tick(only={"events.no_show_sweep"})
    reg2 = (
        await db_session.execute(
            select(EventRegistration).where(EventRegistration.event_id == event_id)
        )
    ).scalar_one()
    assert reg2.status == "no_show"


# --------------------------------------------------------------------------- #
# Audit per write                                                              #
# --------------------------------------------------------------------------- #


async def test_audit_written_on_every_event_write(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    created = await event_service.create_event(
        db_session, principal=organizer, payload=event_payload(), ctx=CTX
    )
    assert await _audit_count(db_session, "event.created") == 1
    await event_service.submit_event(
        db_session, principal=organizer, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert await _audit_count(db_session, "event.submit") == 1
    await event_moderation_service.approve_event(
        db_session, principal=uni, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert await _audit_count(db_session, "event.approved") == 1

    _su, student = await make_student(db_session)
    await registration_service.register(
        db_session, principal=student, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert await _audit_count(db_session, "event.registered") == 1
    await registration_service.cancel_registration(
        db_session, principal=student, event_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert await _audit_count(db_session, "event.registration_cancelled") == 1


# --------------------------------------------------------------------------- #
# Attendee CSV export (organizer/university, audited, email-masked)            #
# --------------------------------------------------------------------------- #


async def test_export_attendees_organizer_includes_email_and_audits(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _s1u, student1 = await make_student(db_session, prefix="s1")
    _s2u, student2 = await make_student(db_session, prefix="s2")
    for s in (student1, student2):
        await registration_service.register(db_session, principal=s, event_id=event_id, ctx=CTX)

    # Check one attendee in so the export reflects check-in state.
    rows = await registration_service.list_attendees(
        db_session, principal=organizer, event_id=event_id
    )
    await registration_service.check_in(
        db_session, principal=organizer, event_id=event_id,
        registration_id=uuid.UUID(rows[0]["registration_id"]), ctx=CTX,
    )

    data = await registration_service.export_attendees(
        db_session, principal=organizer, event_id=event_id, ctx=CTX,
    )
    assert data["include_email"] is True
    assert data["event_title"]
    assert len(data["attendees"]) == 2
    assert all("email" in row for row in data["attendees"])
    assert any(row["checked_in_at"] for row in data["attendees"])
    assert await _audit_count(db_session, "event.attendees_exported") == 1


async def test_export_attendees_university_masks_email(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _su, student = await make_student(db_session)
    await registration_service.register(db_session, principal=student, event_id=event_id, ctx=CTX)

    data = await registration_service.export_attendees(
        db_session, principal=uni, event_id=event_id, ctx=CTX,
    )
    assert data["include_email"] is False
    assert data["attendees"] and all("email" not in row for row in data["attendees"])


async def test_export_attendees_forbidden_for_registrant(db_session) -> None:
    _u, _org, organizer = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)
    _su, student = await make_student(db_session)
    await registration_service.register(db_session, principal=student, event_id=event_id, ctx=CTX)

    # A non-staff principal cannot even see the roster — enumeration-safe 404
    # (``_load_event_for_staff`` hides existence rather than returning 403).
    with pytest.raises(ResourceNotFoundError):
        await registration_service.export_attendees(
            db_session, principal=student, event_id=event_id, ctx=CTX,
        )
