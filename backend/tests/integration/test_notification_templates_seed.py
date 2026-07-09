"""Default-template seeding + rendering for the three account.* emails.

Verifies the seeder is idempotent and that ``process_outbox`` renders each seeded
template (vi + en) — with required-variable validation passing and frontend
``action_url`` values accepted by the renderer's allowlist.
"""

from __future__ import annotations

import uuid

from app.modules.notifications.application.dispatch_service import (
    enqueue_notification,
    process_outbox,
)
from app.modules.notifications.application.template_seed import (
    DEFAULT_TEMPLATES,
    ensure_default_templates,
)
from app.modules.notifications.domain.models import (
    NotificationOutbox,
    NotificationTemplate,
)
from app.modules.notifications.infrastructure.email_adapter import ConsoleEmailAdapter
from sqlalchemy import select


def _expected_template_count() -> int:
    return sum(len(spec["locales"]) for spec in DEFAULT_TEMPLATES)


async def test_seed_is_idempotent(db_session) -> None:
    expected_total = _expected_template_count()
    created_first = await ensure_default_templates(db_session)
    await db_session.commit()
    assert created_first == expected_total

    created_second = await ensure_default_templates(db_session)
    await db_session.commit()
    assert created_second == 0

    total = (
        await db_session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.status == "active"
            )
        )
    ).scalars().all()
    assert len(total) == expected_total


async def test_seeded_templates_render_for_all_locales(db_session) -> None:
    await ensure_default_templates(db_session)
    await db_session.commit()

    recipient = uuid.uuid4()
    expected = 0
    for spec in DEFAULT_TEMPLATES:
        for locale in spec["locales"]:
            # Supply every allowed variable so each template's required set is met.
            variables: dict[str, object] = {
                "email": "user@vinuni.edu.vn",
                "name": "Lan",
                "company_name": "Acme Corp",
                "org_name": "Acme Corp",
                "job_title": "Software Engineer Intern",
                "reason": "Hồ sơ chưa đầy đủ.",
                "token": "abc",
                "applicant_label": "một ứng viên",
                "decision_label": "Đã chấp nhận",
                "event_title": "Career Day 2026",
                "starts_at": "2026-07-01T09:00:00+07:00",
                "venue_or_format": "VinUni Campus",
                "waitlist_position": 3,
                "sender_label": "Acme Corp",
                "counterpart_label": "Acme Corp",
                "provider": "Google",
                "otp_code": "123456",
                "ttl_minutes": "10",
            }
            if "action_url" in spec["variables_schema"]["allowed"]:
                variables["action_url"] = (
                    f"http://localhost:3000/{locale}/auth/verify-email?token=abc"
                )
            await enqueue_notification(
                db_session,
                recipient_id=recipient,
                template_key=spec["key"],
                channel="email",
                locale=locale,
                variables=variables,
            )
            expected += 1
    await db_session.commit()

    adapter = ConsoleEmailAdapter()
    # Drain every enqueued row in one pass (the default limit=50 would otherwise
    # leave the tail of a >50-template catalog unprocessed).
    counts = await process_outbox(
        db_session, email_adapter=adapter, limit=expected + 10
    )
    await db_session.commit()

    # Every seeded template rendered + "sent"; none failed required/unknown checks.
    assert counts["sent"] == expected
    assert counts["failed"] == 0
    rows = (
        await db_session.execute(select(NotificationOutbox))
    ).scalars().all()
    assert all(r.status == "sent" for r in rows)
    # Personalisation substituted (name appears in at least one rendered body).
    assert any("Lan" in mail.body for mail in adapter.outbox)
