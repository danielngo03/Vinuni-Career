"""Admin AI-settings HTTP routes (ADR-0011 §6 + §7 multi-provider).

Routers are HTTP-only: validate, delegate to the service (which enforces RBAC +
audit + allowlist + republish), and shape the response envelope. University-org
admins / superadmin only — students and partners get 403.

Provider/alias endpoints (/providers, /model-aliases) extend the admin surface
with multi-provider configuration. API keys are write-only and encrypted at rest;
responses expose only ``has_api_key``. Concrete ``model_id`` values are also kept
off GET responses.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.ai_settings.api.routing_schemas import (
    CreateRoutingGraphRequest,
    UpdateRoutingGraphRequest,
)
from app.modules.ai_settings.api.schemas import (
    AiModelAliasCreateRequest,
    AiModelAliasUpdateRequest,
    AiProviderCreateRequest,
    AiProviderUpdateRequest,
    AiSettingsDisableRequest,
    AiSettingsUpdateRequest,
)
from app.modules.ai_settings.application import (
    resolver,
    routing_activation_service,
    routing_read_service,
    routing_service,
    settings_service,
)
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.shared.exceptions import ValidationFailedError
from app.shared.responses import success

admin_router = APIRouter(prefix="/admin/ai-settings", tags=["ai-settings-admin"])


async def _commit_and_republish(session: AsyncSession) -> None:
    """Commit admin registry edits and publish the runtime snapshot."""

    await session.commit()
    await resolver.resolve_and_publish(session)
    await session.commit()


@admin_router.get("", summary="Effective AI settings (masked, derived status only)")
async def get_ai_settings(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await settings_service.get_effective_settings(
        session, principal=auth.principal
    )
    return success(data)


@admin_router.patch("", summary="Update aliases / flags / budget / toggles")
async def patch_ai_settings(
    body: AiSettingsUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    data = await settings_service.update_settings(
        session,
        principal=auth.principal,
        payload=body.model_dump(exclude_unset=True),
        ctx=auth.ctx,
    )
    return success(data)


@admin_router.post("/disable-ai", summary="Kill switch: force real calls off + offline")
async def disable_ai(
    body: AiSettingsDisableRequest | None = None,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    reason = body.reason if body else None
    data = await settings_service.disable_ai(
        session, principal=auth.principal, ctx=auth.ctx, reason=reason
    )
    return success(data)


# ---------------------------------------------------------------------------
# Multi-provider admin: providers and model aliases (ADR-0011 §6)
# ---------------------------------------------------------------------------

@admin_router.get("/providers", summary="List all AI provider endpoints")
async def list_providers(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.ai.gateway import provider_registry
    await settings_service._require_ai_settings_admin(session, auth.principal, "read")
    await provider_registry.ensure_defaults(session)
    reveal = settings_service.can_view_provider_identity(auth.principal)
    if reveal:
        # Auditing the reveal mirrors the routing-canvas identity view.
        from app.shared.audit import AuditContext, write_audit
        await write_audit(
            session,
            action="ai_settings.provider_identity_viewed",
            resource_type="ai_provider_config",
            context=AuditContext(
                actor_id=auth.principal.user_id, actor_org_id=auth.principal.org_id,
                ip=auth.ctx.ip, user_agent=auth.ctx.user_agent,
            ),
        )
    await session.commit()
    data = await provider_registry.list_providers(session, reveal_identity=reveal)
    return success(data)


@admin_router.post("/providers", summary="Add a custom AI provider endpoint")
async def create_provider(
    body: AiProviderCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.ai.gateway import provider_registry
    from app.shared.audit import AuditContext, write_audit
    await settings_service._require_ai_settings_admin(session, auth.principal, "manage")
    try:
        data = await provider_registry.create_provider(
            session, payload=body.model_dump(), created_by=auth.principal.user_id
        )
    except ValueError as exc:
        raise ValidationFailedError(details={"reason": str(exc)}) from exc
    await write_audit(
        session,
        action="ai_provider.created",
        resource_type="ai_provider_config",
        resource_id=uuid.UUID(data["id"]),
        context=AuditContext(actor_id=auth.principal.user_id, actor_org_id=auth.principal.org_id,
                             ip=auth.ctx.ip, user_agent=auth.ctx.user_agent),
        after={"name": data["name"], "provider_type": data["provider_type"]},
    )
    await _commit_and_republish(session)
    return success(data)


@admin_router.patch("/providers/{provider_id}", summary="Update a provider config")
async def update_provider(
    provider_id: uuid.UUID,
    body: AiProviderUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.ai.gateway import provider_registry
    await settings_service._require_ai_settings_admin(session, auth.principal, "manage")
    try:
        data = await provider_registry.update_provider(
            session,
            provider_id,
            payload=body.model_dump(exclude_unset=True),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="provider_not_found") from exc
    await _commit_and_republish(session)
    return success(data)


@admin_router.post("/keys/rotate", summary="Re-encrypt all provider keys with the newest key")
async def rotate_provider_keys(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.ai.gateway import provider_registry
    from app.shared.audit import AuditContext, write_audit
    await settings_service._require_ai_settings_admin(session, auth.principal, "manage")
    result = await provider_registry.reencrypt_all_provider_keys(session)
    await write_audit(
        session,
        action="ai_provider.keys_rotated",
        resource_type="ai_provider_config",
        context=AuditContext(
            actor_id=auth.principal.user_id, actor_org_id=auth.principal.org_id,
            ip=auth.ctx.ip, user_agent=auth.ctx.user_agent,
        ),
        after={"rotated": result["rotated"], "skipped": result["skipped"]},
    )
    await _commit_and_republish(session)
    return success(result)


@admin_router.get("/model-aliases", summary="List all model aliases")
async def list_model_aliases(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.ai.gateway import provider_registry
    await settings_service._require_ai_settings_admin(session, auth.principal, "read")
    await provider_registry.ensure_defaults(session)
    reveal = settings_service.can_view_provider_identity(auth.principal)
    if reveal:
        from app.shared.audit import AuditContext, write_audit
        await write_audit(
            session,
            action="ai_settings.provider_identity_viewed",
            resource_type="ai_model_alias",
            context=AuditContext(
                actor_id=auth.principal.user_id, actor_org_id=auth.principal.org_id,
                ip=auth.ctx.ip, user_agent=auth.ctx.user_agent,
            ),
        )
    await session.commit()
    data = await provider_registry.list_aliases(session, reveal_identity=reveal)
    return success(data)


@admin_router.post("/model-aliases", summary="Create a custom model alias")
async def create_model_alias(
    body: AiModelAliasCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.ai.gateway import provider_registry
    from app.shared.audit import AuditContext, write_audit
    await settings_service._require_ai_settings_admin(session, auth.principal, "manage")
    try:
        data = await provider_registry.create_alias(
            session, payload=body.model_dump(), created_by=auth.principal.user_id
        )
    except ValueError as exc:
        raise ValidationFailedError(details={"reason": str(exc)}) from exc
    await write_audit(
        session,
        action="ai_model_alias.created",
        resource_type="ai_model_alias",
        resource_id=uuid.UUID(data["id"]),
        context=AuditContext(actor_id=auth.principal.user_id, actor_org_id=auth.principal.org_id,
                             ip=auth.ctx.ip, user_agent=auth.ctx.user_agent),
        after={"alias_name": data["alias_name"], "provider_name": data["provider_name"]},
    )
    await _commit_and_republish(session)
    return success(data)


@admin_router.patch("/model-aliases/{alias_id}", summary="Update a model alias")
async def update_model_alias(
    alias_id: uuid.UUID,
    body: AiModelAliasUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    from app.ai.gateway import provider_registry
    await settings_service._require_ai_settings_admin(session, auth.principal, "manage")
    try:
        data = await provider_registry.update_alias(
            session,
            alias_id,
            payload=body.model_dump(exclude_unset=True),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="alias_not_found") from exc
    except ValueError as exc:
        raise ValidationFailedError(details={"reason": str(exc)}) from exc
    await _commit_and_republish(session)
    return success(data)


# ---------------------------------------------------------------------------
# AI Provider/Model Routing Canvas (draft CRUD + activation + live view)
# ---------------------------------------------------------------------------

def _routing_graph_presenter(row) -> dict:
    return {
        "id": str(row.id),
        "task_family": row.task_family,
        "graph": row.graph,
        "status": row.status,
        "version": row.version,
    }


@admin_router.post("/routing-graphs", summary="Create a draft AI routing graph")
async def create_routing_graph(
    body: CreateRoutingGraphRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = await routing_service.create_draft_graph(
        session,
        principal=auth.principal,
        task_family=body.task_family,
        graph=body.graph,
        ctx=auth.ctx,
    )
    return success(_routing_graph_presenter(row))


@admin_router.patch("/routing-graphs/{graph_id}", summary="Update a draft AI routing graph")
async def update_routing_graph(
    graph_id: uuid.UUID,
    body: UpdateRoutingGraphRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = await routing_service.update_draft_graph(
        session, principal=auth.principal, graph_id=graph_id, graph=body.graph, ctx=auth.ctx,
    )
    return success(_routing_graph_presenter(row))


@admin_router.get("/routing-graphs/{graph_id}", summary="Get an AI routing graph")
async def get_routing_graph(
    graph_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = await routing_service.get_graph(session, principal=auth.principal, graph_id=graph_id)
    return success(_routing_graph_presenter(row))


@admin_router.get("/routing-graphs", summary="List AI routing graphs")
async def list_routing_graphs(
    task_family: str | None = Query(default=None),
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = await routing_service.list_graphs(
        session, principal=auth.principal, task_family=task_family
    )
    return success([_routing_graph_presenter(r) for r in rows])


@admin_router.post(
    "/routing-graphs/{graph_id}/activate",
    summary="Activate an AI routing graph (compiles into ai_model_aliases)",
)
async def activate_routing_graph(
    graph_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    row = await routing_activation_service.activate_routing_graph(
        session, principal=auth.principal, graph_id=graph_id, ctx=auth.ctx,
    )
    return success(_routing_graph_presenter(row))


@admin_router.get(
    "/routing-canvas/{task_family}",
    summary="Live provider/circuit-breaker view for the routing canvas",
)
async def get_routing_canvas(
    task_family: str,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    view = await routing_read_service.get_routing_canvas_view(
        session, principal=auth.principal, task_family=task_family, ctx=auth.ctx,
    )
    return success(view)
