"""AI-energy settlement — the single choke point that turns an AI result into a
durable, idempotent charge.

CLAUDE.md ("AI usage accounting is product-critical"): every real provider call
that can affect user/partner/university value or cost must pass through a
usage-aware path with a durable ledger, idempotency, and budget attribution.
:func:`charge` is that path. ``AiTaskRunner`` (the single gateway for every LLM
call) calls it on each terminal outcome, and direct callers (e.g. the voice /
mock-interview relay) call it explicitly for turns that do not flow through the
runner.

What :func:`charge` guarantees:

- **Durable ledger.** Writes exactly one ``ai_billable_usage`` row per terminal
  result via :func:`billable_usage.record_billable_usage` — the append-only
  source of truth for attribution + weekly consumption. Only a ``success``
  result charges ``units_charged``; ``blocked`` / ``provider_failed`` /
  ``validation_failed`` / ``cached`` record the event with 0 units.
- **Idempotent.** A settled ``ctx.idempotency_key`` makes a Celery redelivery /
  client retry / cache reuse a COMPLETE no-op — the ledger is never
  double-charged and the wallet is never double-decremented.
- **Masked-account decrement.** For a NEW chargeable user/org-scoped result the
  purchased top-up wallet (``ai_energy_accounts.wallet_units``) is decremented
  for the portion of the charge that exceeds the current week's remaining
  allowance. Weekly-allowance consumption itself is NOT stored on the account —
  it is summed on demand from the ledger (migration ``0084``).
- **Never breaks the caller.** All work is best-effort: any failure is logged and
  swallowed so accounting can never disrupt the user's AI response, and the
  wallet mutation is savepoint-isolated so it can never poison the caller's
  transaction.

SECRECY: this module and the ledger deal only in a MASKED product currency
("energy units"). Provider / model / token / latency / raw USD internals are
never read, written, or surfaced here — the user surface only ever sees a
percentage derived from :class:`EnergyState`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.observability.billable_usage import (
    FEATURE_CHATBOT,
    FEATURE_COVER_LETTER,
    FEATURE_CV_EDIT_COMMAND,
    FEATURE_CV_EXTRACTION,
    FEATURE_CV_FIT_EXPLANATION,
    FEATURE_CV_SUGGESTION,
    FEATURE_EMBEDDINGS,
    FEATURE_INTERVIEW_SIM,
    FEATURE_JD_EXTRACTION,
    FEATURE_JD_WRITER,
    FEATURE_LEARNING_PLAN,
    FEATURE_RERANK,
    FEATURE_SCORECARD_SUGGESTION,
    FEATURE_SCREENING_BRIEF,
    SCOPE_DEPARTMENT,
    SCOPE_ORG,
    SCOPE_USER,
    UsageContext,
    record_billable_usage,
)
from app.ai.observability.models import AiBillableUsage
from app.core.config import get_settings
from app.modules.billing.application import limit_facade
from app.modules.billing.domain.models import AiEnergyAccount

_log = logging.getLogger("billing.energy_service")

# --------------------------------------------------------------------------- #
# Account scope vocabulary (mirrors ai_energy_accounts.scope_type).            #
# --------------------------------------------------------------------------- #
ACCOUNT_SCOPE_USER = "user"
ACCOUNT_SCOPE_ORG = "org"
ACCOUNT_SCOPE_DEPARTMENT = "department"

# Per-feature masked base-unit weights (§3.3). The masked energy "cost" of one
# successful call, keyed by ``UsageContext.feature_key``. These are calibrated
# placeholders (never surfaced as a raw number); tune in the shadow period. A
# direct caller may override with an explicit ``base_units`` argument.
_DEFAULT_BASE_UNITS = 1
_FEATURE_BASE_UNITS: dict[str, int] = {
    FEATURE_CHATBOT: 1,
    FEATURE_EMBEDDINGS: 1,
    FEATURE_RERANK: 1,
    FEATURE_CV_SUGGESTION: 2,
    FEATURE_CV_EDIT_COMMAND: 2,
    FEATURE_CV_FIT_EXPLANATION: 2,
    FEATURE_COVER_LETTER: 2,
    FEATURE_INTERVIEW_SIM: 2,
    FEATURE_LEARNING_PLAN: 2,
    FEATURE_JD_WRITER: 2,
    FEATURE_SCREENING_BRIEF: 2,
    FEATURE_SCORECARD_SUGGESTION: 2,
    FEATURE_CV_EXTRACTION: 3,
    FEATURE_JD_EXTRACTION: 3,
}

# Fallback weekly allowance for an org/department scope whose account carries no
# explicit ``weekly_allowance_units`` ceiling. Calibrated placeholder (there is
# no per-org tier resolver yet — see the limit_facade student resolver); documented
# as follow-up so wallet spend for orgs stays deterministic and testable.
_DEFAULT_ORG_WEEKLY_ALLOWANCE_UNITS = 5000


def base_units_for(feature_key: str) -> int:
    """The masked base unit weight for one successful call of ``feature_key``."""

    return _FEATURE_BASE_UNITS.get(feature_key, _DEFAULT_BASE_UNITS)


@dataclass(frozen=True, slots=True)
class EnergyState:
    """Masked, user-safe snapshot of a scope's remaining AI energy.

    Contains only masked product units — never provider/model/token/USD data.
    The user surface converts ``remaining_units`` / the allowance to a percentage;
    the raw numbers stay internal.
    """

    scope_type: str
    scope_id: uuid.UUID
    consumed_units: int
    weekly_allowance_units: int
    wallet_units: int
    remaining_units: int
    exhausted: bool


# --------------------------------------------------------------------------- #
# Time helpers                                                                 #
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _week_start(now: datetime) -> datetime:
    """UTC Monday 00:00 of ``now``'s ISO week (the weekly-allowance window)."""

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=now.weekday())


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


