"""Student interview response + applications-list status attachment tests.

Covers the two student-experience-completion themes owned by recruitment:

- THEME C — ``list_my_applications`` batch-attaches the SAME identity-safe
  ``upcoming_interview`` / ``offer`` cards + server ``next_action`` the DETAIL path
  exposes (previously list rows always read empty), with no N+1 (one query per
  related entity for the whole page).
- THEME D — a student can respond to THEIR interview
  (``confirm | decline | request_reschedule``): owner-only (non-owner -> 404),
  idempotent replay, conflicting-response 409, past/cancelled 409, optimistic
  version guard, reschedule resets the response, a truthful student timeline
  event + audit, and a masked partner notification (outbox + feed).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.db import get_engine
from app.modules.documents.application import snapshot_service
from app.modules.notifications.domain.models import Notification, NotificationOutbox
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    interview_service,
    offer_service,
)
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    InterviewNotRespondableError,
    InterviewResponseConflictError,
    InvalidApplicationFieldError,
)
from app.modules.recruitment.domain import interview as interview_domain
from app.modules.recruitment.domain import timeline
from app.modules.recruitment.domain.models import Interview
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import event, func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


def _now() -> datetime:
    return datetime.now(tz=UTC)


# --------------------------------------------------------------------------- #
# Setup helpers                                                               #
# --------------------------------------------------------------------------- #


async def _assignee(db, org):
    _u, _m, principal = await add_member(
        db,
        org=org,
        permissions=[
            ("applications", "read"),
            ("interviews", "schedule"),
            ("interviews", "assign"),
            ("interviews", "complete"),
            ("interviews", "cancel"),
            ("interviews", "read"),
        ],
    )
    return principal


async def _reviewed_app(db, *, partner, uni, student, title):
    """Publish a job, apply as ``student``, review -> under_review; return app_id."""

    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title
    )
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db, principal=partner, application_id=app_id, ctx=CTX
    )
    return app_id


async def _schedule(db, *, partner, assignee, app_id, at=None):
    out = await interview_service.schedule_interview(
        db, principal=partner, application_id=app_id,
        mode="online", scheduled_at=at or (_now() + timedelta(days=2)),
        assignee_ids=[assignee.user_id], meeting_link="https://meet.example/abc",
        ctx=CTX,
    )
    return uuid.UUID(out["id"]), out


async def _sent_offer(db, *, partner, app_id):
    out = await offer_service.create_offer(
        db, principal=partner, application_id=app_id,
        position_title="Backend Engineer", expiry_date=_now() + timedelta(days=7),
        salary_amount=25_000_000, ctx=CTX,
    )
    oid = uuid.UUID(out["id"])
    await offer_service.submit_offer(db, principal=partner, offer_id=oid, ctx=CTX)
    await offer_service.approve_offer(
        db, principal=partner, offer_id=oid, decision="approve", ctx=CTX
    )
    return await offer_service.send_offer(db, principal=partner, offer_id=oid, ctx=CTX)


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _responded_outbox_count(db) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(NotificationOutbox).where(
                NotificationOutbox.template_key
                == "application.interview_candidate_responded"
            )
        )
    ).scalar_one()


async def _responded_feed(db) -> list[Notification]:
    return list(
        (
            await db.execute(
                select(Notification).where(
                    Notification.notif_type
                    == "recruitment.interview_candidate_responded"
                )
            )
        ).scalars().all()
    )


# --------------------------------------------------------------------------- #
# THEME D — student respond happy paths                                       #
# --------------------------------------------------------------------------- #


async def test_confirm_happy_path_records_response_timeline_and_notifies(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _sched = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )

    out = await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_id, interview_id=iv_id,
        action="confirm", ctx=CTX,
    )
    assert out["candidate_response"] == interview_domain.CANDIDATE_RESPONSE_CONFIRMED
    assert out["candidate_response_label"]  # localized, never a raw code
    assert out["candidate_responded_at"] is not None

    # Audit + truthful student timeline event.
    assert (
        await _audit_count(db_session, "application.interview_candidate_responded") == 1
    )
    view = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    types = [e["event_type"] for e in view["timeline"]]
    assert timeline.INTERVIEW_CONFIRMED in types

    # Masked partner notification: outbox (created_by + assignee) + in-app feed,
    # and NEVER the student's identity.
    assert await _responded_outbox_count(db_session) >= 1
    feed = await _responded_feed(db_session)
    assert feed
    for row in feed:
        assert su.email not in (row.body or "")
        assert str(student.user_id) not in (row.body or "")


async def test_decline_and_request_reschedule_persist(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    assignee = await _assignee(db_session, porg)

    app_a = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    iv_a, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_a
    )
    declined = await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_a, interview_id=iv_a,
        action="decline", note="I accepted another offer.", ctx=CTX,
    )
    assert declined["candidate_response"] == interview_domain.CANDIDATE_RESPONSE_DECLINED

    app_b = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job B"
    )
    iv_b, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_b
    )
    resched = await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_b, interview_id=iv_b,
        action="request_reschedule", note="Tuesday does not work for me.", ctx=CTX,
    )
    assert (
        resched["candidate_response"]
        == interview_domain.CANDIDATE_RESPONSE_RESCHEDULE
    )
    # The student's note is persisted on the row (partner-visible).
    row = (
        await db_session.execute(select(Interview).where(Interview.id == iv_b))
    ).scalar_one()
    assert row.candidate_response_note == "Tuesday does not work for me."


async def test_invalid_action_is_422(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    with pytest.raises(InvalidApplicationFieldError):
        await interview_service.respond_to_interview(
            db_session, principal=student, application_id=app_id, interview_id=iv_id,
            action="maybe", ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# THEME D — owner scoping / idempotency / conflict / state / version          #
# --------------------------------------------------------------------------- #


async def test_non_owner_respond_is_404(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="owner")
    _su2, other = await make_student(db_session, prefix="intruder")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    # A non-owner student cannot even tell the interview exists.
    with pytest.raises(ResourceNotFoundError):
        await interview_service.respond_to_interview(
            db_session, principal=other, application_id=app_id, interview_id=iv_id,
            action="confirm", ctx=CTX,
        )


async def test_double_confirm_is_idempotent(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    first = await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_id, interview_id=iv_id,
        action="confirm", ctx=CTX,
    )
    second = await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_id, interview_id=iv_id,
        action="confirm", ctx=CTX,
    )
    assert second["candidate_response"] == first["candidate_response"]
    # No second write: exactly one audit + one confirmed timeline event.
    assert (
        await _audit_count(db_session, "application.interview_candidate_responded") == 1
    )
    view = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    types = [e["event_type"] for e in view["timeline"]]
    assert types.count(timeline.INTERVIEW_CONFIRMED) == 1


async def test_conflicting_response_is_409(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_id, interview_id=iv_id,
        action="confirm", ctx=CTX,
    )
    with pytest.raises(InterviewResponseConflictError) as exc:
        await interview_service.respond_to_interview(
            db_session, principal=student, application_id=app_id, interview_id=iv_id,
            action="decline", ctx=CTX,
        )
    assert exc.value.details["reason"] == "interview_response_conflict"
    assert (
        exc.value.details["current_response"]
        == interview_domain.CANDIDATE_RESPONSE_CONFIRMED
    )


async def test_respond_to_past_interview_is_409(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    # Move the interview into the past.
    row = (
        await db_session.execute(select(Interview).where(Interview.id == iv_id))
    ).scalar_one()
    row.scheduled_at = _now() - timedelta(hours=1)
    await db_session.commit()
    with pytest.raises(InterviewNotRespondableError) as exc:
        await interview_service.respond_to_interview(
            db_session, principal=student, application_id=app_id, interview_id=iv_id,
            action="confirm", ctx=CTX,
        )
    assert exc.value.details == {"reason": "interview_not_respondable"}


async def test_respond_to_cancelled_interview_is_409(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    await interview_service.cancel_interview(
        db_session, principal=partner, application_id=app_id, interview_id=iv_id,
        ctx=CTX,
    )
    with pytest.raises(InterviewNotRespondableError):
        await interview_service.respond_to_interview(
            db_session, principal=student, application_id=app_id, interview_id=iv_id,
            action="confirm", ctx=CTX,
        )


async def test_version_conflict_is_409(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, sched = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    with pytest.raises(ApplicationVersionConflictError):
        await interview_service.respond_to_interview(
            db_session, principal=student, application_id=app_id, interview_id=iv_id,
            action="confirm", version=sched["version"] + 99, ctx=CTX,
        )


async def test_reschedule_resets_candidate_response(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _sched = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    confirmed = await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_id, interview_id=iv_id,
        action="confirm", ctx=CTX,
    )
    # respond bumps the optimistic version off the schedule baseline.
    assert confirmed["candidate_response"] is not None
    # Partner reschedules (using the CURRENT version) -> stale confirmation cleared.
    resched = await interview_service.reschedule_interview(
        db_session, principal=partner, application_id=app_id, interview_id=iv_id,
        scheduled_at=_now() + timedelta(days=5), ctx=CTX,
    )
    assert resched["candidate_response"] is None
    # The student can respond again to the new time.
    again = await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_id, interview_id=iv_id,
        action="confirm", ctx=CTX,
    )
    assert again["candidate_response"] == interview_domain.CANDIDATE_RESPONSE_CONFIRMED


async def test_student_detail_surfaces_candidate_response(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    app_id = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Job A"
    )
    assignee = await _assignee(db_session, porg)
    iv_id, _ = await _schedule(
        db_session, partner=partner, assignee=assignee, app_id=app_id
    )
    await interview_service.respond_to_interview(
        db_session, principal=student, application_id=app_id, interview_id=iv_id,
        action="confirm", ctx=CTX,
    )
    view = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    card = view["upcoming_interview"]
    assert card is not None
    assert card["candidate_response"] == interview_domain.CANDIDATE_RESPONSE_CONFIRMED
    assert card["candidate_responded_at"] is not None


# --------------------------------------------------------------------------- #
# THEME C — list attaches interview / offer / next_action (no N+1)            #
# --------------------------------------------------------------------------- #


async def test_list_attaches_interview_offer_next_action(db_session):
    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    assignee = await _assignee(db_session, porg)

    # app_iv: reviewed + scheduled interview.
    app_iv = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Interview Job"
    )
    await _schedule(db_session, partner=partner, assignee=assignee, app_id=app_iv)

    # app_offer: reviewed + a SENT offer.
    app_offer = await _reviewed_app(
        db_session, partner=partner, uni=uni, student=student, title="Offer Job"
    )
    await _sent_offer(db_session, partner=partner, app_id=app_offer)

    # app_plain: submitted only.
    job_plain = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Plain Job"
    )
    sel = await make_builder_cv(db_session, student=student)
    plain = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_plain, cv_selection=sel), ctx=CTX,
    )
    app_plain = uuid.UUID(plain["id"])

    items, _cursor, _limit = await apply_service.list_my_applications(
        db_session, principal=student
    )
    by_id = {uuid.UUID(i["id"]): i for i in items}

    iv_row = by_id[app_iv]
    assert iv_row["upcoming_interview"] is not None
    assert iv_row["offer"] is None
    assert iv_row["next_action"] == timeline.NEXT_PREPARE_FOR_INTERVIEW

    offer_row = by_id[app_offer]
    assert offer_row["offer"] is not None
    assert offer_row["offer"]["status"] == "sent"
    assert offer_row["upcoming_interview"] is None
    assert offer_row["next_action"] == timeline.NEXT_RESPOND_TO_OFFER

    plain_row = by_id[app_plain]
    assert plain_row["upcoming_interview"] is None
    assert plain_row["offer"] is None
    assert plain_row["next_action"] == timeline.NEXT_AWAIT_REVIEW


async def test_list_batch_is_not_n_plus_1(db_session):
    """A page with N apps issues exactly ONE interviews query + ONE offers query."""

    _pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session, prefix="student")
    assignee = await _assignee(db_session, porg)

    # 3 applications, each with a scheduled interview + a sent offer, so both
    # batch paths have real rows to map across the page.
    for i in range(3):
        app_id = await _reviewed_app(
            db_session, partner=partner, uni=uni, student=student, title=f"Job {i}"
        )
        await _schedule(db_session, partner=partner, assignee=assignee, app_id=app_id)
        await _sent_offer(db_session, partner=partner, app_id=app_id)

    counts = {"interviews": 0, "offers": 0}

    def _count(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "from interviews" in low:
            counts["interviews"] += 1
        if "from offers" in low:
            counts["offers"] += 1

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", _count)
    try:
        items, _cursor, _limit = await apply_service.list_my_applications(
            db_session, principal=student
        )
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert len(items) == 3
    # Batched: one query for the whole page per related entity (no per-row read).
    assert counts["interviews"] == 1
    assert counts["offers"] == 1
    for row in items:
        assert row["upcoming_interview"] is not None
        assert row["offer"] is not None
