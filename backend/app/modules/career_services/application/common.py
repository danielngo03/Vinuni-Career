"""Shared helpers for career-services application services.

Every write service in this module follows the same shape:
``permission_checker.require(...)`` (RBAC + tenant isolation) -> mutate ->
``write_audit(...)`` -> ``session.commit()``. These helpers keep that shape
consistent and small (mirrors ``organization.application.rbac_service``).
"""

from __future__ import annotations

import uuid

from app.modules.auth.application.context import RequestContext
from app.shared.audit import AuditContext
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal


def require_org(principal: Principal) -> uuid.UUID:
    """The acting university org id, or 404 if the principal has none.

    404 (not 403) hides whether the resource would exist for a differently
    scoped caller — same enumeration-hiding convention as
    ``organization.application.rbac_service._require_org``.
    """

    if principal.org_id is None:
        raise ResourceNotFoundError()
    return principal.org_id


def audit_ctx(principal: Principal, ctx: RequestContext) -> AuditContext:
    return AuditContext(
        actor_id=principal.user_id,
        actor_org_id=principal.org_id,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )
