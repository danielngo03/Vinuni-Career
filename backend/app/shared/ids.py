"""Shared ID generation utilities."""
from __future__ import annotations

import uuid


def new_id() -> str:
    """Return a new UUID4 string. Used across all modules for entity IDs."""
    return str(uuid.uuid4())
