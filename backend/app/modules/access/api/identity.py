from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.platform.database.models import User, UserOrgRole
from app.platform.database.session import get_db
from app.shared.enum import OrgType
from app.shared.errors import AppError, ErrorCode


def get_active_identity(
    identity_id: str | None = Header(default=None, alias="X-Identity-Id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOrgRole:
    if not identity_id:
        raise AppError(
            code=ErrorCode.BAD_REQUEST,
            message="X-Identity-Id header is required",
            status_code=400,
        )
    identity = db.get(UserOrgRole, identity_id)
    if not identity or identity.user_id != current_user.id:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="Identity is not available for the current user",
            status_code=403,
        )
    return identity


def get_optional_active_identity(
    identity_id: str | None = Header(default=None, alias="X-Identity-Id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOrgRole | None:
    if not identity_id:
        return None
    identity = db.get(UserOrgRole, identity_id)
    if not identity or identity.user_id != current_user.id:
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message="Identity is not available for the current user",
            status_code=403,
        )
    return identity


def require_portal(*allowed: str) -> Callable:
    def dependency(
        identity: UserOrgRole = Depends(get_active_identity),
    ) -> UserOrgRole:
        portal = _portal_for_identity(identity)
        if portal not in allowed:
            raise AppError(
                code=ErrorCode.FORBIDDEN,
                message=f"Workspace access required: {', '.join(allowed)}",
                status_code=403,
            )
        return identity

    return dependency


def _portal_for_identity(identity: UserOrgRole) -> str:
    if identity.org.type == OrgType.UNIVERSITY and identity.role.name == "student":
        return "student"
    if identity.org.type == OrgType.PARTNER:
        return "partner"
    return "university"
