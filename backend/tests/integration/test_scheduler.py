"""Async scheduler + periodic-job tests (ADR-0003 §5).

Each test drives the scheduler's single-tick entrypoint (``runner.tick`` /
``runner.run_job``) — never the underlying ``process_outbox`` / ``sweep_*``
functions directly — so the assertion proves the job runs *as scheduled*. All run
on the SQLite unit path (the PG-only ``FOR UPDATE SKIP LOCKED`` claim is
dialect-guarded and inert here).

Covered:
- outbox.drain: a pending row is delivered (``sent``) by a tick; re-tick is a no-op.
- retry/dead-letter: a forced send failure retries with backoff, then dead-letters
  after ``outbox_max_attempts`` ticks.
- opportunities.deadline_close: an active job past its deadline auto-closes via the
  sweep with exactly one (idempotent) close notification.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.automation.scheduler import runner
from app.modules.notifications.application import dispatch_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.notifications.domain.models import (
    NotificationOutbox,
    NotificationTemplate,
)
from app.modules.opportunities.application import job_service
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import publish_job


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _seed_template(session, *, key: str) -> None:
    session.add(
        NotificationTemplate(
            owner_scope="university",
            key=key,
            channel="email",
            locale="vi",
            status="active",
            subject="Thông báo {{job_title}}",
            body="Chào {{name}}, cập nhật cho {{job_title}}.",
            variables_schema={
                "allowed": ["name", "job_title", "email"],
                "required": ["job_title"],
            },
        )
    )
    await session.flush()


# --------------------------------------------------------------------------- #
# (a) outbox.drain delivers a pending row via a tick                          #
# --------------------------------------------------------------------------- #


async def test_tick_drains_pending_outbox_to_sent(db_session) -> None:
    await _seed_template(db_session, key="application.status_changed")
    await enqueue_notification(
        db_session,
        recipient_id=uuid.uuid4(),
        template_key="application.status_changed",
        channel="email",
        locale="vi",
        variables={"name": "An", "job_title": "Backend Intern", "email": "an@x.com"},
    )
    await db_session.commit()

    # Drive the SCHEDULER, not process_outbox directly. (Release any read lock the
    # test session holds so the scheduler's own session can write under SQLite.)
    await db_session.rollback()
    results = await runner.tick(_now(), session_factory=get_sessionmaker())
    assert "outbox.drain" in results
    assert results["outbox.drain"]["sent"] == 1

    rows = (await db_session.execute(select(NotificationOutbox))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "sent"
    assert rows[0].sent_at is not None
    assert rows[0].next_attempt_at is None

    # Second tick: nothing pending -> no re-send (idempotent).
    await db_session.rollback()
    again = await runner.tick(_now(), session_factory=get_sessionmaker())
    assert again["outbox.drain"]["sent"] == 0


# --------------------------------------------------------------------------- #
# (b) forced send-failure -> retry with backoff -> dead after max attempts    #
# --------------------------------------------------------------------------- #


class _FailingAdapter:
    async def send(self, *, to: str, subject: str, body: str) -> str:
        raise RuntimeError("smtp down")


async def test_tick_retries_then_dead_letters(db_session, monkeypatch) -> None:
    # Inject a stub adapter that always raises, via the default construction path
    # inside process_outbox (the scheduler calls it without an explicit adapter,
    # so it builds one through ``build_email_adapter``).
    monkeypatch.setattr(dispatch_service, "build_email_adapter", lambda: _FailingAdapter())

    await _seed_template(db_session, key="application.status_changed")
    await enqueue_notification(
        db_session,
        recipient_id=uuid.uuid4(),
        template_key="application.status_changed",
        channel="email",
        locale="vi",
        variables={"name": "An", "job_title": "Backend Intern", "email": "an@x.com"},
    )
    await db_session.commit()

    max_attempts = get_settings().outbox_max_attempts
    assert max_attempts == 5

    sm = get_sessionmaker()
    base = _now()

    async def _row() -> NotificationOutbox:
        # Fresh read in a new transaction so the scheduler's commits are visible.
        await db_session.rollback()
        return (await db_session.execute(select(NotificationOutbox))).scalar_one()

    # First tick: transient failure -> still pending, attempts=1, backoff set.
    await db_session.rollback()
    res1 = await runner.run_job("outbox.drain", session_factory=sm, now=base)
    assert res1 == {"sent": 0, "failed": 0, "skipped": 0, "retry": 1, "dead": 0}
    row = await _row()
    assert row.status == "pending"
    assert row.attempts == 1
    assert row.error_code == "SEND_FAILED"
    assert row.next_attempt_at is not None

    # Advance well past each backoff window so the row is reclaimed every tick.
    for i in range(2, max_attempts):
        await db_session.rollback()
        await runner.run_job("outbox.drain", session_factory=sm, now=base + timedelta(days=i))
        row = await _row()
        assert row.status == "pending"
        assert row.attempts == i

    # Final attempt crosses the threshold -> dead-letter (terminal).
    await db_session.rollback()
    res_final = await runner.run_job(
        "outbox.drain", session_factory=sm, now=base + timedelta(days=max_attempts)
    )
    assert res_final["dead"] == 1
    row = await _row()
    assert row.status == "dead"
    assert row.attempts == max_attempts

    # A dead row is never reclaimed again.
    await db_session.rollback()
    res_after = await runner.run_job(
        "outbox.drain", session_factory=sm, now=base + timedelta(days=max_attempts + 1)
    )
    assert res_after["dead"] == 0 and res_after["retry"] == 0


# --------------------------------------------------------------------------- #
# (c) job deadline auto-close sweep + idempotent close notification           #
# --------------------------------------------------------------------------- #


async def _close_notif_count(db_session, job_id) -> int:
    return (
        await db_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.dedupe_key == f"job.auto_closed:{job_id}")
        )
    ).scalar_one()


async def test_tick_auto_closes_past_deadline_job_once(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    past = _now() - timedelta(days=1)
    job_id = await publish_job(
        db_session,
        partner_principal=partner,
        uni_principal=uni,
        title="Expiring Job",
        application_deadline=past,
    )

    await db_session.rollback()
    results = await runner.tick(_now(), session_factory=get_sessionmaker())
    assert results["opportunities.deadline_close"]["closed"] == 1

    await db_session.rollback()
    detail = await job_service.get_job(db_session, principal=partner, job_id=job_id)
    assert detail["status"] == "closed"

    # Exactly one deduped partner close notification + an audit row.
    assert await _close_notif_count(db_session, job_id) == 1
    audit = (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "job.auto_closed")
        )
    ).scalar_one()
    assert audit == 1

    # Re-tick: the now-closed job is excluded -> no duplicate close/notification.
    await db_session.rollback()
    again = await runner.tick(_now(), session_factory=get_sessionmaker())
    assert again["opportunities.deadline_close"]["closed"] == 0
    await db_session.rollback()
    assert await _close_notif_count(db_session, job_id) == 1
