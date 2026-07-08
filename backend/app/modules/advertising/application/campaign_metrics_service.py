"""Write + read path for ``ad_placement_metrics_daily`` (per-campaign analytics).

Recompute-and-UPSERT projection of the privacy-safe ``discovery_events`` ledger,
keyed by ``placement_id``. Two producers keep it fresh (the same shape as
``job_competition_daily``):

- :func:`refresh_placement` — recompute one placement's daily rows from the event
  ledger and SET them (absolute, idempotent). Called READ-THROUGH from the partner
  analytics endpoint (so a partner always sees current numbers between sweeps) and
  by the nightly sweep. ``discovery`` signal-emission is never touched — the
  projection is rebuilt from the ledger, not hooked into the event write path.
- :func:`sweep_refresh` — the nightly self-healing recompute of every placement
  that has any sponsored events (catches retention pruning + late events).

Cross-module read contract: the aggregation reads the ``discovery_events`` table
via a raw ``text()`` query keyed on ``placement_id`` — the SAME no-cross-module-ORM
pattern ``competition_projection_service`` uses to read ``applications``. The
projection ORM model itself is advertising-owned. ``org_id`` is resolved from the
advertising-owned ``sponsored_placements`` row (``discovery_events`` is org-agnostic).

RBAC (:func:`get_placement_analytics` / :func:`get_org_analytics`): a partner sees
ONLY their own org's campaigns; a cross-org/unknown placement is a non-enumerable
``404``. Aggregates only — no viewer/session/candidate id, no PII (health-service
discipline). Cost-per-apply-start is derived at read time from the placement's
already-frozen campaign price; no spend/pacing model is stored (documented
follow-up).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Uuid, bindparam, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.advertising.domain.metrics_models import AdPlacementMetricsDaily
from app.modules.advertising.domain.models import SponsoredPlacement
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

logger = logging.getLogger(__name__)

_RESOURCE = "advertising"

# discovery_events.event_type -> the daily projection column it feeds.
_EVENT_COLUMN: dict[str, str] = {
    "impression": "impressions",
    "click": "clicks",
    "view": "views",
    "apply_start": "apply_starts",
    "save_intent": "save_intents",
    "event_register_intent": "event_register_intents",
}
_COUNTER_COLUMNS: tuple[str, ...] = (
    "impressions",
    "clicks",
    "views",
    "apply_starts",
    "save_intents",
    "event_register_intents",
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _as_uuid(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _coerce_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _date_expr(session: AsyncSession) -> str:
    """Dialect-correct SQL to bucket ``created_at`` into a calendar date.

    SQLite's ``date()`` returns ``'YYYY-MM-DD'`` text; Postgres' ``CAST(.. AS
    DATE)`` returns a real date. ``CAST AS DATE`` on SQLite would (wrongly)
    numeric-coerce, so each dialect uses its own correct expression.
    """

    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    return "CAST(created_at AS DATE)" if dialect == "postgresql" else "date(created_at)"


async def _aggregate_from_events(
    session: AsyncSession, *, placement_id: uuid.UUID
) -> dict[date, dict[str, int]]:
    """Recompute ``{metric_date: {counter: n}}`` for a placement from the ledger."""

    date_expr = _date_expr(session)
    stmt = text(
        f"SELECT {date_expr} AS d, event_type AS et, count(*) AS c"  # noqa: S608
        " FROM discovery_events"
        " WHERE placement_id = :pid"
        f" GROUP BY {date_expr}, event_type"
    ).bindparams(bindparam("pid", type_=Uuid(as_uuid=True)))
    rows = (await session.execute(stmt, {"pid": placement_id})).all()

    buckets: dict[date, dict[str, int]] = {}
    for d_raw, event_type, count in rows:
        column = _EVENT_COLUMN.get(str(event_type))
        if column is None:
            continue
        day = _coerce_date(d_raw)
        if day is None:
            continue
        buckets.setdefault(day, {})[column] = int(count)
    return buckets


async def refresh_placement(
    session: AsyncSession,
    *,
    placement_id: uuid.UUID,
    org_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """Recompute + replace one placement's daily rows. Returns the row count.

    Idempotent: the placement's existing rows are deleted and re-inserted from the
    ledger, so a re-run converges to the same values and stale dates (dropped by
    event retention) never linger.
    """

    stamp = now or _now()
    buckets = await _aggregate_from_events(session, placement_id=placement_id)

    await session.execute(
        delete(AdPlacementMetricsDaily).where(
            AdPlacementMetricsDaily.placement_id == placement_id
        )
    )
    for day, counts in buckets.items():
        session.add(
            AdPlacementMetricsDaily(
                placement_id=placement_id,
                org_id=org_id,
                metric_date=day,
                impressions=counts.get("impressions", 0),
                clicks=counts.get("clicks", 0),
                views=counts.get("views", 0),
                apply_starts=counts.get("apply_starts", 0),
                save_intents=counts.get("save_intents", 0),
                event_register_intents=counts.get("event_register_intents", 0),
                created_at=stamp,
                updated_at=stamp,
            )
        )
    await session.flush()
    return len(buckets)


async def refresh_placement_safe(
    session: AsyncSession,
    *,
    placement_id: uuid.UUID,
    org_id: uuid.UUID,
    now: datetime | None = None,
) -> None:
    """Best-effort refresh isolated in a savepoint (telemetry never breaks a read)."""

    try:
        async with session.begin_nested():
            await refresh_placement(
                session, placement_id=placement_id, org_id=org_id, now=now
            )
    except Exception:  # noqa: BLE001 — projection refresh is best-effort
        logger.warning(
            "ad_placement_metrics.refresh_failed",
            extra={"placement_id": str(placement_id)},
        )


async def _placement_ids_with_events(session: AsyncSession) -> list[uuid.UUID]:
    rows = await session.execute(
        text(
            "SELECT DISTINCT placement_id FROM discovery_events"
            " WHERE placement_id IS NOT NULL"
        )
    )
    return [_as_uuid(r[0]) for r in rows.all() if r[0] is not None]


async def sweep_refresh(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Nightly self-healing recompute of every placement with sponsored events.

    Each placement is refreshed in its own savepoint so one bad placement never
    aborts the sweep. Idempotent (a re-tick recomputes to the same values).
    """

    stamp = now or _now()
    placement_ids = await _placement_ids_with_events(session)
    refreshed = 0
    errors = 0
    for placement_id in placement_ids:
        placement = await session.get(SponsoredPlacement, placement_id)
        if placement is None:
            continue
        try:
            async with session.begin_nested():
                await refresh_placement(
                    session,
                    placement_id=placement_id,
                    org_id=placement.org_id,
                    now=stamp,
                )
            refreshed += 1
        except Exception:  # noqa: BLE001 — one placement must not abort the sweep
            errors += 1
            logger.warning(
                "ad_placement_metrics.sweep_placement_failed",
                extra={"placement_id": str(placement_id)},
            )
    await session.commit()
    return {"refreshed": refreshed, "errors": errors}


