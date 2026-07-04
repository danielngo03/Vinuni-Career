"""In-app Notification Center HTTP routes (``/api/v1/notifications``).

HTTP-only: validate query/path, delegate to the recipient-scoped feed service
(which enforces RBAC and recipient isolation), and shape the canonical response
envelope (``docs/API_CONTRACTS.md`` Notifications section). No business logic here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth, get_request_context
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.api.schemas import (
    NotificationTemplateCreateRequest,
    NotificationTemplatePreviewRequest,
    NotificationTemplateUpdateRequest,
)
from app.modules.notifications.application import feed_service, template_admin_service
from app.shared.responses import paginated, success

router = APIRouter(prefix="/notifications", tags=["notifications"])
template_admin_router = APIRouter(prefix="/notification-templates", tags=["notifications"])


@router.get("", summary="List the caller's in-app notifications (newest-first)")
async def list_notifications(
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=100),
    unread_only: bool = Query(default=False),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items, next_cursor, page_limit, unread = await feed_service.list_feed(
        session,
        principal=auth.principal,
        cursor=cursor,
        limit=limit,
        unread_only=unread_only,
    )
    body = paginated(items, next_cursor=next_cursor, limit=page_limit)
    body["meta"] = {"unread_count": unread}
    return body


@router.get("/unread-count", summary="Caller's total unread notification count")
async def get_unread_count(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    count = await feed_service.unread_count(session, principal=auth.principal)
    return success({"unread_count": count})


@router.post("/read-all", summary="Mark all of the caller's notifications read")
async def read_all(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await feed_service.mark_all_read(session, principal=auth.principal)
    return success(result)


@router.post("/{notification_id}/read", summary="Mark one notification read")
async def mark_read(
    notification_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await feed_service.mark_read(
        session, principal=auth.principal, notification_id=notification_id
    )
    return success(result)


# --------------------------------------------------------------------------- #
# Admin: notification template governance                                    #
# --------------------------------------------------------------------------- #


@template_admin_router.get("", summary="Admin: list notification templates")
async def list_notification_templates(
    key: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    locale: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    items = await template_admin_service.list_templates_admin(
        session,
        principal=auth.principal,
        key=key,
        channel=channel,
        locale=locale,
        status=status_,
    )
    return success(items, meta={"count": len(items)})


@template_admin_router.post(
    "", status_code=201, summary="Admin: create a notification template draft"
)
async def create_notification_template(
    body: NotificationTemplateCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    ctx: RequestContext = Depends(get_request_context),
) -> dict:
    data = await template_admin_service.create_template(
        session,
        principal=auth.principal,
        payload=body.model_dump(mode="json"),
        ctx=ctx,
    )
    return success(data)


@template_admin_router.patch(
    "/{template_id}", summary="Admin: update a draft notification template"
)
async def update_notification_template(
    template_id: uuid.UUID,
    body: NotificationTemplateUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    ctx: RequestContext = Depends(get_request_context),
) -> dict:
    data = await template_admin_service.update_template(
        session,
        principal=auth.principal,
        template_id=template_id,
        payload=body.model_dump(exclude_unset=True, mode="json"),
        ctx=ctx,
    )
    return success(data)


@template_admin_router.post(
    "/{template_id}/preview", summary="Admin: preview a template render (no send)"
)
async def preview_notification_template(
    template_id: uuid.UUID,
    body: NotificationTemplatePreviewRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await template_admin_service.preview_template(
        session,
        principal=auth.principal,
        template_id=template_id,
        sample_variables=body.sample_variables,
    )
    return success(data)


@template_admin_router.post(
    "/{template_id}/activate", summary="Admin: activate (publish/rollback) a version"
)
async def activate_notification_template(
    template_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    ctx: RequestContext = Depends(get_request_context),
) -> dict:
    data = await template_admin_service.activate_template(
        session, principal=auth.principal, template_id=template_id, ctx=ctx
    )
    return success(data)


@template_admin_router.post(
    "/{template_id}/archive", summary="Admin: archive a notification template version"
)
async def archive_notification_template(
    template_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
    ctx: RequestContext = Depends(get_request_context),
) -> dict:
    data = await template_admin_service.archive_template(
        session, principal=auth.principal, template_id=template_id, ctx=ctx
    )
    return success(data)
