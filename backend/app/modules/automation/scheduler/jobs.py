"""Periodic-job registry — the Celery-beat seam (ADR-0003 §1).

A static list of ``(name, interval_seconds, coro)`` entries. Each ``coro`` takes a
caller-owned :class:`AsyncSession` plus the tick ``now`` and delegates to a domain
**application service** (``notifications`` / ``recruitment`` / ``opportunities``).
There is no domain logic here and none in :mod:`runner`; the scheduler only decides
*when* a job runs and *delegates* the *what*.

Production seam: when we move to multi-instance, these same coros register as
Celery beat schedule entries against the existing ``celery_app`` (broker already
``redis://…/1``). The asyncio ``runner`` is deleted; this registry and the domain
services are unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.maintenance import (
    _prune_entrypoint as _ai_ops_prune,
)
from app.ai.observability.maintenance import (
    _reconcile_entrypoint as _ai_usage_daily_reconcile,
)
from app.modules.advertising.application import activation_service as ad_activation
from app.modules.billing.application import expiry_service as billing_expiry
from app.modules.career_outcomes.application import materializer_service
from app.modules.compliance.application import retention_service as compliance_retention
from app.modules.dashboards.application import snapshot_service as mi_snapshot
from app.modules.discovery.application import cleanup_service as discovery_cleanup
from app.modules.notifications.application import dispatch_service
from app.modules.opportunities.application import (
    job_alert_dispatch_service,
    job_service,
    registration_service,
    weekly_digest_service,
)
from app.modules.recruitment.application import (
    interview_service,
    offer_service,
    reveal_service,
    sla_reminder_service,
)

JobCoro = Callable[[AsyncSession, datetime], Awaitable[dict[str, int]]]


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    name: str
    interval_seconds: int
    run: JobCoro


async def _drain_outbox(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await dispatch_service.process_outbox(session, limit=50, now=now)


async def _expire_reveals(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await reveal_service.sweep_expired(session, now=now)


async def _close_deadlines(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await job_service.sweep_deadline_closures(session, now=now)


async def _interview_reminders(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await interview_service.sweep_due_reminders(session, now=now)


async def _offer_expire_sweep(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await offer_service.sweep_offers(session, now=now)


async def _pipeline_sla_reminders(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await sla_reminder_service.sweep_sla_reminders(session, now=now)


async def _event_reminders(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await registration_service.sweep_reminders(session, now=now)


async def _event_reminders_soon(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await registration_service.sweep_reminders_soon(session, now=now)


async def _event_waitlist_backfill(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await registration_service.sweep_waitlist_backfill(session, now=now)


async def _event_auto_complete(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await registration_service.sweep_auto_complete(session, now=now)


async def _event_no_show(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await registration_service.sweep_no_show(session, now=now)


async def _advertising_activation(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await ad_activation.activation_sweep(session, now=now)


async def _advertising_completion(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await ad_activation.completion_sweep(session, now=now)


async def _advertising_flag_reconcile(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await ad_activation.flag_reconcile(session, now=now)


async def _billing_expiry_sweep(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await billing_expiry.expiry_sweep(session, now=now)


async def _billing_expiring_notice(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await billing_expiry.expiring_notice(session, now=now)


async def _career_outcomes_materialize(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await materializer_service.materialize_career_outcomes(session, now)


async def _discovery_session_cleanup(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await discovery_cleanup.session_cleanup(session, now=now)


async def _job_alert_sweep(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await job_alert_dispatch_service.sweep_job_alerts(session, now=now)


async def _weekly_job_digest(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await weekly_digest_service.sweep_weekly_digest(session, now=now)


async def _compliance_retention_sweep(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await compliance_retention.sweep_retention(session, now=now)


async def _market_intelligence_refresh(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await mi_snapshot.refresh(session, now=now)


async def _market_intelligence_reconcile(session: AsyncSession, now: datetime) -> dict[str, int]:
    return await mi_snapshot.reconcile(session, now=now)


async def _evaluate_alerts(session: AsyncSession, _now: datetime) -> dict[str, int]:
    """Evaluate all enabled alert rules and open/resolve incidents. Never raises."""
    import logging  # noqa: PLC0415

    _log = logging.getLogger(__name__)
    try:
        from app.modules.platform_admin.application import alerts_service  # noqa: PLC0415

        return await alerts_service.evaluate_alerts(session)
    except Exception:  # noqa: BLE001
        _log.warning("scheduler.alerts_evaluate_failed", exc_info=True)
        return {"opened": 0, "resolved": 0, "evaluated": 0, "error": 1}


# Cadences per ADR-0003 §2 (multiples of the base tick). Order is the run order
# within a tick; each job is otherwise independent (its own session + commit).
REGISTRY: tuple[ScheduledJob, ...] = (
    ScheduledJob("outbox.drain", 15, _drain_outbox),
    ScheduledJob("reveal.expire_sweep", 300, _expire_reveals),
    ScheduledJob("interview.reminder_sweep", 300, _interview_reminders),
    ScheduledJob("offer.expire_sweep", 300, _offer_expire_sweep),
    # Pipeline SLA reminders: notify the stage's owning reviewer (fallback: the
    # job owner) at 80% ("approaching") and 100%+ ("overdue") of
    # ``pipeline_stages.sla_hours`` elapsed. Idempotent via the per-stage
    # escalating ``sla_reminder_level`` (re-tick is a no-op once notified).
    ScheduledJob("pipeline.sla_reminder_sweep", 300, _pipeline_sla_reminders),
    ScheduledJob("opportunities.deadline_close", 600, _close_deadlines),
    ScheduledJob("events.reminder_sweep", 300, _event_reminders),
    ScheduledJob("events.reminder_sweep_soon", 300, _event_reminders_soon),
    ScheduledJob("events.waitlist_backfill", 300, _event_waitlist_backfill),
    ScheduledJob("events.auto_complete", 600, _event_auto_complete),
    ScheduledJob("events.no_show_sweep", 600, _event_no_show),
    # ADR-0009: date-windowed sponsored-placement activation/completion + a nightly
    # self-healing flag reconcile. Status/time-gated + idempotent (re-tick is a no-op).
    ScheduledJob("advertising.activation_sweep", 300, _advertising_activation),
    ScheduledJob("advertising.completion_sweep", 300, _advertising_completion),
    ScheduledJob("advertising.flag_reconcile", 86400, _advertising_flag_reconcile),
    # ADR-0010: date-windowed subscription expiry + nightly T-7d "expiring soon"
    # notice. Status/end_at-gated + idempotent (re-tick is a no-op).
    ScheduledJob("billing.expiry_sweep", 600, _billing_expiry_sweep),
    ScheduledJob("billing.expiring_notice", 86400, _billing_expiring_notice),
    # ADR-0007: deferred consumer of the non-blocking ``offer.accepted`` seam.
    # First drainer of the generic ``outbox_events`` table. Idempotent two ways
    # (published_at marker + source_event_id unique) -> re-tick is a no-op.
    ScheduledJob("career_outcomes.materialize_sweep", 300, _career_outcomes_materialize),
    # Discovery rescue (spec §3/§8): prune expired guest sessions (short TTL) + old
    # analytics events (retention). Time-gated + idempotent (re-tick is a no-op).
    ScheduledJob("discovery.session_cleanup", 86400, _discovery_session_cleanup),
    # Job alert dispatch: find newly-published jobs matching each active alert
    # and enqueue in-app notifications. Runs every 30 min so students receive
    # matches within ~30 min of a job going live.
    ScheduledJob("opportunities.job_alert_sweep", 1800, _job_alert_sweep),
    # Weekly job digest: top-8 most recently published jobs sent to all active
    # students every 7 days. Idempotent per ISO week via dedupe_key.
    ScheduledJob("opportunities.weekly_job_digest", 604800, _weekly_job_digest),
    # ADR-0014 §35: anonymize application_cv_snapshots past the hardcoded
    # retention window. Time-gated (created_at cutoff) + idempotent (a
    # re-tick finds only newly-expired rows; already-tombstoned rows are
    # skipped by the facade).
    ScheduledJob("compliance.retention_sweep", 86400, _compliance_retention_sweep),
    # B-558 read-model governance: scheduled refresh of the market-intelligence
    # snapshot (well inside ``market_intelligence_stale_after_seconds``) + a
    # nightly drift reconciliation check (read-only; logs only, self-heals via
    # the next scheduled refresh).
    ScheduledJob("dashboards.market_intelligence_refresh_sweep", 900, _market_intelligence_refresh),
    ScheduledJob(
        "dashboards.market_intelligence_reconcile_sweep",
        86400,
        _market_intelligence_reconcile,
    ),
    # AI ops maintenance: hourly self-healing reconcile of the ai_usage_daily
    # rollup (fixes any gaps where the ledger write failed but the ai_ops_event
    # succeeded), plus a nightly prune of raw ai_ops_event rows past 90 days
    # (rollup rows in ai_usage_daily are never pruned). Both are idempotent.
    ScheduledJob("ai_ops.usage_daily_reconcile", 3600, _ai_usage_daily_reconcile),
    ScheduledJob("ai_ops.prune", 86400, _ai_ops_prune),
    # P7: Alert rule evaluation — opens/resolves incidents on threshold breaches.
    # Runs every 5 minutes. Never raises (errors logged, never crashes the scheduler).
    ScheduledJob("alerts.evaluate", 300, _evaluate_alerts),
)


def by_name(name: str) -> ScheduledJob:
    """Return the registered job ``name`` (raises ``KeyError`` if unknown)."""

    for job in REGISTRY:
        if job.name == name:
            return job
    raise KeyError(name)
