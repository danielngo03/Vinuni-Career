"""Integration tests for the saved-job application-deadline nudge sweep (WS-6).

Covers the WS-6 acceptance for the new student re-engagement notification:
- (a) a nudge fires ONCE at the threshold and not twice (idempotent dedupe);
- escalation from the T-48h to the T-24h window (each fires once);
- only the narrowest window fires for a job saved late;
- exclusion of jobs the student already applied to, non-visible jobs, and
  past-deadline jobs;
- (d) notification preferences are respected on BOTH channels;
- (e) the in-app feed row is PII-safe and the outbox row is the durable record.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.notifications.domain.models import Notification, NotificationOutbox
from app.modules.opportunities.application.saved_job_deadline_service import (
    sweep_saved_job_deadlines,
)
from app.modules.opportunities.domain.models import Job, SavedJob
from app.modules.recruitment.domain.models import Application
from app.modules.users.application import user_service
from app.modules.users.domain.models import NotificationPreference
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

_TEMPLATE_KEY = "job.saved_deadline"
_NOTIF_TYPE = "opportunities.saved_job_deadline"


def _now() -> datetime:
    return datetime.now(UTC)


async def _make_user(
    session: AsyncSession, *, full_name: str = "Nguyen Van A", lang: str = "vi"
):
    user = await user_service.create_user(
        session,
        email=f"student-{uuid.uuid4().hex[:10]}@vinuni.edu.vn",
        password_hash="hash",
        full_name=full_name,
        preferred_language=lang,
    )
    return user


async def _make_job(
    session: AsyncSession,
    *,
    application_deadline: datetime | None,
    title: str = "Backend Engineer",
    visibility: str = "public",
    status: str = "active",
    moderation_status: str = "approved",
) -> Job:
    now = _now()
    job = Job(
        org_id=uuid.uuid4(),
        posted_by=uuid.uuid4(),
        title=title,
        slug=f"slug-{uuid.uuid4().hex[:8]}",
        description="Build things.",
        required_skills=[],
        employment_type="full_time",
        location_type="onsite",
        visibility=visibility,
        application_deadline=application_deadline,
        locations=[],
        status=status,
        moderation_status=moderation_status,
        published_at=now - timedelta(days=1),
        created_at=now - timedelta(days=1, minutes=1),
    )
    session.add(job)
    await session.flush()  # populate job.id for SavedJob / Application FKs
    return job


def _save(session: AsyncSession, *, user_id: uuid.UUID, job: Job) -> None:
    session.add(SavedJob(user_id=user_id, job_id=job.id, org_id=job.org_id))


async def _outbox_rows(session: AsyncSession) -> list[NotificationOutbox]:
    return list(
        (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template_key == _TEMPLATE_KEY
                )
            )
        )
        .scalars()
        .all()
    )


async def _feed_count(session: AsyncSession, *, recipient_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == recipient_id,
                Notification.notif_type == _NOTIF_TYPE,
            )
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# (a) Idempotency: fires once at the threshold, not twice                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_deadline_nudge_fires_once_and_not_twice(db_session: AsyncSession) -> None:
    now = _now()
    user = await _make_user(db_session)
    job = await _make_job(db_session, application_deadline=now + timedelta(hours=40))
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    r1 = await sweep_saved_job_deadlines(db_session, now=now)
    assert r1["deadline_nudges"] == 1

    outbox = await _outbox_rows(db_session)
    assert len(outbox) == 1
    assert outbox[0].recipient_id == user.id
    assert outbox[0].dedupe_key is not None
    assert outbox[0].dedupe_key.endswith(":48h")
    assert await _feed_count(db_session, recipient_id=user.id) == 1

    # Re-running the sweep at the same tick enqueues nothing new.
    r2 = await sweep_saved_job_deadlines(db_session, now=now)
    assert r2["deadline_nudges"] == 0
    assert len(await _outbox_rows(db_session)) == 1
    assert await _feed_count(db_session, recipient_id=user.id) == 1


@pytest.mark.asyncio
async def test_deadline_nudge_not_fired_before_window(db_session: AsyncSession) -> None:
    now = _now()
    user = await _make_user(db_session)
    # Deadline 60h away — beyond the widest (48h) window/horizon.
    job = await _make_job(db_session, application_deadline=now + timedelta(hours=60))
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 0
    assert await _outbox_rows(db_session) == []


@pytest.mark.asyncio
async def test_deadline_nudge_escalates_to_24h_window(db_session: AsyncSession) -> None:
    now = _now()
    user = await _make_user(db_session)
    job = await _make_job(db_session, application_deadline=now + timedelta(hours=40))
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    r1 = await sweep_saved_job_deadlines(db_session, now=now)
    assert r1["deadline_nudges"] == 1  # T-48h nudge

    # 20h later the deadline is now within T-24h → the distinct T-24h nudge fires.
    later = now + timedelta(hours=20)
    r2 = await sweep_saved_job_deadlines(db_session, now=later)
    assert r2["deadline_nudges"] == 1  # T-24h nudge

    outbox = await _outbox_rows(db_session)
    windows = sorted(row.dedupe_key.split(":")[-1] for row in outbox)
    assert windows == ["24h", "48h"]
    assert await _feed_count(db_session, recipient_id=user.id) == 2


@pytest.mark.asyncio
async def test_deadline_nudge_late_save_fires_only_narrowest_window(
    db_session: AsyncSession,
) -> None:
    now = _now()
    user = await _make_user(db_session)
    # Saved with only 20h left — both windows are "open" but only T-24h should fire.
    job = await _make_job(db_session, application_deadline=now + timedelta(hours=20))
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 1
    outbox = await _outbox_rows(db_session)
    assert len(outbox) == 1
    assert outbox[0].dedupe_key.endswith(":24h")


# --------------------------------------------------------------------------- #
# Exclusions                                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_deadline_nudge_excludes_already_applied(
    db_session: AsyncSession,
) -> None:
    now = _now()
    user = await _make_user(db_session)
    job = await _make_job(db_session, application_deadline=now + timedelta(hours=40))
    _save(db_session, user_id=user.id, job=job)
    db_session.add(
        Application(
            job_id=job.id,
            applicant_id=user.id,
            org_id=job.org_id,
            status="submitted",
        )
    )
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 0
    assert await _outbox_rows(db_session) == []


@pytest.mark.asyncio
async def test_deadline_nudge_still_fires_after_withdrawal(
    db_session: AsyncSession,
) -> None:
    now = _now()
    user = await _make_user(db_session)
    job = await _make_job(db_session, application_deadline=now + timedelta(hours=40))
    _save(db_session, user_id=user.id, job=job)
    # A WITHDRAWN application does not count as "already applied" — the student
    # can re-apply, so the deadline nudge is still useful.
    db_session.add(
        Application(
            job_id=job.id,
            applicant_id=user.id,
            org_id=job.org_id,
            status="withdrawn",
        )
    )
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 1


@pytest.mark.asyncio
async def test_deadline_nudge_excludes_closed_job(db_session: AsyncSession) -> None:
    now = _now()
    user = await _make_user(db_session)
    job = await _make_job(
        db_session, application_deadline=now + timedelta(hours=40), status="closed"
    )
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 0


@pytest.mark.asyncio
async def test_deadline_nudge_excludes_invitation_only_job(
    db_session: AsyncSession,
) -> None:
    now = _now()
    user = await _make_user(db_session)
    job = await _make_job(
        db_session,
        application_deadline=now + timedelta(hours=40),
        visibility="invitation_only",
    )
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 0


@pytest.mark.asyncio
async def test_deadline_nudge_excludes_past_deadline_job(
    db_session: AsyncSession,
) -> None:
    now = _now()
    user = await _make_user(db_session)
    job = await _make_job(db_session, application_deadline=now - timedelta(hours=1))
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 0


# --------------------------------------------------------------------------- #
# (d) Notification preferences respected                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_deadline_nudge_respects_muted_in_app_preference(
    db_session: AsyncSession,
) -> None:
    now = _now()
    user = await _make_user(db_session)
    db_session.add(
        NotificationPreference(
            user_id=user.id,
            category="job_deadline",
            in_app_enabled=False,
            email_setting="immediate",
        )
    )
    job = await _make_job(db_session, application_deadline=now + timedelta(hours=40))
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 1  # email still enqueued
    # In-app feed row is suppressed by the muted preference.
    assert await _feed_count(db_session, recipient_id=user.id) == 0
    # Email channel still enqueued (email preference is default/immediate).
    assert len(await _outbox_rows(db_session)) == 1


@pytest.mark.asyncio
async def test_deadline_nudge_respects_email_off_preference(
    db_session: AsyncSession,
) -> None:
    now = _now()
    user = await _make_user(db_session)
    db_session.add(
        NotificationPreference(
            user_id=user.id,
            category="job_deadline",
            in_app_enabled=True,
            email_setting="off",
        )
    )
    job = await _make_job(db_session, application_deadline=now + timedelta(hours=40))
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    result = await sweep_saved_job_deadlines(db_session, now=now)
    assert result["deadline_nudges"] == 1  # in-app still created
    # Email suppressed; in-app feed row still created.
    assert await _outbox_rows(db_session) == []
    assert await _feed_count(db_session, recipient_id=user.id) == 1


# --------------------------------------------------------------------------- #
# (e) PII-safe + durable send record                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_deadline_nudge_feed_is_pii_safe_and_outbox_is_durable_record(
    db_session: AsyncSession,
) -> None:
    now = _now()
    user = await _make_user(db_session, full_name="Tran Thi Bich")
    job = await _make_job(
        db_session,
        application_deadline=now + timedelta(hours=40),
        title="Data Analyst",
    )
    _save(db_session, user_id=user.id, job=job)
    await db_session.flush()

    await sweep_saved_job_deadlines(db_session, now=now)

    # The in-app feed row carries NO PII (no recipient name/email) — only the job
    # title + deadline (spec §9: in-app rows can surface on lock screens).
    feed = (
        await db_session.execute(
            select(Notification).where(
                Notification.recipient_id == user.id,
                Notification.notif_type == _NOTIF_TYPE,
            )
        )
    ).scalar_one()
    blob = f"{feed.title}\n{feed.body}"
    assert user.email not in blob
    assert "Tran Thi Bich" not in blob
    assert "Data Analyst" in blob

    # The outbox row is the durable, auditable send record (spec §4/§7):
    # recipient + template key + a per-(job, user, window) dedupe key.
    outbox = await _outbox_rows(db_session)
    assert len(outbox) == 1
    assert outbox[0].recipient_id == user.id
    assert outbox[0].template_key == _TEMPLATE_KEY
    assert outbox[0].dedupe_key.startswith(f"saved_job.deadline_nudge:{job.id}:")
