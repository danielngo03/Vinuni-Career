"""Outbox-based notification dispatch.

Product writes call :func:`enqueue_notification` inside their own transaction —
this only writes a ``notification_outbox`` row and never contacts SMTP/push.
A worker later calls :func:`process_outbox` to render the active template and
deliver via the channel adapter, recording per-row delivery status idempotently
(``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §7).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.analytics.application import ingestion_service as analytics
from app.modules.notifications.application.template_renderer import render
from app.modules.notifications.domain.models import (
    NotificationOutbox,
    NotificationTemplate,
)
from app.modules.notifications.infrastructure.email_adapter import (
    EmailAdapter,
    build_email_adapter,
)
from app.shared.exceptions import ValidationFailedError

logger = logging.getLogger(__name__)


async def enqueue_notification(
    session: AsyncSession,
    *,
    recipient_id: uuid.UUID | None,
    template_key: str,
    channel: str,
    locale: str,
    variables: dict[str, object],
    dedupe_key: str | None = None,
) -> NotificationOutbox:
    """Write a pending outbox row in the caller's transaction (no send)."""

    row = NotificationOutbox(
        recipient_id=recipient_id,
        template_key=template_key,
        channel=channel,
        locale=locale,
        variables=variables,
        status="pending",
        dedupe_key=dedupe_key,
    )
    session.add(row)
    await session.flush()
    return row


async def get_outbox_row(
    session: AsyncSession, *, outbox_id: uuid.UUID
) -> NotificationOutbox | None:
    """Single-row lookup — the seam ``platform_support`` reads/mutates through."""

    return (
        await session.execute(select(NotificationOutbox).where(NotificationOutbox.id == outbox_id))
    ).scalar_one_or_none()


async def status_counts(session: AsyncSession) -> dict[str, int]:
    """Read-only outbox health counts, keyed by ``status`` (``support:read``)."""

    rows = (
        await session.execute(
            select(NotificationOutbox.status, func.count()).group_by(NotificationOutbox.status)
        )
    ).all()
    counts = {"pending": 0, "sent": 0, "failed": 0, "skipped": 0, "dead": 0}
    for status, count in rows:
        counts[status] = int(count)
    return counts