# --------------------------------------------------------------------------- #
# Scope resolution                                                             #
# --------------------------------------------------------------------------- #


def _account_scope(ctx: UsageContext) -> tuple[str, uuid.UUID] | None:
    """Map a usage context to the ``(scope_type, scope_id)`` that pays for it.

    ``platform``/``system`` calls and contexts missing the required id resolve to
    ``None`` (platform-funded — the ledger is still written, no wallet is spent).
    ``department`` scope falls back to the owning org because ``UsageContext`` does
    not carry a department id.
    """

    if ctx.billing_scope == SCOPE_USER and ctx.actor_user_id is not None:
        return (ACCOUNT_SCOPE_USER, ctx.actor_user_id)
    if ctx.billing_scope == SCOPE_ORG and ctx.org_id is not None:
        return (ACCOUNT_SCOPE_ORG, ctx.org_id)
    if ctx.billing_scope == SCOPE_DEPARTMENT and ctx.org_id is not None:
        return (ACCOUNT_SCOPE_ORG, ctx.org_id)
    return None


# --------------------------------------------------------------------------- #
# The settlement choke point                                                  #
# --------------------------------------------------------------------------- #


async def charge(
    session: AsyncSession,
    *,
    ctx: UsageContext,
    result_status: str,
    base_units: int | None = None,
    provider_cost_usd: float | None = None,
) -> None:
    """Settle one AI result: durable idempotent ledger row + masked wallet decrement.

    ``base_units`` is OPTIONAL: the gateway ``AiTaskRunner`` omits it and the
    per-feature weight table (:func:`base_units_for`, keyed by
    ``ctx.feature_key``) is used; a direct caller (e.g. the voice relay) may pass
    an explicit weight. Only a ``success`` result charges units — every other
    terminal status records a 0-unit attribution row.

    NEVER raises into the caller's critical path: any failure is logged and
    swallowed, matching the best-effort accounting contract, and the caller owns
    the surrounding transaction / commit.
    """

    try:
        units = base_units if base_units is not None else base_units_for(ctx.feature_key)

        # Idempotency short-circuit: a settled key is a COMPLETE no-op — never a
        # second ledger row, never a second wallet decrement.
        if ctx.idempotency_key is not None and await _ledger_exists(
            session, ctx.idempotency_key
        ):
            return

        row = await record_billable_usage(
            session,
            ctx=ctx,
            result_status=result_status,
            base_units=units,
            provider_cost_usd=provider_cost_usd,
        )

        # Only a genuinely charged (units > 0) user/org-scoped result spends the
        # persistent top-up wallet. Free/blocked/failed results attribute only.
        if row.units_charged > 0:
            await _spend_wallet_overflow(session, ctx=ctx, units=row.units_charged)
    except Exception:  # noqa: BLE001 — accounting must never break the AI response.
        _log.warning("ai_energy_charge_failed", exc_info=True)


async def _ledger_exists(session: AsyncSession, idempotency_key: str) -> bool:
    result = await session.execute(
        select(AiBillableUsage.id).where(
            AiBillableUsage.idempotency_key == idempotency_key
        )
    )
    return result.first() is not None


