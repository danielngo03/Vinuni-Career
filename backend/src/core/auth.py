"""Small demo authorization helpers.

This is intentionally not production auth. It gives the demo API a clear role
boundary while the project does not yet have accounts, sessions, or JWTs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from backend.src.core.config import settings

try:
    from fastapi import Header, HTTPException, status
except ImportError:  # pragma: no cover - used only when optional API dependency is absent.
    Header = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]
    status = None  # type: ignore[assignment]


DemoRole = Literal["student", "enterprise", "teacher"]


@dataclass(frozen=True)
class DemoUser:
    user_id: str
    role: DemoRole


def require_roles(*allowed_roles: DemoRole) -> Callable[..., DemoUser]:
    def dependency(
        x_demo_role: str | None = Header(default=None, alias="X-Demo-Role"),
        x_demo_user_id: str | None = Header(default=None, alias="X-Demo-User-Id"),
    ) -> DemoUser:
        if not settings.demo_auth_enabled:
            role = allowed_roles[0] if allowed_roles else "enterprise"
            return DemoUser(user_id=x_demo_user_id or f"demo_{role}", role=role)

        role = (x_demo_role or "").strip().lower()
        if role not in {"student", "enterprise", "teacher"}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid X-Demo-Role header. Use student, enterprise, or teacher.",
            )
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {role} is not allowed for this endpoint.",
            )
        return DemoUser(user_id=(x_demo_user_id or f"demo_{role}").strip(), role=role)  # type: ignore[arg-type]

    return dependency
