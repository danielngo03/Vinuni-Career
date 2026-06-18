"""
Shared error types — canonical AppError and ErrorCode used by every module.

This intentionally mirrors app.domain.exceptions so legacy imports continue
to work while modules progressively migrate to app.shared.errors.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    BAD_REQUEST = "bad_request"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMITED = "rate_limited"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    """Typed application error that maps to an HTTP status code."""

    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
