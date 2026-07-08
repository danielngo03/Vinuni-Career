"""AI energy administration — org overview, sub-allocation, wallet grants, and
manual/bank-transfer top-up purchases (partner AI overhaul, write path).

The meter (``app.ai.energy.service``) is read-only: it resolves the org pool +
per-member sub-cap and gates calls. This module is the WRITE path that lets a
partner admin allocate the org pool to departments/members, and lets a member
(or admin) buy more energy when a scope runs out.

RBAC + audit + tenant isolation live HERE (not in routers):

- **Management** (``billing:manage``, org-scoped): the org energy overview,
  setting a department/member weekly sub-cap, granting goodwill wallet to a
  department/member, and requesting a top-up for a department/org. A partner
  Admin holds ``*:*`` so this is covered; a delegated recruiter role can be
  granted ``billing:manage`` narrowly (never hardcoded to a role name).
- **Finance** (superadmin OR a ``university`` org member holding
  ``billing:moderate``): confirming money received for a top-up (crediting real
  wallet capacity), mirroring how ``billing.moderation_service.mark_paid``
  confirms a manual subscription payment. This is a deliberate security choice:
  a partner Admin's ``*:*`` must NOT be able to self-confirm a bank transfer and
  mint free org-wide AI energy that VinUni pays for. For the same reason an
  ``org``-scope wallet grant (net-new org capacity) also requires finance, while
  ``department``/``user`` sub-cap grants (bounded by the org pool via the
  either-exhausted gate) are allowed under management.
- **Self-service**: any authenticated org member may request a top-up for
  THEMSELVES and list/get their own top-ups.

``price_amount``/``currency`` on a top-up are a REAL product price (VND), like a
subscription — allowed. Tokens/USD/provider/model are never stored or exposed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.energy import service as energy_service
from app.ai.energy.models import (
    SCOPE_DEPARTMENT,
    SCOPE_ORG,
    SCOPE_USER,
    TOPUP_CANCELLED,
    TOPUP_PAID,
    TOPUP_PENDING,
    AiEnergyAccount,
    AiEnergyTopup,
)
from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.pagination import clamp_limit
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "billing"

# Internal reference packs (not a table). Prices are a real product price (VND).
ENERGY_PACKS: dict[str, dict] = {
    "small": {"code": "small", "units": 200, "price_amount": Decimal("50000")},
    "medium": {"code": "medium", "units": 500, "price_amount": Decimal("110000")},
    "large": {"code": "large", "units": 1200, "price_amount": Decimal("240000")},
}
_TOPUP_CURRENCY = "VND"

# Static manual/bank-transfer instructions (mirrors billing subscriptions).
_PAYMENT_INSTRUCTIONS: dict[str, str] = {
    "method": "bank_transfer",
    "bank_name": "Vietcombank",
    "account_name": "VINUNI CAREER CENTER",
    "account_number": "0123456789",
    "note_hint": "VINUNI-ENERGY",
}

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        TOPUP_PENDING: "Chờ thanh toán",
        TOPUP_PAID: "Đã thanh toán",
        TOPUP_CANCELLED: "Đã huỷ",
    },
    "en": {
        TOPUP_PENDING: "Pending payment",
        TOPUP_PAID: "Paid",
        TOPUP_CANCELLED: "Cancelled",
    },
}


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


def _audit_ctx(principal: Principal, ctx: RequestContext | None) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip if ctx else None,
        user_agent=ctx.user_agent if ctx else None,
    )


# --------------------------------------------------------------------------- #
# RBAC gates                                                                    #
# --------------------------------------------------------------------------- #


def _org_context(principal: Principal) -> uuid.UUID:
    """The caller's org for an org-scoped admin action (else 403)."""
    if principal.org_id is None:
        raise PermissionDeniedError(details={"reason": "org_context_required"})
    return principal.org_id


def _require_manage(principal: Principal) -> None:
    """Org-scoped energy management (allocation / wallet / admin top-up)."""
    permission_checker.require(
        principal, _RESOURCE, "manage", resource_org_id=principal.org_id
    )


async def _require_finance(session: AsyncSession, principal: Principal) -> None:
    """Money-received confirm authority: superadmin OR university billing:moderate.

    Mirrors ``billing.moderation_service._require_billing_moderator`` so a partner
    Admin's ``*:*`` cannot self-confirm a top-up and mint free AI energy.
    """
    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, "moderate")
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "finance_only"})


