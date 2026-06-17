from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.exceptions import AppError, ErrorCode
from app.core.config import settings
from app.infra.database.models import Permission, RolePermission, User, UserOrgRole
from app.infra.database.session import get_db


def require_permission(resource: str, action: str) -> Callable:
    def dependency(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> User:
        if not settings.enforce_rbac:
            return current_user

        stmt = (
            select(Permission.id)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserOrgRole, UserOrgRole.role_id == RolePermission.role_id)
            .where(
                UserOrgRole.user_id == current_user.id,
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
