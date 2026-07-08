"""Outbox writes and notification dispatch via console adapter (no real SMTP)."""

from __future__ import annotations

import uuid

from app.modules.notifications.application.dispatch_service import (
    enqueue_notification,
    process_outbox,
)
from app.modules.notifications.domain.models import (
    NotificationOutbox,
    NotificationTemplate,
)
from app.modules.notifications.infrastructure.email_adapter import ConsoleEmailAdapter
from app.shared.models import OutboxEvent
from sqlalchemy import select


async def test_outbox_event_write(db_session) -> None:
    event = OutboxEvent(
        aggregate_type="application",
        aggregate_id=uuid.uuid4(),
        event_type="application.submitted",
        payload={"job_id": str(uuid.uuid4())},
    )
    db_session.add(event)
    await db_session.commit()

    row = (
        await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.id == event.id)
        )
    ).scalar_one()
    assert row.event_type == "application.submitted"
    assert row.published_at is None  # unpublished by default


async def test_enqueue_and_dispatch_email(db_session) -> None:
    template = NotificationTemplate(
        owner_scope="university",
        key="application.status_changed",
        channel="email",
        locale="vi",
        status="active",
        subject="Cập nhật đơn ứng tuyển {{job_title}}",
        body="Chào {{name}}, đơn của bạn cho {{job_title}} đã được cập nhật.",
        variables_schema={
            "allowed": ["name", "job_title", "email"],
            "required": ["name", "job_title"],
        },
    )
    db_session.add(template)
    await db_session.flush()

    await enqueue_notification(
        db_session,
        recipient_id=uuid.uuid4(),
        template_key="application.status_changed",
        channel="email",
        locale="vi",
        variables={"name": "An", "job_title": "Backend Intern", "email": "an@example.com"},
    )
    await db_session.commit()

    adapter = ConsoleEmailAdapter()
    counts = await process_outbox(db_session, email_adapter=adapter)
    await db_session.commit()

    assert counts["sent"] == 1
    assert len(adapter.outbox) == 1
    assert "An" in adapter.outbox[0].body

    rows = (await db_session.execute(select(NotificationOutbox))).scalars().all()
    assert all(r.status == "sent" for r in rows)


async def test_dispatch_idempotent_no_reprocess(db_session) -> None:
    # Second run finds no pending rows -> nothing sent again.
    counts = await process_outbox(db_session, email_adapter=ConsoleEmailAdapter())
    assert counts["sent"] == 0


async def test_missing_template_marks_failed(db_session) -> None:
    await enqueue_notification(
        db_session,
        recipient_id=uuid.uuid4(),
        template_key="does.not.exist",
        channel="email",
        locale="vi",
        variables={"email": "x@example.com"},
    )
    await db_session.commit()

    counts = await process_outbox(db_session, email_adapter=ConsoleEmailAdapter())
    await db_session.commit()
    assert counts["failed"] >= 1
