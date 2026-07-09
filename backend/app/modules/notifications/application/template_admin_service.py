"""Admin CRUD + governance for notification templates (``docs/NOTIFICATIONS_
COMMUNICATIONS_SPEC.md`` §4, ``docs/API_CONTRACTS.md`` Notifications section).

This is the back-office surface behind ``ensure_default_templates``
(``template_seed.py``) — university/partner admins can author their own
versions without a deploy. RBAC + org ownership + audit live here, not only in
the router (``.claude/rules/backend.md``).

Governance model (mirrors the ``status``/``version`` fields already on
``NotificationTemplate``, ``docs/DATA_MODEL.md`` §34):

- ``create`` always inserts a new ``draft`` row. If a template already exists
  for the same ``(owner_scope, owner_org_id, key, channel, locale)`` identity,
  the new row gets ``version = max(existing) + 1`` — i.e. "edits create a
  draft version" (spec §4) is implemented by posting a new version rather than
  mutating an already-activated row in place.
- ``update`` only mutates a ``draft`` row. Active/archived rows are immutable;
  callers must ``create`` a new version instead (``ConflictError``).
- ``activate`` validates variables, flips the row to ``active``, and archives
  any other row sharing the same identity that is currently ``active`` — so
  exactly one version is ever live per (key, channel, locale). Activating an
  older ``archived`` version is how a rollback is performed.
- ``archive`` retires a draft/active row without activating a replacement.
- ``preview`` renders sample/caller-supplied variables without dispatching
  anything, for any status (draft/active/archived), so admins can proofread a
  version before or after publishing.

Ownership: a template's ``owner_org_id`` scopes it to one organization (or
``None`` for a platform-wide default owned by a superadmin). A non-superadmin
principal may only manage templates whose ``owner_org_id`` equals their own
``principal.org_id``; a cross-org template_id resolves to ``ResourceNotFound``
(404), never ``PermissionDenied``, so its existence isn't leaked across orgs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application.template_renderer import render, validate_template
from app.modules.notifications.domain.models import NotificationTemplate
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    ConflictError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "notification_templates"
_CHANNELS = frozenset({"email", "in_app", "push"})
_LOCALES = frozenset({"vi", "en"})
_STATUSES = frozenset({"draft", "active", "archived"})


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _presenter(template: NotificationTemplate) -> dict:
    return {
        "id": str(template.id),
        "owner_scope": template.owner_scope,
        "owner_org_id": str(template.owner_org_id) if template.owner_org_id else None,
        "key": template.key,
        "channel": template.channel,
        "locale": template.locale,
        "version": template.version,
        "status": template.status,
        "subject": template.subject,
        "title": template.title,
        "body": template.body,
        "variables_schema": template.variables_schema,
        "created_by": str(template.created_by) if template.created_by else None,
        "updated_by": str(template.updated_by) if template.updated_by else None,
        "activated_at": (template.activated_at.isoformat() if template.activated_at else None),
        "created_at": template.created_at.isoformat(),
        "updated_at": template.updated_at.isoformat(),
    }


async def _resolve_owner(
    session: AsyncSession, principal: Principal
) -> tuple[str, uuid.UUID | None]:
    """Derive ``(owner_scope, owner_org_id)`` for a template the principal authors.

    Never trusts client-supplied ownership — always derived from the acting
    principal's own org, so an admin cannot author a template on behalf of
    another organization.
    """

    if principal.org_id is None:
        if principal.is_superadmin:
            return "university", None
        raise ValidationFailedError(details={"reason": "org_required"})
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type not in ("university", "partner"):
        raise ValidationFailedError(details={"reason": "org_type_unsupported"})
    return org_type, principal.org_id


def _require_visible(template: NotificationTemplate, principal: Principal) -> None:
    """404 (never 403) for a template outside the principal's own org."""

    if principal.is_superadmin:
        return
    if template.owner_org_id != principal.org_id:
        raise ResourceNotFoundError()


async def _get_template(
    session: AsyncSession, template_id: uuid.UUID
) -> NotificationTemplate | None:
    return (
        await session.execute(
            select(NotificationTemplate).where(NotificationTemplate.id == template_id)
        )
    ).scalar_one_or_none()


def _normalize_key(value: str) -> str:
    key = value.strip().lower()
    if not key or not all(ch.isalnum() or ch in ".-_" for ch in key):
        raise ValidationFailedError(details={"field": "key", "reason": "invalid_key"})
    return key


def _normalize_channel(value: str) -> str:
    channel = value.strip().lower()
    if channel not in _CHANNELS:
        raise ValidationFailedError(details={"field": "channel", "reason": "invalid_channel"})
    return channel


def _normalize_locale(value: str) -> str:
    locale = value.strip().lower()
    if locale not in _LOCALES:
        raise ValidationFailedError(details={"field": "locale", "reason": "invalid_locale"})
    return locale


