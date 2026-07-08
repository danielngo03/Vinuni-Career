"""``ai_settings`` admin service: get / update / kill switch (ADR-0011 §5).

RBAC + audit + alias-allowlist validation live HERE (service layer), not in the
router. RBAC mirrors ``advertising._require_advertising_moderator``: superadmin OR a
member of a ``university``-type org holding the relevant ``ai_settings`` permission
— so a partner Admin's ``*:*`` cannot reach this surface. Every write audits a
before/after metadata diff (provider keys are write-only and never audited) and
republishes the runtime snapshot one-way into the gateway.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.provider_models import AiModelAlias
from app.modules.ai_settings.api import presenters
from app.modules.ai_settings.application import resolver
from app.modules.ai_settings.domain import aliases
from app.modules.ai_settings.domain.models import (
    ROLLOUT_OFFLINE,
    ROLLOUT_STATES,
    AiSettings,
)
from app.modules.ai_settings.infrastructure import repository
from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import PermissionDeniedError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "ai_settings"

# Max per-day USD budget an admin may set (defensive ceiling on the field).
_MAX_DAILY_BUDGET_USD = Decimal("10000.00")

_ALIAS_FIELDS = tuple(aliases.ALIAS_FIELDS.keys())
_FLAG_FIELDS = ("cv_llm_structuring_enabled", "job_fit_ai_explanation_enabled")


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _require_ai_settings_admin(
    session: AsyncSession, principal: Principal, action: str
) -> None:
    """Superadmin OR a university-org member holding ``ai_settings:{action}``."""

    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, action)
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


async def _allowed_aliases_for_field(session: AsyncSession, field: str) -> tuple[str, ...]:
    """Return selectable alias names for a task-family field.

    Static aliases keep local/dev behavior stable. DB aliases make the admin
    provider registry truly no-code: once a university admin creates an active
    alias with a compatible task family, it can be selected without a deploy.
    """

    family = aliases.ALIAS_FIELDS.get(field)
    if family is None:
        return ()

    built_in = set(aliases.allowed_aliases(field))
    rows = (
        await session.execute(
            select(AiModelAlias).where(AiModelAlias.is_active.is_(True))
        )
    ).scalars().all()
    dynamic: set[str] = set()
    for row in rows:
        families = {
            item.strip()
            for item in (row.task_families or "").split(",")
            if item.strip()
        }
        if not families or family in families:
            dynamic.add(row.alias_name)
    return tuple(sorted(built_in | dynamic))


async def _validate_alias(session: AsyncSession, field: str, value: str) -> None:
    allowed = await _allowed_aliases_for_field(session, field)
    if value not in allowed:
        # Rejects unknown vendor/model-path injection. ``allowed`` is alias NAMES
        # only — no provider/model id leaks in the error.
        raise ValidationFailedError(
            details={
                "field": field,
                "reason": "alias_not_allowed",
                "allowed": list(allowed),
            }
        )


def _validate_budget(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationFailedError(
            details={"field": "daily_budget_usd", "reason": "invalid_number"}
        ) from exc
    if amount < 0 or amount > _MAX_DAILY_BUDGET_USD:
        raise ValidationFailedError(
            details={"field": "daily_budget_usd", "reason": "out_of_range"}
        )
    return amount.quantize(Decimal("0.01"))


def _validate_per_org_budget(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationFailedError(
            details={"field": "per_org_daily_budget_usd", "reason": "invalid_number"}
        ) from exc
    if amount < 0 or amount > _MAX_DAILY_BUDGET_USD:
        raise ValidationFailedError(
            details={"field": "per_org_daily_budget_usd", "reason": "out_of_range"}
        )
    return amount.quantize(Decimal("0.01"))


async def _apply_updates(
    session: AsyncSession,
    row: AiSettings,
    payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate + apply partial updates; return a metadata-only before/after diff."""

    diff: dict[str, dict[str, Any]] = {"before": {}, "after": {}}

    def _set(field: str, new: Any) -> None:
        old = getattr(row, field)
        if old == new:
            return
        diff["before"][field] = _jsonable(old)
        diff["after"][field] = _jsonable(new)
        setattr(row, field, new)

    for field in _ALIAS_FIELDS:
        if field in payload and payload[field] is not None:
            await _validate_alias(session, field, payload[field])
            _set(field, payload[field])

    for field in _FLAG_FIELDS:
        if field in payload and payload[field] is not None:
            _set(field, bool(payload[field]))

    if payload.get("real_calls_enabled") is not None:
        _set("real_calls_enabled", bool(payload["real_calls_enabled"]))

    if payload.get("rollout_state") is not None:
        state = payload["rollout_state"]
        if state not in ROLLOUT_STATES:
            raise ValidationFailedError(
                details={"field": "rollout_state", "reason": "invalid_state"}
            )
        _set("rollout_state", state)

    if payload.get("daily_budget_usd") is not None:
        _set("daily_budget_usd", _validate_budget(payload["daily_budget_usd"]))

    # per_org_daily_budget_usd: explicit null (clear_per_org_budget=True) removes the
    # cap; a numeric value sets it; omitting the field leaves it unchanged.
    if payload.get("clear_per_org_budget"):
        _set("per_org_daily_budget_usd", None)
    elif payload.get("per_org_daily_budget_usd") is not None:
        _set(
            "per_org_daily_budget_usd",
            _validate_per_org_budget(payload["per_org_daily_budget_usd"]),
        )

    if "notes" in payload:
        _set("notes", payload["notes"])

    return diff


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return value


