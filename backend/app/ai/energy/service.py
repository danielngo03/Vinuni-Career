"""AI energy meter — resolve allowance, measure consumption, enforce the gate.

Consumption is summed on demand from the ``ai_billable_usage`` ledger (credits =
``units_charged``), so there is no counter to drift. Two windows:

- **weekly** (calendar week, Monday 00:00 UTC): the HARD budget. A call is blocked
  when the scope's weekly consumption ≥ allowance **+ wallet**.
- **3h rolling**: SOFT burst warning only — never blocks.

Two independent budget checks resolve a member's state, persona-agnostically:

- **Org budget** — the org pool (``org`` account override, else plan
  ``ai_weekly_energy_units``, else the persona default) + org wallet, measured
  against org-wide consumption. Active for partner members always (their primary
  scope); for other personas ONLY when an admin has set an explicit ``org``
  ceiling row (so distribution starts permissive — nobody is falsely blocked
  before a superadmin distributes).
- **Member budget** — the most-specific applicable ceiling: a ``user`` account
  row ceiling, else the minimum ``department`` ceiling among the member's
  departments (measured against that department's consumption), else the org
  pool (measured against the member's own consumption). Active for
  student/university members always (their primary scope); for partner members
  ONLY when an admin has set a ``user``/``department`` sub-allocation row.

A call is BLOCKED if EITHER active budget is exhausted (consumption ≥ allowance +
wallet). This tightens ONLY when a matching account row exists, so with no
department/user/org rows behavior is unchanged (no regression).

Superadmins are EXEMPT: the meter reports an unlimited state and enforcement is a
no-op (USD/provider cost is still recorded elsewhere, never charged/blocked).

Students meter on their single ``user`` scope. Everything degrades OPEN on an
infra error (a metering failure must never wrongly block a paying user).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy import constants
from app.ai.energy.models import (
    SCOPE_DEPARTMENT,
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
    session: AsyncSession,
    *,
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    since: datetime,
) -> int:
    """Credits charged since ``since`` for exactly one attribution scope.

    Precedence when several are passed is department → org → user, but callers
    pass exactly one. Returns 0 when no scope is given.
    """

    conds = [AiBillableUsage.created_at >= since]
    if department_id is not None:
        conds.append(AiBillableUsage.department_id == department_id)
    elif org_id is not None:
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


async def _accounts_by_scope_id(
    session: AsyncSession, scope_type: str, scope_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, AiEnergyAccount]:
    """All energy accounts of ``scope_type`` for the given scope ids, keyed by id."""

    ids = {i for i in scope_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(AiEnergyAccount).where(
                AiEnergyAccount.scope_type == scope_type,
                AiEnergyAccount.scope_id.in_(ids),
            )
        )
    ).scalars().all()
    return {row.scope_id: row for row in rows}


async def _member_department_ids(
    session: AsyncSession, *, org_id: uuid.UUID, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """The member's department ids in the org (via the org read-model facade).

    Lazily imported to respect the module boundary — ``app.ai.energy`` never
    imports the ``organization`` ORM directly (mirrors the ``limit_facade``
    pattern above). Returns a deterministically sorted list.
    """

    try:
        from app.modules.organization.application import org_reporting_facade

        ids = await org_reporting_facade.department_ids_for_user_in_org(
            session, org_id=org_id, user_id=user_id
        )
    except Exception:  # noqa: BLE001 — dept resolution must never break metering
        return []
    return sorted(ids, key=str)


async def _org_pool_allowance(session: AsyncSession, principal: Principal) -> int:
    """The org pool weekly allowance: explicit ``org`` ceiling → plan → default."""

    org_id = principal.org_id
    acct = await _account(session, SCOPE_ORG, org_id) if org_id is not None else None
    allowance = (
        acct.weekly_allowance_units
        if acct is not None and acct.weekly_allowance_units is not None
        else None
    )
    if allowance is None:
        allowance = await _plan_weekly_units(session, principal)
    if allowance is None:
        allowance = _persona_default_weekly_units(principal)
    return allowance


def _is_university(principal: Principal) -> bool:
    persona = principal.persona
    return persona == _PERSONA_UNIVERSITY_STAFF or persona.startswith("university")


def _blocks(budget: _ScopeBudget | None) -> bool:
    """A budget blocks only when it has real capacity and is exhausted."""

    return budget is not None and budget.capacity > 0 and budget.exhausted


def _action_for(principal: Principal) -> str:
    """The exhaustion CTA the client should offer for this persona."""

    if principal.is_superadmin:
        return constants.ACTION_UNLIMITED
    if _is_university(principal):
        return constants.ACTION_REQUEST_CAPACITY
    return constants.ACTION_UPGRADE


async def _resolve_org_budget(
    session: AsyncSession,
    principal: Principal,
    *,
    week_start: datetime,
    session_start: datetime,
) -> _ScopeBudget | None:
    """The org-pool budget, or ``None`` when the org cap is not applicable.

    Active when the persona meters on the org (partner) OR a superadmin has set an
    explicit ``org`` ceiling row. Otherwise ``None`` — no org-wide cap is imposed
    before distribution (permissive by default).
    """

    org_id = principal.org_id
    if org_id is None:
        return None
    acct = await _account(session, SCOPE_ORG, org_id)
    metered = persona_meters_on_org(principal)
    has_ceiling = acct is not None and acct.weekly_allowance_units is not None
    if not metered and not has_ceiling:
        return None
    allowance = await _org_pool_allowance(session, principal)
    wallet = acct.wallet_units if acct is not None else 0
    weekly_used = await _weekly_used(session, org_id=org_id, since=week_start)
    session_used = await _weekly_used(session, org_id=org_id, since=session_start)
    return _ScopeBudget(
        scope_type=SCOPE_ORG,
        scope_id=org_id,
        weekly_allowance=allowance,
        wallet_units=wallet,
        weekly_used=weekly_used,
        session_used=session_used,
    )


async def _resolve_member_budget(
    session: AsyncSession,
    principal: Principal,
    *,
    week_start: datetime,
    session_start: datetime,
) -> _ScopeBudget | None:
    """The member's most-specific budget, or ``None`` when not applicable.

    Effective ceiling precedence: ``user`` row → minimum ``department`` row →
    org pool. The consumption basis matches the binding ceiling source (member's
    own usage for user/pool; the department's usage for a department ceiling).

    Active for user-metered personas always (student/university — their primary
    scope); for org-metered personas (partner) only when a ``user``/``department``
    sub-allocation row exists (so it tightens ONLY on an explicit admin row).
    """

    user_id = principal.user_id
    if user_id is None:
        return None
    metered_on_org = persona_meters_on_org(principal)

    user_acct = await _account(session, SCOPE_USER, user_id)
    user_ceiling = (
        user_acct.weekly_allowance_units
        if user_acct is not None and user_acct.weekly_allowance_units is not None
        else None
    )

    dept_ceiling: int | None = None
    dept_acct: AiEnergyAccount | None = None
    dept_id: uuid.UUID | None = None
    if user_ceiling is None and principal.org_id is not None:
        dept_ids = await _member_department_ids(
            session, org_id=principal.org_id, user_id=user_id
        )
        if dept_ids:
            accts = await _accounts_by_scope_id(session, SCOPE_DEPARTMENT, dept_ids)
            # Deterministic order (dept_ids is sorted); pick the tightest ceiling.
            capped = [
                (accts[d].weekly_allowance_units, d)
                for d in dept_ids
                if d in accts and accts[d].weekly_allowance_units is not None
            ]
            if capped:
                dept_ceiling, dept_id = min(capped, key=lambda t: (t[0], str(t[1])))
                dept_acct = accts[dept_id]

    has_sub_allocation = user_ceiling is not None or dept_ceiling is not None
    if metered_on_org and not has_sub_allocation:
        return None

    if user_ceiling is not None:
        allowance = user_ceiling
        wallet = user_acct.wallet_units if user_acct is not None else 0
        weekly_used = await _weekly_used(session, user_id=user_id, since=week_start)
        session_used = await _weekly_used(session, user_id=user_id, since=session_start)
        return _ScopeBudget(
            scope_type=SCOPE_USER,
            scope_id=user_id,
            weekly_allowance=allowance,
            wallet_units=wallet,
            weekly_used=weekly_used,
            session_used=session_used,
        )

    if dept_ceiling is not None and dept_id is not None:
        wallet = dept_acct.wallet_units if dept_acct is not None else 0
        weekly_used = await _weekly_used(
            session, department_id=dept_id, since=week_start
        )
        session_used = await _weekly_used(
            session, department_id=dept_id, since=session_start
        )
        return _ScopeBudget(
            scope_type=SCOPE_DEPARTMENT,
            scope_id=dept_id,
            weekly_allowance=dept_ceiling,
            wallet_units=wallet,
            weekly_used=weekly_used,
            session_used=session_used,
        )

    # Fallback: org pool ceiling measured against the member's OWN consumption.
    allowance = await _org_pool_allowance(session, principal)
    weekly_used = await _weekly_used(session, user_id=user_id, since=week_start)
    session_used = await _weekly_used(session, user_id=user_id, since=session_start)
    return _ScopeBudget(
        scope_type=SCOPE_USER,
        scope_id=user_id,
        weekly_allowance=allowance,
        wallet_units=0,
        weekly_used=weekly_used,
        session_used=session_used,
    )


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
    # Persona-aware exhaustion CTA: "request_capacity" (university), "upgrade"
    # (student/partner), or "unlimited" (superadmin).
    action: str
    # Superadmin (or otherwise uncapped) — the meter never blocks/charges.
    unlimited: bool = False

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
            "action": self.action,
            "unlimited": self.unlimited,
        }


def _unlimited_snapshot(principal: Principal, now: datetime) -> EnergySnapshot:
    """The state for a superadmin — full energy, never blocked, no CTA to buy."""

    scope_label = "org" if persona_meters_on_org(principal) else "user"
    return EnergySnapshot(
        scope=scope_label,
        energy_pct=100,
        weekly_used=0,
        weekly_allowance=0,
        wallet_units=0,
        session_used=0,
        session_soft_cap=0,
        blocked=False,
        blocked_reason=None,
        warn=False,
        warn_reason=None,
        week_reset=_iso(_week_reset(now)),
        action=constants.ACTION_UNLIMITED,
        unlimited=True,
    )


def _blocked_reason_for(
    principal: Principal, *, org_blocked: bool, member_blocked: bool
) -> str:
    """User-safe block reason code for a blocked principal."""

    if _is_university(principal):
        return constants.REASON_UNIVERSITY_ALLOCATION_EXCEEDED
    if org_blocked and persona_meters_on_org(principal):
        return constants.REASON_ORG_WEEKLY_EXCEEDED
    if member_blocked and persona_meters_on_org(principal):
        return constants.REASON_MEMBER_ALLOCATION_EXCEEDED
    if org_blocked:
        return constants.REASON_ORG_WEEKLY_EXCEEDED
    return constants.REASON_WEEKLY_EXCEEDED


async def snapshot(session: AsyncSession, *, principal: Principal) -> EnergySnapshot:
    """Resolve the caller's current energy state (never raises)."""
    now = datetime.now(UTC)
    week_start = _week_start(now)
    session_start = now - timedelta(hours=constants.SESSION_WINDOW_HOURS)

    on_org = persona_meters_on_org(principal)
    scope_label = "org" if on_org else "user"
    action = _action_for(principal)

    # Superadmin is exempt: report unlimited, never block/charge (WS1.1).
    if principal.is_superadmin:
        return _unlimited_snapshot(principal, now)

    try:
        org_budget = await _resolve_org_budget(
            session, principal, week_start=week_start, session_start=session_start
        )
        member_budget = await _resolve_member_budget(
            session, principal, week_start=week_start, session_start=session_start
        )
    except Exception:  # noqa: BLE001 — degrade to a permissive snapshot on infra error
        allowance = _persona_default_weekly_units(principal)
        capacity = allowance
        soft_cap = int(round(allowance * constants.SESSION_SOFT_FRACTION))
        return EnergySnapshot(
            scope=scope_label,
            energy_pct=_energy_pct(0, capacity),
            weekly_used=0,
            weekly_allowance=allowance,
            wallet_units=0,
            session_used=0,
            session_soft_cap=soft_cap,
            blocked=False,
            blocked_reason=None,
            warn=False,
            warn_reason=None,
            week_reset=_iso(_week_reset(now)),
            action=action,
        )

    # The primary budget drives the displayed scope + session window; both active
    # budgets participate in the block/warn decision.
    primary = org_budget if on_org else member_budget
    if primary is None:  # defensive — a normal principal always has a primary.
        primary = member_budget or org_budget
    if primary is None:
        allowance = _persona_default_weekly_units(principal)
        primary = _ScopeBudget(
            scope_type=scope_label,
            scope_id=principal.user_id or uuid.uuid4(),
            weekly_allowance=allowance,
            wallet_units=0,
            weekly_used=0,
            session_used=0,
        )

    active = [b for b in (member_budget, org_budget) if b is not None]
    org_blocked = _blocks(org_budget)
    member_blocked = _blocks(member_budget)
    blocked = org_blocked or member_blocked

    allowance = primary.weekly_allowance
    wallet = primary.wallet_units
    weekly_used = primary.weekly_used
    session_used = primary.session_used
    soft_cap = int(round(allowance * constants.SESSION_SOFT_FRACTION))

    # Meter reflects the tightest active constraint.
    remaining_pcts = [
        _energy_pct(b.weekly_used, b.capacity) for b in active if b.capacity > 0
    ]
    energy_pct = min(remaining_pcts) if remaining_pcts else _energy_pct(
        weekly_used, primary.capacity
    )
    used_pcts = [
        round(b.weekly_used * 100 / b.capacity) for b in active if b.capacity > 0
    ]
    weekly_pct_used = max(used_pcts) if used_pcts else 0

    over_burst = soft_cap > 0 and session_used >= soft_cap
    warn = blocked or (weekly_pct_used >= constants.WARNING_THRESHOLD_PCT) or over_burst

    blocked_reason = (
        _blocked_reason_for(
            principal, org_blocked=org_blocked, member_blocked=member_blocked
        )
        if blocked
        else None
    )
    if blocked:
        warn_reason: str | None = blocked_reason
    elif over_burst:
        warn_reason = "AI_SESSION_BURST"
    elif weekly_pct_used >= constants.WARNING_THRESHOLD_PCT:
        warn_reason = "AI_WEEKLY_NEARING_LIMIT"
    else:
        warn_reason = None

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
        action=action,
    )


