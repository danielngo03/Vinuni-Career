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

from app.ai.energy import constants as energy_constants
from app.core.config import get_settings
from app.modules.billing.domain import lifecycle
from app.modules.billing.domain.models import Subscription, SubscriptionPlan
from app.modules.users.application import user_read_facade
from app.shared.permissions import Principal

# The masked weekly AI-energy plan-limit key (canonical vocabulary lives in the
# energy module). Its VALUE is an opaque product credit count — never USD/tokens.
_WEEKLY_ENERGY_KEY = energy_constants.PLAN_LIMIT_KEY_WEEKLY_UNITS

# Segment bonuses layered on the free/default student plan. ``ai_daily_cost_quota_usd``
# is an INTERNAL cost mechanic (budget_guard/superadmin only) and must never reach a
# subscriber billing response — see ``INTERNAL_LIMIT_KEYS`` / ``subscriber_limits``.
_VINUNI_STUDENT_LIMITS = {
    "student_segment": "vinuni_student",
    "ai_daily_cost_quota_usd": 0.20,
    _WEEKLY_ENERGY_KEY: energy_constants.DEFAULT_WEEKLY_UNITS_STUDENT_VINUNI,
}
_EXTERNAL_STUDENT_LIMITS = {
    "student_segment": "external_student",
    "ai_daily_cost_quota_usd": 0.02,
    _WEEKLY_ENERGY_KEY: energy_constants.DEFAULT_WEEKLY_UNITS_STUDENT_EXTERNAL,
}

# Limit keys that are INTERNAL cost/segment mechanics. ``resolve_limits`` keeps them
# (budget_guard resolves the USD quota, the energy meter reads the raw units), but the
# self-service billing surface strips them via :func:`subscriber_limits` so a student /
# partner never sees a raw USD figure or the internal segment marker.
INTERNAL_LIMIT_KEYS = frozenset({"ai_daily_cost_quota_usd", "student_segment"})


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


def _institution_domains() -> set[str]:
    return {
        item.strip().lower().lstrip("@")
        for item in get_settings().institution_email_domains.split(",")
        if item.strip()
    }


def _is_institution_email(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[1].lower()
    return domain in _institution_domains()


async def _email_for_user(session: AsyncSession, user_id: Any) -> str | None:
    return await user_read_facade.get_email(session, user_id)


async def _student_segment_limits(
    session: AsyncSession, principal: Principal
) -> dict[str, Any]:
    if principal.user_id is None or principal.org_id is not None:
        return {}
    email = await _email_for_user(session, principal.user_id)
    if _is_institution_email(email):
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


# --------------------------------------------------------------------------- #
# Subscriber-facing masking (student/partner billing surface)                  #
# --------------------------------------------------------------------------- #


def subscriber_limits(raw: dict[str, Any], *, weekly_energy: int | None = None) -> dict:
    """Strip INTERNAL cost/segment keys and expose the masked weekly AI-energy row.

    Removes ``ai_daily_cost_quota_usd`` (raw USD) and ``student_segment`` so a
    subscriber never sees a cost figure or internal marker, and surfaces
    ``ai_weekly_energy_units`` as an OPAQUE product credit count (never USD/tokens).
    ``weekly_energy`` fills the row only when the map does not already carry it (so an
    explicit paid-plan value such as the Pro tier's is preserved).
    """

    out = {k: v for k, v in (raw or {}).items() if k not in INTERNAL_LIMIT_KEYS}
    if weekly_energy is not None:
        out.setdefault(_WEEKLY_ENERGY_KEY, int(weekly_energy))
    return out


async def subscriber_weekly_energy_default(
    session: AsyncSession, principal: Principal
) -> int:
    """Weekly AI-energy allowance default for the CALLER's own segment/persona.

    Mirrors the energy meter's resolution so billing and the header meter agree: a
    VinUni student -> 300, an external student -> 120, a partner org -> 400, else the
    safe-low fallback. Used to fill the free-tier comparison cell and the entitlements
    row when no plan sets ``ai_weekly_energy_units`` explicitly.
    """

    if principal.org_id is not None:
        return energy_constants.DEFAULT_WEEKLY_UNITS_PARTNER_ORG
    if principal.user_id is not None:
        email = await _email_for_user(session, principal.user_id)
        if _is_institution_email(email):
            return energy_constants.DEFAULT_WEEKLY_UNITS_STUDENT_VINUNI
        return energy_constants.DEFAULT_WEEKLY_UNITS_STUDENT_EXTERNAL
    return energy_constants.DEFAULT_WEEKLY_UNITS_FALLBACK


def plan_weekly_energy_units(plan: SubscriptionPlan, *, segment_default: int) -> int:
    """Weekly AI-energy shown for ONE plan on the comparison table.

    An explicit ``ai_weekly_energy_units`` on the plan (e.g. a paid tier) wins; else a
    partner plan falls back to the partner-org default and a student plan (the free
    tier) to the caller's segment default (VinUni 300 / external 120).
    """

    explicit = (plan.limits or {}).get(_WEEKLY_ENERGY_KEY)
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass
    if plan.audience == lifecycle.AUDIENCE_PARTNER:
        return energy_constants.DEFAULT_WEEKLY_UNITS_PARTNER_ORG
    return segment_default
