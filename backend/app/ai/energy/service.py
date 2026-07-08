"""AI energy meter — resolve allowance, measure consumption, enforce the gate.

Consumption is summed on demand from the ``ai_billable_usage`` ledger (credits =
``units_charged``), so there is no counter to drift. Two windows:

- **weekly** (calendar week, Monday 00:00 UTC): the HARD budget. A call is blocked
  when the scope's weekly consumption ≥ allowance **+ wallet**.
- **3h rolling**: SOFT burst warning only — never blocks.

Resolution chain for a PARTNER member's call:
1. ORG pool — ``weekly_allowance_units`` (org account override, else plan
   ``ai_weekly_energy_units``, else the persona default) + org wallet.
2. the member's own sub-allocation ceiling + personal wallet, when an admin has
   set one (a ``user`` energy account row).
A call is blocked if EITHER the org pool OR the member's own ceiling is exhausted.

Students meter on their single ``user`` scope. Everything degrades OPEN on an
infra error (a metering failure must never wrongly block a paying user).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy import constants
from app.ai.energy.models import (
    SCOPE_ORG,
    SCOPE_USER,
    AiEnergyAccount,
)
from app.ai.observability.billable_usage import (
    PERSONA_PARTNER,
    PERSONA_STUDENT,
    PERSONA_SYSTEM,
    PERSONA_UNIVERSITY,
    UsageContext,
    make_idempotency_key,
)
from app.ai.observability.billable_usage import (
    SCOPE_ORG as LEDGER_SCOPE_ORG,
)
from app.ai.observability.billable_usage import (
    SCOPE_USER as LEDGER_SCOPE_USER,
)
from app.ai.observability.models import AiBillableUsage
from app.shared.exceptions import QuotaExceededError
from app.shared.permissions import Principal

# Auth persona vocabulary (mirror of app.modules.auth.domain.personas — kept as
# local literals to avoid a cross-module implementation import).
_PERSONA_PARTNER_MEMBER = "partner_member"
_PERSONA_UNIVERSITY_STAFF = "university_staff"
_PERSONA_STUDENT = "student"
_PERSONA_ALUMNI = "alumni"

# Personas whose AI budget is the shared partner ORG pool (vs the USER scope).
_ORG_PERSONAS = frozenset({_PERSONA_PARTNER_MEMBER})


def _week_start(now: datetime) -> datetime:
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday, time.min, tzinfo=UTC)


def _week_reset(now: datetime) -> datetime:
    return _week_start(now) + timedelta(days=7)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _energy_pct(used: int, capacity: int) -> int:
    """Remaining energy as a 0..100 percentage of total capacity."""
    if capacity <= 0:
        return 0
    remaining = max(0, capacity - used)
    return max(0, min(100, round(remaining * 100 / capacity)))


def persona_meters_on_org(principal: Principal) -> bool:
    """Whether this principal's AI budget is the shared partner ORG pool."""
    return principal.org_id is not None and principal.persona in _ORG_PERSONAS


# --------------------------------------------------------------------------- #
# Allowance resolution                                                          #
# --------------------------------------------------------------------------- #


async def _account(
    session: AsyncSession, scope_type: str, scope_id: uuid.UUID
) -> AiEnergyAccount | None:
    return (
        await session.execute(
            select(AiEnergyAccount).where(
                AiEnergyAccount.scope_type == scope_type,
                AiEnergyAccount.scope_id == scope_id,
            )
        )
    ).scalar_one_or_none()


async def _plan_weekly_units(session: AsyncSession, principal: Principal) -> int | None:
    """Weekly allowance from the resolved subscription plan, if the plan sets it."""
    try:
        from app.modules.billing.application import limit_facade

        value = await limit_facade.resolve_limit(
            session,
            principal,
            key=constants.PLAN_LIMIT_KEY_WEEKLY_UNITS,
            default=None,
        )
        if value is None:
            return None
        return int(value)
    except Exception:  # noqa: BLE001 — plan resolution must never break metering
        return None


def _persona_default_weekly_units(principal: Principal) -> int:
    persona = principal.persona
    if persona in _ORG_PERSONAS:
        return constants.DEFAULT_WEEKLY_UNITS_PARTNER_ORG
    if persona == _PERSONA_UNIVERSITY_STAFF or persona.startswith("university"):
        return constants.DEFAULT_WEEKLY_UNITS_UNIVERSITY
    if persona in (_PERSONA_STUDENT, _PERSONA_ALUMNI):
        # VinUni vs external is a plan/segment concern resolved via the facade
        # first; fall back to the external default (the safer, lower number).
        return constants.DEFAULT_WEEKLY_UNITS_STUDENT_EXTERNAL
    return constants.DEFAULT_WEEKLY_UNITS_FALLBACK


