"""Internal helpers shared across the recruitment services.

RBAC + tenant isolation follow the project pattern: ownership/org scope is
checked in the service layer and a cross-owner/cross-org access returns ``404``
(never ``403``) so resources are not enumerable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.domain.models import Application
from app.shared.audit import AuditContext
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal

RESOURCE = "applications"


def now() -> datetime:
    return datetime.now(tz=UTC)


def as_aware(dt: datetime) -> datetime:
    """Coerce a possibly-naive timestamp (SQLite reads back naive) to UTC-aware."""

    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def to_uuid(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def use_for_update() -> bool:
    return get_settings().database_url.startswith("postgresql")


async def load_application(
    session: AsyncSession, *, application_id: uuid.UUID, lock: bool = False
) -> Application:
    stmt = select(Application).where(
        Application.id == application_id, Application.deleted_at.is_(None)
    )
    if lock and use_for_update():
        stmt = stmt.with_for_update()
    app = (await session.execute(stmt)).scalar_one_or_none()
    if app is None:
        raise ResourceNotFoundError()
    return app


async def org_display_name(session: AsyncSession, org_id: uuid.UUID) -> str:
    name = await org_reporting_facade.display_name_for(session, org_id)
    return name or "VinUni Career"
