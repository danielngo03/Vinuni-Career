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
from app.shared import personas
from app.shared.exceptions import QuotaExceededError
from app.shared.permissions import Principal

# Auth persona vocabulary — sourced from the shared kernel (single source of
# truth) instead of re-declared literals. ``app/ai`` may import ``app/shared``
# (kernel) but not ``app.modules.auth`` (a cross-module implementation import).
_PERSONA_UNIVERSITY_STAFF = personas.UNIVERSITY_STAFF
_PERSONA_STUDENT = personas.STUDENT
_PERSONA_ALUMNI = personas.ALUMNI

# Personas whose AI budget is the shared partner ORG pool (vs the USER scope).
_ORG_PERSONAS = personas.ORG_PERSONAS


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


async def weekly_used_units(
    session: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> int:
    """Credits a scope consumed in the current calendar week (Mon 00:00 UTC).

    Public helper for the admin energy-overview surface so a per-member /
    per-org "used this week" number matches the snapshot exactly.
    """
    week_start = _week_start(datetime.now(UTC))
    return await _weekly_used(
        session, org_id=org_id, user_id=user_id, since=week_start
    )


# --------------------------------------------------------------------------- #
# Snapshot                                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EnergySnapshot:
    """PII/leakage-safe energy state for the UI meter and enforcement.

    For a partner member the primary meter (``weekly``) is the shared ORG pool
    (unchanged). When an admin has set that member a personal sub-allocation
    (a ``user`` energy account with a non-null ``weekly_allowance_units``), the
    ``allocation`` sub-block carries the member's OWN ceiling + wallet + usage,
    and the member is ``blocked`` when EITHER the org pool OR their own sub-cap
    is exhausted (wallet consumed after allowance within each scope).
    """

    scope: str  # "org" | "user"
    energy_pct: int  # remaining, 0..100 (the BINDING scope when a sub-cap exists)
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
    # Member sub-allocation (only set for a partner member with a sub-cap row).
    allocation_allowance: int | None = None
    allocation_wallet: int = 0
    allocation_used: int = 0
    allocation_blocked: bool = False

    def _allocation_public(self) -> dict | None:
        if self.allocation_allowance is None:
            return None
        capacity = self.allocation_allowance + self.allocation_wallet
        return {
            "used": self.allocation_used,
            "allowance": self.allocation_allowance,
            "wallet": self.allocation_wallet,
            "capacity": capacity,
            "energy_pct": _energy_pct(self.allocation_used, capacity),
            "blocked": self.allocation_blocked,
        }

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
            # Member's personal sub-allocation, or ``None`` when they share the
            # org pool directly (no admin sub-cap set).
            "allocation": self._allocation_public(),
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


async def org_pool_snapshot(
    session: AsyncSession, *, principal: Principal
) -> EnergySnapshot:
    """The PURE org-pool energy state, independent of the caller's personal sub-cap.

    ``snapshot`` folds a partner member's personal ``user`` sub-allocation into
    ``energy_pct``/``blocked`` (the MIN of the org pool and their own ceiling), so
    an admin who ALSO holds a personal sub-cap would see the org overview
    under-report the org pool. The admin energy overview needs the TRUE org pool
    (org allowance + org wallet + org-scoped weekly usage), so it uses this view.
    """
    return await snapshot(
        session, principal=principal, include_member_allocation=False
    )


async def snapshot(
    session: AsyncSession,
    *,
    principal: Principal,
    include_member_allocation: bool = True,
) -> EnergySnapshot:
    """Resolve the caller's current energy state (never raises).

    ``include_member_allocation`` (default ``True``) folds a partner member's
    personal ``user`` sub-cap into the binding meter. Set it ``False`` for a pure
    org-pool view (see :func:`org_pool_snapshot`).
    """
    now = datetime.now(UTC)
    week_start = _week_start(now)
    session_start = now - timedelta(hours=constants.SESSION_WINDOW_HOURS)

    on_org = persona_meters_on_org(principal)
    scope_label = "org" if on_org else "user"

    # Member sub-allocation (only populated for a partner member with a sub-cap).
    alloc_allowance: int | None = None
    alloc_wallet = 0
    alloc_used = 0

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
            # Member's personal sub-cap on top of the org pool: an admin has
            # allocated this member a weekly ceiling + optional personal wallet.
            # Skipped for a pure org-pool view (admin overview).
            member_id = principal.user_id
            member_acct = (
                await _account(session, SCOPE_USER, member_id)
                if include_member_allocation and member_id
                else None
            )
            if (
                member_acct is not None
                and member_acct.weekly_allowance_units is not None
            ):
                alloc_allowance = member_acct.weekly_allowance_units
                alloc_wallet = member_acct.wallet_units
                alloc_used = await _weekly_used(
                    session, org_id=None, user_id=member_id, since=week_start
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
        alloc_allowance = None
        alloc_wallet = 0
        alloc_used = 0

    capacity = allowance + wallet
    soft_cap = int(round(allowance * constants.SESSION_SOFT_FRACTION))
    org_blocked = weekly_used >= capacity and capacity > 0

    # Member sub-cap gate: blocked when the member's own ceiling + wallet is used
    # up (independent of the org pool). No sub-cap row → never member-blocked, so
    # a plain org-pool member is behaviourally unchanged.
    alloc_capacity = (alloc_allowance or 0) + alloc_wallet
    alloc_blocked = (
        alloc_allowance is not None
        and alloc_capacity > 0
        and alloc_used >= alloc_capacity
    )
    blocked = org_blocked or alloc_blocked

    # Meter % reflects the BINDING scope so it never shows headroom the member
    # cannot actually use.
    org_pct = _energy_pct(weekly_used, capacity)
    energy_pct = org_pct
    if alloc_allowance is not None:
        energy_pct = min(org_pct, _energy_pct(alloc_used, alloc_capacity))

    if org_blocked:
        blocked_reason: str | None = (
            constants.REASON_ORG_WEEKLY_EXCEEDED if on_org
            else constants.REASON_WEEKLY_EXCEEDED
        )
    elif alloc_blocked:
        blocked_reason = constants.REASON_MEMBER_ALLOCATION_EXCEEDED
    else:
        blocked_reason = None

    weekly_pct_used = 0 if capacity <= 0 else round(weekly_used * 100 / capacity)
    alloc_pct_used = (
        0 if alloc_capacity <= 0 else round(alloc_used * 100 / alloc_capacity)
    )
    over_burst = soft_cap > 0 and session_used >= soft_cap
    nearing = (
        weekly_pct_used >= constants.WARNING_THRESHOLD_PCT
        or alloc_pct_used >= constants.WARNING_THRESHOLD_PCT
    )
    warn = nearing or over_burst or blocked
    warn_reason = None
    if blocked:
        warn_reason = blocked_reason
    elif over_burst:
        warn_reason = "AI_SESSION_BURST"
    elif nearing:
        warn_reason = "AI_WEEKLY_NEARING_LIMIT"

    return EnergySnapshot(
        scope=scope_label,
        energy_pct=energy_pct,
        weekly_used=weekly_used,
        weekly_allowance=allowance,
        wallet_units=wallet,
        session_used=session_used,
        session_soft_cap=soft_cap,
        blocked=blocked,
        blocked_reason=blocked_reason,
        warn=warn,
        warn_reason=warn_reason,
        week_reset=_iso(_week_reset(now)),
        allocation_allowance=alloc_allowance,
        allocation_wallet=alloc_wallet,
        allocation_used=alloc_used,
        allocation_blocked=alloc_blocked,
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
    if snap.blocked_reason == constants.REASON_ORG_WEEKLY_EXCEEDED:
        raise QuotaExceededError(
            "Tổ chức của bạn đã dùng hết năng lượng AI trong tuần. "
            "Quản trị viên có thể nâng gói hoặc mua thêm để tiếp tục.",
            details={"reason": constants.REASON_ORG_WEEKLY_EXCEEDED, "scope": "org"},
        )
    if snap.blocked_reason == constants.REASON_MEMBER_ALLOCATION_EXCEEDED:
        raise QuotaExceededError(
            "Bạn đã dùng hết phần năng lượng AI được phân bổ cho bạn trong tuần. "
            "Bạn có thể mua thêm cho chính mình hoặc đề nghị quản trị viên tăng hạn mức.",
            details={
                "reason": constants.REASON_MEMBER_ALLOCATION_EXCEEDED,
                "scope": "user",
            },
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