async def _spend_wallet_overflow(
    session: AsyncSession,
    *,
    ctx: UsageContext,
    units: int,
    now: datetime | None = None,
) -> None:
    """Decrement the top-up wallet by this charge's over-the-weekly-allowance part.

    Weekly-allowance consumption is tracked by the ledger sum (not stored on the
    account, per migration 0084); the wallet is spent only for the overflow this
    specific charge pushed past the current week's remaining allowance. Runs in a
    savepoint so a failure can never poison the caller's transaction.
    """

    scope = _account_scope(ctx)
    if scope is None:
        return
    scope_type, scope_id = scope
    now = now or _now()

    nested = await session.begin_nested()
    try:
        account = await _load_account(session, scope_type, scope_id, lock=True)
        if account is None or account.wallet_units <= 0:
            await nested.commit()
            return

        allowance = await _weekly_allowance(session, account, scope_type, scope_id, now=now)
        consumed = await _consumed_this_week(session, scope_type, scope_id, now=now)
        consumed_before = consumed - units
        spend = max(0, consumed - allowance) - max(0, consumed_before - allowance)
        if spend > 0:
            account.wallet_units = max(0, account.wallet_units - spend)
            account.updated_at = now
        await nested.commit()
    except Exception:
        if nested.is_active:
            await nested.rollback()
        raise


# --------------------------------------------------------------------------- #
# Exhaustion read model (masked)                                              #
# --------------------------------------------------------------------------- #


async def energy_state(
    session: AsyncSession,
    *,
    scope_type: str,
    scope_id: uuid.UUID,
    now: datetime | None = None,
) -> EnergyState:
    """Masked remaining-energy snapshot for a scope (weekly allowance + wallet).

    ``remaining = max(0, weekly_allowance + wallet - consumed_this_week)``;
    ``exhausted`` is ``remaining <= 0``. Persona-appropriate exhaustion UX
    (student/partner upgrade vs university admin-limit workflow) is built on top of
    this by the surfaces — this function only reports the masked numbers.
    """

    now = now or _now()
    account = await _load_account(session, scope_type, scope_id)
    wallet = account.wallet_units if account is not None else 0
    allowance = await _weekly_allowance(session, account, scope_type, scope_id, now=now)
    consumed = await _consumed_this_week(session, scope_type, scope_id, now=now)
    remaining = max(0, allowance + wallet - consumed)
    return EnergyState(
        scope_type=scope_type,
        scope_id=scope_id,
        consumed_units=consumed,
        weekly_allowance_units=allowance,
        wallet_units=wallet,
        remaining_units=remaining,
        exhausted=remaining <= 0,
    )


async def is_exhausted(
    session: AsyncSession,
    *,
    scope_type: str,
    scope_id: uuid.UUID,
    now: datetime | None = None,
) -> bool:
    """Whether a scope has spent its weekly allowance AND top-up wallet."""

    state = await energy_state(session, scope_type=scope_type, scope_id=scope_id, now=now)
    return state.exhausted


# --------------------------------------------------------------------------- #
# Internal queries                                                            #
# --------------------------------------------------------------------------- #


async def _load_account(
    session: AsyncSession,
    scope_type: str,
    scope_id: uuid.UUID,
    *,
    lock: bool = False,
) -> AiEnergyAccount | None:
    stmt = select(AiEnergyAccount).where(
        AiEnergyAccount.scope_type == scope_type,
        AiEnergyAccount.scope_id == scope_id,
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def _weekly_allowance(
    session: AsyncSession,
    account: AiEnergyAccount | None,
    scope_type: str,
    scope_id: uuid.UUID,
    *,
    now: datetime,
) -> int:
    if account is not None and account.weekly_allowance_units is not None:
        return int(account.weekly_allowance_units)
    if scope_type == ACCOUNT_SCOPE_USER:
        return await limit_facade.resolve_user_weekly_energy_units(session, scope_id, now=now)
    return _DEFAULT_ORG_WEEKLY_ALLOWANCE_UNITS


async def _consumed_this_week(
    session: AsyncSession,
    scope_type: str,
    scope_id: uuid.UUID,
    *,
    now: datetime,
) -> int:
    """Sum of charged units for the scope since UTC Monday (ledger is the truth)."""

    week_start = _week_start(now)
    scope_col = (
        AiBillableUsage.actor_user_id
        if scope_type == ACCOUNT_SCOPE_USER
        else AiBillableUsage.org_id
    )
    total = await session.scalar(
        select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
            scope_col == scope_id,
            AiBillableUsage.created_at >= week_start,
        )
    )
    return int(total or 0)
