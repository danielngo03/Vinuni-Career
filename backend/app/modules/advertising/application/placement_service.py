"""Partner advertiser surface: placement create / edit / submit / cancel / delete
/ get / list-mine + the package catalog (ADR-0009 §5/§7/§9.4).

RBAC is enforced here (not in routers) via ``PermissionChecker`` plus org-scoped
tenant isolation: a partner only ever sees / mutates its own org's placements, and
a cross-org (or unknown) access returns ``404`` — never ``403`` — so resources are
not enumerable. Target ownership is validated through the ``opportunities`` owner
facade (``sponsorship_facade.load_target``) so this module never imports the
``Job``/``Event`` ORM. Every write records an audit row in the caller's transaction.

Gates (ADR-0009 §5):
- ``submit`` requires ``disclosure_confirmed=true`` → else ``422 disclosure_required``.
- ``submit`` is rejected ``409 active_placement_limit`` if it would exceed
  ``ADVERTISING_MAX_ACTIVE_PER_ORG`` concurrent in-flight placements.
- ``submit`` is rejected ``409 placement_exists`` if another live placement already
  covers the target (the partial-unique ``uq_placement_inflight`` invariant; enforced
  in-service for the SQLite test path).
- ``price_amount`` is frozen onto the placement from the package at ``submit``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.advertising.api import presenters
from app.modules.advertising.application import activation_service, creative_service
from app.modules.advertising.application.errors import (
    ActivePlacementLimitError,
    DisclosureRequiredError,
    IllegalPlacementTransitionError,
    InvalidPlacementFieldError,
    PlacementExistsError,
    PlacementNotEditableError,
    PlacementVersionConflictError,
)
from app.modules.advertising.domain import lifecycle
from app.modules.advertising.domain.models import AdPackage, SponsoredPlacement
from app.modules.auth.application.context import RequestContext
from app.modules.opportunities.application import sponsorship_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.moderation import compute_due_by
from app.shared.pagination import build_cursor_page, clamp_limit, decode_cursor
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "advertising"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


# --------------------------------------------------------------------------- #
# Packages (pricing catalog)                                                  #
# --------------------------------------------------------------------------- #


async def list_packages(
    session: AsyncSession, *, locale: str = "vi", active_only: bool = True
) -> list[dict]:
    """Return the pricing tiers (name + price + duration + what each grants)."""

    stmt = select(AdPackage)
    if active_only:
        stmt = stmt.where(AdPackage.is_active.is_(True))
    stmt = stmt.order_by(AdPackage.duration_days.asc(), AdPackage.price_amount.asc())
    rows = list((await session.execute(stmt)).scalars().all())
    return [presenters.package(p, locale=locale) for p in rows]


async def _load_package(
    session: AsyncSession, package_id: uuid.UUID
) -> AdPackage | None:
    return (
        await session.execute(
            select(AdPackage).where(AdPackage.id == package_id)
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Loading / ownership                                                         #
# --------------------------------------------------------------------------- #


async def _load_owned(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    lock: bool = False,
) -> SponsoredPlacement:
    """Load a non-deleted placement the ``principal`` owns; else ``404``."""

    stmt = select(SponsoredPlacement).where(
        SponsoredPlacement.id == placement_id,
        SponsoredPlacement.deleted_at.is_(None),
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    placement = (await session.execute(stmt)).scalar_one_or_none()
    if placement is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and placement.org_id != principal.org_id:
        raise ResourceNotFoundError()
    return placement


async def _present(
    session: AsyncSession, placement: SponsoredPlacement, *, locale: str
) -> dict:
    pkg = await _load_package(session, placement.package_id)
    ref = await sponsorship_facade.load_target(
        session, target_type=placement.target_type, target_id=placement.target_id
    )
    creatives = await creative_service.load_for_placement(session, placement.id)
    return presenters.placement(
        placement, locale=locale, pkg=pkg,
        target_title=ref.title if ref else None, creatives=creatives,
    )


# --------------------------------------------------------------------------- #
# Create / update                                                             #
# --------------------------------------------------------------------------- #


async def create_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "create", resource_org_id=principal.org_id
    )
    assert principal.user_id is not None

    target_type = payload["target_type"]
    placement_type = payload["placement_type"]
    if target_type not in lifecycle.TARGET_TYPES:
        raise InvalidPlacementFieldError(field="target_type")
    if placement_type not in lifecycle.PLACEMENT_TYPES:
        raise InvalidPlacementFieldError(field="placement_type")

    # Target ownership — cross-org or unknown target is indistinguishable from
    # missing (404), mirroring jobs enumeration-masking.
    ref = await sponsorship_facade.load_target(
        session, target_type=target_type, target_id=payload["target_id"]
    )
    if ref is None or (
        not principal.is_superadmin and ref.org_id != principal.org_id
    ):
        raise ResourceNotFoundError()

    pkg = await _load_package(session, payload["package_id"])
    if pkg is None or not pkg.is_active:
        raise InvalidPlacementFieldError(field="package_id")
    if not lifecycle.package_allows(
        placement_type,
        pkg_grants_sponsored=pkg.grants_sponsored,
        pkg_grants_featured=pkg.grants_featured,
    ):
        raise InvalidPlacementFieldError(field="placement_type")

    start_at = payload["start_at"]
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=UTC)
    end_at = start_at + timedelta(days=pkg.duration_days)

    placement = SponsoredPlacement(
        org_id=principal.org_id,
        created_by=principal.user_id,
        target_type=target_type,
        target_id=payload["target_id"],
        placement_type=placement_type,
        package_id=pkg.id,
        price_amount=None,  # frozen at submit
        currency=pkg.currency,
        start_at=start_at,
        end_at=end_at,
        status=lifecycle.DRAFT,
        disclosure_confirmed=bool(payload.get("disclosure_confirmed", False)),
    )
    session.add(placement)
    await session.flush()

    await write_audit(
        session, action="advertising.placement_created",
        resource_type="advertising_placement", resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"status": placement.status, "target_type": target_type,
               "target_id": str(payload["target_id"]),
               "placement_type": placement_type, "package": pkg.code},
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


_UPDATABLE = {"placement_type", "package_id", "start_at", "disclosure_confirmed"}


async def update_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    placement = await _load_owned(
        session, principal=principal, placement_id=placement_id, lock=True
    )
    permission_checker.require(
        principal, _RESOURCE, "edit", resource_org_id=placement.org_id
    )
    if placement.status not in lifecycle.EDITABLE_STATES:
        raise PlacementNotEditableError()

    expected_version = payload.pop("version", None)
    if expected_version is not None and expected_version != placement.version:
        raise PlacementVersionConflictError()

    new_placement_type = payload.get("placement_type", placement.placement_type)
    if new_placement_type not in lifecycle.PLACEMENT_TYPES:
        raise InvalidPlacementFieldError(field="placement_type")

    pkg: AdPackage | None = None
    if "package_id" in payload:
        pkg = await _load_package(session, payload["package_id"])
        if pkg is None or not pkg.is_active:
            raise InvalidPlacementFieldError(field="package_id")
    else:
        pkg = await _load_package(session, placement.package_id)
    if pkg is not None and not lifecycle.package_allows(
        new_placement_type,
        pkg_grants_sponsored=pkg.grants_sponsored,
        pkg_grants_featured=pkg.grants_featured,
    ):
        raise InvalidPlacementFieldError(field="placement_type")

    changed: dict[str, object] = {}
    if "placement_type" in payload:
        placement.placement_type = payload["placement_type"]
        changed["placement_type"] = True
    if "package_id" in payload and pkg is not None:
        placement.package_id = pkg.id
        placement.currency = pkg.currency
        changed["package_id"] = True
    if "disclosure_confirmed" in payload:
        placement.disclosure_confirmed = bool(payload["disclosure_confirmed"])
        changed["disclosure_confirmed"] = True
    if "start_at" in payload and payload["start_at"] is not None:
        start_at = payload["start_at"]
        if start_at.tzinfo is None:
            start_at = start_at.replace(tzinfo=UTC)
        placement.start_at = start_at
        changed["start_at"] = True
    # Recompute the window when start or package (duration) changed.
    if ("start_at" in changed or "package_id" in changed) and pkg is not None:
        base = placement.start_at
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        placement.end_at = base + timedelta(days=pkg.duration_days)

    if changed:
        placement.version += 1
    await session.flush()
    await write_audit(
        session, action="advertising.placement_updated",
        resource_type="advertising_placement", resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"fields": sorted(changed.keys())},
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


# --------------------------------------------------------------------------- #
# Submit (disclosure + caps gate + price freeze)                              #
# --------------------------------------------------------------------------- #


async def _count_in_flight_for_org(
    session: AsyncSession, *, org_id: uuid.UUID, exclude_id: uuid.UUID
) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(SponsoredPlacement)
            .where(
                SponsoredPlacement.org_id == org_id,
                SponsoredPlacement.deleted_at.is_(None),
                SponsoredPlacement.id != exclude_id,
                SponsoredPlacement.status.in_(list(lifecycle.IN_FLIGHT_STATES)),
            )
        )
    ).scalar_one()


async def _target_has_inflight(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    exclude_id: uuid.UUID,
) -> bool:
    row = (
        await session.execute(
            select(SponsoredPlacement.id).where(
                SponsoredPlacement.target_type == target_type,
                SponsoredPlacement.target_id == target_id,
                SponsoredPlacement.deleted_at.is_(None),
                SponsoredPlacement.id != exclude_id,
                SponsoredPlacement.status.in_(list(lifecycle.IN_FLIGHT_STATES)),
            )
        )
    ).first()
    return row is not None


async def submit_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    ctx: RequestContext,
    version: int | None = None,
    disclosure_confirmed: bool | None = None,
    locale: str = "vi",
) -> dict:
    placement = await _load_owned(
        session, principal=principal, placement_id=placement_id, lock=True
    )
    permission_checker.require(
        principal, _RESOURCE, "submit", resource_org_id=placement.org_id
    )
    if version is not None and version != placement.version:
        raise PlacementVersionConflictError()
    if not lifecycle.can_transition("submit", placement.status):
        raise IllegalPlacementTransitionError(event="submit")

    # The partner may confirm disclosure as part of submit.
    if disclosure_confirmed is not None:
        placement.disclosure_confirmed = bool(disclosure_confirmed)
    if not placement.disclosure_confirmed:
        raise DisclosureRequiredError()

    # Per-org concurrency cap.
    limit = get_settings().advertising_max_active_per_org
    in_flight = await _count_in_flight_for_org(
        session, org_id=placement.org_id, exclude_id=placement.id
    )
    if in_flight >= limit:
        raise ActivePlacementLimitError(limit=limit)

    # One in-flight placement per target.
    if await _target_has_inflight(
        session, target_type=placement.target_type,
        target_id=placement.target_id, exclude_id=placement.id,
    ):
        raise PlacementExistsError()

    pkg = await _load_package(session, placement.package_id)
    if pkg is None or not pkg.is_active:
        raise InvalidPlacementFieldError(field="package_id")

    now = _now()
    # Freeze the price from the package (price freeze).
    placement.price_amount = pkg.price_amount
    placement.currency = pkg.currency
    placement.status = lifecycle.PENDING_APPROVAL
    placement.submitted_at = now
    placement.due_by = compute_due_by(
        now, sla_hours=get_settings().advertising_moderation_sla_hours
    )
    placement.moderation_note = None
    placement.moderation_reason_code = None
    placement.claimed_by = None
    placement.claimed_at = None
    placement.version += 1
    await session.flush()

    await write_audit(
        session, action="advertising.placement_submitted",
        resource_type="advertising_placement", resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"status": placement.status, "price_amount": str(pkg.price_amount)},
    )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


# --------------------------------------------------------------------------- #
# Cancel / delete                                                            #
# --------------------------------------------------------------------------- #


async def cancel_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    ctx: RequestContext,
    version: int | None = None,
    locale: str = "vi",
) -> dict:
    placement = await _load_owned(
        session, principal=principal, placement_id=placement_id, lock=True
    )
    permission_checker.require(
        principal, _RESOURCE, "edit", resource_org_id=placement.org_id
    )
    if version is not None and version != placement.version:
        raise PlacementVersionConflictError()
    if not lifecycle.can_transition("cancel", placement.status):
        raise IllegalPlacementTransitionError(event="cancel")

    was_active = placement.status == lifecycle.ACTIVE
    placement.status = lifecycle.CANCELLED
    placement.cancelled_at = _now()
    placement.version += 1
    await session.flush()
    await write_audit(
        session, action="advertising.placement_cancelled",
        resource_type="advertising_placement", resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        after={"status": placement.status, "by": "partner"},
    )
    # Recompute flags inline if this was live (another active placement may keep
    # the flag ON; else it turns OFF).
    if was_active:
        await activation_service.recompute_target_flags(
            session, target_type=placement.target_type,
            target_id=placement.target_id, actor=principal,
            reason="placement_cancelled",
        )
    await session.commit()
    await session.refresh(placement)
    return await _present(session, placement, locale=locale)


async def delete_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    placement = await _load_owned(
        session, principal=principal, placement_id=placement_id, lock=True
    )
    permission_checker.require(
        principal, _RESOURCE, "edit", resource_org_id=placement.org_id
    )
    if placement.status not in lifecycle.DELETABLE_STATES:
        raise PlacementNotEditableError()
    placement.deleted_at = _now()
    placement.version += 1
    await session.flush()
    await write_audit(
        session, action="advertising.placement_deleted",
        resource_type="advertising_placement", resource_id=placement.id,
        context=_audit_ctx(principal, ctx),
        before={"status": placement.status},
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# Reads                                                                       #
# --------------------------------------------------------------------------- #


async def get_placement(
    session: AsyncSession, *, principal: Principal, placement_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    placement = await _load_owned(
        session, principal=principal, placement_id=placement_id
    )
    permission_checker.require(
        principal, _RESOURCE, "view", resource_org_id=placement.org_id
    )
    return await _present(session, placement, locale=locale)


async def list_my_placements(
    session: AsyncSession,
    *,
    principal: Principal,
    status: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    locale: str = "vi",
) -> tuple[list[dict], str | None, int]:
    """Partner-scoped list of the caller org's placements (any status)."""

    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, _RESOURCE, "view", resource_org_id=principal.org_id
    )
    page_limit = clamp_limit(limit)
    stmt = select(SponsoredPlacement).where(
        SponsoredPlacement.org_id == principal.org_id,
        SponsoredPlacement.deleted_at.is_(None),
    )
    if status is not None:
        stmt = stmt.where(SponsoredPlacement.status == status)

    decoded = decode_cursor(cursor)
    if decoded is not None:
        anchor_created = datetime.fromisoformat(decoded["created_at"])
        anchor_id = uuid.UUID(decoded["id"])
        stmt = stmt.where(
            or_(
                SponsoredPlacement.created_at < anchor_created,
                (SponsoredPlacement.created_at == anchor_created)
                & (SponsoredPlacement.id < anchor_id),
            )
        )
    stmt = stmt.order_by(
        SponsoredPlacement.created_at.desc(), SponsoredPlacement.id.desc()
    ).limit(page_limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    page = build_cursor_page(
        rows,
        limit=page_limit,
        cursor_builder=lambda p: {
            "created_at": p.created_at.isoformat(),
            "id": str(p.id),
        },
    )
    # Present each row through the shared `_present` (package + target title +
    # creatives), matching the university `moderation_service.list_all` shape so
    # the partner table renders the real target title instead of the
    # "target unavailable" fallback. Page-limited, so the per-row resolution is
    # bounded.
    items = [await _present(session, p, locale=locale) for p in page.items]
    return items, page.next_cursor, page.limit
