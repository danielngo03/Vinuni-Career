"""Retention read + scheduled enforcement (``docs/DATA_MODEL.md`` §35).

The read-only text presenter is public/authenticated (no admin-edit endpoint
in V1 — the constants live in :mod:`app.modules.compliance.domain.retention`).
The sweep job soft-anonymizes ``application_cv_snapshots`` rows past the
constant via the ``documents`` module's snapshot facade (no direct
cross-module ORM writes), registered in
``app.modules.automation.scheduler.jobs``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.compliance.domain import retention
from app.modules.documents.application import snapshot_service


def get_policy_text(*, locale: str = "vi") -> list[dict[str, object]]:
    return retention.as_dict(locale=locale)


async def sweep_retention(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Anonymize application CV snapshots past the retention window.

    Idempotent: :func:`snapshot_service.anonymize_expired_snapshots` skips
    already-tombstoned rows, so re-running the sweep is always a no-op beyond
    genuinely newly-expired rows.
    """

    now = now or datetime.now(tz=UTC)
    cutoff = now - timedelta(days=retention.APPLICATION_CV_SNAPSHOT_RETENTION_DAYS)
    anonymized = await snapshot_service.anonymize_expired_snapshots(session, older_than=cutoff)
    return {"anonymized": anonymized}
