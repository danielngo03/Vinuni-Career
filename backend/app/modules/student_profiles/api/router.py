"""Student-profile HTTP routes (identity-only profile).

Routers are HTTP-only: validate, delegate to services (which enforce RBAC +
ownership + audit + optimistic locking), and shape the response envelope.

The profile is identity-only (owner decision 2026-07-06): name/email (from the
account), phone/location, privacy gates, avatar, and ``is_open_to_work``. All
career content lives in the student's CVs, so there are no profile child
collections and no profile-content AI endpoints.

Chosen paths (documented as an addition to ``docs/API_CONTRACTS.md``):

- ``GET    /api/v1/students/me/profile``           own profile
- ``PATCH  /api/v1/students/me/profile``           update identity + privacy
- ``POST   /api/v1/students/me/avatar``            upload/replace avatar
- ``DELETE /api/v1/students/me/avatar``            remove avatar
- ``GET    /api/v1/students/{profile_id}/avatar``  serve an avatar (auth required)
- ``GET    /api/v1/students/talent``               open-to-work talent search (partner/staff)
- ``GET    /api/v1/students/{profile_id}/profile`` privacy-gated read of another profile

The ``me`` / ``talent`` literals are declared before the dynamic ``{profile_id}``
routes so they are never captured.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.student_profiles.api.schemas import UpdateProfileRequest
from app.modules.student_profiles.application import (
    avatar_service,
    profile_service,
    talent_pool_service,
)
from app.shared.responses import success

router = APIRouter(prefix="/students", tags=["student_profiles"])


# --------------------------------------------------------------------------- #
# Talent pool (partner / university staff passive search)                      #
# Must be registered BEFORE /{profile_id}/... routes to avoid path capture.   #
# --------------------------------------------------------------------------- #


@router.get("/talent", summary="Search open-to-work students (partner/staff only)")
async def search_talent_pool(
    keyword: str | None = Query(None, max_length=100),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=20),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await talent_pool_service.search_talent_pool(
        session,
        principal=auth.principal,
        keyword=keyword,
        cursor=cursor,
        limit=limit,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Own profile                                                                  #
# --------------------------------------------------------------------------- #


@router.get("/me/profile", summary="Get my student profile")
async def get_my_profile(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await profile_service.get_my_profile(session, principal=auth.principal)
    return success(data)


@router.patch("/me/profile", summary="Update my identity + privacy/visibility")
async def update_my_profile(
    body: UpdateProfileRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await profile_service.update_my_profile(
        session,
        principal=auth.principal,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Avatar upload / remove / serve                                                #
# --------------------------------------------------------------------------- #


@router.post("/me/avatar", summary="Upload or replace my avatar")
async def upload_avatar(
    file: UploadFile,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await file.read()
    result = await avatar_service.upload_avatar(
        session,
        principal=auth.principal,
        filename=file.filename or "avatar",
        data=data,
        content_type=file.content_type,
        ctx=auth.ctx,
    )
    return success(result)


@router.delete("/me/avatar", summary="Remove my avatar")
async def remove_avatar(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await avatar_service.remove_avatar(session, principal=auth.principal, ctx=auth.ctx)
    return success(result)


@router.get("/{profile_id}/avatar", summary="Serve a student avatar (auth required)")
async def serve_avatar(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    auth: CurrentAuth = Depends(get_current_auth),
) -> Response:
    blob = await avatar_service.serve_avatar(session, profile_id=profile_id)
    return Response(content=blob.content, media_type=blob.media_type)


# --------------------------------------------------------------------------- #
# Partner / community read of another student's profile                        #
# --------------------------------------------------------------------------- #


@router.get(
    "/{profile_id}/profile",
    summary="Read another student's profile (privacy-gated)",
)
async def get_profile_for_viewer(
    profile_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await profile_service.get_profile_for_viewer(
        session, principal=auth.principal, profile_id=profile_id
    )
    return success(data)