async def oldest_pending_age_seconds(
    session: AsyncSession, *, now: datetime | None = None
) -> int | None:
    """Age (seconds) of the oldest ``pending`` row, or ``None`` if none pending."""

    now = now or datetime.now(tz=UTC)
    oldest = (
        await session.execute(
            select(NotificationOutbox.created_at)
            .where(NotificationOutbox.status == "pending")
            .order_by(NotificationOutbox.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if oldest is None:
        return None
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    return int((now - oldest).total_seconds())


async def retry_scheduled_count(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Count of ``pending`` rows backoff-scheduled into the future (``retry_scheduled``)."""

    now = now or datetime.now(tz=UTC)
    return (
        await session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(
                NotificationOutbox.status == "pending",
                NotificationOutbox.next_attempt_at.is_not(None),
                NotificationOutbox.next_attempt_at > now,
            )
        )
    ).scalar_one()


async def requeue_dead_letter(session: AsyncSession, *, outbox_id: uuid.UUID) -> NotificationOutbox:
    """Re-arm a dead-lettered row for redelivery (support-console requeue action).

    Only legal on ``status="dead"`` rows — the caller (``platform_support``)
    is responsible for raising the user-safe 409 ``not_dead_lettered`` when
    this raises :class:`ValueError`. Resets exactly the fields
    :func:`process_outbox` reads to reconsider a row for delivery.
    """

    row = await get_outbox_row(session, outbox_id=outbox_id)
    if row is None or row.status != "dead":
        raise ValueError("not_dead_lettered")
    row.status = "pending"
    row.attempts = 0
    row.next_attempt_at = None
    row.error_code = None
    await session.flush()
    return row


async def dedupe_exists(session: AsyncSession, *, dedupe_key: str) -> bool:
    """``True`` iff a (any-status) outbox row already exists for ``dedupe_key``.

    The cross-module seam other modules use to check-before-enqueue instead of
    importing ``NotificationOutbox`` directly.
    """

    return (
        await session.execute(
            select(NotificationOutbox.id).where(NotificationOutbox.dedupe_key == dedupe_key)
        )
    ).first() is not None


async def _active_template(
    session: AsyncSession, *, key: str, channel: str, locale: str
) -> NotificationTemplate | None:
    stmt = (
        select(NotificationTemplate)
        .where(
            NotificationTemplate.key == key,
            NotificationTemplate.channel == channel,
            NotificationTemplate.locale == locale,
            NotificationTemplate.status == "active",
        )
        .order_by(NotificationTemplate.version.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _backoff_seconds(attempts: int) -> int:
    """Exponential backoff for a transient send failure (ADR-0003 §3).

    ``min(BASE * 2**(attempts-1), CAP)`` with BASE=60s, CAP=1h. ``attempts`` is the
    number of delivery attempts made so far (>= 1 when called).
    """

    base, cap = 60, 3600
    return min(base * (2 ** max(attempts - 1, 0)), cap)


async def process_outbox(
    session: AsyncSession,
    *,
    email_adapter: EmailAdapter | None = None,
    limit: int = 50,
    action_url_allowlist: set[str] | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Render + deliver due ``pending`` outbox rows. Returns a per-status count.

    Idempotent + at-least-once safe: only ``pending`` rows whose ``next_attempt_at``
    is null/past are claimed; terminal states (``sent``/``failed``/``skipped``/
    ``dead``) are never reprocessed. A transient adapter failure keeps the row
    ``pending`` with an exponential ``next_attempt_at`` until ``outbox_max_attempts``
    is reached, after which it becomes terminal ``dead`` (dead-letter). Permanent
    template/render errors are terminal ``failed`` (no retry).

    On PostgreSQL the claim select uses ``FOR UPDATE SKIP LOCKED`` so multiple
    drainers never double-send; the clause is dialect-guarded and inert on SQLite.
    """

    settings = get_settings()
    adapter = email_adapter or build_email_adapter()
    now = now or datetime.now(tz=UTC)
    max_attempts = settings.outbox_max_attempts
    if action_url_allowlist is None:
        # Default-trust our own backend + public web app origins so account
        # emails (verification / reset) with absolute frontend links render.
        action_url_allowlist = {settings.frontend_url, settings.app_url}
    stmt = (
        select(NotificationOutbox)
        .where(
            NotificationOutbox.status == "pending",
            or_(
                NotificationOutbox.next_attempt_at.is_(None),
                NotificationOutbox.next_attempt_at <= now,
            ),
        )
        .order_by(NotificationOutbox.created_at)
        .limit(limit)
    )
    # Prod-readiness for the Celery/multi-worker path; inert on the SQLite unit DB.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    rows = list((await session.execute(stmt)).scalars().all())
    counts = {"sent": 0, "failed": 0, "skipped": 0, "retry": 0, "dead": 0}

    for row in rows:
        row.attempts += 1
        template = await _active_template(
            session, key=row.template_key, channel=row.channel, locale=row.locale
        )
        if template is None:
            row.status = "failed"
            row.error_code = "TEMPLATE_NOT_FOUND"
            counts["failed"] += 1
            logger.warning(
                "notification.template_missing",
                extra={"template_key": row.template_key, "channel": row.channel},
            )
            continue

        try:
            rendered = render(
                body=template.body,
                subject=template.subject,
                title=template.title,
                variables=dict(row.variables),
                variables_schema=dict(template.variables_schema),
                action_url_allowlist=action_url_allowlist,
            )
        except ValidationFailedError as exc:
            row.status = "failed"
            row.error_code = "TEMPLATE_VARIABLE_ERROR"
            counts["failed"] += 1
            logger.warning(
                "notification.render_failed",
                extra={"template_key": row.template_key, "detail": exc.details},
            )
            continue

        try:
            if row.channel == "email":
                to = str(row.variables.get("email", "")) or "unknown@local"
                await adapter.send(
                    to=to,
                    subject=rendered.subject or rendered.title or "Thông báo",
                    body=rendered.body,
                )
        except Exception:  # noqa: BLE001 - transient delivery failure -> retry/dead
            # A single adapter failure must NOT roll back the batch: keep this row
            # pending with backoff (or dead-letter it) and continue with the rest.
            row.error_code = "SEND_FAILED"
            if row.attempts >= max_attempts:
                row.status = "dead"
                counts["dead"] += 1
                logger.warning(
                    "notification.dead_letter",
                    extra={"template_key": row.template_key, "attempts": row.attempts},
                )
            else:
                row.next_attempt_at = now + timedelta(seconds=_backoff_seconds(row.attempts))
                counts["retry"] += 1
                logger.info(
                    "notification.send_retry",
                    extra={"template_key": row.template_key, "attempts": row.attempts},
                )
            continue

        row.status = "sent"
        row.error_code = None
        row.next_attempt_at = None
        row.sent_at = now
        counts["sent"] += 1
        await analytics.record_event_safe(
            session,
            event_type="notification.sent",
            aggregate_type="notification",
            aggregate_id=row.id,
            actor_type="system",
            properties={
                "template_key": row.template_key,
                "channel": row.channel,
                "recipient_id": str(row.recipient_id) if row.recipient_id else None,
            },
        )

    await session.flush()
    return counts
