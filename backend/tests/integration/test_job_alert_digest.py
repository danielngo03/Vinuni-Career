"""Scheduled AI job-alert EMAIL digest sweep (WS-15, Task N).

Covers:

- deterministic matching against the alert criteria (keyword match / no match),
  reusing the canonical public-visibility matcher (so a student is never digested
  a job they could not discover);
- delivery via the notifications OUTBOX + template renderer (email channel,
  template ``job.alert_digest``) — no synchronous SMTP;
- fires ONCE per (alert, digest-window): a second same-day sweep enqueues nothing
  (watermark + outbox dedupe_key);
- respects the ``job_alert`` email preference (``off`` -> no email enqueued);
- PII-safe payload (only the student's own alert name + public job titles + own
  contact; no provider/model/token internals);
- the optional AI summary line is metered (offline fake provider) and off by
  default (deterministic core always ships).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.notifications.application.template_seed import ensure_default_templates
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.opportunities.application import job_alert_digest_service
from app.modules.opportunities.domain.models import Job, JobAlert
from app.modules.users.domain.models import NotificationPreference
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents_utils import make_student

_FORBIDDEN = [
    "openrouter", "openai", "anthropic", "claude", "gpt-4", "gemini", "deepseek",
    "model_alias", "prompt_tokens", "completion_tokens", "provider", "usd",
]


def _now() -> datetime:
    return datetime.now(UTC)


def _make_job(session: AsyncSession, *, title: str, published_minutes_ago: int = 5) -> Job:
    now = _now()
    job = Job(
        org_id=uuid.uuid4(),
        posted_by=uuid.uuid4(),
        title=title,
        slug=f"slug-{uuid.uuid4().hex[:8]}",
        description="Test job",
        required_skills=[],
        employment_type="full_time",
        location_type="onsite",
        visibility="public",
        locations=[],
        status="active",
        moderation_status="approved",
        published_at=now - timedelta(minutes=published_minutes_ago),
        created_at=now - timedelta(minutes=published_minutes_ago + 1),
    )
    session.add(job)
    return job


def _make_alert(
    session: AsyncSession, *, user_id: uuid.UUID, keywords: str | None = None,
    name: str = "My Alert",
) -> JobAlert:
    alert = JobAlert(
        user_id=user_id, name=name, keywords=keywords, is_active=True,
    )
    session.add(alert)
    return alert


async def _outbox(session: AsyncSession) -> list[NotificationOutbox]:
    """Digest outbox rows only (the student registration flow also enqueues one)."""

    return list(
        (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.template_key == "job.alert_digest"
                )
            )
        )
        .scalars()
        .all()
    )


# --------------------------------------------------------------------------- #
# Deterministic matching + email delivery                                      #
# --------------------------------------------------------------------------- #


async def test_digest_enqueues_email_for_keyword_match(db_session) -> None:
    await ensure_default_templates(db_session)
    _u, student = await make_student(db_session)
    _make_job(db_session, title="Python Backend Engineer")
    _make_alert(db_session, user_id=student.user_id, keywords="python")
    await db_session.flush()

    result = await job_alert_digest_service.sweep_job_alert_digests(db_session, _now())
    assert result["digests_enqueued"] == 1

    rows = await _outbox(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.template_key == "job.alert_digest"
    assert row.channel == "email"
    assert row.recipient_id == student.user_id
    assert "Python Backend Engineer" in row.variables["job_lines"]
    assert row.variables["match_count"] == "1"
    # Default (offline) -> no AI summary line.
    assert row.variables["ai_summary"] == ""


async def test_digest_no_match_enqueues_nothing(db_session) -> None:
    await ensure_default_templates(db_session)
    _u, student = await make_student(db_session)
    _make_job(db_session, title="Marketing Specialist")
    _make_alert(db_session, user_id=student.user_id, keywords="python")
    await db_session.flush()

    result = await job_alert_digest_service.sweep_job_alert_digests(db_session, _now())
    assert result["digests_enqueued"] == 0
    assert result["skipped_no_match"] == 1
    assert await _outbox(db_session) == []


async def test_digest_is_pii_safe(db_session) -> None:
    await ensure_default_templates(db_session)
    _u, student = await make_student(db_session)
    _make_job(db_session, title="Python Backend Engineer")
    _make_alert(db_session, user_id=student.user_id, keywords="python")
    await db_session.flush()

    await job_alert_digest_service.sweep_job_alert_digests(db_session, _now())
    rows = await _outbox(db_session)
    blob = str(dict(rows[0].variables)).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term!r}"


# --------------------------------------------------------------------------- #
# Idempotency per (alert, window)                                              #
# --------------------------------------------------------------------------- #


async def test_digest_fires_once_per_window_watermark(db_session) -> None:
    await ensure_default_templates(db_session)
    _u, student = await make_student(db_session)
    _make_job(db_session, title="Python Backend Engineer")
    _make_alert(db_session, user_id=student.user_id, keywords="python")
    await db_session.flush()

    now = _now()
    r1 = await job_alert_digest_service.sweep_job_alert_digests(db_session, now)
    r2 = await job_alert_digest_service.sweep_job_alert_digests(db_session, now)
    assert r1["digests_enqueued"] == 1
    # Watermark advanced -> no new jobs after ``now`` -> nothing re-sent.
    assert r2["digests_enqueued"] == 0
    assert len(await _outbox(db_session)) == 1


async def test_digest_dedupe_key_blocks_second_send_same_day(db_session) -> None:
    """Even if the watermark is reset within the same day, the dedupe_key holds."""
    await ensure_default_templates(db_session)
    _u, student = await make_student(db_session)
    _make_job(db_session, title="Python Backend Engineer")
    alert = _make_alert(db_session, user_id=student.user_id, keywords="python")
    await db_session.flush()

    now = _now()
    await job_alert_digest_service.sweep_job_alert_digests(db_session, now)
    # Rewind the watermark so the same job matches again in the same window.
    alert.last_digest_at = now - timedelta(hours=2)
    await db_session.flush()

    result = await job_alert_digest_service.sweep_job_alert_digests(db_session, now)
    assert result["digests_enqueued"] == 0
    assert result["skipped_dupe"] == 1
    assert len(await _outbox(db_session)) == 1


# --------------------------------------------------------------------------- #
# Preferences                                                                  #
# --------------------------------------------------------------------------- #


async def test_digest_respects_email_off_preference(db_session) -> None:
    await ensure_default_templates(db_session)
    _u, student = await make_student(db_session)
    db_session.add(
        NotificationPreference(
            user_id=student.user_id,
            category="job_alert",
            in_app_enabled=True,
            email_setting="off",
        )
    )
    _make_job(db_session, title="Python Backend Engineer")
    _make_alert(db_session, user_id=student.user_id, keywords="python")
    await db_session.flush()

    result = await job_alert_digest_service.sweep_job_alert_digests(db_session, _now())
    assert result["digests_enqueued"] == 0
    assert result["skipped_pref_off"] == 1
    assert await _outbox(db_session) == []


# --------------------------------------------------------------------------- #
# Optional AI summary line (metered, offline fake provider)                     #
# --------------------------------------------------------------------------- #


async def test_digest_ai_summary_is_metered_when_enabled(db_session, monkeypatch) -> None:
    from app.ai.observability.models import AiBillableUsage
    from sqlalchemy import func

    await ensure_default_templates(db_session)
    _u, student = await make_student(db_session)
    _make_job(db_session, title="Python Backend Engineer")
    _make_alert(db_session, user_id=student.user_id, keywords="python")
    await db_session.flush()

    monkeypatch.setattr(
        job_alert_digest_service, "real_provider_active", lambda: True
    )

    async def _fake_generate(**kwargs):
        return "Có việc làm mới phù hợp với bạn — cùng xem ngay nhé!"

    monkeypatch.setattr(job_alert_digest_service, "generate_note", _fake_generate)

    now = _now()
    result = await job_alert_digest_service.sweep_job_alert_digests(db_session, now)
    assert result["digests_enqueued"] == 1
    assert result["ai_summaries"] == 1

    rows = await _outbox(db_session)
    assert "Có việc làm mới phù hợp" in rows[0].variables["ai_summary"]

    # Metered once per (alert, UTC-day).
    charged = (
        await db_session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.feature_key == "job_alert_digest",
                AiBillableUsage.actor_user_id == student.user_id,
            )
        )
    ).scalar_one()
    assert int(charged) == 2  # FEATURE_JOB_ALERT_DIGEST unit cost
