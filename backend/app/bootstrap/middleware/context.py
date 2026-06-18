from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.shared.constants import TRACE_ID_HEADER
from app.shared.context import RequestContext, set_request_context


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get(TRACE_ID_HEADER, str(uuid4()))
        set_request_context(
            RequestContext(
                trace_id=trace_id,
            )
        )
        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        return response