# --------------------------------------------------------------------------- #
# Scope validation (tenant isolation)                                           #
# --------------------------------------------------------------------------- #


async def _validate_scope_in_org(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    scope_type: str,
    scope_id: uuid.UUID,
) -> None:
    """Ensure a department/user scope belongs to ``org_id`` (else 403)."""
    if scope_type == SCOPE_DEPARTMENT:
        ok = await org_reporting_facade.department_in_org(
            session, org_id=org_id, department_id=scope_id
        )
        if not ok:
            raise PermissionDeniedError(details={"reason": "cross_org_scope"})
    elif scope_type == SCOPE_USER:
        members = await org_reporting_facade.active_member_ids(
            session, org_id=org_id, user_ids={scope_id}
        )
        if scope_id not in members:
            raise PermissionDeniedError(details={"reason": "cross_org_scope"})
    else:
        raise ValidationFailedError(
            details={"field": "scope_type", "reason": "invalid_scope"}
        )


# --------------------------------------------------------------------------- #
# Account helpers                                                               #
# --------------------------------------------------------------------------- #


async def _load_account(
    session: AsyncSession, scope_type: str, scope_id: uuid.UUID, *, lock: bool = False
) -> AiEnergyAccount | None:
    stmt = select(AiEnergyAccount).where(
        AiEnergyAccount.scope_type == scope_type,
        AiEnergyAccount.scope_id == scope_id,
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def _upsert_account(
    session: AsyncSession,
    *,
    scope_type: str,
    scope_id: uuid.UUID,
    org_id: uuid.UUID | None,
    updated_by: uuid.UUID | None,
    lock: bool = False,
) -> AiEnergyAccount:
    acct = await _load_account(session, scope_type, scope_id, lock=lock)
    if acct is None:
        acct = AiEnergyAccount(
            scope_type=scope_type,
            scope_id=scope_id,
            org_id=org_id,
            wallet_units=0,
            updated_by=updated_by,
        )
        session.add(acct)
        await session.flush()
    elif org_id is not None and acct.org_id is None:
        acct.org_id = org_id
    return acct


# --------------------------------------------------------------------------- #
# Presenters                                                                    #
# --------------------------------------------------------------------------- #


def _status_label(status: str, *, locale: str) -> str:
    return _STATUS_LABELS.get(locale, _STATUS_LABELS["vi"]).get(status, status)


def _present_topup(topup: AiEnergyTopup, *, locale: str = "vi") -> dict:
    return {
        "id": str(topup.id),
        "org_id": str(topup.org_id) if topup.org_id else None,
        "scope_type": topup.scope_type,
        "scope_id": str(topup.scope_id),
        "units": topup.units,
        "price_amount": f"{topup.price_amount:.2f}",
        "currency": topup.currency,
        "status": topup.status,
        "status_label": _status_label(topup.status, locale=locale),
        "pack_code": topup.pack_code,
        "payment_reference": topup.payment_reference,
        "requested_by": str(topup.requested_by),
        "paid_at": topup.paid_at.astimezone(UTC).isoformat() if topup.paid_at else None,
        "created_at": (
            topup.created_at.astimezone(UTC).isoformat() if topup.created_at else None
        ),
        "version": topup.version,
    }


def _packs_public() -> list[dict]:
    return [
        {
            "code": p["code"],
            "units": p["units"],
            "price_amount": f"{p['price_amount']:.2f}",
            "currency": _TOPUP_CURRENCY,
        }
        for p in ENERGY_PACKS.values()
    ]


# --------------------------------------------------------------------------- #
# Org overview                                                                  #
# --------------------------------------------------------------------------- #


async def get_org_energy_overview(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    """The org pool snapshot + every department/member sub-allocation.

    Management-gated, org-scoped. Never exposes tokens/USD/provider/model — only
    abstract energy credits + the derived %.
    """
    _require_manage(principal)
    org_id = _org_context(principal)

    pool = await energy_service.snapshot(session, principal=principal)

    rows = (
        await session.execute(
            select(AiEnergyAccount).where(
                AiEnergyAccount.org_id == org_id,
                AiEnergyAccount.scope_type.in_([SCOPE_DEPARTMENT, SCOPE_USER]),
            )
        )
    ).scalars().all()

    allocations: list[dict] = []
    for acct in rows:
        # Per-member weekly usage is metered (user-scoped ledger); department
        # usage is advisory until the ledger carries department_id (follow-up).
        weekly_used = 0
        if acct.scope_type == SCOPE_USER:
            weekly_used = await energy_service.weekly_used_units(
                session, user_id=acct.scope_id
            )
        allocations.append(
            {
                "scope_type": acct.scope_type,
                "scope_id": str(acct.scope_id),
                "weekly_allowance_units": acct.weekly_allowance_units,
                "wallet_units": acct.wallet_units,
                "weekly_used": weekly_used,
                "enforced": acct.scope_type == SCOPE_USER,
            }
        )

    return {
        "org_pool": pool.to_public(),
        "allocations": allocations,
        "packs": _packs_public(),
    }


# --------------------------------------------------------------------------- #
# Allocation (department / member weekly sub-cap)                               #
# --------------------------------------------------------------------------- #


async def set_allocation(
    session: AsyncSession,
    *,
    principal: Principal,
    scope_type: str,
    scope_id: uuid.UUID,
    weekly_allowance_units: int | None,
    ctx: RequestContext | None = None,
    locale: str = "vi",
) -> dict:
    """Set (or clear, with ``None``) a department/member weekly sub-cap.

    The org allowance itself is plan-driven, so only ``department``/``user``
    scopes are settable here. ``None`` clears the sub-cap → that scope shares the
    org pool again.
    """
    _require_manage(principal)
    org_id = _org_context(principal)
    if scope_type not in (SCOPE_DEPARTMENT, SCOPE_USER):
        raise ValidationFailedError(
            details={"field": "scope_type", "reason": "invalid_scope"}
        )
    if weekly_allowance_units is not None and weekly_allowance_units < 0:
        raise ValidationFailedError(
            details={"field": "weekly_allowance_units", "reason": "out_of_range"}
        )
    await _validate_scope_in_org(
        session, org_id=org_id, scope_type=scope_type, scope_id=scope_id
    )

    acct = await _upsert_account(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
        org_id=org_id,
        updated_by=principal.user_id,
        lock=True,
    )
    before = acct.weekly_allowance_units
    acct.weekly_allowance_units = weekly_allowance_units
    acct.updated_by = principal.user_id
    await session.flush()

    await write_audit(
        session,
        action="ai_energy.allocation_set",
        resource_type="ai_energy_account",
        resource_id=acct.id,
        context=_audit_ctx(principal, ctx),
        before={"weekly_allowance_units": before},
        after={
            "scope_type": scope_type,
            "scope_id": str(scope_id),
            "weekly_allowance_units": weekly_allowance_units,
        },
    )
    await session.commit()
    return {
        "scope_type": scope_type,
        "scope_id": str(scope_id),
        "weekly_allowance_units": acct.weekly_allowance_units,
        "wallet_units": acct.wallet_units,
    }


# --------------------------------------------------------------------------- #
# Wallet grant (goodwill — no purchase)                                         #
# --------------------------------------------------------------------------- #


async def grant_wallet(
    session: AsyncSession,
    *,
    principal: Principal,
    scope_type: str,
    scope_id: uuid.UUID,
    units: int,
    reason: str,
    ctx: RequestContext | None = None,
    locale: str = "vi",
) -> dict:
    """Add goodwill ``wallet_units`` to a scope (a manual grant, not a purchase).

    Department/member grants are management-gated (bounded by the org pool via
    the either-exhausted meter). An ``org``-scope grant mints net-new org-wide
    capacity, so it requires the finance authority — a partner Admin cannot
    self-grant free org energy.
    """
    if units <= 0:
        raise ValidationFailedError(
            details={"field": "units", "reason": "out_of_range"}
        )
    if not reason or not reason.strip():
        raise ValidationFailedError(details={"field": "reason", "reason": "required"})

    if scope_type == SCOPE_ORG:
        await _require_finance(session, principal)
        org_id = scope_id  # target org (finance may credit any org)
    elif scope_type in (SCOPE_DEPARTMENT, SCOPE_USER):
        _require_manage(principal)
        org_id = _org_context(principal)
        await _validate_scope_in_org(
            session, org_id=org_id, scope_type=scope_type, scope_id=scope_id
        )
    else:
        raise ValidationFailedError(
            details={"field": "scope_type", "reason": "invalid_scope"}
        )

    acct = await _upsert_account(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
        org_id=org_id,
        updated_by=principal.user_id,
        lock=True,
    )
    acct.wallet_units += units
    acct.updated_by = principal.user_id
    await session.flush()

    await write_audit(
        session,
        action="ai_energy.wallet_granted",
        resource_type="ai_energy_account",
        resource_id=acct.id,
        context=_audit_ctx(principal, ctx),
        after={
            "scope_type": scope_type,
            "scope_id": str(scope_id),
            "units": units,
            "reason": reason.strip()[:200],
            "wallet_units": acct.wallet_units,
        },
    )
    await session.commit()
    return {
        "scope_type": scope_type,
        "scope_id": str(scope_id),
        "wallet_units": acct.wallet_units,
    }


# --------------------------------------------------------------------------- #
# Top-up purchase (request -> pending -> finance confirm -> credit)             #
# --------------------------------------------------------------------------- #


async def request_topup(
    session: AsyncSession,
    *,
    principal: Principal,
    pack_code: str,
    scope_type: str = SCOPE_USER,
    scope_id: uuid.UUID | None = None,
    ctx: RequestContext | None = None,
    locale: str = "vi",
) -> dict:
    """Create a ``pending`` top-up + return bank-transfer instructions.

    Any authenticated org member may request for THEMSELVES (``user`` scope,
    ``scope_id`` defaults to the caller). Requesting for another member, a
    department, or the org requires management (``billing:manage``).
    """
    if not principal.is_authenticated or principal.user_id is None:
        raise PermissionDeniedError()
    org_id = _org_context(principal)

    pack = ENERGY_PACKS.get(pack_code)
    if pack is None:
        raise ValidationFailedError(
            details={"field": "pack_code", "reason": "invalid_pack"}
        )

    if scope_type == SCOPE_USER:
        target_id: uuid.UUID = scope_id or principal.user_id
        if target_id != principal.user_id:
            _require_manage(principal)  # admin requesting on behalf of a member
        await _validate_scope_in_org(
            session, org_id=org_id, scope_type=SCOPE_USER, scope_id=target_id
        )
    elif scope_type == SCOPE_DEPARTMENT:
        _require_manage(principal)
        if scope_id is None:
            raise ValidationFailedError(
                details={"field": "scope_id", "reason": "required"}
            )
        target_id = scope_id
        await _validate_scope_in_org(
            session, org_id=org_id, scope_type=SCOPE_DEPARTMENT, scope_id=target_id
        )
    elif scope_type == SCOPE_ORG:
        _require_manage(principal)
        target_id = scope_id or org_id
        if target_id != org_id:
            raise PermissionDeniedError(details={"reason": "cross_org_scope"})
    else:
        raise ValidationFailedError(
            details={"field": "scope_type", "reason": "invalid_scope"}
        )

    topup = AiEnergyTopup(
        org_id=org_id,
        scope_type=scope_type,
        scope_id=target_id,
        units=int(pack["units"]),
        price_amount=pack["price_amount"],  # price freeze
        currency=_TOPUP_CURRENCY,
        status=TOPUP_PENDING,
        requested_by=principal.user_id,
        pack_code=pack["code"],
    )
    session.add(topup)
    await session.flush()

    await write_audit(
        session,
        action="ai_energy.topup_requested",
        resource_type="ai_energy_topup",
        resource_id=topup.id,
        context=_audit_ctx(principal, ctx),
        after={
            "scope_type": scope_type,
            "scope_id": str(target_id),
            "units": topup.units,
            "pack_code": topup.pack_code,
            "price_amount": str(topup.price_amount),
        },
    )
    await session.commit()
    await session.refresh(topup)

    data = _present_topup(topup, locale=locale)
    instructions = dict(_PAYMENT_INSTRUCTIONS)
    instructions["reference_hint"] = f"VINUNI-ENERGY-{str(topup.id)[:8].upper()}"
    data["payment_instructions"] = instructions
    return data


async def confirm_topup(
    session: AsyncSession,
    *,
    principal: Principal,
    topup_id: uuid.UUID,
    payment_reference: str,
    ctx: RequestContext | None = None,
    locale: str = "vi",
) -> dict:
    """Mark a pending top-up paid + credit the target scope wallet (idempotent).

    Finance-gated. Re-confirming an already-paid top-up is a no-op (never
    double-credits). Confirming a cancelled top-up is a conflict.
    """
    await _require_finance(session, principal)
    if not payment_reference or not payment_reference.strip():
        raise ValidationFailedError(
            details={"field": "payment_reference", "reason": "required"}
        )

    stmt = select(AiEnergyTopup).where(AiEnergyTopup.id == topup_id)
    if _use_for_update():
        stmt = stmt.with_for_update()
    topup = (await session.execute(stmt)).scalar_one_or_none()
    if topup is None:
        raise ResourceNotFoundError()

    if topup.status == TOPUP_PAID:
        return _present_topup(topup, locale=locale)  # idempotent — no double credit
    if topup.status == TOPUP_CANCELLED:
        raise ConflictError()

    acct = await _upsert_account(
        session,
        scope_type=topup.scope_type,
        scope_id=topup.scope_id,
        org_id=topup.org_id,
        updated_by=principal.user_id,
        lock=True,
    )
    acct.wallet_units += topup.units
    acct.updated_by = principal.user_id

    topup.status = TOPUP_PAID
    topup.payment_reference = payment_reference.strip()
    topup.paid_by = principal.user_id
    topup.paid_at = _now()
    topup.version += 1
    await session.flush()

    await write_audit(
        session,
        action="ai_energy.topup_paid",
        resource_type="ai_energy_topup",
        resource_id=topup.id,
        context=_audit_ctx(principal, ctx),
        after={
            "scope_type": topup.scope_type,
            "scope_id": str(topup.scope_id),
            "units": topup.units,
            "payment_reference": topup.payment_reference,
            "wallet_units": acct.wallet_units,
        },
    )
    await session.commit()
    await session.refresh(topup)
    return _present_topup(topup, locale=locale)


# --------------------------------------------------------------------------- #
# List / get                                                                    #
# --------------------------------------------------------------------------- #


async def list_org_topups(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> list[dict]:
    """All top-ups for the caller's org (management-gated)."""
    _require_manage(principal)
    org_id = _org_context(principal)
    stmt = select(AiEnergyTopup).where(AiEnergyTopup.org_id == org_id)
    if status is not None:
        stmt = stmt.where(AiEnergyTopup.status == status)
    stmt = stmt.order_by(AiEnergyTopup.created_at.desc()).limit(clamp_limit(limit))
    rows = (await session.execute(stmt)).scalars().all()
    return [_present_topup(t, locale=locale) for t in rows]


async def list_my_topups(
    session: AsyncSession,
    *,
    principal: Principal,
    limit: int | None = None,
    locale: str = "vi",
) -> list[dict]:
    """The caller's own top-ups (requested by them, or targeting their user scope)."""
    if not principal.is_authenticated or principal.user_id is None:
        raise PermissionDeniedError()
    uid = principal.user_id
    stmt = (
        select(AiEnergyTopup)
        .where(
            (AiEnergyTopup.requested_by == uid)
            | (
                (AiEnergyTopup.scope_type == SCOPE_USER)
                & (AiEnergyTopup.scope_id == uid)
            )
        )
        .order_by(AiEnergyTopup.created_at.desc())
        .limit(clamp_limit(limit))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_present_topup(t, locale=locale) for t in rows]


async def get_topup(
    session: AsyncSession,
    *,
    principal: Principal,
    topup_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """A single top-up the caller may see (own, org-admin of it, or superadmin)."""
    if not principal.is_authenticated:
        raise PermissionDeniedError()
    topup = (
        await session.execute(
            select(AiEnergyTopup).where(AiEnergyTopup.id == topup_id)
        )
    ).scalar_one_or_none()
    if topup is None:
        raise ResourceNotFoundError()

    is_owner = topup.requested_by == principal.user_id or (
        topup.scope_type == SCOPE_USER and topup.scope_id == principal.user_id
    )
    is_org_admin = (
        topup.org_id is not None
        and principal.org_id == topup.org_id
        and permission_checker.can(principal, _RESOURCE, "manage")
    )
    if not (principal.is_superadmin or is_owner or is_org_admin):
        raise ResourceNotFoundError()  # don't leak existence cross-tenant
    return _present_topup(topup, locale=locale)
