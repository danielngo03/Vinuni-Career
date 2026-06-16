from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.exceptions.types import AppError, ErrorCode
from app.core.context import get_request_context


def _trace_id() -> str | None:
    context = get_request_context()
    return context.trace_id if context else None


def _payload(code: str, message: str, details: object | None = None) -> dict:
    body = {"error": {"code": code, "message": message, "trace_id": _trace_id()}}
    if details:
        body["error"]["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code.value, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content=_payload(ErrorCode.BAD_REQUEST.value, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=422,
            content=_payload(
                ErrorCode.VALIDATION_ERROR.value,
                "Request validation failed",
                exc.errors(),
            ),
        )
