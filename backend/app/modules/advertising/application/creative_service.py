"""Campaign-creative upload / list / serve / delete (spec §5/§6).

Mirrors the organization-logo media pipeline: RBAC + tenant isolation + audit are
enforced HERE (not in the router). The write side is owner-scoped — a partner (or
the university, for its own curated placements) may attach/remove creatives only
on a placement THEIR org owns; a cross-org or unknown placement id surfaces as
``404`` (never ``403``) so placements are not enumerable. The public serve side
returns bytes only for an APPROVED creative on an ACTIVE, in-window placement, so
a draft/paused/expired or rejected creative never leaks.

The internal ``image_path`` storage key is never returned; public surfaces get
only the resolved :func:`creative_media.public_creative_url`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.advertising.api import presenters
from app.modules.advertising.application.errors import InvalidCreativeFieldError
from app.modules.advertising.domain import creatives as creative_vocab
from app.modules.advertising.domain import lifecycle
from app.modules.advertising.domain.models import CampaignCreative, SponsoredPlacement
from app.modules.advertising.infrastructure import creative_media
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import documents_storage_facade as storage_backend
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "advertising"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


@dataclass(slots=True)
class CreativeBytes:
    """Resolved public creative payload for the serve endpoint."""

    content: bytes
    media_type: str


def _require_creative_write(principal: Principal, *, org_id: uuid.UUID) -> None:
    """Allow ``advertising:edit`` OR ``organizations:update`` on the owning org.

    Either grant authorizes attaching/removing creatives (a partner advertiser
    role carries ``advertising:edit``; an org admin carries ``organizations:
    update``). A member with neither is denied 403.
    """

    if principal.is_superadmin:
        return
    if permission_checker.can(principal, _RESOURCE, "edit", resource_org_id=org_id):
        return
    if permission_checker.can(
        principal, "organizations", "update", resource_org_id=org_id
    ):
        return
    raise PermissionDeniedError(details={"reason": "creative_write_denied"})


async def _load_owned_placement(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    lock: bool = False,
) -> SponsoredPlacement:
    """Load a non-deleted placement the ``principal``'s org owns; else ``404``."""

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


async def _load_owned_creative(
    session: AsyncSession,
    *,
    principal: Principal,
    creative_id: uuid.UUID,
    lock: bool = False,
) -> tuple[CampaignCreative, SponsoredPlacement]:
    stmt = select(CampaignCreative).where(
        CampaignCreative.id == creative_id,
        CampaignCreative.deleted_at.is_(None),
    )
    if lock and _use_for_update():
        stmt = stmt.with_for_update()
    creative = (await session.execute(stmt)).scalar_one_or_none()
    if creative is None:
        raise ResourceNotFoundError()
    placement = await _load_owned_placement(
        session, principal=principal, placement_id=creative.placement_id
    )
    return creative, placement


async def load_for_placement(
    session: AsyncSession, placement_id: uuid.UUID
) -> list[CampaignCreative]:
    """All non-deleted creatives for a placement (for placement projections)."""

    return list(
        (
            await session.execute(
                select(CampaignCreative)
                .where(
                    CampaignCreative.placement_id == placement_id,
                    CampaignCreative.deleted_at.is_(None),
                )
                .order_by(CampaignCreative.created_at.desc())
            )
        ).scalars().all()
    )


def _parse_focal(value: object, *, field: str) -> float:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise InvalidCreativeFieldError(field=field) from exc
    if not (0.0 <= f <= 1.0):
        raise InvalidCreativeFieldError(field=field)
    return f


# --------------------------------------------------------------------------- #
# Upload                                                                       #
# --------------------------------------------------------------------------- #