@dataclass(frozen=True, slots=True)
class _ScopeBudget:
    """Resolved capacity for one scope (org pool OR a member ceiling)."""

    scope_type: str
    scope_id: uuid.UUID
    weekly_allowance: int
    wallet_units: int
    weekly_used: int
    session_used: int

    @property
    def capacity(self) -> int:
        return self.weekly_allowance + self.wallet_units

    @property
    def exhausted(self) -> bool:
        return self.weekly_used >= self.capacity


async def _weekly_used(
    session: AsyncSession, *, org_id: uuid.UUID | None, user_id: uuid.UUID | None,
    since: datetime,
) -> int:
    conds = [AiBillableUsage.created_at >= since]
    if org_id is not None:
        conds.append(AiBillableUsage.org_id == org_id)
    elif user_id is not None:
        conds.append(AiBillableUsage.actor_user_id == user_id)
    else:
        return 0
    total = (
        await session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(*conds)
        )
    ).scalar_one()
    return int(total or 0)


# --------------------------------------------------------------------------- #
# Snapshot                                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EnergySnapshot:
    """PII/leakage-safe energy state for the UI meter and enforcement."""

    scope: str  # "org" | "user"
    energy_pct: int  # remaining, 0..100
    weekly_used: int
    weekly_allowance: int
    wallet_units: int
    session_used: int
    session_soft_cap: int
    blocked: bool
    blocked_reason: str | None
    warn: bool
    warn_reason: str | None
    week_reset: str

    def to_public(self) -> dict:
        """Shape returned to end users — credits/units are internal; expose %.

        We DO return the raw weekly used/allowance/wallet as opaque *energy*
        credit numbers (not tokens, not USD) so the UI can render a precise bar;
        the hidden-internals rule forbids tokens/USD/provider/model, not an
        abstract product credit count.
        """
        return {
            "scope": self.scope,
            "energy_pct": self.energy_pct,
            "weekly": {
                "used": self.weekly_used,
                "allowance": self.weekly_allowance,
                "wallet": self.wallet_units,
                "capacity": self.weekly_allowance + self.wallet_units,
            },
            "session_3h": {
                "used": self.session_used,
                "soft_cap": self.session_soft_cap,
                "over_soft_cap": self.session_used >= self.session_soft_cap > 0,
            },
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "warning": self.warn,
            "warning_reason": self.warn_reason,
            "week_reset": self.week_reset,
        }


async def snapshot(session: AsyncSession, *, principal: Principal) -> EnergySnapshot:
    """Resolve the caller's current energy state (never raises)."""
    now = datetime.now(UTC)
    week_start = _week_start(now)
    session_start = now - timedelta(hours=constants.SESSION_WINDOW_HOURS)

    on_org = persona_meters_on_org(principal)
    scope_label = "org" if on_org else "user"

    try:
        if on_org and principal.org_id is not None:
            org_id = principal.org_id
            acct = await _account(session, SCOPE_ORG, org_id)
            allowance = (
                acct.weekly_allowance_units
                if acct and acct.weekly_allowance_units is not None
                else None
            )
            if allowance is None:
                allowance = await _plan_weekly_units(session, principal)
            if allowance is None:
                allowance = _persona_default_weekly_units(principal)
            wallet = acct.wallet_units if acct else 0
            weekly_used = await _weekly_used(
                session, org_id=org_id, user_id=None, since=week_start
            )
            session_used = await _weekly_used(
                session, org_id=org_id, user_id=None, since=session_start
            )
        else:
            user_id = principal.user_id
            acct = await _account(session, SCOPE_USER, user_id) if user_id else None
            allowance = (
                acct.weekly_allowance_units
                if acct and acct.weekly_allowance_units is not None
                else None
            )
            if allowance is None:
                allowance = await _plan_weekly_units(session, principal)
            if allowance is None:
                allowance = _persona_default_weekly_units(principal)
            wallet = acct.wallet_units if acct else 0
            weekly_used = await _weekly_used(
                session, org_id=None, user_id=user_id, since=week_start
            )
            session_used = await _weekly_used(
                session, org_id=None, user_id=user_id, since=session_start
            )
    except Exception:  # noqa: BLE001 — degrade to a permissive snapshot on infra error
        allowance = _persona_default_weekly_units(principal)
        wallet = 0
        weekly_used = 0
        session_used = 0

    capacity = allowance + wallet
    soft_cap = int(round(allowance * constants.SESSION_SOFT_FRACTION))
    blocked = weekly_used >= capacity and capacity > 0
    weekly_pct_used = 0 if capacity <= 0 else round(weekly_used * 100 / capacity)
    over_burst = soft_cap > 0 and session_used >= soft_cap
    warn = (weekly_pct_used >= constants.WARNING_THRESHOLD_PCT) or over_burst
    warn_reason = None
    if blocked:
        warn = True
        warn_reason = (
            constants.REASON_ORG_WEEKLY_EXCEEDED if on_org
            else constants.REASON_WEEKLY_EXCEEDED
        )
    elif over_burst:
        warn_reason = "AI_SESSION_BURST"
    elif weekly_pct_used >= constants.WARNING_THRESHOLD_PCT:
        warn_reason = "AI_WEEKLY_NEARING_LIMIT"

    return EnergySnapshot(
        scope=scope_label,
        energy_pct=_energy_pct(weekly_used, capacity),
        weekly_used=weekly_used,
        weekly_allowance=allowance,
        wallet_units=wallet,
        session_used=session_used,
        session_soft_cap=soft_cap,
        blocked=blocked,
        blocked_reason=(
            (constants.REASON_ORG_WEEKLY_EXCEEDED if on_org
             else constants.REASON_WEEKLY_EXCEEDED)
            if blocked else None
        ),
        warn=warn,
        warn_reason=warn_reason,
        week_reset=_iso(_week_reset(now)),
    )


