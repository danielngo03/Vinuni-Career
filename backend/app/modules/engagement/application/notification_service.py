from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.engagement.infrastructure.models import Notification
from app.shared.errors import AppError, ErrorCode


def unread_count(db: Session, user_id: str) -> int:
    count = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
    )
    return int(count or 0)

def mark_all_read(db: Session, user_id: str) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()

def get_my_notifications(db: Session, user_id: str, limit: int = 20, offset: int = 0) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))

def mark_read(db: Session, notification_id: str, user_id: str) -> Notification:
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user_id:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Notification not found", status_code=404)
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n
