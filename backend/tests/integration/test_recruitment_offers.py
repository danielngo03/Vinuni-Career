"""Recruitment offer tests (ADR-0007 first slice).

Covers the offer 8-state machine + approval gate + candidate accept/decline on top
of the ADR-0004 stage engine, ADR-0005 scorecards, and ADR-0006 interviews:

- create draft -> submit -> approve -> send happy path; send-before-approve -> 409
  ``offer_not_approved``; second LIVE offer -> 409 ``offer_exists``; edit-after-draft
  -> 409 ``offer_not_editable``.
- student accept -> offer ``accepted`` + ``applications.status='hired'`` + Offer-stage
  ``candidate_stages`` row closed PASSED/``exit_kind='hired'`` + ``offer.accepted``
  outbox event (career seam, NO salary) + ``application.hired`` audit; student decline
  -> ``declined``, application stays ``under_review``; respond expired -> 409
  ``offer_not_actionable``; respond not-owner -> 404; idempotent respond replay;
  optimistic version conflict -> 409; cross-org -> 404.
- salary Fernet-encrypted at rest + absent from the notification body, the board
  glance, and the ``offer.accepted`` event; the student offer projection carries no
  partner internals; expiry sweep via ``tick()`` flips ``sent -> expired`` + notifies
  + is idempotent; an audit row per write.
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
    offer_service,
)
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    OfferExistsError,
    OfferNotActionableError,
    OfferNotApprovedError,
    OfferNotEditableError,
)
from app.modules.recruitment.domain import lifecycle, pipeline
from app.modules.recruitment.domain import offer as offer_domain
from app.modules.recruitment.domain.models import Application, CandidateStage, Offer
from app.modules.recruitment.infrastructure.offer_salary_crypto import decrypt_salary
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog, OutboxEvent
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


def _now() -> datetime:
    return datetime.now(tz=UTC)


_SALARY = 25_000_000


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


async def _setup_reviewed(db):
    """Published job + applied + reviewed (candidate ACTIVE at stage 1)."""

    _pu, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=partner, uni_principal=uni)

    su, student = await make_student(db, prefix="student")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(db, principal=partner, application_id=app_id, ctx=CTX)
    return partner, su, student, job_id, app_id


def _create_kwargs(**over) -> dict:
    base = {
        "position_title": "Backend Engineer",
        "expiry_date": _now() + timedelta(days=7),
        "salary_amount": _SALARY,
        "start_date": (_now() + timedelta(days=30)).date(),
        "benefits_summary": "Health insurance, 15 days PTO",
    }
    base.update(over)
    return base


async def _create_offer(db, *, partner, app_id, **over) -> dict:
    return await offer_service.create_offer(
        db, principal=partner, application_id=app_id, ctx=CTX, **_create_kwargs(**over)
    )


async def _to_approved(db, *, partner, app_id, **over) -> dict:
    out = await _create_offer(db, partner=partner, app_id=app_id, **over)
    oid = uuid.UUID(out["id"])
    await offer_service.submit_offer(db, principal=partner, offer_id=oid, ctx=CTX)
    return await offer_service.approve_offer(
        db, principal=partner, offer_id=oid, decision="approve", ctx=CTX
    )


async def _to_sent(db, *, partner, app_id, **over) -> dict:
    appr = await _to_approved(db, partner=partner, app_id=app_id, **over)
    return await offer_service.send_offer(
        db, principal=partner, offer_id=uuid.UUID(appr["id"]), ctx=CTX
    )


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Happy path + approval gate                                                  #
# --------------------------------------------------------------------------- #


async def test_create_submit_approve_send_happy_path(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    out = await _create_offer(db_session, partner=partner, app_id=app_id)
    assert out["status"] == offer_domain.STATUS_DRAFT
    oid = uuid.UUID(out["id"])
    assert await _audit_count(db_session, "application.offer_created") == 1

    submitted = await offer_service.submit_offer(
        db_session, principal=partner, offer_id=oid, ctx=CTX
    )
    assert submitted["status"] == offer_domain.STATUS_PENDING_APPROVAL

    approved = await offer_service.approve_offer(
        db_session, principal=partner, offer_id=oid, decision="approve", ctx=CTX
    )
    assert approved["status"] == offer_domain.STATUS_APPROVED
    assert approved["approved_by"] == str(partner.user_id)
    assert approved["approved_at"] is not None

    sent = await offer_service.send_offer(db_session, principal=partner, offer_id=oid, ctx=CTX)
    assert sent["status"] == offer_domain.STATUS_SENT
    assert sent["sent_at"] is not None
    for action in ("offer_submitted", "offer_approved", "offer_sent"):
        assert await _audit_count(db_session, f"application.{action}") == 1


async def test_send_before_approve_is_409_offer_not_approved(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    out = await _create_offer(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(out["id"])
    # Still a draft (never submitted/approved) -> send is blocked by the gate.
    with pytest.raises(OfferNotApprovedError) as exc:
        await offer_service.send_offer(db_session, principal=partner, offer_id=oid, ctx=CTX)
    assert exc.value.details == {"reason": "offer_not_approved"}

    # Submitted but not yet approved -> still blocked.
    await offer_service.submit_offer(db_session, principal=partner, offer_id=oid, ctx=CTX)
    with pytest.raises(OfferNotApprovedError):
        await offer_service.send_offer(db_session, principal=partner, offer_id=oid, ctx=CTX)


async def test_approve_reject_bounces_back_to_draft(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    out = await _create_offer(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(out["id"])
    await offer_service.submit_offer(db_session, principal=partner, offer_id=oid, ctx=CTX)
    rejected = await offer_service.approve_offer(
        db_session, principal=partner, offer_id=oid, decision="reject", ctx=CTX
    )
    assert rejected["status"] == offer_domain.STATUS_DRAFT
    # Editable again after a reject-back.
    edited = await offer_service.update_draft(
        db_session, principal=partner, offer_id=oid, salary_amount=30_000_000, ctx=CTX
    )
    assert edited["salary_amount"] == 30_000_000


# --------------------------------------------------------------------------- #
# One LIVE offer / editable-only-in-draft                                     #
# --------------------------------------------------------------------------- #


async def test_second_live_offer_is_409_offer_exists(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    await _create_offer(db_session, partner=partner, app_id=app_id)
    with pytest.raises(OfferExistsError) as exc:
        await _create_offer(db_session, partner=partner, app_id=app_id)
    assert exc.value.details == {"reason": "offer_exists"}


async def test_edit_after_submit_is_409_offer_not_editable(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    out = await _create_offer(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(out["id"])
    await offer_service.submit_offer(db_session, principal=partner, offer_id=oid, ctx=CTX)
    with pytest.raises(OfferNotEditableError) as exc:
        await offer_service.update_draft(
            db_session,
            principal=partner,
            offer_id=oid,
            salary_amount=99_000_000,
            ctx=CTX,
        )
    assert exc.value.details == {"reason": "offer_not_editable"}


async def test_update_draft_version_conflict_is_409(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    out = await _create_offer(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(out["id"])
    with pytest.raises(ApplicationVersionConflictError):
        await offer_service.update_draft(
            db_session,
            principal=partner,
            offer_id=oid,
            salary_amount=1,
            version=999,
            ctx=CTX,
        )
    ok = await offer_service.update_draft(
        db_session,
        principal=partner,
        offer_id=oid,
        salary_amount=1,
        version=out["version"],
        ctx=CTX,
    )
    assert ok["version"] == out["version"] + 1


# --------------------------------------------------------------------------- #
# Reveal precondition on SEND                                                 #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Candidate accept -> hired + stage closed + career seam                      #
# --------------------------------------------------------------------------- #


async def test_student_accept_marks_hired_closes_stage_emits_event(db_session) -> None:
    partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    sent = await _to_sent(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(sent["id"])

    out = await offer_service.respond_offer(
        db_session,
        principal=student,
        offer_id=oid,
        decision="accepted",
        idempotency_key="resp-1",
        ctx=CTX,
    )
    assert out["status"] == offer_domain.STATUS_ACCEPTED

    # applications.status -> hired (terminal positive; not active/withdrawable).
    app_row = (
        await db_session.execute(select(Application).where(Application.id == app_id))
    ).scalar_one()
    assert app_row.status == lifecycle.HIRED
    assert lifecycle.HIRED not in lifecycle.ACTIVE_STATUSES

    # The open Offer-stage candidate_stages row is closed PASSED / exit_kind='hired'.
    closed = (
        (
            await db_session.execute(
                select(CandidateStage).where(CandidateStage.application_id == app_id)
            )
        )
        .scalars()
        .all()
    )
    assert any(
        c.status == pipeline.STAGE_PASSED and c.exit_kind == pipeline.EXIT_HIRED for c in closed
    )

    # The non-blocking career-outcome seam event was emitted (NO salary in payload).
    events = (
        (
            await db_session.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == "offer.accepted")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["application_id"] == str(app_id)
    assert payload["position_title"] == "Backend Engineer"
    assert "salary" not in str(payload).lower()
    assert str(_SALARY) not in str(payload)

    assert await _audit_count(db_session, "application.hired") == 1


async def test_student_decline_keeps_application_under_review(db_session) -> None:
    partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    sent = await _to_sent(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(sent["id"])

    out = await offer_service.respond_offer(
        db_session,
        principal=student,
        offer_id=oid,
        decision="declined",
        notes="Accepted another role",
        idempotency_key="resp-d",
        ctx=CTX,
    )
    assert out["status"] == offer_domain.STATUS_DECLINED
    # The application is NOT auto-rejected — it stays under_review.
    app_row = (
        await db_session.execute(select(Application).where(Application.id == app_id))
    ).scalar_one()
    assert app_row.status == lifecycle.UNDER_REVIEW
    # decline_reason is partner-internal — never on the student projection.
    assert "decline_reason" not in out
    assert await _audit_count(db_session, "application.offer_declined") == 1


async def test_respond_replay_is_idempotent(db_session) -> None:
    partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    sent = await _to_sent(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(sent["id"])
    await offer_service.respond_offer(
        db_session,
        principal=student,
        offer_id=oid,
        decision="accepted",
        idempotency_key="r1",
        ctx=CTX,
    )
    # Replay the SAME accept -> no-op (no duplicate hired/event/audit).
    again = await offer_service.respond_offer(
        db_session,
        principal=student,
        offer_id=oid,
        decision="accepted",
        idempotency_key="r1",
        ctx=CTX,
    )
    assert again["status"] == offer_domain.STATUS_ACCEPTED
    assert await _audit_count(db_session, "application.hired") == 1
    events = (
        await db_session.execute(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.event_type == "offer.accepted")
        )
    ).scalar_one()
    assert events == 1


async def test_respond_to_expired_is_409_offer_not_actionable(db_session) -> None:
    partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    sent = await _to_sent(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(sent["id"])
    # Force the deadline into the past.
    offer = (await db_session.execute(select(Offer).where(Offer.id == oid))).scalar_one()
    offer.expiry_date = _now() - timedelta(hours=1)
    await db_session.commit()

    with pytest.raises(OfferNotActionableError) as exc:
        await offer_service.respond_offer(
            db_session,
            principal=student,
            offer_id=oid,
            decision="accepted",
            idempotency_key="r-exp",
            ctx=CTX,
        )
    assert exc.value.details == {"reason": "offer_not_actionable"}
    # Lazy-expire flipped it.
    offer = (await db_session.execute(select(Offer).where(Offer.id == oid))).scalar_one()
    assert offer.status == offer_domain.STATUS_EXPIRED


async def test_respond_by_non_owner_is_404(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    sent = await _to_sent(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(sent["id"])
    _ou, other = await make_student(db_session, prefix="intruder")
    with pytest.raises(ResourceNotFoundError):
        await offer_service.respond_offer(
            db_session,
            principal=other,
            offer_id=oid,
            decision="accepted",
            idempotency_key="r-x",
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Cross-org isolation                                                         #
# --------------------------------------------------------------------------- #


async def test_cross_org_offer_actions_are_404(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    out = await _create_offer(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(out["id"])
    _bu, _borg, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    with pytest.raises(ResourceNotFoundError):
        await offer_service.create_offer(
            db_session,
            principal=partner_b,
            application_id=app_id,
            ctx=CTX,
            **_create_kwargs(),
        )
    with pytest.raises(ResourceNotFoundError):
        await offer_service.submit_offer(db_session, principal=partner_b, offer_id=oid, ctx=CTX)
    with pytest.raises(ResourceNotFoundError):
        await offer_service.list_offers_partner(
            db_session, principal=partner_b, application_id=app_id
        )


# --------------------------------------------------------------------------- #
# Salary encryption / visibility                                             #
# --------------------------------------------------------------------------- #


async def test_salary_encrypted_at_rest_and_partner_sees_it(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    out = await _create_offer(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(out["id"])
    row = (await db_session.execute(select(Offer).where(Offer.id == oid))).scalar_one()
    # Stored ciphertext is NOT the plaintext figure but decrypts to it.
    assert row.salary_amount is not None
    assert row.salary_amount != str(_SALARY)
    assert decrypt_salary(row.salary_amount) == str(_SALARY)
    # The partner view decrypts it.
    assert out["salary_amount"] == _SALARY


async def test_salary_absent_from_notification_body_and_board_glance(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    await _to_sent(db_session, partner=partner, app_id=app_id)

    # No queued candidate notification carries the salary figure.
    rows = (
        (
            await db_session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key.like("recruitment.offer_received:%")
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows
    for r in rows:
        assert str(_SALARY) not in str(r.variables)
        assert "salary" not in str(r.variables).lower()

    # The partner board glance carries NO salary (open the detail to see comp).
    view = await apply_service.get_application(db_session, principal=partner, application_id=app_id)
    offer_block = view["pipeline"]["offer"]
    assert offer_block is not None
    assert offer_block["status"] == offer_domain.STATUS_SENT
    assert "salary_amount" not in offer_block
    assert "comp_summary" not in offer_block
    assert str(_SALARY) not in str(offer_block)


async def test_student_projection_has_no_partner_internals(db_session) -> None:
    partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    await _to_sent(db_session, partner=partner, app_id=app_id)
    view = await apply_service.get_application(db_session, principal=student, application_id=app_id)
    card = view["offer"]
    assert card is not None
    assert card["position_title"] == "Backend Engineer"
    # The student DOES see their own comp summary, but never partner internals.
    blob = str(view).lower()
    assert "approved_by" not in blob
    assert "decline_reason" not in blob
    assert "created_by" not in blob


async def test_draft_offer_not_visible_to_student(db_session) -> None:
    partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    await _create_offer(db_session, partner=partner, app_id=app_id)
    # A draft offer is partner-internal: not on the student detail, not listed.
    view = await apply_service.get_application(db_session, principal=student, application_id=app_id)
    assert view["offer"] is None
    listed = await offer_service.list_offers_student(db_session, principal=student)
    assert listed == []


# --------------------------------------------------------------------------- #
# Expiry sweep (ADR-0003 scheduler) via tick()                                #
# --------------------------------------------------------------------------- #


async def _expired_outbox_count(db_session, oid) -> int:
    return (
        await db_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.dedupe_key.like(f"recruitment.offer_expired:{oid}:%"))
        )
    ).scalar_one()


async def test_expire_sweep_flips_sent_to_expired_idempotent(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    sent = await _to_sent(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(sent["id"])
    offer = (await db_session.execute(select(Offer).where(Offer.id == oid))).scalar_one()
    offer.expiry_date = _now() - timedelta(hours=1)
    await db_session.commit()

    await db_session.rollback()
    res1 = await runner.tick(
        _now(), session_factory=get_sessionmaker(), only=["offer.expire_sweep"]
    )
    assert res1["offer.expire_sweep"]["expired"] == 1

    # Idempotent: the row is no longer ``sent`` so a re-run finds no work.
    await db_session.rollback()
    res2 = await runner.tick(
        _now(), session_factory=get_sessionmaker(), only=["offer.expire_sweep"]
    )
    assert res2["offer.expire_sweep"]["expired"] == 0

    # Read the post-tick state from a FRESH session (as the app does after a
    # scheduler tick) — a long-lived test session can serve a stale page cache for
    # an updated row across SQLite connections.
    async with get_sessionmaker()() as fresh:
        offer = (await fresh.execute(select(Offer).where(Offer.id == oid))).scalar_one()
        assert offer.status == offer_domain.STATUS_EXPIRED
        # Exactly one expired notice to the candidate (deduped).
        assert await _expired_outbox_count(fresh, oid) == 1


async def test_offer_expire_sweep_emits_timeline_event(db_session) -> None:
    from app.modules.recruitment.application import apply_service

    partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    sent = await _to_sent(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(sent["id"])
    offer = (await db_session.execute(select(Offer).where(Offer.id == oid))).scalar_one()
    offer.expiry_date = _now() - timedelta(hours=1)
    await db_session.commit()

    await db_session.rollback()
    res = await runner.tick(_now(), session_factory=get_sessionmaker(), only=["offer.expire_sweep"])
    assert res["offer.expire_sweep"]["expired"] == 1

    async with get_sessionmaker()() as fresh:
        view = await apply_service.get_application(fresh, principal=student, application_id=app_id)
        types = [e["event_type"] for e in view["timeline"]]
        assert types.count("offer_sent") == 1
        assert types.count("offer_expired") == 1


async def test_expiring_reminder_enqueued_once(db_session) -> None:
    partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    # Deadline ~12h out -> inside the T-24h window but NOT expired.
    sent = await _to_sent(
        db_session, partner=partner, app_id=app_id, expiry_date=_now() + timedelta(hours=12)
    )
    oid = uuid.UUID(sent["id"])

    await db_session.rollback()
    res1 = await runner.tick(
        _now(), session_factory=get_sessionmaker(), only=["offer.expire_sweep"]
    )
    assert res1["offer.expire_sweep"]["expiring"] == 1
    assert res1["offer.expire_sweep"]["expired"] == 0

    await db_session.rollback()
    res2 = await runner.tick(
        _now(), session_factory=get_sessionmaker(), only=["offer.expire_sweep"]
    )
    # Deduped on the per-offer outbox key -> no second reminder.
    assert res2["offer.expire_sweep"]["expiring"] == 0

    await db_session.rollback()
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.dedupe_key == f"recruitment.offer_expiring:{oid}:expiring")
        )
    ).scalar_one()
    assert count == 1
