"""In-app Notification Center backend tests (autopilot slice 3).

Covers the recipient-scoped read API (list newest-first + unread_count, cursor
pagination, ``unread_only``, idempotent mark-one-read with ``404`` for a
non-recipient, mark-all-read), the ``create_in_app`` facade (vi/en rendering per
recipient locale, in-app preference gating, contact-PII safety), and that real
product events (apply / job-approve) write the expected feed row for the right
recipient with the right ``action_url``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.notifications.application import feed_service
from app.modules.notifications.domain.models import Notification
from app.modules.opportunities.application import job_service, moderation_service
from app.modules.recruitment.application import access, apply_service
from app.modules.users.domain.models import NotificationPreference
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal
from sqlalchemy import func, select

from tests.auth_utils import CTX, register_verified
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import (
    apply_payload,
    job_payload,
    make_builder_cv,
    publish_job,
)


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


def _email(prefix: str = "notif") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}@vinuni.edu.vn"


def _principal(user_id: uuid.UUID, persona: str = "student") -> Principal:
    # The read feed only requires an authenticated principal (recipient scoping is
    # the RBAC boundary), so any persona/permission set is fine here.
    return Principal(user_id=user_id, persona=persona, permissions=frozenset())


async def _seed(
    db, recipient_id: uuid.UUID, *, count: int, is_read: bool = False
) -> list[Notification]:
    """Insert ``count`` rows with strictly increasing ``created_at`` (deterministic
    newest-first ordering on SQLite, whose ``NOW()`` is only second-resolution)."""

    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows: list[Notification] = []
    for i in range(count):
        row = Notification(
            recipient_id=recipient_id,
            notif_type="recruitment.application_received",
            title=f"title-{i}",
            body=f"body-{i}",
            action_url=f"/partner/applications/{i}",
            is_read=is_read,
            channels=["in_app"],
            delivered_at={},
            created_at=base + timedelta(minutes=i),
        )
        db.add(row)
        rows.append(row)
    await db.commit()
    return rows


async def _count_rows(db, recipient_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_id == recipient_id)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Read API                                                                     #
# --------------------------------------------------------------------------- #


async def test_list_returns_only_own_rows_newest_first_with_unread_count(db_session):
    me = await register_verified(db_session, email=_email("me"))
    other = await register_verified(db_session, email=_email("other"))
    await _seed(db_session, me.id, count=3)
    await _seed(db_session, other.id, count=5)  # must never appear in my feed

    items, next_cursor, limit, unread = await feed_service.list_feed(
        db_session, principal=_principal(me.id)
    )
    assert len(items) == 3
    # Newest-first: the last-seeded (title-2) comes first.
    assert [i["title"] for i in items] == ["title-2", "title-1", "title-0"]
    assert next_cursor is None
    assert unread == 3
    # Feed item shape matches the contract (no internal fields leaked).
    assert set(items[0]) == {
        "id",
        "notif_type",
        "title",
        "body",
        "action_url",
        "is_read",
        "created_at",
    }


async def test_list_pagination_walks_with_cursor(db_session):
    me = await register_verified(db_session, email=_email("me"))
    await _seed(db_session, me.id, count=5)

    page1, cur1, _l, unread1 = await feed_service.list_feed(
        db_session, principal=_principal(me.id), limit=2
    )
    assert [i["title"] for i in page1] == ["title-4", "title-3"]
    assert cur1 is not None
    assert unread1 == 5  # total unread, independent of the page size

    page2, cur2, _l2, _u2 = await feed_service.list_feed(
        db_session, principal=_principal(me.id), limit=2, cursor=cur1
    )
    assert [i["title"] for i in page2] == ["title-2", "title-1"]
    assert cur2 is not None

    page3, cur3, _l3, _u3 = await feed_service.list_feed(
        db_session, principal=_principal(me.id), limit=2, cursor=cur2
    )
    assert [i["title"] for i in page3] == ["title-0"]
    assert cur3 is None


async def test_list_unread_only_filters_read_rows(db_session):
    me = await register_verified(db_session, email=_email("me"))
    read_rows = await _seed(db_session, me.id, count=2, is_read=True)
    await _seed(db_session, me.id, count=3, is_read=False)

    items, _c, _l, unread = await feed_service.list_feed(
        db_session, principal=_principal(me.id), unread_only=True
    )
    assert len(items) == 3
    assert all(i["is_read"] is False for i in items)
    assert unread == 3
    read_ids = {str(r.id) for r in read_rows}
    assert not ({i["id"] for i in items} & read_ids)


async def test_unread_count_endpoint(db_session):
    me = await register_verified(db_session, email=_email("me"))
    await _seed(db_session, me.id, count=2, is_read=True)
    await _seed(db_session, me.id, count=4, is_read=False)
    assert await feed_service.unread_count(db_session, principal=_principal(me.id)) == 4


async def test_mark_read_is_idempotent(db_session):
    me = await register_verified(db_session, email=_email("me"))
    rows = await _seed(db_session, me.id, count=2)
    target = rows[0]

    first = await feed_service.mark_read(
        db_session, principal=_principal(me.id), notification_id=target.id
    )
    assert first["status"] == "ok"
    assert first["is_read"] is True
    assert first["unread_count"] == 1

    # Replays do not error and do not change the count further.
    second = await feed_service.mark_read(
        db_session, principal=_principal(me.id), notification_id=target.id
    )
    assert second["unread_count"] == 1


async def test_mark_read_on_another_users_row_is_404_not_403(db_session):
    me = await register_verified(db_session, email=_email("me"))
    other = await register_verified(db_session, email=_email("other"))
    rows = await _seed(db_session, other.id, count=1)

    # A recipient acting on someone else's notification cannot tell it exists.
    with pytest.raises(ResourceNotFoundError):
        await feed_service.mark_read(
            db_session, principal=_principal(me.id), notification_id=rows[0].id
        )
    # Unknown id is likewise a 404.
    with pytest.raises(ResourceNotFoundError):
        await feed_service.mark_read(
            db_session, principal=_principal(me.id), notification_id=uuid.uuid4()
        )


async def test_mark_all_read_zeroes_unread(db_session):
    me = await register_verified(db_session, email=_email("me"))
    other = await register_verified(db_session, email=_email("other"))
    await _seed(db_session, me.id, count=4, is_read=False)
    await _seed(db_session, other.id, count=2, is_read=False)  # untouched

    result = await feed_service.mark_all_read(db_session, principal=_principal(me.id))
    assert result == {"updated": 4, "unread_count": 0}
    assert await feed_service.unread_count(db_session, principal=_principal(me.id)) == 0
    # The other user's unread is unaffected.
    assert await feed_service.unread_count(db_session, principal=_principal(other.id)) == 2


# --------------------------------------------------------------------------- #
# create_in_app facade                                                         #
# --------------------------------------------------------------------------- #


async def test_create_in_app_renders_vietnamese_for_vi_recipient(db_session):
    user = await register_verified(db_session, email=_email("vi"), locale="vi")
    row = await feed_service.create_in_app(
        db_session,
        recipient_id=user.id,
        notif_type="opportunities.job_approved",
        action_url="/partner/jobs/1",
        variables={"job_title": "Backend Intern"},
    )
    await db_session.commit()
    assert row is not None
    assert row.title == "Tin tuyển dụng đã được duyệt"
    assert "Backend Intern" in row.body
    assert "đã được duyệt" in row.body
    assert row.channels == ["in_app"]
    assert "in_app" in row.delivered_at


async def test_create_in_app_renders_english_for_en_recipient(db_session):
    user = await register_verified(db_session, email=_email("en"), locale="en")
    row = await feed_service.create_in_app(
        db_session,
        recipient_id=user.id,
        notif_type="opportunities.job_approved",
        action_url="/partner/jobs/1",
        variables={"job_title": "Backend Intern"},
    )
    await db_session.commit()
    assert row is not None
    assert row.title == "Job posting approved"
    assert "approved and is now live" in row.body


async def test_create_in_app_respects_in_app_disabled_preference(db_session):
    user = await register_verified(db_session, email=_email("muted"))
    # Mute the (non-mandatory) category that application notifs map to.
    db_session.add(
        NotificationPreference(user_id=user.id, category="application_status", in_app_enabled=False)
    )
    await db_session.commit()

    row = await feed_service.create_in_app(
        db_session,
        recipient_id=user.id,
        notif_type="recruitment.application_under_review",
        action_url="/student/applications/1",
        variables={"company_name": "Acme", "job_title": "X"},
    )
    await db_session.commit()
    assert row is None
    assert await _count_rows(db_session, user.id) == 0


async def test_create_in_app_dedupes_on_action_url(db_session):
    user = await register_verified(db_session, email=_email("dedupe"))
    a = await feed_service.create_in_app(
        db_session,
        recipient_id=user.id,
        notif_type="opportunities.job_approved",
        action_url="/partner/jobs/9",
        variables={"job_title": "X"},
    )
    b = await feed_service.create_in_app(
        db_session,
        recipient_id=user.id,
        notif_type="opportunities.job_approved",
        action_url="/partner/jobs/9",
        variables={"job_title": "X"},
    )
    await db_session.commit()
    assert a is not None and b is not None
    assert a.id == b.id
    assert await _count_rows(db_session, user.id) == 1


async def test_partner_facing_notification_uses_neutral_label_no_contact_pii(db_session):
    partner_user = await register_verified(db_session, email=_email("partner"))
    # Simulate the apply-flow variables (neutral "a candidate" label — no contact).
    student_email = "student.real@vinuni.edu.vn"
    row = await feed_service.create_in_app(
        db_session,
        recipient_id=partner_user.id,
        notif_type="recruitment.application_received",
        action_url="/partner/applications/42",
        variables={"job_title": "Backend Intern", "applicant_label": "một ứng viên"},
    )
    await db_session.commit()
    assert row is not None
    blob = f"{row.title} {row.body}"
    assert "một ứng viên" in blob
    assert student_email not in blob


# --------------------------------------------------------------------------- #
# Wired product events                                                          #
# --------------------------------------------------------------------------- #


async def _published(db, *, title="Live Job", **over):
    partner_user, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title, **over
    )
    return partner_user, partner, uni, job_id


async def _feed_for(db, recipient_id: uuid.UUID, notif_type: str) -> list[Notification]:
    return list(
        (
            await db.execute(
                select(Notification).where(
                    Notification.recipient_id == recipient_id,
                    Notification.notif_type == notif_type,
                )
            )
        )
        .scalars()
        .all()
    )


async def test_apply_creates_in_app_for_partner_with_neutral_label(db_session):
    partner_user, _partner, _uni, job_id = await _published(db_session)
    su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)

    app = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )

    rows = await _feed_for(db_session, partner_user.id, "recruitment.application_received")
    assert len(rows) == 1
    row = rows[0]
    assert row.action_url == f"/partner/applications/{app['id']}"
    # The feed row carries a neutral label + no contact PII (the real identity
    # lives on the application detail behind RBAC).
    blob = f"{row.title} {row.body}"
    assert su.email not in blob


async def test_job_approve_creates_in_app_for_partner(db_session):
    partner_user, partner, uni, _published_id = await _published(db_session)
    # A fresh job we approve explicitly so we can assert the approval feed row.
    created = await job_service.create_job(
        db_session, principal=partner, payload=job_payload("Data Intern"), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db_session, principal=partner, job_id=job_id, ctx=CTX)
    await moderation_service.approve_job(db_session, principal=uni, job_id=job_id, ctx=CTX)

    rows = await _feed_for(db_session, partner_user.id, "opportunities.job_approved")
    # The helper already approved one job; assert the new job produced its own row.
    mine = [r for r in rows if r.action_url == f"/partner/jobs/{job_id}"]
    assert len(mine) == 1
    assert "Data Intern" in mine[0].body
