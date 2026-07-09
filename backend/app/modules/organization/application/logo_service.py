"""Organization logo media pipeline: upload, remove, and public serve.

RBAC + tenant isolation + audit are enforced here, not in the router
(``docs/SECURITY_PRIVACY.md`` "Public Media And Organization Assets",
``docs/API_CONTRACTS.md`` "Organization Media And Logo Delivery"):

- Write side (``organizations:update``): a partner admin uploads/removes **their
  own** org's logo. A cross-org ``org_id`` is hidden as ``404`` (never 403), so
  the endpoint cannot be used to probe which org ids exist.
- Read side (public): bytes are served only for an **active partner** org via the
  shared :func:`company_directory_service.get_listable_org_by_slug` predicate, so
  suspended/pending/university orgs never leak media.

The internal ``logo_path`` storage key is never returned to any client; public
surfaces receive only the resolved ``logo_url`` (see ``public_presenters``).

# TODO(moderation): university brand-safety moderation of uploaded logos
# (remove/replace/queue) is a separate slice and is intentionally not built here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import documents_storage_facade as storage_backend
from app.modules.organization.api import presenters
from app.modules.organization.application import company_directory_service
from app.modules.organization.application.errors import VersionConflictError
from app.modules.organization.domain.models import Organization
from app.modules.organization.infrastructure import logo_media
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "organizations"


@dataclass(slots=True)
class LogoBytes:
    """Resolved public logo payload for the serve endpoint."""

    content: bytes
    media_type: str


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _load_writable_org(
    session: AsyncSession, *, principal: Principal, org_id: uuid.UUID
) -> Organization:
    """Load ``org_id`` for a write, enforcing tenant isolation then RBAC.

    A missing org OR an org the principal does not belong to surfaces as ``404``
    (indistinguishable, no enumeration). A same-org principal lacking
    ``organizations:update`` surfaces as ``403``.
    """

    org = (
        await session.execute(
            select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if org is None:
        raise ResourceNotFoundError()
    # Tenant isolation first: cross-org access is hidden as 404, never 403.
    if not principal.is_superadmin and principal.org_id != org.id:
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "update", resource_org_id=org.id)
    return org


def _check_version(org: Organization, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != org.version:
        raise VersionConflictError()


async def upload_logo(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    filename: str,
    data: bytes,
    content_type: str | None,
    expected_version: int | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Validate + store an org logo, replacing any previous one. Versioned + audited."""

    org = await _load_writable_org(session, principal=principal, org_id=org_id)
    _check_version(org, expected_version)

    try:
        media = logo_media.validate_logo(
            data, content_type, max_bytes=get_settings().org_logo_max_bytes
        )
    except logo_media.LogoValidationError as exc:
        message = exc.message_vi if locale == "vi" else exc.message_en
        raise ValidationFailedError(message, details={"reason": exc.reason}) from exc

    storage = storage_backend.get_storage()
    asset_id = uuid.uuid4()
    new_key = logo_media.storage_key_for(org.id, asset_id, media.extension)
    storage.save(new_key, data)

    old_key = org.logo_path
    org.logo_path = new_key
    org.version += 1
    await session.flush()

    # Best-effort cleanup of the superseded object (never block the write on it).
    if old_key and old_key != new_key:
        try:
            storage.delete(old_key)
        except Exception:  # noqa: BLE001 - storage cleanup is non-critical
            pass

    await write_audit(
        session,
        action="organization.logo_updated",
        resource_type="organization",
        resource_id=org.id,
        context=_audit_ctx(principal, ctx),
        after={"has_logo": True, "media_type": media.media_type},
    )
    await session.commit()
    return presenters.organization_detail(org, locale=locale)


async def remove_logo(
    session: AsyncSession,
    *,
    principal: Principal,
    org_id: uuid.UUID,
    expected_version: int | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Clear an org's logo (idempotent). Versioned + audited."""

    org = await _load_writable_org(session, principal=principal, org_id=org_id)
    _check_version(org, expected_version)

    old_key = org.logo_path
    if old_key:
        org.logo_path = None
        org.version += 1
        await session.flush()
        try:
            storage_backend.get_storage().delete(old_key)
        except Exception:  # noqa: BLE001 - storage cleanup is non-critical
            pass
        await write_audit(
            session,
            action="organization.logo_removed",
            resource_type="organization",
            resource_id=org.id,
            context=_audit_ctx(principal, ctx),
            after={"has_logo": False},
        )
    await session.commit()
    return presenters.organization_detail(org, locale=locale)


async def serve_logo(session: AsyncSession, *, slug: str) -> LogoBytes:
    """Public logo bytes for an active-partner ``slug``, or ``404``.

    404 covers: not a listable org (university/pending/suspended/deleted/missing)
    and a listable org that simply has no logo set.
    """

    org = await company_directory_service.get_listable_org_by_slug(session, slug=slug)
    if org is None or not org.logo_path:
        raise ResourceNotFoundError()
    try:
        content = storage_backend.get_storage().load(org.logo_path)
    except storage_backend.StorageError as exc:
        # Logo row exists but the object is gone -> treat as missing, never 500.
        raise ResourceNotFoundError() from exc
    return LogoBytes(content=content, media_type=logo_media.media_type_for_key(org.logo_path))
