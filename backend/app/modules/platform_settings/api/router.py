"""Platform appearance settings routes.

Public GET: no auth — the frontend reads font settings server-side on every request.
Admin PATCH: university_admin / superadmin only — select the active font from the
self-hosted catalogue.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.platform_settings.api.schemas import PlatformFontUpdateRequest
from app.modules.platform_settings.application import settings_service
from app.shared.responses import success

public_router = APIRouter(prefix="/platform-settings", tags=["platform-settings"])
admin_router = APIRouter(prefix="/admin/platform-settings", tags=["platform-settings-admin"])


@public_router.get("", summary="Active font and font catalogue (no auth)")
async def get_platform_settings(
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await settings_service.get_settings(session)
    return success(data)


@admin_router.get("", summary="Active platform settings (admin view)")
async def admin_get_platform_settings(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await settings_service.get_settings(session)
    return success(data)


@admin_router.patch("", summary="Select active font from self-hosted catalogue")
async def patch_platform_settings(
    body: PlatformFontUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await settings_service.update_settings(
        session,
        principal=auth.principal,
        font_key=body.font_key,
        actor_id=auth.principal.user_id if auth.principal.is_authenticated else None,
    )
    return success(data)
