"""Org-wide partner recruiting board reads (interview + offer boards).

Two new cross-job reads on top of the ADR-0006 interview + ADR-0007 offer engines:

- ``interview_service.list_org_interviews`` — every interview for the caller org's
  jobs (``interviews:read`` at org scope). ``scope`` = upcoming/past/all; ``mine``
  narrows to the caller's own assignments; ``meeting_link`` is attendee-only per row.
- ``offer_service.list_org_offers`` — every offer for the caller org's jobs
  (``offers:create`` at org scope). ``scope`` = live/terminal/needs_action/all; comp
  is decrypted on the recruiter's own-org management row.

Covered here: RBAC denial, tenant isolation (incl. cross-org ``job_id``), scope
filters, ``mine`` filter, attendee-only meeting link, pagination (``total`` vs.
``limit``/``offset``), and the exact frozen row shapes (so the parallel FE lane
never breaks on a renamed field).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    interview_service,
    offer_service,
)
from app.shared.exceptions import PermissionDeniedError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job

_SALARY = 25_000_000

_INTERVIEW_ROW_KEYS = {
    "id",
    "application_id",
    "job_id",
    "job_title",
    "candidate_handle",
    "stage_name",
    "mode",
    "mode_label",
    "scheduled_at",
    "duration_minutes",
    "status",
    "status_label",
    "location",
    "meeting_link",
    "assignees",
    "assignee_count",
    "is_attendee",
}

_OFFER_ROW_KEYS = {
    "id",
    "application_id",
    "job_id",
    "job_title",
    "candidate_handle",
    "position_title",
    "status",
    "status_label",
    "is_live",
    "expiry_date",
    "sent_at",
    "approved_at",
    "created_at",
    "salary_amount",
    "salary_currency",
    "salary_period",
    "period_label",
    "start_date",
}


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _online(assignees: list[uuid.UUID], *, at=None, link="https://meet.example/room") -> dict:
    return {
        "mode": "online",
        "scheduled_at": at or (_now() + timedelta(days=2)),
        "assignee_ids": assignees,
        "meeting_link": link,
    }


async def _org_with_apps(db, n: int):
    """Partner org + university + one published job + ``n`` reviewed applications.

    Returns ``(porg, partner, uni, job_id, [(app_id, student_principal), ...])``.
    """

    _pu, porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=partner, uni_principal=uni)

    apps: list[tuple[uuid.UUID, object]] = []
    for i in range(n):
        _su, student = await make_student(db, prefix=f"student{i}")
        sel = await make_builder_cv(db, student=student)
        app = await apply_service.apply_to_job(
            db,
            principal=student,
            payload=apply_payload(job_id=job_id, cv_selection=sel),
            ctx=CTX,
        )
        app_id = uuid.UUID(app["id"])
        await decision_service.review_application(
            db, principal=partner, application_id=app_id, ctx=CTX
        )
        apps.append((app_id, student))
    return porg, partner, uni, job_id, apps


async def _assignee(db, org):
    """An org member granted the interview + read capabilities (board-viewable)."""

    _u, _m, principal = await add_member(
        db,
        org=org,
        permissions=[
            ("applications", "read"),
            ("interviews", "read"),
            ("interviews", "schedule"),
            ("interviews", "assign"),
            ("interviews", "complete"),
            ("interviews", "cancel"),
        ],
    )
    return principal


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


async def _to_approved(db, *, partner, app_id) -> dict:
    out = await _create_offer(db, partner=partner, app_id=app_id)
    oid = uuid.UUID(out["id"])
    await offer_service.submit_offer(db, principal=partner, offer_id=oid, ctx=CTX)
    return await offer_service.approve_offer(
        db, principal=partner, offer_id=oid, decision="approve", ctx=CTX
    )


async def _to_sent(db, *, partner, app_id) -> dict:
    appr = await _to_approved(db, partner=partner, app_id=app_id)
    return await offer_service.send_offer(
        db, principal=partner, offer_id=uuid.UUID(appr["id"]), ctx=CTX
    )


# --------------------------------------------------------------------------- #
# Interview board — RBAC / tenant isolation                                    #
# --------------------------------------------------------------------------- #


async def test_interview_board_rbac_denied_without_interviews_read(db_session) -> None:
    porg, _partner, _uni, _job, _apps = await _org_with_apps(db_session, 1)
    # A member WITHOUT interviews:read (only applications:read) is denied.
    _u, _m, viewer = await add_member(
        db_session, org=porg, permissions=[("applications", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await interview_service.list_org_interviews(db_session, principal=viewer, scope="all")


async def test_interview_board_tenant_isolation(db_session) -> None:
    porg, partner, uni, _job, apps = await _org_with_apps(db_session, 1)
    a = await _assignee(db_session, porg)
    await interview_service.schedule_interview(
        db_session,
        principal=partner,
        application_id=apps[0][0],
        **_online([a.user_id]),
        ctx=CTX,
    )

    # Another org's admin never sees org A's interviews.
    _bu, _borg, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    board_b = await interview_service.list_org_interviews(
        db_session, principal=partner_b, scope="all"
    )
    assert board_b["total"] == 0
    assert board_b["interviews"] == []

    # Org A sees its own single interview.
    board_a = await interview_service.list_org_interviews(
        db_session, principal=partner, scope="all"
    )
    assert board_a["total"] == 1

    # A cross-org job_id filter yields an empty board (never a tenant leak).
    job_b = await publish_job(
        db_session, partner_principal=partner_b, uni_principal=uni, title="Org B Job"
    )
    cross = await interview_service.list_org_interviews(
        db_session, principal=partner, scope="all", job_id=job_b
    )
    assert cross["total"] == 0
    assert cross["interviews"] == []


# --------------------------------------------------------------------------- #
# Interview board — scope filters                                              #
# --------------------------------------------------------------------------- #


async def test_interview_board_scope_filters(db_session) -> None:
    porg, partner, _uni, _job, apps = await _org_with_apps(db_session, 4)
    a = await _assignee(db_session, porg)

    # app0: upcoming (scheduled, future).
    await interview_service.schedule_interview(
        db_session,
        principal=partner,
        application_id=apps[0][0],
        **_online([a.user_id], at=_now() + timedelta(days=2)),
        ctx=CTX,
    )
    # app1: scheduled but PAST-dated.
    await interview_service.schedule_interview(
        db_session,
        principal=partner,
        application_id=apps[1][0],
        **_online([a.user_id], at=_now() - timedelta(days=2)),
        ctx=CTX,
    )
    # app2: completed.
    iv2 = await interview_service.schedule_interview(
        db_session,
        principal=partner,
        application_id=apps[2][0],
        **_online([a.user_id], at=_now() + timedelta(days=1)),
        ctx=CTX,
    )
    await interview_service.complete_interview(
        db_session,
        principal=partner,
        application_id=apps[2][0],
        interview_id=uuid.UUID(iv2["id"]),
        outcome="completed",
        ctx=CTX,
    )
    # app3: cancelled.
    iv3 = await interview_service.schedule_interview(
        db_session,
        principal=partner,
        application_id=apps[3][0],
        **_online([a.user_id], at=_now() + timedelta(days=1)),
        ctx=CTX,
    )
    await interview_service.cancel_interview(
        db_session,
        principal=partner,
        application_id=apps[3][0],
        interview_id=uuid.UUID(iv3["id"]),
        ctx=CTX,
    )

    upcoming = await interview_service.list_org_interviews(
        db_session, principal=partner, scope="upcoming"
    )
    assert upcoming["total"] == 1
    assert upcoming["interviews"][0]["application_id"] == str(apps[0][0])

    past = await interview_service.list_org_interviews(db_session, principal=partner, scope="past")
    past_app_ids = {r["application_id"] for r in past["interviews"]}
    assert past["total"] == 3
    assert past_app_ids == {str(apps[1][0]), str(apps[2][0]), str(apps[3][0])}

    all_board = await interview_service.list_org_interviews(
        db_session, principal=partner, scope="all"
    )
    assert all_board["total"] == 4

    # Optional status filter narrows further (independent of scope).
    completed = await interview_service.list_org_interviews(
        db_session, principal=partner, scope="all", status="completed"
    )
    assert completed["total"] == 1
    assert completed["interviews"][0]["application_id"] == str(apps[2][0])


# --------------------------------------------------------------------------- #
# Interview board — mine filter + attendee-only meeting link                   #
# --------------------------------------------------------------------------- #


async def test_interview_board_mine_filter(db_session) -> None:
    porg, partner, _uni, _job, apps = await _org_with_apps(db_session, 2)
    a = await _assignee(db_session, porg)
    b = await _assignee(db_session, porg)
    await interview_service.schedule_interview(
        db_session, principal=partner, application_id=apps[0][0], **_online([a.user_id]), ctx=CTX
    )
    await interview_service.schedule_interview(
        db_session, principal=partner, application_id=apps[1][0], **_online([b.user_id]), ctx=CTX
    )

    # Without mine, ``a`` (a valid board viewer) sees both org interviews.
    full = await interview_service.list_org_interviews(db_session, principal=a, scope="all")
    assert full["total"] == 2

    # mine=true returns only the interview ``a`` is assigned to.
    mine = await interview_service.list_org_interviews(
        db_session, principal=a, scope="all", mine=True
    )
    assert mine["total"] == 1
    assert mine["interviews"][0]["application_id"] == str(apps[0][0])
    assert mine["interviews"][0]["is_attendee"] is True


async def test_interview_board_meeting_link_attendee_only(db_session) -> None:
    porg, partner, _uni, _job, apps = await _org_with_apps(db_session, 2)
    a = await _assignee(db_session, porg)
    b = await _assignee(db_session, porg)
    link_a = "https://meet.example/room-a"
    link_b = "https://meet.example/room-b"
    await interview_service.schedule_interview(
        db_session,
        principal=partner,
        application_id=apps[0][0],
        **_online([a.user_id], link=link_a),
        ctx=CTX,
    )
    await interview_service.schedule_interview(
        db_session,
        principal=partner,
        application_id=apps[1][0],
        **_online([b.user_id], link=link_b),
        ctx=CTX,
    )

    board = await interview_service.list_org_interviews(db_session, principal=a, scope="all")
    by_app = {r["application_id"]: r for r in board["interviews"]}
    # ``a`` is an attendee of app0 only -> link present there, withheld elsewhere.
    assert by_app[str(apps[0][0])]["meeting_link"] == link_a
    assert by_app[str(apps[0][0])]["is_attendee"] is True
    assert by_app[str(apps[1][0])]["meeting_link"] is None
    assert by_app[str(apps[1][0])]["is_attendee"] is False


# --------------------------------------------------------------------------- #
# Interview board — pagination + row shape                                     #
# --------------------------------------------------------------------------- #


async def test_interview_board_pagination(db_session) -> None:
    porg, partner, _uni, _job, apps = await _org_with_apps(db_session, 3)
    a = await _assignee(db_session, porg)
    for i, (app_id, _student) in enumerate(apps):
        await interview_service.schedule_interview(
            db_session,
            principal=partner,
            application_id=app_id,
            **_online([a.user_id], at=_now() + timedelta(days=2 + i)),
            ctx=CTX,
        )

    page1 = await interview_service.list_org_interviews(
        db_session, principal=partner, scope="upcoming", limit=2, offset=0
    )
    assert page1["total"] == 3
    assert len(page1["interviews"]) == 2

    page2 = await interview_service.list_org_interviews(
        db_session, principal=partner, scope="upcoming", limit=2, offset=2
    )
    assert page2["total"] == 3
    assert len(page2["interviews"]) == 1

    seen = {r["id"] for r in page1["interviews"]} | {r["id"] for r in page2["interviews"]}
    assert len(seen) == 3


async def test_interview_board_row_shape(db_session) -> None:
    porg, partner, uni, job_id, apps = await _org_with_apps(db_session, 1)
    a = await _assignee(db_session, porg)
    await interview_service.schedule_interview(
        db_session,
        principal=partner,
        application_id=apps[0][0],
        mode="onsite",
        scheduled_at=_now() + timedelta(days=2),
        assignee_ids=[a.user_id],
        location="VinUni Campus, Hanoi",
        ctx=CTX,
    )
    board = await interview_service.list_org_interviews(
        db_session, principal=partner, scope="all", locale="en"
    )
    row = board["interviews"][0]
    assert set(row.keys()) == _INTERVIEW_ROW_KEYS
    assert row["id"]
    assert row["application_id"] == str(apps[0][0])
    assert row["job_id"] == str(job_id)
    assert row["job_title"]  # the published job's real title
    assert row["candidate_handle"]  # applications are always identified
    assert row["stage_name"]  # the active pipeline stage name
    assert row["mode"] == "onsite"
    assert row["mode_label"] == "On-site"
    assert row["status"] == "scheduled"
    assert row["status_label"] == "Scheduled"
    assert row["location"] == "VinUni Campus, Hanoi"
    assert row["duration_minutes"] == 60
    assert row["assignee_count"] == 1
    assert row["assignees"][0]["user_id"] == str(a.user_id)
    assert "display_name" in row["assignees"][0]
    # The partner admin who scheduled is NOT an interviewer -> not an attendee.
    assert row["is_attendee"] is False
    assert row["meeting_link"] is None


# --------------------------------------------------------------------------- #
# Offer board — RBAC / tenant isolation                                        #
# --------------------------------------------------------------------------- #


async def test_offer_board_rbac_denied_without_offers_create(db_session) -> None:
    porg, _partner, _uni, _job, _apps = await _org_with_apps(db_session, 1)
    # A member WITHOUT offers:create (only applications:read) is denied.
    _u, _m, viewer = await add_member(
        db_session, org=porg, permissions=[("applications", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await offer_service.list_org_offers(db_session, principal=viewer, scope="all")


async def test_offer_board_tenant_isolation(db_session) -> None:
    porg, partner, uni, _job, apps = await _org_with_apps(db_session, 1)
    await _create_offer(db_session, partner=partner, app_id=apps[0][0])

    _bu, _borg, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    board_b = await offer_service.list_org_offers(db_session, principal=partner_b, scope="all")
    assert board_b["total"] == 0
    assert board_b["offers"] == []

    board_a = await offer_service.list_org_offers(db_session, principal=partner, scope="all")
    assert board_a["total"] == 1

    job_b = await publish_job(
        db_session, partner_principal=partner_b, uni_principal=uni, title="Org B Job"
    )
    cross = await offer_service.list_org_offers(
        db_session, principal=partner, scope="all", job_id=job_b
    )
    assert cross["total"] == 0


# --------------------------------------------------------------------------- #
# Offer board — scope filters                                                  #
# --------------------------------------------------------------------------- #


async def test_offer_board_scope_filters(db_session) -> None:
    porg, partner, _uni, _job, apps = await _org_with_apps(db_session, 6)

    # app0: draft (LIVE).
    await _create_offer(db_session, partner=partner, app_id=apps[0][0])
    # app1: pending_approval (LIVE, needs_action).
    o1 = await _create_offer(db_session, partner=partner, app_id=apps[1][0])
    await offer_service.submit_offer(
        db_session, principal=partner, offer_id=uuid.UUID(o1["id"]), ctx=CTX
    )
    # app2: approved (LIVE, needs_action).
    await _to_approved(db_session, partner=partner, app_id=apps[2][0])
    # app3: sent (LIVE).
    await _to_sent(db_session, partner=partner, app_id=apps[3][0])
    # app4: rescinded (TERMINAL).
    o4 = await _create_offer(db_session, partner=partner, app_id=apps[4][0])
    await offer_service.rescind_offer(
        db_session, principal=partner, offer_id=uuid.UUID(o4["id"]), ctx=CTX
    )
    # app5: declined (TERMINAL) — the student declines a sent offer.
    o5 = await _to_sent(db_session, partner=partner, app_id=apps[5][0])
    await offer_service.respond_offer(
        db_session,
        principal=apps[5][1],
        offer_id=uuid.UUID(o5["id"]),
        decision="declined",
        idempotency_key=uuid.uuid4().hex,
        ctx=CTX,
    )

    live = await offer_service.list_org_offers(db_session, principal=partner, scope="live")
    assert live["total"] == 4
    assert {r["status"] for r in live["offers"]} <= {
        "draft",
        "pending_approval",
        "approved",
        "sent",
    }

    terminal = await offer_service.list_org_offers(db_session, principal=partner, scope="terminal")
    assert terminal["total"] == 2
    assert {r["status"] for r in terminal["offers"]} == {"declined", "rescinded"}

    needs = await offer_service.list_org_offers(
        db_session, principal=partner, scope="needs_action"
    )
    assert needs["total"] == 2
    assert {r["status"] for r in needs["offers"]} == {"pending_approval", "approved"}

    all_board = await offer_service.list_org_offers(db_session, principal=partner, scope="all")
    assert all_board["total"] == 6
    # ``all`` puts LIVE offers before TERMINAL ones.
    statuses = [r["status"] for r in all_board["offers"]]
    live_positions = [i for i, s in enumerate(statuses) if s in {
        "draft",
        "pending_approval",
        "approved",
        "sent",
    }]
    term_positions = [i for i, s in enumerate(statuses) if s in {"declined", "rescinded"}]
    assert max(live_positions) < min(term_positions)


# --------------------------------------------------------------------------- #
# Offer board — pagination + row shape (comp decrypted)                        #
# --------------------------------------------------------------------------- #


async def test_offer_board_pagination(db_session) -> None:
    _porg, partner, _uni, _job, apps = await _org_with_apps(db_session, 3)
    for app_id, _student in apps:
        await _create_offer(db_session, partner=partner, app_id=app_id)

    page1 = await offer_service.list_org_offers(
        db_session, principal=partner, scope="all", limit=2, offset=0
    )
    assert page1["total"] == 3
    assert len(page1["offers"]) == 2

    page2 = await offer_service.list_org_offers(
        db_session, principal=partner, scope="all", limit=2, offset=2
    )
    assert page2["total"] == 3
    assert len(page2["offers"]) == 1

    seen = {r["id"] for r in page1["offers"]} | {r["id"] for r in page2["offers"]}
    assert len(seen) == 3


async def test_offer_board_row_shape_and_comp(db_session) -> None:
    _porg, partner, _uni, job_id, apps = await _org_with_apps(db_session, 1)
    await _create_offer(db_session, partner=partner, app_id=apps[0][0])

    board = await offer_service.list_org_offers(
        db_session, principal=partner, scope="all", locale="en"
    )
    row = board["offers"][0]
    assert set(row.keys()) == _OFFER_ROW_KEYS
    assert row["id"]
    assert row["application_id"] == str(apps[0][0])
    assert row["job_id"] == str(job_id)
    assert row["job_title"]
    assert row["candidate_handle"]  # applications are always identified
    assert row["position_title"] == "Backend Engineer"
    assert row["status"] == "draft"
    assert row["status_label"] == "Draft"
    assert row["is_live"] is True
    # Comp is DECRYPTED for the recruiter managing their own org's offers.
    assert row["salary_amount"] == _SALARY
    assert row["salary_currency"] == "VND"
    assert row["salary_period"] == "monthly"
    assert row["period_label"] == "month"  # en label
    assert row["sent_at"] is None
    assert row["approved_at"] is None
    assert row["created_at"]
