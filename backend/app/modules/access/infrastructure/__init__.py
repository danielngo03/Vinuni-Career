"""
Access module — infrastructure layer.

SQLAlchemy repositories. These import ORM models and DB session.
No FastAPI, no domain event bus (events emitted by use cases, not repos).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.access.domain import ActiveIdentity, PortalType
from app.platform.database.models import UserOrgRole
from app.shared.enum import OrgType
from app.shared.errors import AppError, ErrorCode


class IdentityRepository:
    """Read-side repo: resolve ActiveIdentity from DB rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_active_identity(self, user_id: str, identity_id: str) -> ActiveIdentity:
        identity = self._db.get(UserOrgRole, identity_id)
        if not identity or identity.user_id != user_id:
            raise AppError(
                code=ErrorCode.FORBIDDEN,
                message="Identity is not available for the current user",
                status_code=403,
            )
        return self._to_value_object(identity)

    def list_identities(self, user_id: str) -> list[ActiveIdentity]:
        rows = self._db.scalars(
            select(UserOrgRole).where(UserOrgRole.user_id == user_id)
        ).all()
        return [self._to_value_object(r) for r in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _to_value_object(self, identity: UserOrgRole) -> ActiveIdentity:
        org = identity.org
        role = identity.role
        portal = self._resolve_portal(org.type, role.name)
        permissions = frozenset(
            f"{rp.permission.resource}:{rp.permission.action}"
            for rp in role.permissions
        )
        return ActiveIdentity(
            identity_id=identity.id,
            user_id=identity.user_id,
            org_id=org.id,
            org_type=org.type,
            role_name=role.name,
            portal=portal,
            permissions=permissions,
        )

    @staticmethod
    def _resolve_portal(org_type: str, role_name: str) -> PortalType:
        if org_type == OrgType.UNIVERSITY and role_name == "student":
            return PortalType.STUDENT
        if org_type == OrgType.PARTNER:
            return PortalType.PARTNER
        return PortalType.UNIVERSITY