def _normalize_variables_schema(value: dict | None) -> dict:
    schema = value or {}
    if not isinstance(schema, dict):
        raise ValidationFailedError(
            details={"field": "variables_schema", "reason": "invalid_schema"}
        )
    allowed = schema.get("allowed", [])
    required = schema.get("required", [])
    if not (
        isinstance(allowed, list)
        and all(isinstance(item, str) and item.strip() for item in allowed)
    ):
        raise ValidationFailedError(
            details={"field": "variables_schema.allowed", "reason": "invalid"}
        )
    if not (
        isinstance(required, list)
        and all(isinstance(item, str) and item.strip() for item in required)
    ):
        raise ValidationFailedError(
            details={"field": "variables_schema.required", "reason": "invalid"}
        )
    return {"allowed": list(allowed), "required": list(required)}


async def _next_version(
    session: AsyncSession,
    *,
    owner_scope: str,
    owner_org_id: uuid.UUID | None,
    key: str,
    channel: str,
    locale: str,
) -> int:
    stmt = select(NotificationTemplate.version).where(
        NotificationTemplate.owner_scope == owner_scope,
        NotificationTemplate.owner_org_id == owner_org_id,
        NotificationTemplate.key == key,
        NotificationTemplate.channel == channel,
        NotificationTemplate.locale == locale,
    )
    versions = (await session.execute(stmt)).scalars().all()
    return (max(versions) + 1) if versions else 1