# --------------------------------------------------------------------------- #
# Reads (partner campaign analytics)                                          #
# --------------------------------------------------------------------------- #


async def _load_owned(
    session: AsyncSession, *, principal: Principal, placement_id: uuid.UUID
) -> SponsoredPlacement:
    """Load a non-deleted placement the principal's org owns; else ``404``."""

    placement = (
        await session.execute(
            select(SponsoredPlacement).where(
                SponsoredPlacement.id == placement_id,
                SponsoredPlacement.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if placement is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and placement.org_id != principal.org_id:
        raise ResourceNotFoundError()
    return placement


def _ratio_pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def _cost_per(price: Decimal | None, apply_starts: int) -> str | None:
    if price is None or apply_starts <= 0:
        return None
    return f"{(price / Decimal(apply_starts)):.2f}"


async def _placement_totals_and_series(
    session: AsyncSession, *, placement_id: uuid.UUID
) -> tuple[dict[str, int], list[dict]]:
    rows = (
        await session.execute(
            select(AdPlacementMetricsDaily)
            .where(AdPlacementMetricsDaily.placement_id == placement_id)
            .order_by(AdPlacementMetricsDaily.metric_date.asc())
        )
    ).scalars().all()

    totals = dict.fromkeys(_COUNTER_COLUMNS, 0)
    daily: list[dict] = []
    for row in rows:
        for col in _COUNTER_COLUMNS:
            totals[col] += getattr(row, col)
        daily.append(
            {
                "date": row.metric_date.isoformat(),
                "impressions": row.impressions,
                "clicks": row.clicks,
                "views": row.views,
                "apply_starts": row.apply_starts,
                "save_intents": row.save_intents,
                "event_register_intents": row.event_register_intents,
                "ctr_pct": _ratio_pct(row.clicks, row.impressions),
            }
        )
    return totals, daily


def _analytics_note(locale: str) -> str:
    if locale == "en":
        return (
            "Aggregate campaign metrics only (no viewer identities). Cost per "
            "apply-start uses the frozen campaign price divided by apply-starts."
        )
    return (
        "Chỉ số tổng hợp của chiến dịch (không có danh tính người xem). Chi phí "
        "mỗi lượt bắt đầu ứng tuyển = giá chiến dịch đã chốt chia cho số lượt."
    )


async def get_placement_analytics(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    locale: str = "vi",
    refresh: bool = True,
) -> dict:
    """Owner-scoped per-campaign analytics for one placement (read-through refresh).

    RBAC: ``advertising:view`` on the OWNING org; cross-org/unknown -> ``404``.
    """

    placement = await _load_owned(
        session, principal=principal, placement_id=placement_id
    )
    permission_checker.require(
        principal, _RESOURCE, "view", resource_org_id=placement.org_id
    )
    if refresh:
        await refresh_placement_safe(
            session, placement_id=placement.id, org_id=placement.org_id
        )
        await session.commit()

    totals, daily = await _placement_totals_and_series(
        session, placement_id=placement.id
    )
    return {
        "placement_id": str(placement.id),
        "org_id": str(placement.org_id),
        "totals": totals,
        "ctr_pct": _ratio_pct(totals["clicks"], totals["impressions"]),
        "apply_start_rate_pct": _ratio_pct(
            totals["apply_starts"], totals["impressions"]
        ),
        "cost_per_apply_start": _cost_per(placement.price_amount, totals["apply_starts"]),
        "campaign_price": (
            f"{placement.price_amount:.2f}" if placement.price_amount is not None else None
        ),
        "currency": placement.currency,
        "daily": daily,
        "day_count": len(daily),
        "note": _analytics_note(locale),
    }


async def get_org_analytics(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID | None = None,
    locale: str = "vi",
) -> dict:
    """Org-wide campaign rollup for the caller's org (all owned placements).

    RBAC: ``advertising:view`` on the caller's org. A partner may only read their
    OWN org; a superadmin may pass an explicit ``org_id``.
    """

    target_org = org_id if (principal.is_superadmin and org_id) else principal.org_id
    if target_org is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "view", resource_org_id=target_org
    )

    rows = (
        await session.execute(
            select(
                AdPlacementMetricsDaily.placement_id,
                func.sum(AdPlacementMetricsDaily.impressions).label("impressions"),
                func.sum(AdPlacementMetricsDaily.clicks).label("clicks"),
                func.sum(AdPlacementMetricsDaily.views).label("views"),
                func.sum(AdPlacementMetricsDaily.apply_starts).label("apply_starts"),
                func.sum(AdPlacementMetricsDaily.save_intents).label("save_intents"),
                func.sum(
                    AdPlacementMetricsDaily.event_register_intents
                ).label("event_register_intents"),
            )
            .where(AdPlacementMetricsDaily.org_id == target_org)
            .group_by(AdPlacementMetricsDaily.placement_id)
        )
    ).all()

    totals = dict.fromkeys(_COUNTER_COLUMNS, 0)
    per_campaign: list[dict] = []
    for r in rows:
        campaign = {col: int(getattr(r, col) or 0) for col in _COUNTER_COLUMNS}
        for col in _COUNTER_COLUMNS:
            totals[col] += campaign[col]
        per_campaign.append(
            {
                "placement_id": str(r.placement_id),
                **campaign,
                "ctr_pct": _ratio_pct(campaign["clicks"], campaign["impressions"]),
            }
        )

    per_campaign.sort(key=lambda c: (-c["impressions"], c["placement_id"]))
    return {
        "org_id": str(target_org),
        "campaign_count": len(per_campaign),
        "totals": totals,
        "ctr_pct": _ratio_pct(totals["clicks"], totals["impressions"]),
        "apply_start_rate_pct": _ratio_pct(
            totals["apply_starts"], totals["impressions"]
        ),
        "campaigns": per_campaign,
        "note": _analytics_note(locale),
    }