async def _settings_view(session: AsyncSession, row: AiSettings) -> dict:
    view = presenters.settings_view(row)
    view["allowed_aliases"] = {
        family: list(await _allowed_aliases_for_field(session, field))
        for field, family in aliases.ALIAS_FIELDS.items()
    }
    return view


async def get_effective_settings(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Masked effective settings (read). Lazily seeds the singleton if absent."""

    await _require_ai_settings_admin(session, principal, "read")
    row = await repository.get_or_create_platform(session)
    await session.commit()
    return await _settings_view(session, row)


async def update_settings(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict[str, Any],
    ctx: RequestContext,
) -> dict:
    """Partial update of aliases/flags/budget/toggles. Audited + republished."""

    await _require_ai_settings_admin(session, principal, "manage")
    row = await repository.get_or_create_platform(session)
    diff = await _apply_updates(session, row, payload)

    if diff["after"]:
        row.updated_by = principal.user_id
        row.version += 1
        await session.flush()
        await write_audit(
            session,
            action="ai_settings.updated",
            resource_type="ai_settings",
            resource_id=row.id,
            context=_audit_ctx(principal, ctx),
            before=diff["before"],
            after=diff["after"],
        )
    await session.commit()
    await session.refresh(row)
    # One-way republish AFTER commit so custom provider/model routes are live.
    await resolver.resolve_and_publish(session)
    return await _settings_view(session, row)


async def disable_ai(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    reason: str | None = None,
) -> dict:
    """Kill switch: force real calls off + rollout ``offline``, audited (ADR-0011 §5)."""

    await _require_ai_settings_admin(session, principal, "manage")
    row = await repository.get_or_create_platform(session)

    before = {
        "real_calls_enabled": row.real_calls_enabled,
        "rollout_state": row.rollout_state,
    }
    row.real_calls_enabled = False
    row.rollout_state = ROLLOUT_OFFLINE
    if reason:
        row.notes = reason
    row.updated_by = principal.user_id
    row.version += 1
    await session.flush()
    await write_audit(
        session,
        action="ai_settings.disabled",
        resource_type="ai_settings",
        resource_id=row.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={"real_calls_enabled": False, "rollout_state": ROLLOUT_OFFLINE},
    )
    await session.commit()
    await session.refresh(row)
    await resolver.resolve_and_publish(session)
    return await _settings_view(session, row)
