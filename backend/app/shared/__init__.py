"""
Shared kernel: IDs, errors, domain events, pagination.

These primitives are safe to import by any module because they carry
no business logic and no ORM/infrastructure dependencies.
"""
from app.shared.errors import AppError, ErrorCode
from app.shared.events import DomainEvent, EventBus, InMemoryEventBus
from app.shared.ids import new_id
from app.shared.pagination import PageRequest, PageResult

__all__ = [
    "AppError",
    "ErrorCode",
    "DomainEvent",
    "EventBus",
    "InMemoryEventBus",
    "PageRequest",
    "PageResult",
    "new_id",
]
