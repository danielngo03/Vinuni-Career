"""Compatibility alias. New code must import from :mod:`app.shared.errors`."""

from app.shared.errors import AppError, ErrorCode

__all__ = ["AppError", "ErrorCode"]
