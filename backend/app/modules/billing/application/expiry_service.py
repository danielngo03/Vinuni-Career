"""Date-windowed subscription expiry + T-7d "expiring soon" notice — the services
shared by the ADR-0003 scheduler jobs (ADR-0010 §6).

Both sweeps are status/time-gated and idempotent: a re-tick is a no-op. Expiry is
purely time-based (no inline expiry needed); ``mark_paid``/``cancel`` flip status
inline in their own transaction. When an ``active`` window closes, the row flips to
``expired`` and the principal's limits revert to the default plan (the facade then
returns ``{}`` for that principal). Flush-only — the scheduler job owns the commit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.application import notify
from app.modules.billing.domain import lifecycle
from app.modules.billing.domain.models import Subscription
from app.shared.audit import AuditContext, write_audit

# Notify the owner T-7d before an active subscription's window closes.
_EXPIRING_WINDOW = timedelta(days=7)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite reads timestamps back naive; coerce to UTC-aware for comparison."""

    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _audit_ctx(sub: Subscription) -> AuditContext:
    return AuditContext(actor_id=None, actor_org_id=None)


async def expiry_sweep(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Expire every active subscription whose window has closed.

    ``status=active AND end_at <= now`` -> ``expired`` + revert limits to default.
    Status/end_at-gated + idempotent. Flush-only.
    """

    now = now or _now()
    rows = list(
        (
            await session.execute(
                select(Subscription).where(
                    Subscription.deleted_at.is_(None),
                    Subscription.status == lifecycle.ACTIVE,
                    Subscription.end_at.isnot(None),
                    Subscription.end_at <= now,
                )
            )
        )
        .scalars()
        .all()
    )
    expired = 0
    for sub in rows:
        end_at = _aware(sub.end_at)
        if end_at is None or end_at > now:
            continue  # defensive against naive-stored bounds
        sub.status = lifecycle.EXPIRED
        sub.expired_at = now
        sub.version += 1
        await write_audit(
            session,
            action="billing.subscription_expired",
            resource_type="subscription",
            resource_id=sub.id,
            context=_audit_ctx(sub),
            after={"status": sub.status, "principal_type": sub.principal_type},
        )
        await notify.notify_owner(
            session,
            subscription=sub,
            template_key="billing.expired",
        )
        expired += 1
    await session.flush()
    return {"expired": expired}


async def expiring_notice(session: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    """Enqueue a deduped T-7d "expiring soon" notice for active subscriptions.

    ``status=active AND now < end_at <= now+7d AND expiring_notified_at IS NULL``
    -> set the dedupe stamp + notify. Idempotent. Flush-only.
    """

    now = now or _now()
    soon = list(
        (
            await session.execute(
                select(Subscription).where(
                    Subscription.deleted_at.is_(None),
                    Subscription.status == lifecycle.ACTIVE,
                    Subscription.end_at.isnot(None),
                    Subscription.end_at > now,
                    Subscription.end_at <= now + _EXPIRING_WINDOW,
                    Subscription.expiring_notified_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    notified = 0
    for sub in soon:
        sub.expiring_notified_at = now
        sub.version += 1
        await notify.notify_owner(
            session,
            subscription=sub,
            template_key="billing.expiring",
        )
        notified += 1
    await session.flush()
    return {"expiring_notices": notified}
