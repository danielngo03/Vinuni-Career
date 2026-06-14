"""
In-memory session store for CV data during testing.
Replace with a real database (SQLite/PostgreSQL) in production.
"""
import uuid
from typing import Any

# Simple in-memory storage: { session_id: { "cv_text": ..., "profile": ... } }
_store: dict[str, dict[str, Any]] = {}


def create_session() -> str:
    """Create a new session and return its ID."""
    session_id = str(uuid.uuid4())
    _store[session_id] = {}
    return session_id


def save_cv_text(session_id: str, cv_text: str) -> None:
    """Save raw CV text to session."""
    if session_id not in _store:
        _store[session_id] = {}
    _store[session_id]["cv_text"] = cv_text


def save_profile(session_id: str, profile: dict[str, Any]) -> None:
    """Save parsed CV profile to session."""
    if session_id not in _store:
        _store[session_id] = {}
    _store[session_id]["profile"] = profile


def get_profile(session_id: str) -> dict[str, Any] | None:
    """Get parsed CV profile from session."""
    session = _store.get(session_id)
    if not session:
        return None
    return session.get("profile")


def get_cv_text(session_id: str) -> str | None:
    """Get raw CV text from session."""
    session = _store.get(session_id)
    if not session:
        return None
    return session.get("cv_text")


def list_sessions() -> list[str]:
    """List all active session IDs."""
    return list(_store.keys())


def delete_session(session_id: str) -> bool:
    """Delete a session."""
    if session_id in _store:
        del _store[session_id]
        return True
    return False
