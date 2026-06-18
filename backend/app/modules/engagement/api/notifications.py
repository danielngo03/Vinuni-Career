from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.engagement.application.notification_service import (
    get_my_notifications,
    mark_all_read,
    mark_read,
    unread_count,
)
from app.modules.engagement.infrastructure.models import Notification
from app.modules.engagement.schemas import NotificationView
from app.platform.database.models.identity import User
from app.platform.database.session import get_db
from app.shared.schemas import PageParams

router = APIRouter()

@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    return {"count": unread_count(db, current_user.id)}

@router.post("/read-all")
def read_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    mark_all_read(db, current_user.id)
    return {"message": "All notifications marked as read"}

@router.get("", response_model=list[NotificationView])
def get_notifications(
    page: PageParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Notification]:
    return get_my_notifications(db, current_user.id, limit=page.limit, offset=page.offset)

@router.post("/{notification_id}/read", response_model=NotificationView)
def read_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Notification:
    return mark_read(db, notification_id, current_user.id)
