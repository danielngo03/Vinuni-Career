"""University-admin CV template catalogue management.

Students consume active templates through ``GET /cv-templates``. This service is
the no-code back-office surface for university staff to add or tune template
metadata without a deploy. RBAC and university-org gating live here, not only in
routers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.api import presenters
from app.modules.documents.domain import themes
from app.modules.documents.domain.models import CvTemplate, CvTemplateVersion
from app.modules.organization.application import org_reporting_facade
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "cv_templates"


def _audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


async def _require_template_admin(session: AsyncSession, principal: Principal, action: str) -> None:
    if principal.is_superadmin:
        return
    permission_checker.require(principal, _RESOURCE, action)
    org_type = await org_reporting_facade.org_type_for(session, principal.org_id)
    if org_type != "university":
        raise PermissionDeniedError(details={"reason": "university_only"})


def _normalize_key(value: str) -> str:
    key = value.strip().lower().replace(" ", "_").replace("-", "_")
    if not key or not all(ch.isalnum() or ch == "_" for ch in key):
        raise ValidationFailedError(details={"field": "key", "reason": "invalid_template_key"})
    return key


def _normalize_category(value: str) -> str:
    category = value.strip().lower().replace(" ", "_").replace("-", "_")
    if not category or not all(ch.isalnum() or ch == "_" for ch in category):
        raise ValidationFailedError(
            details={"field": "category", "reason": "invalid_template_category"}
        )
    return category


def _normalize_layout_schema(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValidationFailedError(
            details={"field": "layout_schema", "reason": "invalid_layout_schema"}
        )
    # A full visual theme (layout/palette/typography/...) validates through its own
    # structural check; the P4 composer produces this shape. Legacy metadata-only
    # schemas ({section_order, target_roles, strengths}) still validate below.
    if themes.is_full_theme(value):
        return value
    section_order = value.get("section_order")
    if section_order is not None and not (
        isinstance(section_order, list)
        and all(isinstance(item, str) and item.strip() for item in section_order)
    ):
        raise ValidationFailedError(
            details={"field": "layout_schema.section_order", "reason": "invalid"}
        )
    target_roles = value.get("target_roles")
    if target_roles is not None and not (
        isinstance(target_roles, list)
        and all(isinstance(item, str) and item.strip() for item in target_roles)
    ):
        raise ValidationFailedError(
            details={"field": "layout_schema.target_roles", "reason": "invalid"}
        )
    strengths = value.get("strengths")
    if strengths is not None and not (
        isinstance(strengths, list)
        and all(isinstance(item, str) and item.strip() for item in strengths)
    ):
        raise ValidationFailedError(
            details={"field": "layout_schema.strengths", "reason": "invalid"}
        )
    return value


async def _get_template(session: AsyncSession, template_id: uuid.UUID) -> CvTemplate | None:
    return (
        await session.execute(select(CvTemplate).where(CvTemplate.id == template_id))
    ).scalar_one_or_none()


async def list_templates_admin(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> list[dict]:
    await _require_template_admin(session, principal, "read")
    rows = (
        (
            await session.execute(
                select(CvTemplate).order_by(
                    CvTemplate.is_active.desc(), CvTemplate.category, CvTemplate.key
                )
            )
        )
        .scalars()
        .all()
    )
    return [presenters.template(row, locale=locale, include_admin_fields=True) for row in rows]


async def create_template(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_template_admin(session, principal, "create")
    key = _normalize_key(payload["key"])
    clash = (await session.execute(select(CvTemplate.id).where(CvTemplate.key == key))).first()
    if clash is not None:
        raise ValidationFailedError(details={"field": "key", "reason": "duplicate_template_key"})
    is_active = bool(payload.get("is_active", True))
    template = CvTemplate(
        key=key,
        name_vi=payload["name_vi"].strip(),
        name_en=payload["name_en"].strip(),
        category=_normalize_category(payload["category"]),
        layout_schema=_normalize_layout_schema(payload.get("layout_schema") or {}),
        is_active=is_active,
        status="published" if is_active else "draft",
        version=1,
        owner_org_id=principal.org_id,
        published_at=datetime.now(UTC) if is_active else None,
    )
    session.add(template)
    await session.flush()
    # Immutable snapshot of version 1 so student CVs can bind to an exact design.
    await _snapshot_template_version(session, template, created_by=principal.user_id)
    await write_audit(
        session,
        action="cv_template.created",
        resource_type="cv_template",
        resource_id=template.id,
        context=_audit_ctx(principal, ctx),
        after={"key": template.key, "category": template.category, "version": 1},
    )
    await session.commit()
    return presenters.template(template, locale=locale, include_admin_fields=True)


async def _snapshot_template_version(
    session: AsyncSession, template: CvTemplate, *, created_by: uuid.UUID | None
) -> CvTemplateVersion:
    """Insert the immutable design snapshot for the template's current version."""

    version = CvTemplateVersion(
        template_id=template.id,
        version_number=template.version,
        design_json=template.layout_schema or {},
        preview_image=template.preview_image,
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    return version


async def update_template(
    session: AsyncSession,
    *,
    principal: Principal,
    template_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    await _require_template_admin(session, principal, "update")
    template = await _get_template(session, template_id)
    if template is None:
        raise ResourceNotFoundError()

    before = {
        "key": template.key,
        "category": template.category,
        "is_active": template.is_active,
        "version": template.version,
    }

    if "key" in payload:
        key = _normalize_key(payload["key"])
        if key != template.key:
            clash = (
                await session.execute(
                    select(CvTemplate.id).where(CvTemplate.key == key, CvTemplate.id != template.id)
                )
            ).first()
            if clash is not None:
                raise ValidationFailedError(
                    details={"field": "key", "reason": "duplicate_template_key"}
                )
            template.key = key
    if "name_vi" in payload:
        template.name_vi = payload["name_vi"].strip()
    if "name_en" in payload:
        template.name_en = payload["name_en"].strip()
    if "category" in payload:
        template.category = _normalize_category(payload["category"])
    design_changed = False
    if "layout_schema" in payload:
        new_schema = _normalize_layout_schema(payload["layout_schema"] or {})
        if new_schema != (template.layout_schema or {}):
            design_changed = True
            # A design change publishes a NEW immutable version so student CVs
            # bound to the prior version keep rendering unchanged.
            template.version += 1
            template.layout_schema = new_schema
    if "is_active" in payload:
        template.is_active = bool(payload["is_active"])

    await session.flush()
    if design_changed:
        template.published_at = datetime.now(UTC)
        await _snapshot_template_version(session, template, created_by=principal.user_id)
    await write_audit(
        session,
        action="cv_template.updated",
        resource_type="cv_template",
        resource_id=template.id,
        context=_audit_ctx(principal, ctx),
        before=before,
        after={
            "key": template.key,
            "category": template.category,
            "is_active": template.is_active,
            "version": template.version,
        },
    )
    await session.commit()
    return presenters.template(template, locale=locale, include_admin_fields=True)
