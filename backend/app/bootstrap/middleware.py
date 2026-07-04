"""Request-id middleware.

Assigns/propagates a ``req_...`` id, binds it to the logging context, and echoes
it back via the ``X-Request-ID`` header so every error envelope is traceable.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        incoming = request.headers.get(_HEADER)
        request_id = incoming or f"req_{uuid.uuid4().hex}"
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[_HEADER] = request_id
        return response