async def list_templates_admin(
    session: AsyncSession,
    *,
    principal: Principal,
    key: str | None = None,
    channel: str | None = None,
    locale: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """List templates visible to the principal, newest version first.

    A non-superadmin only sees templates owned by their own org
    (``owner_org_id == principal.org_id``); passing ``key``/``channel``/
    ``locale`` narrows to one identity's full version history ("list
    versions").
    """

    permission_checker.require(principal, _RESOURCE, "read")
    stmt = select(NotificationTemplate)
    if not principal.is_superadmin:
        stmt = stmt.where(NotificationTemplate.owner_org_id == principal.org_id)
    if key is not None:
        stmt = stmt.where(NotificationTemplate.key == _normalize_key(key))
    if channel is not None:
        stmt = stmt.where(NotificationTemplate.channel == _normalize_channel(channel))
    if locale is not None:
        stmt = stmt.where(NotificationTemplate.locale == _normalize_locale(locale))
    if status is not None:
        if status not in _STATUSES:
            raise ValidationFailedError(details={"field": "status", "reason": "invalid_status"})
        stmt = stmt.where(NotificationTemplate.status == status)
    stmt = stmt.order_by(
        NotificationTemplate.key,
        NotificationTemplate.channel,
        NotificationTemplate.locale,
        NotificationTemplate.version.desc(),
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_presenter(row) for row in rows]


async def create_template(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
) -> dict:
    permission_checker.require(principal, _RESOURCE, "create", resource_org_id=principal.org_id)
    owner_scope, owner_org_id = await _resolve_owner(session, principal)

    key = _normalize_key(payload["key"])
    channel = _normalize_channel(payload["channel"])
    locale = _normalize_locale(payload["locale"])
    body = payload["body"]
    subject = payload.get("subject")
    title = payload.get("title")
    variables_schema = _normalize_variables_schema(payload.get("variables_schema"))

    # Reject unknown ``{{var}}`` placeholders before it ever reaches storage.
    validate_template(body=body, subject=subject, title=title, variables_schema=variables_schema)

    version = await _next_version(
        session,
        owner_scope=owner_scope,
        owner_org_id=owner_org_id,
        key=key,
        channel=channel,
        locale=locale,
    )

    template = NotificationTemplate(
        owner_scope=owner_scope,
        owner_org_id=owner_org_id,
        key=key,
        channel=channel,
        locale=locale,
        version=version,
        status="draft",
        subject=subject,
        title=title,
        body=body,
        variables_schema=variables_schema,
        created_by=principal.user_id,
    )
    session.add(template)
    await session.flush()
    await write_audit(
        session,
        action="notification_template.created",
        resource_type="notification_template",
        resource_id=template.id,
        context=_audit_ctx(principal, ctx),
        after={"key": key, "channel": channel, "locale": locale, "version": version},
    )
    await session.commit()
    return _presenter(template)


async def update_template(
    session: AsyncSession,
    *,
    principal: Principal,
    template_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
) -> dict:
    template = await _get_template(session, template_id)
    if template is None:
        raise ResourceNotFoundError()
    _require_visible(template, principal)
    permission_checker.require(
        principal, _RESOURCE, "update", resource_org_id=template.owner_org_id
    )

    if template.status != "draft":
        raise ConflictError(
            "Chỉ có thể chỉnh sửa bản nháp. Hãy tạo phiên bản mới để cập nhật.",
            details={"reason": "template_not_draft", "status": template.status},
        )

    before = {
        "subject": template.subject,
        "title": template.title,
        "body": template.body,
        "variables_schema": template.variables_schema,
    }

    subject = payload.get("subject", template.subject)
    title = payload.get("title", template.title)
    body = payload.get("body", template.body)
    variables_schema = (
        _normalize_variables_schema(payload["variables_schema"])
        if "variables_schema" in payload
        else template.variables_schema
    )

    validate_template(body=body, subject=subject, title=title, variables_schema=variables_schema)

    if "subject" in payload:
        template.subject = subject
    if "title" in payload:
        template.title = title
    if "body" in payload:
        template.body = body
    if "variables_schema" in payload:
        template.variables_schema = variables_schema
    template.updated_by = principal.user_id

    await session.flush()
    await write_audit(
        session,
        action="notification_template.updated",
        resource_type="notification_template",
        resource_id=template.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={
            "subject": template.subject,
            "title": template.title,
            "body": template.body,
            "variables_schema": template.variables_schema,
        },
    )
    await session.refresh(template)
    result = _presenter(template)
    await session.commit()
    return result


async def activate_template(
    session: AsyncSession,
    *,
    principal: Principal,
    template_id: uuid.UUID,
    ctx: RequestContext,
) -> dict:
    """Publish a draft/archived version, retiring whichever version is live.

    Activating an older ``archived`` version is the supported "rollback"
    path: its content is unchanged, only its status flips back to ``active``.
    """

    template = await _get_template(session, template_id)
    if template is None:
        raise ResourceNotFoundError()
    _require_visible(template, principal)
    permission_checker.require(
        principal, _RESOURCE, "activate", resource_org_id=template.owner_org_id
    )

    if template.status == "active":
        raise ConflictError(
            "Mẫu này đã được kích hoạt.",
            details={"reason": "already_active"},
        )

    validate_template(
        body=template.body,
        subject=template.subject,
        title=template.title,
        variables_schema=template.variables_schema,
    )

    stmt = select(NotificationTemplate).where(
        NotificationTemplate.owner_scope == template.owner_scope,
        NotificationTemplate.owner_org_id == template.owner_org_id,
        NotificationTemplate.key == template.key,
        NotificationTemplate.channel == template.channel,
        NotificationTemplate.locale == template.locale,
        NotificationTemplate.status == "active",
        NotificationTemplate.id != template.id,
    )
    previously_active = (await session.execute(stmt)).scalars().all()
    for row in previously_active:
        row.status = "archived"

    template.status = "active"
    template.activated_at = datetime.now(tz=UTC)
    template.updated_by = principal.user_id

    await session.flush()
    await write_audit(
        session,
        action="notification_template.activated",
        resource_type="notification_template",
        resource_id=template.id,
        context=_audit_ctx(principal, ctx),
        before={"status": "draft_or_archived"},
        after={"status": "active", "version": template.version},
    )
    await session.refresh(template)
    result = _presenter(template)
    await session.commit()
    return result


async def archive_template(
    session: AsyncSession,
    *,
    principal: Principal,
    template_id: uuid.UUID,
    ctx: RequestContext,
) -> dict:
    template = await _get_template(session, template_id)
    if template is None:
        raise ResourceNotFoundError()
    _require_visible(template, principal)
    permission_checker.require(
        principal, _RESOURCE, "archive", resource_org_id=template.owner_org_id
    )

    if template.status == "archived":
        raise ConflictError("Mẫu này đã được lưu trữ.", details={"reason": "already_archived"})

    before_status = template.status
    template.status = "archived"
    template.updated_by = principal.user_id

    await session.flush()
    await write_audit(
        session,
        action="notification_template.archived",
        resource_type="notification_template",
        resource_id=template.id,
        context=_audit_ctx(principal, ctx),
        before={"status": before_status},
        after={"status": "archived"},
    )
    await session.refresh(template)
    result = _presenter(template)
    await session.commit()
    return result


async def preview_template(
    session: AsyncSession,
    *,
    principal: Principal,
    template_id: uuid.UUID,
    sample_variables: dict | None = None,
) -> dict:
    """Render subject/body with sample data. Never sends anything."""

    template = await _get_template(session, template_id)
    if template is None:
        raise ResourceNotFoundError()
    _require_visible(template, principal)
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=template.owner_org_id)

    variables = dict(sample_variables or {})
    allowed, required = (
        set(template.variables_schema.get("allowed", []))
        | set(template.variables_schema.get("required", [])),
        set(template.variables_schema.get("required", [])),
    )
    # Fill any un-supplied variable (required or optional) with a readable
    # placeholder so admins can proofread layout without hand-typing every
    # value; caller-supplied values always win.
    for name in allowed:
        variables.setdefault(name, f"[{name}]")

    rendered = render(
        body=template.body,
        subject=template.subject,
        title=template.title,
        variables=variables,
        variables_schema=template.variables_schema,
        action_url_allowlist={"/"},
    )
    return {
        "template_id": str(template.id),
        "locale": template.locale,
        "channel": template.channel,
        "subject": rendered.subject,
        "title": rendered.title,
        "body": rendered.body,
        "required_variables": sorted(required),
    }
