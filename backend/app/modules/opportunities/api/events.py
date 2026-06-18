from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.api.rbac import require_permission
from app.modules.opportunities.application.event_service import (
    create_event,
    get_event,
    list_events,
    register_event,
)
from app.modules.opportunities.infrastructure.models import Event, EventRegistration
from app.modules.opportunities.schemas import (
    EventCreate,
    EventRegistrationCreate,
    EventRegistrationView,
    EventView,
)
from app.platform.database.models import User
from app.platform.database.session import get_db

router = APIRouter()

@router.get("", response_model=list[EventView])
def get_events(
    db: Session = Depends(get_db),
    org_id: str | None = Query(default=None),
    _: User = Depends(get_current_user),
) -> list[Event]:
    return list_events(db, org_id=org_id)

@router.post("", response_model=EventView, status_code=201)
def post_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("event", "create")),
) -> Event:
    return create_event(db, payload, actor_id=current_user.id)

@router.get("/{event_id}", response_model=EventView)
def get_event_by_id(
    event_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Event:
    return get_event(db, event_id)

@router.post("/{event_id}/register", response_model=EventRegistrationView, status_code=201)
def register_for_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventRegistration:
    payload = EventRegistrationCreate(event_id=event_id, student_id=current_user.id)
    return register_event(db, payload)
