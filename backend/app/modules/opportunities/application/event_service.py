from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.opportunities.infrastructure.models import Event, EventRegistration
from app.modules.opportunities.schemas import EventCreate, EventRegistrationCreate
from app.shared.enum import EventRegistrationStatus, EventStatus
from app.shared.errors import AppError, ErrorCode


def create_event(db: Session, payload: EventCreate, *, actor_id: str | None = None) -> Event:
    event = Event(
        org_id=payload.org_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        event_type=payload.event_type,
        start_time=payload.start_time,
        end_time=payload.end_time,
        location_type=payload.location_type,
        location_address=payload.location_address,
        meeting_url=payload.meeting_url,
        max_attendees=payload.max_attendees,
        status=EventStatus.PUBLISHED,
        approved_by=actor_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_events(db: Session, *, org_id: str | None = None, limit: int = 20, offset: int = 0) -> list[Event]:
    stmt = select(Event).where(Event.deleted_at.is_(None)).order_by(Event.start_time.asc())
    if org_id:
        stmt = stmt.where(Event.org_id == org_id)
    return list(db.scalars(stmt.limit(limit).offset(offset)))


def get_event(db: Session, event_id: str) -> Event:
    event = db.get(Event, event_id)
    if not event or event.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Event not found", status_code=404)
    return event


def register_event(db: Session, payload: EventRegistrationCreate) -> EventRegistration:
    event = db.scalar(
        select(Event).where(Event.id == payload.event_id).with_for_update()
    )
    if not event or event.deleted_at is not None:
        raise AppError(code=ErrorCode.NOT_FOUND, message="Event not found", status_code=404)

    if event.status != EventStatus.PUBLISHED:
        raise AppError(code=ErrorCode.BAD_REQUEST, message="Event is not open for registration", status_code=400)

    existing = db.scalar(
        select(EventRegistration).where(
            EventRegistration.event_id == payload.event_id,
            EventRegistration.student_id == payload.student_id,
        )
    )
    if existing:
        raise AppError(code=ErrorCode.CONFLICT, message="Already registered for this event", status_code=409)

    status = EventRegistrationStatus.REGISTERED
    if event.max_attendees:
        from sqlalchemy import func
        registered_count = db.scalar(
            select(func.count()).where(
                EventRegistration.event_id == payload.event_id,
                EventRegistration.status == EventRegistrationStatus.REGISTERED
            )
        ) or 0

        if registered_count >= event.max_attendees:
            status = EventRegistrationStatus.WAITLISTED

    registration = EventRegistration(
        event_id=payload.event_id,
        student_id=payload.student_id,
        status=status,
    )
    db.add(registration)
    db.commit()
    db.refresh(registration)
    return registration
