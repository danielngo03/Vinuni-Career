"""Recruitment interview tests (ADR-0006 first slice).

Covers the interview + reviewer-assignee + threshold layer on the ADR-0004 stage
engine and ADR-0005 scorecards:

- schedule happy path (non-anonymous); reveal precondition on an anonymous app
  (409 ``reveal_required``); anonymous + accepted reveal schedules.
- one OPEN interview per (application, stage) (409 ``interview_exists``); reschedule
  version conflict (409); cancel frees the slot; complete / no_show transitions.
- the assignee set drives the upgraded advance gate: a ``scorecard`` stage with 2
  assignees needs 2 submitted ASSIGNEE scorecards (409 ``scorecard_required
  {submitted, required:2}``); a non-assignee scorecard does NOT count.
- ``score_threshold`` stage: all submitted but avg below threshold -> 409
  ``score_below_threshold {avg_overall, threshold}``; avg >= threshold -> advances.
- ``scorecards.interview_id`` auto-linked on submit; reminder sweep enqueues once per
  window (idempotent via dedupe); cross-org schedule/list -> 404.
- meeting_link encrypted at rest, decrypted only for attendees, absent from the
  board glance and the student projection; anonymity (student projection has no
  assignee / scorecard / gate); audit row per write.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.db import get_sessionmaker
from app.modules.automation.scheduler import runner
from app.modules.documents.application import snapshot_service
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    interview_service,
    reveal_service,
    scorecard_service,
    stage_service,
)
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    InterviewExistsError,
    InterviewNotActionableError,
    InvalidApplicationFieldError,
    RevealRequiredError,
    ScoreBelowThresholdError,
    ScorecardRequiredError,
)
from app.modules.recruitment.domain import interview as interview_domain
from app.modules.recruitment.domain import lifecycle, scorecard
from app.modules.recruitment.domain.models import Interview, PipelineStage, Scorecard
from app.modules.recruitment.infrastructure.meeting_link_crypto import (
    decrypt_meeting_link,
)
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

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
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _scores(*, technical=4, communication=4, culture_fit=4, motivation=4) -> list[dict]:
    return [
        {"criterion_key": "technical", "score": technical},
        {"criterion_key": "communication", "score": communication},
        {"criterion_key": "culture_fit", "score": culture_fit},
        {"criterion_key": "motivation", "score": motivation},
    ]


async def _setup_reviewed(db, *, is_anonymous=False):
    """Published job + applied + reviewed (candidate ACTIVE at stage 1)."""

    _pu, porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=partner, uni_principal=uni)

    su, student = await make_student(db, prefix="student")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=is_anonymous),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db, principal=partner, application_id=app_id, ctx=CTX
    )
    return porg, partner, su, student, job_id, app_id


async def _current_stage(db, app_id) -> PipelineStage:
    active = await stage_service._active_stage(db, application_id=app_id)
    assert active is not None
    return (
        await db.execute(select(PipelineStage).where(PipelineStage.id == active.stage_id))
    ).scalar_one()


async def _set_current_action(db, app_id, action: str, *, threshold=None) -> None:
    stage = await _current_stage(db, app_id)
    stage.required_action = action
    if threshold is not None:
        stage.score_threshold = threshold
    await db.commit()


async def _assignee(db, org):
    _u, _m, principal = await add_member(
        db,
        org=org,
        permissions=[
            ("applications", "read"),
            ("scorecards", "submit"),
            ("scorecards", "read"),
            ("interviews", "schedule"),
            ("interviews", "assign"),
            ("interviews", "complete"),
            ("interviews", "cancel"),
            ("interviews", "read"),
        ],
    )
    return principal


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _accept_reveal(db, *, partner, student, app_id) -> None:
    await reveal_service.request_reveal(
        db, principal=partner, application_id=app_id,
        reason="We would like to schedule an interview and learn more about you.",
        ctx=CTX,
    )
    await reveal_service.respond_reveal(
        db, principal=student, application_id=app_id,
        decision=lifecycle.REVEAL_ACCEPTED, ctx=CTX,
    )


def _online(*, assignees: list[uuid.UUID], at=None, link="https://meet.example/abc") -> dict:
    return {
        "mode": "online",
        "scheduled_at": at or (_now() + timedelta(days=2)),
        "assignee_ids": assignees,
        "meeting_link": link,
    }


# --------------------------------------------------------------------------- #
# Schedule + reveal precondition                                              #
# --------------------------------------------------------------------------- #


async def test_schedule_non_anonymous_ok(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    assignee = await _assignee(db_session, org)

    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[assignee.user_id]), ctx=CTX,
    )
    assert out["status"] == interview_domain.STATUS_SCHEDULED
    assert out["mode"] == "online"
    assert len(out["assignees"]) == 1
    # The scheduler (partner admin) is NOT an attendee -> link withheld.
    assert out["meeting_link"] is None
    assert await _audit_count(db_session, "application.interview_scheduled") == 1


async def test_schedule_anonymous_without_reveal_is_409_reveal_required(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(
        db_session, is_anonymous=True
    )
    assignee = await _assignee(db_session, org)
    with pytest.raises(RevealRequiredError) as exc:
        await interview_service.schedule_interview(
            db_session, principal=partner, application_id=app_id,
            **_online(assignees=[assignee.user_id]), ctx=CTX,
        )
    assert exc.value.details == {"reason": "reveal_required"}


async def test_schedule_anonymous_after_accepted_reveal_ok(db_session) -> None:
    org, partner, _su, student, _job, app_id = await _setup_reviewed(
        db_session, is_anonymous=True
    )
    assignee = await _assignee(db_session, org)
    await _accept_reveal(db_session, partner=partner, student=student, app_id=app_id)

    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[assignee.user_id]), ctx=CTX,
    )
    assert out["status"] == interview_domain.STATUS_SCHEDULED


async def test_online_requires_link_onsite_requires_location_422(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    assignee = await _assignee(db_session, org)
    with pytest.raises(InvalidApplicationFieldError):
        await interview_service.schedule_interview(
            db_session, principal=partner, application_id=app_id,
            mode="online", scheduled_at=_now() + timedelta(days=1),
            assignee_ids=[assignee.user_id], meeting_link=None, ctx=CTX,
        )
    with pytest.raises(InvalidApplicationFieldError):
        await interview_service.schedule_interview(
            db_session, principal=partner, application_id=app_id,
            mode="onsite", scheduled_at=_now() + timedelta(days=1),
            assignee_ids=[assignee.user_id], location=None, ctx=CTX,
        )


async def test_assignee_must_be_org_member_422(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    _bu, _borg, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    with pytest.raises(InvalidApplicationFieldError):
        await interview_service.schedule_interview(
            db_session, principal=partner, application_id=app_id,
            **_online(assignees=[partner_b.user_id]), ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Open-interview uniqueness / reschedule / cancel / complete                  #
# --------------------------------------------------------------------------- #


async def test_second_open_interview_is_409_interview_exists(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    assignee = await _assignee(db_session, org)
    await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[assignee.user_id]), ctx=CTX,
    )
    with pytest.raises(InterviewExistsError) as exc:
        await interview_service.schedule_interview(
            db_session, principal=partner, application_id=app_id,
            **_online(assignees=[assignee.user_id]), ctx=CTX,
        )
    assert exc.value.details == {"reason": "interview_exists"}


async def test_reschedule_version_conflict_is_409(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    assignee = await _assignee(db_session, org)
    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[assignee.user_id]), ctx=CTX,
    )
    iv_id = uuid.UUID(out["id"])
    with pytest.raises(ApplicationVersionConflictError):
        await interview_service.reschedule_interview(
            db_session, principal=partner, application_id=app_id, interview_id=iv_id,
            scheduled_at=_now() + timedelta(days=5), version=999, ctx=CTX,
        )
    # Correct version bumps it + re-notifies + audits.
    ok = await interview_service.reschedule_interview(
        db_session, principal=partner, application_id=app_id, interview_id=iv_id,
        scheduled_at=_now() + timedelta(days=5), version=out["version"], ctx=CTX,
    )
    assert ok["version"] == out["version"] + 1
    assert await _audit_count(db_session, "application.interview_rescheduled") == 1


async def test_interview_reschedule_success_emits_timeline_and_notification(
    db_session,
) -> None:
    from app.modules.recruitment.application import apply_service

    org, partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    assignee = await _assignee(db_session, org)
    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[assignee.user_id]), ctx=CTX,
    )
    iv_id = uuid.UUID(out["id"])

    new_time = _now() + timedelta(days=3)
    ok = await interview_service.reschedule_interview(
        db_session, principal=partner, application_id=app_id, interview_id=iv_id,
        scheduled_at=new_time, version=out["version"], ctx=CTX,
    )
    assert ok["version"] == out["version"] + 1
    assert await _audit_count(db_session, "application.interview_rescheduled") == 1

    outbox = (
        await db_session.execute(
            select(func.count()).select_from(NotificationOutbox)
            .where(
                NotificationOutbox.template_key == "application.interview_rescheduled"
            )
        )
    ).scalar_one()
    assert outbox == 1

    view = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    types = [e["event_type"] for e in view["timeline"]]
    assert types.count("interview_scheduled") == 1
    assert types.count("interview_rescheduled") == 1


async def test_cancel_frees_open_slot_then_can_reschedule_new(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    assignee = await _assignee(db_session, org)
    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[assignee.user_id]), ctx=CTX,
    )
    iv_id = uuid.UUID(out["id"])
    cancelled = await interview_service.cancel_interview(
        db_session, principal=partner, application_id=app_id, interview_id=iv_id,
        ctx=CTX,
    )
    assert cancelled["status"] == interview_domain.STATUS_CANCELLED
    assert await _audit_count(db_session, "application.interview_cancelled") == 1
    # Slot freed: a new open interview for the same stage now succeeds.
    again = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[assignee.user_id]), ctx=CTX,
    )
    assert again["status"] == interview_domain.STATUS_SCHEDULED


async def test_complete_and_no_show_transitions(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    assignee = await _assignee(db_session, org)
    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[assignee.user_id]), ctx=CTX,
    )
    iv_id = uuid.UUID(out["id"])
    done = await interview_service.complete_interview(
        db_session, principal=partner, application_id=app_id, interview_id=iv_id,
        outcome="completed", ctx=CTX,
    )
    assert done["status"] == interview_domain.STATUS_COMPLETED
    assert await _audit_count(db_session, "application.interview_completed") == 1
    # A completed interview is no longer actionable.
    with pytest.raises(InterviewNotActionableError):
        await interview_service.cancel_interview(
            db_session, principal=partner, application_id=app_id, interview_id=iv_id,
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Assignee-driven advance gate (scorecard action)                             #
# --------------------------------------------------------------------------- #


async def test_two_assignee_gate_requires_two_assignee_scorecards(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    a = await _assignee(db_session, org)
    b = await _assignee(db_session, org)
    await _set_current_action(db_session, app_id, scorecard.ACTION_SCORECARD)
    await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[a.user_id, b.user_id]), ctx=CTX,
    )

    # 0 submitted -> 409 {submitted:0, required:2}
    with pytest.raises(ScorecardRequiredError) as exc0:
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )
    assert exc0.value.details == {
        "reason": "scorecard_required", "submitted": 0, "required": 2,
    }

    # A submits -> 409 {submitted:1, required:2}
    await scorecard_service.submit_scorecard(
        db_session, principal=a, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    with pytest.raises(ScorecardRequiredError) as exc1:
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )
    assert exc1.value.details == {
        "reason": "scorecard_required", "submitted": 1, "required": 2,
    }

    # B submits -> both in -> advances.
    await scorecard_service.submit_scorecard(
        db_session, principal=b, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    out = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out["pipeline"]["position"] == 2


async def test_non_assignee_scorecard_does_not_count_toward_gate(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    a = await _assignee(db_session, org)
    b = await _assignee(db_session, org)
    outsider = await _assignee(db_session, org)  # member but NOT assigned
    await _set_current_action(db_session, app_id, scorecard.ACTION_SCORECARD)
    await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[a.user_id, b.user_id]), ctx=CTX,
    )

    # The non-assignee submits — it must NOT move the gate denominator.
    await scorecard_service.submit_scorecard(
        db_session, principal=outsider, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    with pytest.raises(ScorecardRequiredError) as exc:
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )
    assert exc.value.details == {
        "reason": "scorecard_required", "submitted": 0, "required": 2,
    }


# --------------------------------------------------------------------------- #
# score_threshold gate                                                        #
# --------------------------------------------------------------------------- #


async def test_score_threshold_below_then_above(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    a = await _assignee(db_session, org)
    await _set_current_action(
        db_session, app_id, interview_domain.ACTION_SCORE_THRESHOLD, threshold=4.0
    )
    await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[a.user_id]), ctx=CTX,
    )

    # Assignee submits avg 3.0 (< 4.0): count gate met, average gate fails.
    await scorecard_service.submit_scorecard(
        db_session, principal=a, application_id=app_id,
        recommendation="no", scores=_scores(technical=3, communication=3,
        culture_fit=3, motivation=3), ctx=CTX,
    )
    with pytest.raises(ScoreBelowThresholdError) as exc:
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )
    assert exc.value.details == {
        "reason": "score_below_threshold", "avg_overall": 3.0, "threshold": 4.0,
    }

    # Assignee raises the scores to avg 5.0 (>= 4.0) -> advances.
    await scorecard_service.submit_scorecard(
        db_session, principal=a, application_id=app_id,
        recommendation="strong_yes", scores=_scores(technical=5, communication=5,
        culture_fit=5, motivation=5), ctx=CTX,
    )
    out = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out["pipeline"]["position"] == 2


# --------------------------------------------------------------------------- #
# scorecard.interview_id auto-link                                            #
# --------------------------------------------------------------------------- #


async def test_scorecard_auto_links_to_open_interview(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    a = await _assignee(db_session, org)
    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[a.user_id]), ctx=CTX,
    )
    iv_id = uuid.UUID(out["id"])
    await scorecard_service.submit_scorecard(
        db_session, principal=a, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    sc = (
        await db_session.execute(
            select(Scorecard).where(
                Scorecard.application_id == app_id,
                Scorecard.submitted_by_user_id == a.user_id,
            )
        )
    ).scalar_one()
    assert sc.interview_id == iv_id


# --------------------------------------------------------------------------- #
# meeting_link encryption / attendee visibility / board absence               #
# --------------------------------------------------------------------------- #


async def test_meeting_link_encrypted_at_rest_and_attendee_only(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    attendee = await _assignee(db_session, org)
    viewer = await add_member(
        db_session, org=org,
        permissions=[("applications", "read"), ("interviews", "read")],
    )
    viewer_principal = viewer[2]

    plain = "https://meet.example/secret-room"
    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[attendee.user_id], link=plain), ctx=CTX,
    )
    iv_id = uuid.UUID(out["id"])

    # Encrypted at rest: the stored column is NOT the plaintext URL but decrypts to it.
    row = (
        await db_session.execute(select(Interview).where(Interview.id == iv_id))
    ).scalar_one()
    assert row.meeting_link is not None and row.meeting_link != plain
    assert decrypt_meeting_link(row.meeting_link) == plain

    # Attendee (assigned interviewer) sees the decrypted link.
    as_attendee = await interview_service.list_interviews(
        db_session, principal=attendee, application_id=app_id
    )
    assert as_attendee["interviews"][0]["meeting_link"] == plain

    # Non-attendee partner member (has manage perm) never receives the link.
    as_viewer = await interview_service.list_interviews(
        db_session, principal=viewer_principal, application_id=app_id
    )
    assert as_viewer["interviews"][0]["meeting_link"] is None


async def test_meeting_link_absent_from_board_glance(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    a = await _assignee(db_session, org)
    await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[a.user_id]), ctx=CTX,
    )
    view = await apply_service.get_application(
        db_session, principal=partner, application_id=app_id
    )
    iv_block = view["pipeline"]["interview"]
    assert iv_block is not None
    assert iv_block["status"] == interview_domain.STATUS_SCHEDULED
    assert iv_block["assignee_count"] == 1
    assert "meeting_link" not in iv_block


# --------------------------------------------------------------------------- #
# Anonymity — student projection carries NO interview-internal data            #
# --------------------------------------------------------------------------- #


def _all_keys(obj, acc: set) -> set:
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            _all_keys(v, acc)
    elif isinstance(obj, list):
        for item in obj:
            _all_keys(item, acc)
    return acc


async def test_student_projection_has_no_assignee_scorecard_or_gate(db_session) -> None:
    org, partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    a = await _assignee(db_session, org)
    # Onsite so the student card's location_or_link is an address (no link/ciphertext).
    await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        mode="onsite", scheduled_at=_now() + timedelta(days=2),
        assignee_ids=[a.user_id], location="VinUni Campus, Hanoi", ctx=CTX,
    )
    await scorecard_service.submit_scorecard(
        db_session, principal=a, application_id=app_id,
        recommendation="strong_yes", scores=_scores(technical=5),
        comment="internal note", ctx=CTX,
    )
    view = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    # The student sees their OWN interview card (identity-safe) ...
    card = view["upcoming_interview"]
    assert card is not None
    assert card["location_or_link"] == "VinUni Campus, Hanoi"
    # ... but NEVER assignees / scorecards / gate / pipeline-internal / meeting_link.
    keys = _all_keys(view, set())
    assert "assignees" not in keys
    assert "evaluation" not in keys
    assert "meeting_link" not in keys
    assert "pipeline" not in view
    blob = str(view).lower()
    assert str(a.user_id) not in blob
    assert "scorecard" not in blob
    assert "internal note" not in blob


# --------------------------------------------------------------------------- #
# Cross-org isolation                                                          #
# --------------------------------------------------------------------------- #


async def test_cross_org_schedule_and_list_are_404(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    a = await _assignee(db_session, org)
    _bu, _borg, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    with pytest.raises(ResourceNotFoundError):
        await interview_service.schedule_interview(
            db_session, principal=partner_b, application_id=app_id,
            **_online(assignees=[a.user_id]), ctx=CTX,
        )
    with pytest.raises(ResourceNotFoundError):
        await interview_service.list_interviews(
            db_session, principal=partner_b, application_id=app_id
        )


# --------------------------------------------------------------------------- #
# Reminder sweep (ADR-0003 scheduler) — dedupe / idempotency via tick()        #
# --------------------------------------------------------------------------- #


async def _reminder_outbox_count(db_session, iv_id) -> int:
    return (
        await db_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.dedupe_key.like(f"interview.reminder%:{iv_id}:%"))
        )
    ).scalar_one()


async def test_reminder_sweep_enqueues_once_per_window(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    a = await _assignee(db_session, org)
    # Within the 24h window (>1h out) -> exactly the 24h reminders fire.
    out = await interview_service.schedule_interview(
        db_session, principal=partner, application_id=app_id,
        **_online(assignees=[a.user_id], at=_now() + timedelta(hours=23)), ctx=CTX,
    )
    iv_id = uuid.UUID(out["id"])

    await db_session.rollback()
    res1 = await runner.tick(
        _now(), session_factory=get_sessionmaker(), only=["interview.reminder_sweep"]
    )
    # candidate (24h) + assignee (24h) = 2 reminders.
    assert res1["interview.reminder_sweep"]["reminders"] == 2

    await db_session.rollback()
    res2 = await runner.tick(
        _now(), session_factory=get_sessionmaker(), only=["interview.reminder_sweep"]
    )
    assert res2["interview.reminder_sweep"]["reminders"] == 0

    # Exactly two deduped reminder outbox rows survive (idempotent).
    await db_session.rollback()
    assert await _reminder_outbox_count(db_session, iv_id) == 2
