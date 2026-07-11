"""Platform Admin P7 — Alert Rules & Incidents service.

Superadmin-only. Every write is audited.

Metric sources:
  - ``ai_spend_vs_budget_pct`` — (spend_today / budget) * 100; from ai_ops overview().
  - ``ai_error_rate``          — error_rate (0–1 fraction); from ai_ops overview().
  - ``queue_depth``            — celery_default_queue_depth; from system_health queues_health().
  - ``outbox_failed``          — outbox.failed count; from system_health services_health().

Evaluation is idempotent:
  - A firing rule with an already-open incident does NOT open a duplicate.
  - A passing rule with an open incident auto-resolves it.

Notification dispatch is best-effort: a notification failure never aborts the sweep.
User-safe incident messages never expose provider/model/prompt/cost internals.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.platform_admin.domain.models import (
    _VALID_COMPARISONS,
    _VALID_METRICS,
    _VALID_SEVERITIES,
    AlertRule,
    Incident,
)
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_superadmin(principal: Principal) -> None:
    """Service-layer RBAC guard (defence-in-depth — router already checks)."""
    if not principal.is_superadmin:
        raise PermissionDeniedError()


def _validate_rule_fields(
    metric: str,
    comparison: str,
    severity: str,
    threshold: float,
) -> None:
    if metric not in _VALID_METRICS:
        raise ValidationFailedError(
            f"Invalid metric '{metric}'. Must be one of: {sorted(_VALID_METRICS)}."
        )
    if comparison not in _VALID_COMPARISONS:
        raise ValidationFailedError(
            f"Invalid comparison '{comparison}'. Must be one of: {sorted(_VALID_COMPARISONS)}."
        )
    if severity not in _VALID_SEVERITIES:
        raise ValidationFailedError(
            f"Invalid severity '{severity}'. Must be one of: {sorted(_VALID_SEVERITIES)}."
        )
    if not isinstance(threshold, (int, float)) or threshold != threshold:  # NaN guard
        raise ValidationFailedError("threshold must be a finite numeric value.")


def _rule_to_dict(rule: AlertRule) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "metric": rule.metric,
        "comparison": rule.comparison,
        "threshold": rule.threshold,
        "window_days": rule.window_days,
        "severity": rule.severity,
        "enabled": rule.enabled,
        "channels": rule.channels,
        "updated_by": str(rule.updated_by) if rule.updated_by else None,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }


def _incident_to_dict(inc: Incident) -> dict[str, Any]:
    return {
        "id": str(inc.id),
        "rule_id": str(inc.rule_id),
        "metric": inc.metric,
        "severity": inc.severity,
        "status": inc.status,
        "message": inc.message,
        "value": inc.value,
        "threshold": inc.threshold,
        "triggered_at": inc.triggered_at.isoformat(),
        "acknowledged_at": inc.acknowledged_at.isoformat() if inc.acknowledged_at else None,
        "acknowledged_by": str(inc.acknowledged_by) if inc.acknowledged_by else None,
        "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
        "created_at": inc.created_at.isoformat(),
    }


def _build_incident_message(metric: str, value: float, comparison: str, threshold: float) -> str:
    """Build a user-safe incident message without internals."""
    labels: dict[str, str] = {
        "ai_spend_vs_budget_pct": "AI spend vs budget",
        "ai_error_rate": "AI error rate",
        "queue_depth": "Queue depth",
        "outbox_failed": "Outbox failed count",
    }
    comparison_words: dict[str, str] = {
        "gt": "exceeded",
        "gte": "reached or exceeded",
        "lt": "dropped below",
        "lte": "reached or dropped below",
    }
    label = labels.get(metric, metric)
    action = comparison_words.get(comparison, comparison)

    # Format values nicely
    if metric == "ai_error_rate":
        val_str = f"{value * 100:.1f}%"
        thr_str = f"{threshold * 100:.1f}%"
    elif metric == "ai_spend_vs_budget_pct":
        val_str = f"{value:.1f}%"
        thr_str = f"{threshold:.1f}%"
    else:
        val_str = f"{value:.0f}"
        thr_str = f"{threshold:.0f}"

    return f"{label} {val_str} {action} threshold {thr_str}."


# ---------------------------------------------------------------------------
# Pure comparator (unit-tested)
# ---------------------------------------------------------------------------


def check_rule(metric_value: float, comparison: str, threshold: float) -> bool:
    """Pure threshold comparator. Returns True when the rule fires."""
    if comparison == "gt":
        return metric_value > threshold
    if comparison == "gte":
        return metric_value >= threshold
    if comparison == "lt":
        return metric_value < threshold
    if comparison == "lte":
        return metric_value <= threshold
    return False


# ---------------------------------------------------------------------------
# Rule CRUD
# ---------------------------------------------------------------------------


async def list_rules(
    session: AsyncSession,
    *,
    principal: Principal,
) -> list[dict[str, Any]]:
    _require_superadmin(principal)
    result = await session.execute(select(AlertRule).order_by(AlertRule.created_at))
    return [_rule_to_dict(r) for r in result.scalars().all()]


async def create_rule(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    name: str,
    metric: str,
    comparison: str,
    threshold: float,
    window_days: int = 1,
    severity: str = "warning",
    enabled: bool = True,
    channels: list[str] | None = None,
) -> dict[str, Any]:
    _require_superadmin(principal)
    _validate_rule_fields(metric, comparison, severity, threshold)
    if not name or not name.strip():
        raise ValidationFailedError("Alert rule name must not be empty.")

    rule = AlertRule(
        name=name.strip(),
        metric=metric,
        comparison=comparison,
        threshold=float(threshold),
        window_days=max(1, int(window_days)),
        severity=severity,
        enabled=enabled,
        channels=channels or [],
        updated_by=principal.user_id,
    )
    session.add(rule)
    await session.flush()
    await session.refresh(rule)
    after = _rule_to_dict(rule)
    await write_audit(
        session,
        action="alert_rule.created",
        resource_type="alert_rule",
        resource_id=rule.id,
        context=ctx,
        before=None,
        after=after,
    )
    await session.commit()
    return after


async def update_rule(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    rule_id: uuid.UUID,
    **fields: Any,
) -> dict[str, Any]:
    _require_superadmin(principal)

    result = await session.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise ResourceNotFoundError("Alert rule not found.")

    before = _rule_to_dict(rule)

    if "name" in fields:
        v = str(fields["name"]).strip()
        if not v:
            raise ValidationFailedError("Alert rule name must not be empty.")
        rule.name = v
    if "metric" in fields:
        rule.metric = str(fields["metric"])
    if "comparison" in fields:
        rule.comparison = str(fields["comparison"])
    if "threshold" in fields:
        rule.threshold = float(fields["threshold"])
    if "window_days" in fields:
        rule.window_days = max(1, int(fields["window_days"]))
    if "severity" in fields:
        rule.severity = str(fields["severity"])
    if "enabled" in fields:
        rule.enabled = bool(fields["enabled"])
    if "channels" in fields:
        rule.channels = list(fields["channels"])

    # Re-validate after partial update
    _validate_rule_fields(rule.metric, rule.comparison, rule.severity, rule.threshold)
    rule.updated_by = principal.user_id
    await session.flush()
    await session.refresh(rule)

    after = _rule_to_dict(rule)
    await write_audit(
        session,
        action="alert_rule.updated",
        resource_type="alert_rule",
        resource_id=rule.id,
        context=ctx,
        before=before,
        after=after,
    )
    await session.commit()
    return after


async def delete_rule(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    rule_id: uuid.UUID,
) -> dict[str, Any]:
    _require_superadmin(principal)

    result = await session.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise ResourceNotFoundError("Alert rule not found.")

    before = _rule_to_dict(rule)
    await session.delete(rule)
    await write_audit(
        session,
        action="alert_rule.deleted",
        resource_type="alert_rule",
        resource_id=rule_id,
        context=ctx,
        before=before,
        after=None,
    )
    await session.commit()
    return {"id": str(rule_id), "deleted": True}


# ---------------------------------------------------------------------------
# Incident management
# ---------------------------------------------------------------------------


async def list_incidents(
    session: AsyncSession,
    *,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None, int]:
    """Return (items, next_cursor, limit) for the incidents list endpoint."""
    stmt = select(Incident).order_by(Incident.triggered_at.desc())

    if status is not None:
        stmt = stmt.where(Incident.status == status)

    if cursor is not None:
        # Cursor encodes the triggered_at ISO string of the last seen row.
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            stmt = stmt.where(Incident.triggered_at < cursor_dt)
        except (ValueError, TypeError):
            pass  # ignore malformed cursor — start from top

    stmt = stmt.limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = rows[-1].triggered_at.isoformat()

    return [_incident_to_dict(r) for r in rows], next_cursor, limit


async def acknowledge_incident(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    incident_id: uuid.UUID,
) -> dict[str, Any]:
    _require_superadmin(principal)

    result = await session.execute(select(Incident).where(Incident.id == incident_id))
    inc = result.scalar_one_or_none()
    if inc is None:
        raise ResourceNotFoundError("Incident not found.")

    before = _incident_to_dict(inc)

    if inc.status not in ("open", "acknowledged"):
        # Already resolved — idempotent: return current state without re-auditing.
        return before

    if inc.status == "acknowledged":
        # Already acked — idempotent.
        return before

    inc.status = "acknowledged"
    inc.acknowledged_at = datetime.now(tz=UTC)
    inc.acknowledged_by = principal.user_id
    await session.flush()

    after = _incident_to_dict(inc)
    await write_audit(
        session,
        action="incident.acknowledged",
        resource_type="incident",
        resource_id=inc.id,
        context=ctx,
        before=before,
        after=after,
    )
    await session.commit()
    return after


async def resolve_incident(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    incident_id: uuid.UUID,
) -> dict[str, Any]:
    _require_superadmin(principal)

    result = await session.execute(select(Incident).where(Incident.id == incident_id))
    inc = result.scalar_one_or_none()
    if inc is None:
        raise ResourceNotFoundError("Incident not found.")

    if inc.status == "resolved":
        # Already resolved — idempotent.
        return _incident_to_dict(inc)

    before = _incident_to_dict(inc)
    inc.status = "resolved"
    inc.resolved_at = datetime.now(tz=UTC)
    await session.flush()

    after = _incident_to_dict(inc)
    await write_audit(
        session,
        action="incident.resolved",
        resource_type="incident",
        resource_id=inc.id,
        context=ctx,
        before=before,
        after=after,
    )
    await session.commit()
    return after


# ---------------------------------------------------------------------------
# Metric fetchers (best-effort wrappers)
# ---------------------------------------------------------------------------


async def _safe_fetch(coro: Any) -> float | None:
    """Await a metric coroutine; return None on any failure."""
    try:
        return await coro
    except Exception:  # noqa: BLE001
        logger.warning("alerts.metric_fetch_failed", exc_info=True)
        return None


async def _fetch_metric(session: AsyncSession, metric: str, window_days: int) -> float | None:
    """Fetch the current value for a metric. Returns None on error."""
    if metric == "ai_spend_vs_budget_pct":
        from app.modules.ai_ops.application import ai_ops_read_service  # noqa: PLC0415

        async def _get() -> float:
            data = await ai_ops_read_service.overview(session, range_days=window_days)
            spend = float(data.get("spend_today", 0.0))
            budget = float(data.get("budget") or 0.0)
            if budget <= 0:
                return 0.0
            return (spend / budget) * 100.0

        return await _safe_fetch(_get())

    if metric == "ai_error_rate":
        from app.modules.ai_ops.application import ai_ops_read_service  # noqa: PLC0415

        async def _get_err() -> float:
            data = await ai_ops_read_service.overview(session, range_days=window_days)
            return float(data.get("error_rate", 0.0))

        return await _safe_fetch(_get_err())

    if metric == "queue_depth":
        from app.modules.platform_admin.application import system_health_service  # noqa: PLC0415

        async def _get_q() -> float:
            # queues_health needs a Principal — use a sentinel superadmin principal.
            _sentinel = Principal(
                user_id=None,
                persona="superadmin",
                org_id=None,
                is_superadmin=True,
                permissions=frozenset(),
            )
            data = await system_health_service.queues_health(principal=_sentinel)
            depth = data.get("celery_default_queue_depth")
            return float(depth) if depth is not None else 0.0

        return await _safe_fetch(_get_q())

    if metric == "outbox_failed":
        from app.modules.platform_admin.application import system_health_service  # noqa: PLC0415

        async def _get_ob() -> float:
            _sentinel = Principal(
                user_id=None,
                persona="superadmin",
                org_id=None,
                is_superadmin=True,
                permissions=frozenset(),
            )
            data = await system_health_service.services_health(session, principal=_sentinel)
            outbox = data.get("outbox", {})
            failed = outbox.get("failed", 0)
            dead = outbox.get("dead", 0)
            return float((failed or 0) + (dead or 0))

        return await _safe_fetch(_get_ob())

    logger.warning("alerts.unknown_metric", extra={"metric": metric})
    return None


# ---------------------------------------------------------------------------
# Notification helper (best-effort)
# ---------------------------------------------------------------------------


async def _enqueue_incident_notification_best_effort(
    session: AsyncSession,
    incident: Incident,
    channels: list[str],
    event: str,  # "opened" | "resolved"
) -> None:
    """Enqueue outbox notifications for an incident event. Never raises."""
    try:
        from app.modules.notifications.application import dispatch_service  # noqa: PLC0415

        for channel in channels:
            if channel not in ("in_app", "email"):
                continue
            template_key = f"incident.{event}"
            await dispatch_service.enqueue_notification(
                session,
                recipient_id=None,  # broadcast to superadmin; template resolves recipients
                template_key=template_key,
                channel=channel,
                locale="en",
                variables={
                    "incident_id": str(incident.id),
                    "metric": incident.metric,
                    "severity": incident.severity,
                    "message": incident.message,
                    "status": incident.status,
                    "triggered_at": incident.triggered_at.isoformat(),
                },
                dedupe_key=f"incident.{event}.{incident.id}",
            )
    except Exception:  # noqa: BLE001
        logger.warning(
            "alerts.notification_enqueue_failed",
            extra={"incident_id": str(incident.id), "event": event},
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Evaluate alerts — called by the scheduler job
# ---------------------------------------------------------------------------


async def evaluate_alerts(session: AsyncSession) -> dict[str, int]:
    """Evaluate all enabled alert rules and open/resolve incidents.

    For each enabled rule:
      - Fetch current metric value (best-effort; skip rule on fetch failure).
      - If threshold fires AND no OPEN incident exists: open a new Incident.
      - If threshold does NOT fire AND an OPEN incident exists: auto-resolve it.
      - Notification enqueue is best-effort; a failure never aborts the sweep.

    Returns ``{opened, resolved, evaluated}`` counts.
    """
    opened = 0
    resolved = 0
    evaluated = 0

    # Load enabled rules.
    rules_result = await session.execute(select(AlertRule).where(AlertRule.enabled.is_(True)))
    rules = list(rules_result.scalars().all())

    for rule in rules:
        evaluated += 1

        # Fetch metric — skip this rule if the fetch fails.
        value = await _fetch_metric(session, rule.metric, rule.window_days)
        if value is None:
            logger.warning(
                "alerts.evaluate_skip_metric_unavailable",
                extra={"rule_id": str(rule.id), "metric": rule.metric},
            )
            continue

        fires = check_rule(value, rule.comparison, rule.threshold)

        # Look up existing open incident for this rule.
        open_inc_result = await session.execute(
            select(Incident).where(
                Incident.rule_id == rule.id,
                Incident.status == "open",
            )
        )
        open_incident = open_inc_result.scalar_one_or_none()

        now = datetime.now(tz=UTC)

        if fires and open_incident is None:
            # Open a new incident.
            msg = _build_incident_message(rule.metric, value, rule.comparison, rule.threshold)
            inc = Incident(
                rule_id=rule.id,
                metric=rule.metric,
                severity=rule.severity,
                status="open",
                message=msg,
                value=value,
                threshold=rule.threshold,
                triggered_at=now,
            )
            session.add(inc)
            try:
                await session.flush()
                await session.commit()
                opened += 1
                logger.info(
                    "alerts.incident_opened",
                    extra={
                        "rule_id": str(rule.id),
                        "metric": rule.metric,
                        "value": value,
                        "threshold": rule.threshold,
                    },
                )
                # Best-effort notification (after commit so incident row exists).
                if rule.channels:
                    await _enqueue_incident_notification_best_effort(
                        session, inc, list(rule.channels), "opened"
                    )
                    try:
                        await session.commit()
                    except Exception:  # noqa: BLE001
                        await session.rollback()
            except Exception:  # noqa: BLE001
                await session.rollback()
                logger.warning(
                    "alerts.incident_open_failed",
                    extra={"rule_id": str(rule.id)},
                    exc_info=True,
                )

        elif not fires and open_incident is not None:
            # Auto-resolve the open incident.
            open_incident.status = "resolved"
            open_incident.resolved_at = now
            try:
                await session.flush()
                await session.commit()
                resolved += 1
                logger.info(
                    "alerts.incident_auto_resolved",
                    extra={
                        "rule_id": str(rule.id),
                        "incident_id": str(open_incident.id),
                        "metric": rule.metric,
                        "value": value,
                    },
                )
                # Best-effort notification.
                if rule.channels:
                    await _enqueue_incident_notification_best_effort(
                        session, open_incident, list(rule.channels), "resolved"
                    )
                    try:
                        await session.commit()
                    except Exception:  # noqa: BLE001
                        await session.rollback()
            except Exception:  # noqa: BLE001
                await session.rollback()
                logger.warning(
                    "alerts.incident_resolve_failed",
                    extra={"rule_id": str(rule.id)},
                    exc_info=True,
                )

    return {"opened": opened, "resolved": resolved, "evaluated": evaluated}
