from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.platform.database.models import Permission, RolePermission, User, UserOrgRole
from app.platform.database.session import get_db
from app.shared.config import settings
from app.shared.errors import AppError, ErrorCode


def require_permission(resource: str, action: str) -> Callable:
    def dependency(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        identity_id: str | None = Header(default=None, alias="X-Identity-Id"),
    ) -> User:
        if not settings.enforce_rbac:
            return current_user
        if not identity_id:
            raise AppError(
                code=ErrorCode.BAD_REQUEST,
                message="X-Identity-Id header is required",
                status_code=400,
            )

        stmt = (
            select(Permission.id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserOrgRole, UserOrgRole.role_id == RolePermission.role_id)
            .where(
                UserOrgRole.user_id == current_user.id,
                UserOrgRole.id == identity_id,
                Permission.resource == resource,
                Permission.action == action,
            )
            .limit(1)
        )
        if db.scalar(stmt):
            return current_user
        raise AppError(
            code=ErrorCode.FORBIDDEN,
            message=f"Missing permission: {resource}:{action}",
            status_code=403,
        )

    return dependency
