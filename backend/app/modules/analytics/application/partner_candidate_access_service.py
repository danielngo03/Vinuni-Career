"""``partner_candidate_access_events`` writer + reader (spec §"Recruiting
Intelligence Read Models" -> ``partner_candidate_access_events``).

:func:`record_access_event` is called from ``recruitment`` at the exact points
where a partner touches a candidate's application/CV/identity — it is
instrumentation ONLY (no business-logic change at the call site) and never
raises: a logging failure must never block a legitimate CV download or reveal
decision. :func:`list_access_events` / :func:`detect_access_alerts` are the
RBAC-gated reads that power the "who viewed which CV" compliance surface and
the dashboard's ``access_alerts`` widget.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.domain.partner_read_models import PartnerCandidateAccessEvent
from app.modules.opportunities.application import job_read_facade
from app.modules.users.application import user_service

logger = logging.getLogger(__name__)

EVENT_TYPES: frozenset[str] = frozenset(
    {
        "application_opened",
        "cv_previewed",
        "cv_downloaded",
        "identity_reveal_requested",
        "identity_revealed_viewed",
    }
)

_ALERT_LABELS = {
    "vi": {
        "cv_download_spike": "Số lượt tải CV bất thường trong 24 giờ qua",
        "reveal_spike": "Số yêu cầu tiết lộ danh tính tăng bất thường trong 24 giờ qua",
    },
    "en": {
        "cv_download_spike": "Unusual CV download volume in the last 24h",
        "reveal_spike": "Unusual identity-reveal request volume in the last 24h",
    },
}

# A single actor downloading/reveal-requesting more than this many distinct
# applications in 24h is flagged for a human look — not blocked, just surfaced.
_CV_DOWNLOAD_ALERT_THRESHOLD = 15
_REVEAL_ALERT_THRESHOLD = 8


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def record_access_event(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    application_id: uuid.UUID,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID | None,
    event_type: str,
    actor_department_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> None:
    if event_type not in EVENT_TYPES:
        logger.warning(
            "partner_candidate_access.unknown_event_type", extra={"event_type": event_type}
        )
        return
    try:
        async with session.begin_nested():
            session.add(
                PartnerCandidateAccessEvent(
                    org_id=org_id,
                    actor_id=actor_id,
                    actor_department_id=actor_department_id,
                    application_id=application_id,
                    job_id=job_id,
                    candidate_id=candidate_id,
                    event_type=event_type,
                    reason=reason,
                )
            )
            await session.flush()
    except Exception:  # noqa: BLE001 — audit instrumentation must never break the read/download
        logger.warning(
            "partner_candidate_access.record_failed",
            extra={"event_type": event_type, "application_id": str(application_id)},
        )


async def list_access_events(
    session: AsyncSession, *, org_id: uuid.UUID, limit: int = 50
) -> list[dict]:
    """Newest-first access log for the org — the compliance/security review view.

    Never surfaces candidate name/email; only the application/job reference and
    the acting partner member, so a security reviewer can correlate with the
    application detail (which itself enforces the reveal gate) without this log
    becoming a second identity-leak surface.
    """

    rows = (
        (
            await session.execute(
                select(PartnerCandidateAccessEvent)
                .where(PartnerCandidateAccessEvent.org_id == org_id)
                .order_by(PartnerCandidateAccessEvent.occurred_at.desc())
                .limit(max(limit, 1))
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return []

    job_ids = {r.job_id for r in rows}
    titles = await job_read_facade.get_job_titles(session, job_ids)
    actor_ids = {r.actor_id for r in rows if r.actor_id is not None}
    actor_names: dict[uuid.UUID, str | None] = {}
    for actor_id in actor_ids:
        user = await user_service.get_by_id(session, actor_id)
        actor_names[actor_id] = user.full_name if user else None

    return [
        {
            "id": r.id,
            "event_type": r.event_type,
            "application_id": str(r.application_id),
            "job_title": titles.get(r.job_id) or "—",
            "actor_name": actor_names.get(r.actor_id) if r.actor_id else None,
            "reason": r.reason,
            "occurred_at": r.occurred_at.isoformat(),
        }
        for r in rows
    ]


async def detect_access_alerts(
    session: AsyncSession, *, org_id: uuid.UUID, locale: str = "vi"
) -> list[dict]:
    """Best-effort anomaly surface: unusual CV-download or reveal-request volume
    by a single actor in the trailing 24h. Returns ``[]`` (never fabricated
    alerts) when nothing crosses the threshold."""

    since = _now() - timedelta(hours=24)
    rows = (
        await session.execute(
            select(
                PartnerCandidateAccessEvent.actor_id,
                PartnerCandidateAccessEvent.event_type,
            ).where(
                PartnerCandidateAccessEvent.org_id == org_id,
                PartnerCandidateAccessEvent.occurred_at >= since,
            )
        )
    ).all()
    if not rows:
        return []

    by_actor_download: Counter[uuid.UUID] = Counter()
    by_actor_reveal: Counter[uuid.UUID] = Counter()
    for actor_id, event_type in rows:
        if actor_id is None:
            continue
        if event_type == "cv_downloaded":
            by_actor_download[actor_id] += 1
        elif event_type == "identity_reveal_requested":
            by_actor_reveal[actor_id] += 1

    labels = _ALERT_LABELS.get(locale, _ALERT_LABELS["vi"])
    alerts: list[dict] = []
    for actor_id, count in by_actor_download.items():
        if count >= _CV_DOWNLOAD_ALERT_THRESHOLD:
            user = await user_service.get_by_id(session, actor_id)
            alerts.append(
                {
                    "code": "cv_download_spike",
                    "label": labels["cv_download_spike"],
                    "actor_name": user.full_name if user else None,
                    "count": count,
                    "window_hours": 24,
                }
            )
    for actor_id, count in by_actor_reveal.items():
        if count >= _REVEAL_ALERT_THRESHOLD:
            user = await user_service.get_by_id(session, actor_id)
            alerts.append(
                {
                    "code": "reveal_spike",
                    "label": labels["reveal_spike"],
                    "actor_name": user.full_name if user else None,
                    "count": count,
                    "window_hours": 24,
                }
            )
    return alerts
