from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    trace_id: str
    org_id: str | None = None
    dept_id: str | None = None
    user_id: str | None = None


_request_context: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def set_request_context(context: RequestContext) -> None:
    _request_context.set(context)


def get_request_context() -> RequestContext | None:
    return _request_context.get()
