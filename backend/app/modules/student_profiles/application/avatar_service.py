"""Student avatar upload, remove, and serve.

Privacy: avatar bytes are served through the authenticated profile endpoint.
The serve URL is a stable path keyed on ``profile_id``; actual storage key is
never exposed. The ``avatar_path`` column is private — never returned in API
responses (only ``avatar_url`` pointing to the serve endpoint).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import documents_storage_facade as storage_backend
from app.modules.student_profiles.application._shared import load_owned_profile
from app.modules.student_profiles.infrastructure import avatar_media
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import ValidationFailedError
from app.shared.permissions import Principal

_AVATAR_MAX_MB = 3
_AVATAR_MAX_BYTES = _AVATAR_MAX_MB * 1024 * 1024


@dataclass(slots=True)
class AvatarBytes:
    content: bytes
    media_type: str


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _avatar_url(profile_id: uuid.UUID, version: int) -> str:
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/students/{profile_id}/avatar?v={version}"


async def upload_avatar(
    session: AsyncSession,
    *,
    principal: Principal,
    filename: str,
    data: bytes,
    content_type: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Validate + store a student avatar, replacing any previous one."""

    profile = await load_owned_profile(session, principal=principal)

    try:
        media = avatar_media.validate_avatar(
            data, content_type, max_bytes=_AVATAR_MAX_BYTES
        )
    except avatar_media.AvatarValidationError as exc:
        message = exc.message_vi if locale == "vi" else exc.message_en
        raise ValidationFailedError(message, details={"reason": exc.reason}) from exc

    storage = storage_backend.get_storage()
    asset_id = uuid.uuid4()
    assert principal.user_id is not None  # guaranteed by load_owned_profile above
    new_key = avatar_media.storage_key_for(principal.user_id, asset_id, media.extension)
    storage.save(new_key, data)

    old_key = getattr(profile, "avatar_path", None)
    profile.avatar_path = new_key
    profile.version += 1
    await session.flush()

    if old_key and old_key != new_key:
        try:
            storage.delete(old_key)
        except Exception:  # noqa: BLE001
            pass

    await write_audit(
        session,
        action="student_profile.avatar_updated",
        resource_type="student_profile",
        resource_id=profile.id,
        context=_audit_ctx(principal, ctx),
        after={"has_avatar": True, "media_type": media.media_type},
    )
    await session.commit()

    return {"avatar_url": _avatar_url(profile.id, profile.version)}


async def remove_avatar(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
) -> dict:
    """Clear a student's avatar (idempotent). Audited."""

    profile = await load_owned_profile(session, principal=principal)

    old_key = getattr(profile, "avatar_path", None)
    if old_key:
        profile.avatar_path = None
        profile.version += 1
        await session.flush()
        try:
            storage_backend.get_storage().delete(old_key)
        except Exception:  # noqa: BLE001
            pass
        await write_audit(
            session,
            action="student_profile.avatar_removed",
            resource_type="student_profile",
            resource_id=profile.id,
            context=_audit_ctx(principal, ctx),
            after={"has_avatar": False},
        )
    await session.commit()

    return {"avatar_url": None}


async def serve_avatar(session: AsyncSession, *, profile_id: uuid.UUID) -> AvatarBytes:
    """Return raw avatar bytes for a profile, or raise ResourceNotFoundError."""

    from app.modules.student_profiles.domain.models import StudentProfile
    from app.shared.exceptions import ResourceNotFoundError

    profile = (
        await session.execute(
            select(StudentProfile).where(
                StudentProfile.id == profile_id,
                StudentProfile.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    avatar_path = profile.avatar_path if profile is not None else None
    if profile is None or not avatar_path:
        raise ResourceNotFoundError()

    storage = storage_backend.get_storage()
    data = storage.load(avatar_path)
    if not data:
        raise ResourceNotFoundError()

    media_type = avatar_media.media_type_for_key(avatar_path)
    return AvatarBytes(content=data, media_type=media_type)
