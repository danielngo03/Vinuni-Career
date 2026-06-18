from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.context import get_request_context
from app.shared.errors import AppError, ErrorCode

__all__ = ["AppError", "ErrorCode", "register_exception_handlers"]


def _trace_id() -> str | None:
    context = get_request_context()
    return context.trace_id if context else None


def _payload(code: str, message: str, details: object | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {"code": code, "message": message, "trace_id": _trace_id()}
    }
    if details:
        body["error"]["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code.value, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(ErrorCode.BAD_REQUEST.value, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload(
                ErrorCode.VALIDATION_ERROR.value,
                "Request validation failed",
                exc.errors(),
            ),
        )
