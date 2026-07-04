"""Student-profile HTTP routes.

Routers are HTTP-only: validate, delegate to services (which enforce RBAC +
ownership + audit + optimistic locking), and shape the response envelope.

Chosen paths (documented as an addition to ``docs/API_CONTRACTS.md``):

- ``GET    /api/v1/students/me/profile``              own full profile (+ completion %)
- ``PATCH  /api/v1/students/me/profile``              update core profile + privacy
- ``GET    /api/v1/students/me/profile/{kind}``       list a child collection
- ``POST   /api/v1/students/me/profile/{kind}``       add a child item
- ``PATCH  /api/v1/students/me/profile/{kind}/{id}``  update a child item
- ``DELETE /api/v1/students/me/profile/{kind}/{id}``  delete (soft) a child item
- ``GET    /api/v1/students/{profile_id}/profile``    privacy-gated read of another
                                                       student's profile

``{kind}`` is one of ``education`` | ``experience`` | ``skills`` | ``links`` (the
plural URL segment maps to the singular service ``kind``). The ``me`` literal is
declared before the dynamic ``{profile_id}`` route so it is never captured.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.student_profiles.api.schemas import (
    EducationRequest,
    ExperienceRequest,
    LinkRequest,
    SkillRequest,
    UpdateProfileRequest,
)
from app.modules.student_profiles.application import (
    avatar_service,
    profile_service,
    section_service,
    talent_pool_service,
)
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.responses import success

router = APIRouter(prefix="/students", tags=["student_profiles"])

# Map the plural URL segment to the singular service ``kind``.
_KIND_BY_SEGMENT = {
    "education": "education",
    "experience": "experience",
    "skills": "skill",
    "links": "link",
}

_SCHEMA_BY_KIND: dict[str, type[BaseModel]] = {
    "education": EducationRequest,
    "experience": ExperienceRequest,
    "skill": SkillRequest,
    "link": LinkRequest,
}


def _resolve_kind(segment: str) -> str:
    kind = _KIND_BY_SEGMENT.get(segment)
    if kind is None:
        raise ResourceNotFoundError()
    return kind


def _parse(schema: type[BaseModel], body: dict) -> dict:
    """Validate a child-item body against ``schema`` and emit the error envelope.

    The schema is selected at runtime from the path segment, so validation runs
    inside the handler; a raw pydantic error is converted to the standard
    ``VALIDATION_FAILED`` envelope (field locations only — never raw values).
    """

    try:
        model = schema(**body)
    except ValidationError as exc:
        fields = [
            {"loc": ".".join(str(p) for p in err.get("loc", [])), "type": err.get("type")}
            for err in exc.errors()
        ]
        raise ValidationFailedError(details={"fields": fields}) from exc
    return model.model_dump(exclude_unset=True)


# --------------------------------------------------------------------------- #
# Talent pool (partner / university staff passive search)                      #
# Must be registered BEFORE /{profile_id}/... routes to avoid path capture.   #
# --------------------------------------------------------------------------- #


@router.get("/talent", summary="Search open-to-work students (partner/staff only)")
async def search_talent_pool(
    open_to_work_type: str | None = Query(None),
    degree_level: str | None = Query(None),
    keyword: str | None = Query(None, max_length=100),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=20),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await talent_pool_service.search_talent_pool(
        session,
        principal=auth.principal,
        open_to_work_type=open_to_work_type,
        degree_level=degree_level,
        keyword=keyword,
        cursor=cursor,
        limit=limit,
    )
    return success(data)


# --------------------------------------------------------------------------- #
# Own profile                                                                  #
# --------------------------------------------------------------------------- #


@router.get("/me/profile", summary="Get my student profile (with completion %)")
async def get_my_profile(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await profile_service.get_my_profile(session, principal=auth.principal)
    return success(data)


@router.get("/me/ai-summary-draft", summary="AI-drafted profile summary paragraph")
async def ai_summary_draft(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await profile_service.get_ai_summary_draft(session, principal=auth.principal)
    return success(data)


@router.get("/me/ai-skill-suggestions", summary="AI-suggested skills based on my profile")
async def ai_skill_suggestions(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await profile_service.get_ai_skill_suggestions(session, principal=auth.principal)
    return success(data)


@router.get("/me/ai-career-snapshot", summary="AI-generated personalized job search snapshot")
async def ai_career_snapshot(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await profile_service.get_ai_career_snapshot(session, principal=auth.principal)
    return success(data)


@router.patch("/me/profile", summary="Update my core profile + privacy/visibility")
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
    result = await avatar_service.remove_avatar(
        session, principal=auth.principal, ctx=auth.ctx
    )
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
# Child collections (education / experience / skills / links)                  #
# --------------------------------------------------------------------------- #


@router.get("/me/profile/{segment}", summary="List a profile child collection")
async def list_items(
    segment: str,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    kind = _resolve_kind(segment)
    data = await section_service.list_items(session, kind=kind, principal=auth.principal)
    return success(data)


@router.post(
    "/me/profile/{segment}",
    status_code=status.HTTP_201_CREATED,
    summary="Add a profile child item",
)
async def create_item(
    segment: str,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    kind = _resolve_kind(segment)
    payload = _parse(_SCHEMA_BY_KIND[kind], body)
    data = await section_service.create_item(
        session, kind=kind, principal=auth.principal, payload=payload, ctx=auth.ctx
    )
    return success(data)


@router.patch("/me/profile/{segment}/{item_id}", summary="Update a profile child item")
async def update_item(
    segment: str,
    item_id: uuid.UUID,
    body: dict,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    kind = _resolve_kind(segment)
    payload = _parse(_SCHEMA_BY_KIND[kind], body)
    data = await section_service.update_item(
        session,
        kind=kind,
        principal=auth.principal,
        child_id=item_id,
        payload=payload,
        ctx=auth.ctx,
    )
    return success(data)


@router.delete("/me/profile/{segment}/{item_id}", summary="Delete a profile child item")
async def delete_item(
    segment: str,
    item_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    kind = _resolve_kind(segment)
    data = await section_service.delete_item(
        session, kind=kind, principal=auth.principal, child_id=item_id, ctx=auth.ctx
    )
    return success(data)


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
