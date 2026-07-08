"""Global exception handlers emitting the API_CONTRACTS error envelope.

Clients only ever receive ``{"error": {code, message, details, request_id}}``.
Internal details — stack traces, provider/model names, raw enum codes, DB errors
— are logged server-side and never leaked to the client.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx
from app.shared.exceptions import (
    AppError,
    AuthRequiredError,
    InternalError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.responses import error_envelope

logger = logging.getLogger(__name__)


def _envelope(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=error_envelope(
            code=exc.code,
            message=exc.message,
            request_id=request_id_ctx.get(),
            details=exc.details,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        # Expected, user-safe errors. Log at info/warning without PII.
        logger.info("app.error", extra={"code": exc.code})
        return _envelope(exc)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Surface field locations only — no raw values that may contain PII.
        fields = [
            {"loc": ".".join(str(p) for p in err.get("loc", [])), "type": err.get("type")}
            for err in exc.errors()
        ]
        wrapped = ValidationFailedError(details={"fields": fields})
        return _envelope(wrapped)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _envelope(ResourceNotFoundError())
        if exc.status_code == 401:
            return _envelope(AuthRequiredError())
        mapped = AppError()
        mapped.http_status = exc.status_code
        mapped.code = "INTERNAL_ERROR" if exc.status_code >= 500 else "VALIDATION_FAILED"
        return _envelope(mapped)

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Never leak internals. Full traceback is logged server-side only.
        logger.exception("app.unhandled_error")
        return _envelope(InternalError())
