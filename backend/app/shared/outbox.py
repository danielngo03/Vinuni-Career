"""
Transactional outbox interface and domain event types.

The outbox pattern ensures domain events are never lost: a domain event is
written to the ``outbox_events`` table in the same DB transaction as the
aggregate mutation. A background worker polls the table and dispatches events
to the event bus / Temporal workflow.

Usage in a service:
    from app.shared.outbox import OutboxWriter, RegistrationSubmitted

    writer = OutboxWriter(db)
    writer.emit(RegistrationSubmitted(aggregate_id=app_id, registration_type="STUDENT"))
    db.commit()   # outbox row + domain mutation committed atomically
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Domain event dataclasses — one per significant domain transition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegistrationSubmitted:
    aggregate_id: str          # RegistrationApplication.id
    registration_type: str     # "STUDENT" | "PARTNER"
    university_org_id: str
    user_id: str
    version: int = 1
    event_type: str = field(default="registration.submitted", init=False)
    aggregate_type: str = field(default="RegistrationApplication", init=False)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegistrationApproved:
    aggregate_id: str
    registration_type: str
    user_id: str
    event_type: str = field(default="registration.approved", init=False)
    aggregate_type: str = field(default="RegistrationApplication", init=False)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegistrationChangesRequested:
    aggregate_id: str
    registration_type: str
    user_id: str
    checklist: list[dict[str, Any]] = field(default_factory=list)
    event_type: str = field(default="registration.changes_requested", init=False)
    aggregate_type: str = field(default="RegistrationApplication", init=False)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentUploaded:
    aggregate_id: str          # Document.id
    owner_id: str
    category: str
    storage_key: str
    event_type: str = field(default="document.uploaded", init=False)
    aggregate_type: str = field(default="Document", init=False)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentScanCompleted:
    aggregate_id: str
    scan_result: str           # "CLEAN" | "INFECTED" | "ERROR"
    event_type: str = field(default="document.scan_completed", init=False)
    aggregate_type: str = field(default="Document", init=False)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# OutboxWriter — writes event rows in the same DB transaction
# ---------------------------------------------------------------------------

class OutboxWriter:
    """Write domain events to the outbox table atomically.

    Import the SQLAlchemy model lazily to avoid circular imports.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def emit(self, event: Any) -> None:
        """Persist one outbox event row.  Call before db.commit()."""
        from app.platform.database.models.outbox import OutboxEvent  # lazy

        payload = {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in asdict(event).items()
            if k not in {"event_type", "aggregate_type", "occurred_at", "metadata"}
        }
        row = OutboxEvent(
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            payload=json.dumps(payload),
            occurred_at=event.occurred_at,
            metadata_json=json.dumps(event.metadata),
        )
        self._db.add(row)
