"""Energy DISTRIBUTION helpers — read/write ``AiEnergyAccount`` ceilings.

The superadmin control plane distributes AI energy down the org → department →
user tree by setting ``weekly_allowance_units`` ceilings on
:class:`AiEnergyAccount` rows, and reads live weekly consumption grouped per
scope from the ``ai_billable_usage`` ledger.

These helpers keep all ``AiEnergyAccount`` ORM access inside ``app.ai.energy``
(the shared energy substrate) so the governance module never imports the ORM
directly. RBAC + audit live in the calling application service; these functions
are pure substrate reads/writes and never commit (the caller owns the tx).

Everything here is INTERNAL energy-credit accounting — never tokens, USD,
provider, or model.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy.models import (
    SCOPE_DEPARTMENT,
    SCOPE_ORG,
    SCOPE_USER,
    AiEnergyAccount,
)
from app.ai.observability.models import AiBillableUsage

_VALID_SCOPES = frozenset({SCOPE_ORG, SCOPE_DEPARTMENT, SCOPE_USER})


def current_week_start(now: datetime | None = None) -> datetime:
    """Monday 00:00 UTC of the current calendar week (weekly HARD window)."""

    now = now or datetime.now(UTC)
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday, time.min, tzinfo=UTC)


def is_valid_scope_type(scope_type: str) -> bool:
    return scope_type in _VALID_SCOPES


async def get_account(
    session: AsyncSession, *, scope_type: str, scope_id: uuid.UUID
) -> AiEnergyAccount | None:
    return (
        await session.execute(
            select(AiEnergyAccount).where(
                AiEnergyAccount.scope_type == scope_type,
                AiEnergyAccount.scope_id == scope_id,
            )
        )
    ).scalar_one_or_none()


async def upsert_allowance(
    session: AsyncSession,
    *,
    scope_type: str,
    scope_id: uuid.UUID,
    org_id: uuid.UUID | None,
    weekly_allowance_units: int | None,
    updated_by: uuid.UUID | None,
) -> AiEnergyAccount:
    """Create or update the ceiling for one scope (no commit).

    ``weekly_allowance_units = None`` clears the ceiling → the scope inherits the
    parent pool. The wallet balance is left untouched. Returns the flushed row.
    """

    acct = await get_account(session, scope_type=scope_type, scope_id=scope_id)
    if acct is None:
        acct = AiEnergyAccount(
            scope_type=scope_type,
            scope_id=scope_id,
            org_id=org_id,
            weekly_allowance_units=weekly_allowance_units,
            updated_by=updated_by,
        )
        session.add(acct)
    else:
        acct.weekly_allowance_units = weekly_allowance_units
        acct.org_id = org_id
        acct.updated_by = updated_by
    await session.flush()
    return acct


@dataclass(frozen=True, slots=True)
class ScopeAllowance:
    """A scope's ceiling + wallet, or ``None`` ceiling when it inherits."""

    weekly_allowance_units: int | None
    wallet_units: int


async def allowances_for(
    session: AsyncSession, *, scope_type: str, scope_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, ScopeAllowance]:
    """Ceiling + wallet per scope id (absent id ⇒ no row ⇒ inherits)."""

    ids = {i for i in scope_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(
                AiEnergyAccount.scope_id,
                AiEnergyAccount.weekly_allowance_units,
                AiEnergyAccount.wallet_units,
            ).where(
                AiEnergyAccount.scope_type == scope_type,
                AiEnergyAccount.scope_id.in_(ids),
            )
        )
    ).all()
    return {
        row.scope_id: ScopeAllowance(
            weekly_allowance_units=row.weekly_allowance_units,
            wallet_units=int(row.wallet_units or 0),
        )
        for row in rows
    }


async def used_by_users(
    session: AsyncSession, *, user_ids: Iterable[uuid.UUID], since: datetime
) -> dict[uuid.UUID, int]:
    """Weekly credits charged per user since ``since`` (grouped sum)."""

    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(
                AiBillableUsage.actor_user_id,
                func.coalesce(func.sum(AiBillableUsage.units_charged), 0),
            )
            .where(
                AiBillableUsage.actor_user_id.in_(ids),
                AiBillableUsage.created_at >= since,
            )
            .group_by(AiBillableUsage.actor_user_id)
        )
    ).all()
    return {row[0]: int(row[1] or 0) for row in rows}


async def used_by_departments(
    session: AsyncSession, *, department_ids: Iterable[uuid.UUID], since: datetime
) -> dict[uuid.UUID, int]:
    """Weekly credits charged per department since ``since`` (grouped sum)."""

    ids = {i for i in department_ids if i is not None}
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(
                AiBillableUsage.department_id,
                func.coalesce(func.sum(AiBillableUsage.units_charged), 0),
            )
            .where(
                AiBillableUsage.department_id.in_(ids),
                AiBillableUsage.created_at >= since,
            )
            .group_by(AiBillableUsage.department_id)
        )
    ).all()
    return {row[0]: int(row[1] or 0) for row in rows}


async def used_by_org(
    session: AsyncSession, *, org_id: uuid.UUID, since: datetime
) -> int:
    """Weekly credits charged org-wide since ``since``."""

    total = (
        await session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.org_id == org_id,
                AiBillableUsage.created_at >= since,
            )
        )
    ).scalar_one()
    return int(total or 0)
