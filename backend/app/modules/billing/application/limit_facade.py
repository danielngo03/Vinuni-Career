"""Limit-resolution facade — the ONLY way any module reads tier limits.

The load-bearing integration seam (ADR-0010 §3). A consuming module (today: the
``documents`` CV-quota cap) calls :func:`resolve_limit` / :func:`resolve_limits`
**without importing subscription ORM**, exactly mirroring how ``advertising``
drives ``opportunities`` through one ``sponsorship_facade``. The dependency is
one-way (``documents -> billing``); ``billing`` never imports ``documents``.

Resolution rule: merge policy layers in business order:

1. visible default/free plan for the audience (student/partner),
2. student segment bonus (VinUni email vs external email),
3. active paid subscription's ``plan.limits`` map.

The org subscription is chosen when ``principal.org_id`` is set (partner);
otherwise the user subscription (student). Only ``status == 'active'`` AND
``end_at > now`` counts — expired/cancelled/pending rows resolve to defaults.

One indexed query per check (``idx_subscriptions_principal``); no N+1, no heavy
join. A request-scoped memoization is a trivial later optimization.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import is_institution_email
from app.modules.billing.domain import lifecycle
from app.modules.billing.domain.models import Subscription, SubscriptionPlan
from app.modules.users.application import user_read_facade
from app.shared.permissions import Principal

_VINUNI_STUDENT_LIMITS = {
    "student_segment": "vinuni_student",
    "ai_daily_cost_quota_usd": 0.20,
}
_EXTERNAL_STUDENT_LIMITS = {
    "student_segment": "external_student",
    "ai_daily_cost_quota_usd": 0.02,
}

# Weekly AI-energy allowance (WS-1). Shadow-period-calibrated placeholders: the
# free/default tier grants this many masked energy units per week, while a paid
# plan (Premium) overrides via ``subscription_plans.limits.weekly_energy_units``
# (intended ~5000). Never shown to students (masked to % by the energy service).
_DEFAULT_WEEKLY_ENERGY_UNITS = 1000  # Free tier default; calibrated in shadow period.


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _as_aware(dt: datetime | None) -> datetime | None:
    """SQLite reads timestamps back naive; coerce to UTC-aware for comparison."""

    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _principal_key(principal: Principal) -> tuple[str, Any] | None:
    """``(principal_type, principal_id)`` for the subscription lookup, or ``None``.

    Org context (partner) -> the org subscription; else the user subscription.
    """

    if principal.org_id is not None:
        return (lifecycle.PRINCIPAL_ORG, principal.org_id)
    if principal.user_id is not None:
        return (lifecycle.PRINCIPAL_USER, principal.user_id)
    return None


def _audience_for_principal(principal: Principal) -> str | None:
    if principal.org_id is not None:
        return lifecycle.AUDIENCE_PARTNER
    if principal.user_id is not None:
        return lifecycle.AUDIENCE_STUDENT
    return None


async def _email_for_user(session: AsyncSession, user_id: Any) -> str | None:
    return await user_read_facade.get_email(session, user_id)


async def _student_segment_limits(
    session: AsyncSession, principal: Principal
) -> dict[str, Any]:
    if principal.user_id is None or principal.org_id is not None:
        return {}
    email = await _email_for_user(session, principal.user_id)
    if is_institution_email(email):
        return dict(_VINUNI_STUDENT_LIMITS)
    return dict(_EXTERNAL_STUDENT_LIMITS)


async def _default_plan(
    session: AsyncSession, audience: str
) -> SubscriptionPlan | None:
    return (
        await session.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.audience == audience,
                SubscriptionPlan.is_default.is_(True),
                SubscriptionPlan.is_visible.is_(True),
            )
        )
    ).scalars().first()


async def _active_plan(
    session: AsyncSession, principal: Principal, *, now: datetime | None = None
) -> SubscriptionPlan | None:
    key = _principal_key(principal)
    if key is None:
        return None
    principal_type, principal_id = key
    now = now or _now()
    sub = (
        await session.execute(
            select(Subscription)
            .where(
                Subscription.principal_type == principal_type,
                Subscription.principal_id == principal_id,
                Subscription.status == lifecycle.ACTIVE,
                Subscription.deleted_at.is_(None),
            )
            .order_by(Subscription.activated_at.desc().nulls_last())
        )
    ).scalars().first()
    if sub is None:
        return None
    if not lifecycle.is_active_now(sub.status, _as_aware(sub.end_at), now):
        return None
    return (
        await session.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
        )
    ).scalar_one_or_none()


async def resolve_limits(
    session: AsyncSession, principal: Principal, *, now: datetime | None = None
) -> dict:
    """Return effective tier/segment limits for ``principal``.

    The result is safe for product modules to consume directly: free/default plan
    limits and student segment bonuses are already included, and active paid
    subscription limits override them key-by-key.
    """

    audience = _audience_for_principal(principal)
    effective: dict[str, Any] = {}
    if audience is not None:
        default_plan = await _default_plan(session, audience)
        if default_plan is not None:
            effective.update(default_plan.limits or {})
    if audience == lifecycle.AUDIENCE_STUDENT:
        effective.update(await _student_segment_limits(session, principal))

    plan = await _active_plan(session, principal, now=now)
    if plan is not None:
        effective.update(plan.limits or {})
    return effective


async def resolve_user_ai_daily_cost_quota(
    session: AsyncSession,
    user_id: Any,
    *,
    now: datetime | None = None,
) -> float:
    """Return the per-user daily AI USD quota resolved from tier policy.

    ``0`` means no user-specific quota. The global platform budget still applies
    separately in ``ai_settings``.

    LEGACY (WS-1): this resolver is no longer wired into the AI gateway — the
    per-user student USD-daily enforcement gate in ``budget_guard.check_async``
    was removed in favour of the masked-energy account
    (:mod:`app.modules.billing.application.energy_service`). It is retained only
    as a tier-policy resolver (the ``ai_daily_cost_quota_usd`` plan-limit value is
    still meaningful for reporting/tests); prefer
    :func:`resolve_user_weekly_energy_units` for new call sites.
    """

    principal = Principal(user_id=user_id, persona="student")
    value = await resolve_limit(
        session,
        principal,
        key="ai_daily_cost_quota_usd",
        default=0,
        now=now,
    )
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def resolve_user_weekly_energy_units(
    session: AsyncSession,
    user_id: Any,
    *,
    now: datetime | None = None,
) -> int:
    """Return the per-user weekly AI-energy allowance resolved from tier policy.

    Mirrors :func:`resolve_user_ai_daily_cost_quota`: the value is layered by the
    same rules as :func:`resolve_limits` (default/free plan -> VinUni vs external
    student segment -> active paid plan's ``limits`` map). The free/default tier
    falls back to :data:`_DEFAULT_WEEKLY_ENERGY_UNITS` (1000); a paid plan raises
    it via ``subscription_plans.limits.weekly_energy_units`` (intended ~5000).
    Both numbers are shadow-period-calibrated placeholders and are never exposed
    to students (masked to % by ``energy_service``).
    """

    principal = Principal(user_id=user_id, persona="student")
    value = await resolve_limit(
        session,
        principal,
        key="weekly_energy_units",
        default=_DEFAULT_WEEKLY_ENERGY_UNITS,
        now=now,
    )
    try:
        return int(value)
    except (TypeError, ValueError):
        return _DEFAULT_WEEKLY_ENERGY_UNITS


async def resolve_limit(
    session: AsyncSession,
    principal: Principal,
    *,
    key: str,
    default: Any,
    now: datetime | None = None,
) -> Any:
    """Single-key convenience: ``resolve_limits(...).get(key, default)``.

    Returns ``default`` whenever there is no active paid subscription OR the active
    plan does not carry ``key`` (so an absent/None override never overrides the
    platform default).
    """

    limits = await resolve_limits(session, principal, now=now)
    value = limits.get(key)
    return default if value is None else value