# --------------------------------------------------------------------------- #
# Enforcement                                                                   #
# --------------------------------------------------------------------------- #


async def enforce_energy(session: AsyncSession, *, principal: Principal) -> None:
    """Hard gate before a token-spending AI call.

    Raises ``QuotaExceededError`` (409) only on genuine WEEKLY exhaustion (after
    wallet). The 3h window is advisory and never blocks here. No-op for
    unauthenticated principals. Degrades OPEN on any infra error (a metering
    failure must never wrongly block a paying user).
    """
    if not principal.is_authenticated:
        return
    try:
        snap = await snapshot(session, principal=principal)
    except Exception:  # noqa: BLE001
        return
    if not snap.blocked:
        return
    if snap.scope == "org":
        raise QuotaExceededError(
            "Tổ chức của bạn đã dùng hết năng lượng AI trong tuần. "
            "Quản trị viên có thể nâng gói hoặc mua thêm để tiếp tục.",
            details={"reason": constants.REASON_ORG_WEEKLY_EXCEEDED, "scope": "org"},
        )
    raise QuotaExceededError(
        "Bạn đã dùng hết năng lượng AI trong tuần. Hạn mức sẽ đặt lại vào thứ Hai, "
        "hoặc bạn có thể nâng gói / mua thêm để tiếp tục.",
        details={"reason": constants.REASON_WEEKLY_EXCEEDED, "scope": "user"},
    )


# --------------------------------------------------------------------------- #
# UsageContext builder — call sites use this so the ledger + meter stay in sync #
# --------------------------------------------------------------------------- #


def _persona_for_ledger(principal: Principal) -> str:
    if not principal.is_authenticated:
        return PERSONA_SYSTEM
    if principal.persona in _ORG_PERSONAS:
        return PERSONA_PARTNER
    if principal.persona.startswith("university"):
        return PERSONA_UNIVERSITY
    if principal.persona in (_PERSONA_STUDENT, _PERSONA_ALUMNI):
        return PERSONA_STUDENT
    return PERSONA_SYSTEM


def build_usage_context(
    principal: Principal | None,
    *,
    feature_key: str,
    task_type: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    idempotency_parts: tuple[Any, ...] | None = None,
) -> UsageContext:
    """Build a :class:`UsageContext` for a principal + feature.

    Sets ``billing_scope`` to the org pool for partner members, else the user
    scope. Pass ``idempotency_parts`` (the stable identity of the *result*) when
    the same logical result could be produced more than once.
    """
    if principal is None or not principal.is_authenticated:
        persona = PERSONA_SYSTEM
        org_id = None
        user_id = None
        billing_scope = "platform"
    else:
        persona = _persona_for_ledger(principal)
        on_org = persona_meters_on_org(principal)
        org_id = principal.org_id
        user_id = principal.user_id
        billing_scope = LEDGER_SCOPE_ORG if on_org else LEDGER_SCOPE_USER

    idem = (
        make_idempotency_key(feature_key, *idempotency_parts)
        if idempotency_parts
        else None
    )
    return UsageContext(
        actor_persona=persona,
        feature_key=feature_key,
        task_type=task_type,
        billing_scope=billing_scope,
        actor_user_id=user_id,
        org_id=org_id,
        resource_type=resource_type,
        resource_id=resource_id,
        session_id=session_id,
        idempotency_key=idem,
    )


def charge_units(feature_key: str) -> int:
    """Cost-weighted credits a successful call to *feature_key* debits."""
    return constants.unit_cost(feature_key)
