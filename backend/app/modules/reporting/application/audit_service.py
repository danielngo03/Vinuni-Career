from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.platform.database.models import AuditLog


def write_audit(
    db: Session,
    *,
    actor_id: str | None,
    action: str,
    target_resource: str,
    target_id: str | None,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
) -> AuditLog:
    audit = AuditLog(
        actor_id=actor_id,
        action=action,
        target_resource=target_resource,
        target_id=target_id,
        old_data=old_data,
        new_data=new_data,
    )
    db.add(audit)
    return audit