# --------------------------------------------------------------------------- #
# Enforcement                                                                   #
# --------------------------------------------------------------------------- #


async def enforce_energy(session: AsyncSession, *, principal: Principal) -> None:
    """Hard gate before a token-spending AI call.

    Raises ``QuotaExceededError`` (409) only on genuine WEEKLY exhaustion (after
    wallet). The 3h window is advisory and never blocks here. No-op for
    unauthenticated principals and superadmins (WS1.1). Degrades OPEN on any infra
    error (a metering failure must never wrongly block a paying user).
    """
    if not principal.is_authenticated or principal.is_superadmin:
        return
    try:
        snap = await snapshot(session, principal=principal)
    except Exception:  # noqa: BLE001
        return
    if not snap.blocked:
        return

    reason = snap.blocked_reason
    details = {"reason": reason, "scope": snap.scope, "action": snap.action}

    if reason == constants.REASON_UNIVERSITY_ALLOCATION_EXCEEDED:
        # University = distribution, NOT billing. Never say "nâng gói / mua thêm".
        raise QuotaExceededError(
            "Bạn đã dùng hết năng lượng AI được cấp trong tuần. "
            "Vui lòng gửi yêu cầu cấp thêm hạn mức cho quản trị viên để tiếp tục.",
            details=details,
        )
    if reason == constants.REASON_ORG_WEEKLY_EXCEEDED:
        raise QuotaExceededError(
            "Tổ chức của bạn đã dùng hết năng lượng AI trong tuần. "
            "Quản trị viên có thể nâng gói hoặc mua thêm để tiếp tục.",
            details=details,
        )
    if reason == constants.REASON_MEMBER_ALLOCATION_EXCEEDED:
        raise QuotaExceededError(
            "Bạn đã dùng hết phần năng lượng AI được phân bổ trong tuần. "
            "Quản trị viên của tổ chức có thể tăng hạn mức cho bạn.",
            details=details,
        )
    raise QuotaExceededError(
        "Bạn đã dùng hết năng lượng AI trong tuần. Hạn mức sẽ đặt lại vào thứ Hai, "
        "hoặc bạn có thể nâng gói / mua thêm để tiếp tục.",
        details=details,
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


async def resolve_primary_department_id(
    session: AsyncSession, *, principal: Principal | None
) -> uuid.UUID | None:
    """The acting member's PRIMARY department id, or ``None``.

    Picked deterministically as the first (sorted) of the member's departments in
    their org. Call sites pass the result to :func:`build_usage_context` so each
    billable-usage row is attributed to a department for per-department energy
    accounting + ceilings. Never raises — metering must not break on a lookup
    failure.
    """

    if (
        principal is None
        or not principal.is_authenticated
        or principal.org_id is None
        or principal.user_id is None
    ):
        return None
    dept_ids = await _member_department_ids(
        session, org_id=principal.org_id, user_id=principal.user_id
    )
    return dept_ids[0] if dept_ids else None


def build_usage_context(
    principal: Principal | None,
    *,
    feature_key: str,
    task_type: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    idempotency_parts: tuple[Any, ...] | None = None,
) -> UsageContext:
    """Build a :class:`UsageContext` for a principal + feature.

    Sets ``billing_scope`` to the org pool for partner members, else the user
    scope. Pass ``department_id`` (resolve via
    :func:`resolve_primary_department_id`) to attribute the charge to a
    department. Pass ``idempotency_parts`` (the stable identity of the *result*)
    when the same logical result could be produced more than once.
    """
    if principal is None or not principal.is_authenticated:
        persona = PERSONA_SYSTEM
        org_id = None
        user_id = None
        billing_scope = "platform"
        department_id = None
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
        department_id=department_id,
        resource_type=resource_type,
        resource_id=resource_id,
        session_id=session_id,
        idempotency_key=idem,
    )


def charge_units(feature_key: str) -> int:
    """Cost-weighted credits a successful call to *feature_key* debits."""
    return constants.unit_cost(feature_key)
