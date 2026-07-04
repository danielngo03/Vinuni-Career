"""Shared helpers for documents / CV Studio tests."""

from __future__ import annotations

import uuid

from app.modules.auth.domain.personas import permissions_for
from app.shared.permissions import Principal
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import register_verified
from tests.org_utils import email


class InMemoryStorage:
    """A dict-backed StorageBackend so tests never touch the filesystem."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> None:
        self._data[key] = data

    def load(self, key: str) -> bytes:
        from app.modules.documents.infrastructure.storage import StorageError

        if key not in self._data:
            raise StorageError("object not found")
        return self._data[key]

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


async def make_student(
    session: AsyncSession, *, prefix: str = "student"
) -> tuple[object, Principal]:
    """Register a verified student and return (user, student_principal)."""

    user = await register_verified(session, email=email(prefix))
    principal = Principal(
        user_id=user.id,
        persona="student",
        org_id=None,
        is_superadmin=False,
        permissions=permissions_for("student"),
    )
    return user, principal


def cv_text_en() -> bytes:
    return (
        b"John Candidate\n"
        b"Email: john.candidate@example.com | Phone: +84 912 345 678\n\n"
        b"Objective\nBackend engineering internship focused on APIs.\n\n"
        b"Education\nVinUniversity - BSc Computer Science, 2022 - 2026.\n\n"
        b"Experience\nSoftware Intern, Example Tech (2024 - 2025)\n"
        b"- Built REST APIs with FastAPI and PostgreSQL.\n\n"
        b"Skills\nPython, FastAPI, SQLAlchemy, PostgreSQL.\n\n"
        b"Projects\nCareer platform with async workers.\n"
    )


def new_key() -> str:
    return uuid.uuid4().hex
