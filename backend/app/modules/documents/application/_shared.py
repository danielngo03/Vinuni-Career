"""Internal helpers shared across the documents services.

RBAC + tenant isolation patterns mirror ``opportunities.job_service``: ownership
is checked in the service layer and a cross-owner access returns ``404`` (never
``403``) so resources are not enumerable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.documents.domain.models import CvProfile, CvSection
from app.shared.audit import AuditContext
from app.shared.permissions import Principal

# CV resource key used by the RBAC checker (students hold ``cv:*``).
RESOURCE = "cv"


def now() -> datetime:
    return datetime.now(tz=UTC)


def to_uuid(value: object) -> uuid.UUID | None:
    """Coerce an id-like value (str/UUID/None) to ``uuid.UUID``.

    Callers (HTTP routers serialize to JSON; the recruitment module may pass
    strings) hand ids as either ``str`` or ``uuid.UUID``. The cross-database
    ``Uuid`` column type requires a real ``uuid.UUID`` on SQLite, so normalize
    here before any query/assignment.
    """

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


def build_snapshot(profile: CvProfile, sections: list[CvSection]) -> dict:
    """Build the immutable CV JSON snapshot stored on a cv_versions row."""

    return {
        "title": profile.title,
        "language": profile.language,
        "template_id": str(profile.template_id) if profile.template_id else None,
        "source_type": profile.source_type,
        "canvas": profile.canvas_json or {},
        "sections": [
            {
                "id": str(s.id),
                "section_type": s.section_type,
                "title": s.title,
                "sort_order": s.sort_order,
                "content_json": s.content_json or {},
                "is_visible": s.is_visible,
            }
            for s in sorted(sections, key=lambda x: (x.sort_order, str(x.id)))
        ],
    }


async def next_version_number(session: AsyncSession, *, cv_id: uuid.UUID) -> int:
    from sqlalchemy import func, select

    from app.modules.documents.domain.models import CvVersion

    current = (
        await session.execute(
            select(func.max(CvVersion.version_number)).where(CvVersion.cv_id == cv_id)
        )
    ).scalar_one_or_none()
    return (current or 0) + 1