async def upload_creative(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    slot: str,
    data: bytes,
    content_type: str | None,
    alt_vi: str | None = None,
    alt_en: str | None = None,
    focal_x: object = 0.5,
    focal_y: object = 0.5,
    click_target: str | None = None,
    analytics_source_surface: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Validate + store a creative for a slot on the caller's placement.

    A newly uploaded creative is always ``pending`` review — replacing/adding a
    creative re-enters the moderation queue (the university must re-approve).
    """

    placement = await _load_owned_placement(
        session, principal=principal, placement_id=placement_id, lock=True
    )
    _require_creative_write(principal, org_id=placement.org_id)

    if not creative_vocab.is_valid_slot(slot):
        raise InvalidCreativeFieldError(field="slot")
    fx = _parse_focal(focal_x, field="focal_x")
    fy = _parse_focal(focal_y, field="focal_y")

    try:
        media = creative_media.validate_creative(
            data, content_type, max_bytes=get_settings().campaign_creative_max_bytes
        )
    except creative_media.CreativeValidationError as exc:
        message = exc.message_vi if locale == "vi" else exc.message_en
        raise ValidationFailedError(message, details={"reason": exc.reason}) from exc

    assert principal.user_id is not None
    asset_id = uuid.uuid4()
    key = creative_media.storage_key_for(placement.id, asset_id, media.extension)
    storage_backend.get_storage().save(key, data)

    creative = CampaignCreative(
        id=asset_id,
        placement_id=placement.id,
        slot=slot,
        image_path=key,
        media_type=media.media_type,
        file_size=len(data),
        alt_vi=alt_vi,
        alt_en=alt_en,
        focal_x=fx,
        focal_y=fy,
        click_target=click_target,
        analytics_source_surface=analytics_source_surface,
        moderation_status=creative_vocab.CREATIVE_PENDING,
        created_by=principal.user_id,
    )
    session.add(creative)
    await session.flush()

    await write_audit(
        session,
        action="advertising.creative_uploaded",
        resource_type="advertising_creative",
        resource_id=creative.id,
        context=_audit_ctx(principal, ctx),
        after={
            "placement_id": str(placement.id),
            "slot": slot,
            "media_type": media.media_type,
            "org_id": str(placement.org_id),
        },
    )
    await session.commit()
    await session.refresh(creative)
    return presenters.creative(creative, locale=locale)


# --------------------------------------------------------------------------- #
# List (partner / owner preview)                                              #
# --------------------------------------------------------------------------- #


async def list_creatives(
    session: AsyncSession,
    *,
    principal: Principal,
    placement_id: uuid.UUID,
    locale: str = "vi",
) -> list[dict]:
    """Creatives on the caller's placement (owner-scoped; cross-org -> 404)."""

    placement = await _load_owned_placement(
        session, principal=principal, placement_id=placement_id
    )
    permission_checker.require(
        principal, _RESOURCE, "view", resource_org_id=placement.org_id
    )
    rows = (
        await session.execute(
            select(CampaignCreative)
            .where(
                CampaignCreative.placement_id == placement.id,
                CampaignCreative.deleted_at.is_(None),
            )
            .order_by(CampaignCreative.created_at.desc())
        )
    ).scalars().all()
    return [presenters.creative(c, locale=locale) for c in rows]


# --------------------------------------------------------------------------- #
# Delete                                                                       #
# --------------------------------------------------------------------------- #


async def delete_creative(
    session: AsyncSession,
    *,
    principal: Principal,
    creative_id: uuid.UUID,
    ctx: RequestContext,
) -> None:
    creative, placement = await _load_owned_creative(
        session, principal=principal, creative_id=creative_id, lock=True
    )
    _require_creative_write(principal, org_id=placement.org_id)

    creative.deleted_at = _now()
    creative.version += 1
    await session.flush()
    old_key = creative.image_path
    await write_audit(
        session,
        action="advertising.creative_deleted",
        resource_type="advertising_creative",
        resource_id=creative.id,
        context=_audit_ctx(principal, ctx),
        before={"slot": creative.slot, "org_id": str(placement.org_id)},
    )
    await session.commit()
    # Best-effort object cleanup (never block the soft-delete on storage).
    try:
        storage_backend.get_storage().delete(old_key)
    except Exception:  # noqa: BLE001 - storage cleanup is non-critical
        pass


# --------------------------------------------------------------------------- #
# Public serve                                                                 #
# --------------------------------------------------------------------------- #


def _creative_window_open(creative: CampaignCreative, now: datetime) -> bool:
    if creative.start_at is not None and now < _aware(creative.start_at):
        return False
    return not (creative.end_at is not None and now >= _aware(creative.end_at))


def _placement_is_live(placement: SponsoredPlacement, now: datetime) -> bool:
    return (
        placement.deleted_at is None
        and placement.status == lifecycle.ACTIVE
        and _aware(placement.start_at) <= now < _aware(placement.end_at)
    )


async def serve_creative(
    session: AsyncSession, *, creative_id: uuid.UUID, now: datetime | None = None
) -> CreativeBytes:
    """Public creative bytes — only an APPROVED creative on a LIVE placement.

    404 covers: missing/soft-deleted creative, not-approved creative, a creative
    whose own window is closed, and a placement that is not active/in-window (so
    a paused/expired/draft campaign never serves a banner).
    """

    now = now or _now()
    creative = (
        await session.execute(
            select(CampaignCreative).where(
                CampaignCreative.id == creative_id,
                CampaignCreative.deleted_at.is_(None),
                CampaignCreative.moderation_status
                == creative_vocab.CREATIVE_APPROVED,
            )
        )
    ).scalar_one_or_none()
    if creative is None or not _creative_window_open(creative, now):
        raise ResourceNotFoundError()

    placement = (
        await session.execute(
            select(SponsoredPlacement).where(
                SponsoredPlacement.id == creative.placement_id
            )
        )
    ).scalar_one_or_none()
    if placement is None or not _placement_is_live(placement, now):
        raise ResourceNotFoundError()

    try:
        content = storage_backend.get_storage().load(creative.image_path)
    except storage_backend.StorageError as exc:
        raise ResourceNotFoundError() from exc
    return CreativeBytes(
        content=content,
        media_type=creative_media.media_type_for_key(creative.image_path),
    )
