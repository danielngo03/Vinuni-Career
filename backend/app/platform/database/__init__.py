"""
app/platform/database — SQLAlchemy session factory and Base declarative.

This is the canonical location. app.platform.database is a backward-compat shim.
"""
from __future__ import annotations

from app.platform.database.session import Base, SessionLocal, get_db

__all__ = ["Base", "SessionLocal", "get_db"]
