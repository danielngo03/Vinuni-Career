"""Superadmin AI energy distribution API (WS1.6).

The platform superadmin distributes weekly AI energy down an org → department →
user tree by setting ``AiEnergyAccount`` ceilings, and reads a live
read-model of ceiling vs weekly consumption per scope (grouped ledger sums — no
heavy per-row joins).

Superadmin-only, enforced here in the service layer. Masked energy only —
credits + a remaining ``energy_pct`` — never tokens, USD, provider, or model.
Cross-module data (org type, departments, members, user identity) is resolved
through read-model facades, never a direct ORM import.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy import constants, distribution
from app.ai.energy.models import SCOPE_DEPARTMENT, SCOPE_ORG, SCOPE_USER
from app.modules.organization.application import org_reporting_facade
from app.modules.users.application import user_read_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal

MAX_ALLOWANCE_UNITS = 1_000_000
_ORG_TYPE_UNIVERSITY = "university"


def _require_superadmin(principal: Principal) -> None:
    if not principal.is_superadmin:
        raise PermissionDeniedError()


def _energy_pct(used: int, capacity: int | None) -> int | None:
    """Remaining energy as 0..100, or ``None`` when the scope has no own ceiling."""

    if capacity is None or capacity <= 0:
        return None
    remaining = max(0, capacity - used)
    return max(0, min(100, round(remaining * 100 / capacity)))


def _org_default_units(org_type: str | None) -> int:
    if org_type == _ORG_TYPE_UNIVERSITY:
        return constants.DEFAULT_WEEKLY_UNITS_UNIVERSITY
    return constants.DEFAULT_WEEKLY_UNITS_PARTNER_ORG


# --------------------------------------------------------------------------- #
# Read model                                                                    #
# --------------------------------------------------------------------------- #


async def list_allocations(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> dict[str, Any]:
    """Live distribution read-model for an org: org pool + departments + members.

    Each node carries its explicit ``weekly_allowance_units`` (``None`` = inherit),
    the ``units_used`` this week, and a masked ``energy_pct`` (``None`` when the
    node inherits — it has no own cap). One grouped sum per scope tier.
    """

    _require_superadmin(principal)
    org_type = await org_reporting_facade.org_type_for(session, org_id)
    if org_type is None:
        raise ResourceNotFoundError("Không tìm thấy tổ chức.")

    week_start = distribution.current_week_start()

    departments = await org_reporting_facade.list_departments_for_org(
        session, org_id=org_id
    )
    members = await org_reporting_facade.list_members_for_org(session, org_id=org_id)
    dept_ids = [d["id"] for d in departments]
    user_ids = [m["user_id"] for m in members]

    # Ceilings per tier.
    org_acct = await distribution.get_account(
        session, scope_type=SCOPE_ORG, scope_id=org_id
    )
    dept_allow = await distribution.allowances_for(
        session, scope_type=SCOPE_DEPARTMENT, scope_ids=dept_ids
    )
    user_allow = await distribution.allowances_for(
        session, scope_type=SCOPE_USER, scope_ids=user_ids
    )

    # Live weekly consumption per tier (grouped sums).
    org_used = await distribution.used_by_org(session, org_id=org_id, since=week_start)
    dept_used = await distribution.used_by_departments(
        session, department_ids=dept_ids, since=week_start
    )
    user_used = await distribution.used_by_users(
        session, user_ids=user_ids, since=week_start
    )
    contacts = await user_read_facade.get_user_contacts(session, user_ids)

    org_ceiling = org_acct.weekly_allowance_units if org_acct is not None else None
    org_effective = org_ceiling if org_ceiling is not None else _org_default_units(org_type)
    org_node = {
        "scope_type": SCOPE_ORG,
        "scope_id": str(org_id),
        "weekly_allowance_units": org_ceiling,
        "effective_allowance_units": org_effective,
        "wallet_units": int(org_acct.wallet_units) if org_acct is not None else 0,
        "units_used": org_used,
        "energy_pct": _energy_pct(org_used, org_effective),
    }

    dept_nodes: list[dict[str, Any]] = []
    for d in departments:
        did = d["id"]
        allow = dept_allow.get(did)
        ceiling = allow.weekly_allowance_units if allow is not None else None
        used = dept_used.get(did, 0)
        dept_nodes.append(
            {
                "scope_type": SCOPE_DEPARTMENT,
                "scope_id": str(did),
                "name": d["name"],
                "weekly_allowance_units": ceiling,
                "wallet_units": allow.wallet_units if allow is not None else 0,
                "units_used": used,
                "energy_pct": _energy_pct(used, ceiling),
            }
        )

    member_nodes: list[dict[str, Any]] = []
    for m in members:
        uid = m["user_id"]
        allow = user_allow.get(uid)
        ceiling = allow.weekly_allowance_units if allow is not None else None
        used = user_used.get(uid, 0)
        contact = contacts.get(uid)
        member_nodes.append(
            {
                "scope_type": SCOPE_USER,
                "scope_id": str(uid),
                "email": contact.email if contact else None,
                "name": contact.full_name if contact else None,
                "department_ids": [str(x) for x in m["department_ids"]],
                "weekly_allowance_units": ceiling,
                "wallet_units": allow.wallet_units if allow is not None else 0,
                "units_used": used,
                "energy_pct": _energy_pct(used, ceiling),
            }
        )

    return {
        "org_id": str(org_id),
        "org_type": org_type,
        "week_start": week_start.isoformat(),
        "org": org_node,
        "departments": dept_nodes,
        "members": member_nodes,
    }


# --------------------------------------------------------------------------- #
# Write                                                                         #
# --------------------------------------------------------------------------- #


def _validate_allowance(units: int | None) -> int | None:
    if units is None:
        return None
    units = int(units)
    if units < 0 or units > MAX_ALLOWANCE_UNITS:
        raise ValidationFailedError("Số năng lượng AI không hợp lệ.")
    return units


async def _validate_scope_belongs_to_org(
    session: AsyncSession,
    *,
    scope_type: str,
    scope_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """Ensure the target scope belongs to ``org_id`` (tenant safety)."""

    if await org_reporting_facade.org_type_for(session, org_id) is None:
        raise ResourceNotFoundError("Không tìm thấy tổ chức.")
    if scope_type == SCOPE_ORG:
        if scope_id != org_id:
            raise ValidationFailedError("Phạm vi tổ chức không khớp.")
        return
    if scope_type == SCOPE_DEPARTMENT:
        if not await org_reporting_facade.department_belongs_to_org(
            session, department_id=scope_id, org_id=org_id
        ):
            raise ValidationFailedError("Phòng ban không thuộc tổ chức này.")
        return
    if scope_type == SCOPE_USER:
        members = await org_reporting_facade.active_member_ids(
            session, org_id=org_id, user_ids=[scope_id]
        )
        if scope_id not in members:
            raise ValidationFailedError("Người dùng không thuộc tổ chức này.")
        return
    raise ValidationFailedError("Loại phạm vi không hợp lệ.")


async def upsert_allocation(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: AuditContext,
    scope_type: str,
    scope_id: uuid.UUID,
    org_id: uuid.UUID,
    weekly_allowance_units: int | None,
) -> dict[str, Any]:
    """Set (or clear) the weekly energy ceiling for one scope. Audited.

    ``weekly_allowance_units = None`` clears the ceiling → the scope inherits its
    parent pool. Validates that the scope belongs to the org before writing.
    """

    _require_superadmin(principal)
    if not distribution.is_valid_scope_type(scope_type):
        raise ValidationFailedError("Loại phạm vi không hợp lệ.")
    weekly_allowance_units = _validate_allowance(weekly_allowance_units)
    await _validate_scope_belongs_to_org(
        session, scope_type=scope_type, scope_id=scope_id, org_id=org_id
    )

    existing = await distribution.get_account(
        session, scope_type=scope_type, scope_id=scope_id
    )
    before = {
        "scope_type": scope_type,
        "scope_id": str(scope_id),
        "weekly_allowance_units": (
            existing.weekly_allowance_units if existing is not None else None
        ),
    }

    acct = await distribution.upsert_allowance(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
        # Org rows denormalize org_id = scope_id so the whole tree resolves fast.
        org_id=scope_id if scope_type == SCOPE_ORG else org_id,
        weekly_allowance_units=weekly_allowance_units,
        updated_by=principal.user_id,
    )
    after = {
        "scope_type": scope_type,
        "scope_id": str(scope_id),
        "org_id": str(org_id),
        "weekly_allowance_units": acct.weekly_allowance_units,
    }
    await write_audit(
        session,
        action="ai_energy_allocation.updated",
        resource_type="ai_energy_account",
        resource_id=acct.id,
        context=ctx,
        before=before,
        after=after,
    )
    await session.commit()
    return {
        "id": str(acct.id),
        "scope_type": acct.scope_type,
        "scope_id": str(acct.scope_id),
        "org_id": str(acct.org_id) if acct.org_id else None,
        "weekly_allowance_units": acct.weekly_allowance_units,
        "wallet_units": int(acct.wallet_units),
    }
