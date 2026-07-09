"""Uploaded-CV read-only enforcement at the service layer (B-589).

Owner decision 2026-07-05 (``CLAUDE.md``): an uploaded CV is viewed READ-ONLY —
the student's own original document — while the visual builder/editor and CV AI
edits are reserved for TEMPLATE-created CVs. This was previously frontend-only;
these tests assert the service layer now refuses every user-initiated edit /
AI-mutation path with a friendly ``UploadedCvReadOnlyError`` (409) while leaving
reading, duplicating, and (implicitly) export untouched.

Covered:
- section upsert / create / version-restore on an uploaded CV -> blocked;
- canvas update on an uploaded CV -> blocked;
- AI request_suggestion / request_edit_command / accept on an uploaded CV -> blocked;
- a TEMPLATE-created (builder) CV -> still editable;
- a DUPLICATE of an uploaded CV -> allowed and editable.
"""

from __future__ import annotations

import os
import uuid

import pytest
from app.core.config import get_settings
from app.modules.documents.application import (
    cv_ai_service,
    cv_canvas_service,
    cv_creation_service,
    cv_section_service,
    cv_service,
    ingestion_service,
    template_seed,
)
from app.modules.documents.application.errors import UploadedCvReadOnlyError
from app.modules.documents.domain import catalog
from app.modules.documents.infrastructure import storage
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import InMemoryStorage, make_student, new_key
from tests.fixtures import cv as F


@pytest.fixture(autouse=True)
def _isolated_storage_and_sync():
    storage.set_storage(InMemoryStorage())
    os.environ["CV_INGESTION_ASYNC"] = "false"
    get_settings.cache_clear()
    yield
    storage.set_storage(None)
    os.environ.pop("CV_INGESTION_ASYNC", None)
    get_settings.cache_clear()


async def _make_uploaded_cv(db, student) -> dict:
    """Run the real upload -> ingest -> import path to produce an uploaded CV."""

    await template_seed.ensure_default_templates(db)
    await db.commit()
    up = await ingestion_service.create_upload(
        db,
        principal=student,
        filename="cv.pdf",
        data=F.text_pdf_en(),
        content_type="application/pdf",
        idempotency_key=new_key(),
        ctx=CTX,
    )
    ing = await ingestion_service.start_ingestion(
        db,
        principal=student,
        document_id=uuid.UUID(up["document_id"]),
        ctx=CTX,
    )
    detail = await ingestion_service.import_ingestion(
        db,
        principal=student,
        ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={"title": "Uploaded CV"},
        ctx=CTX,
    )
    assert detail["source_type"] == catalog.SOURCE_TYPE_FOR_MODE[catalog.CREATION_UPLOADED_IMPORT]
    assert detail["is_uploaded"] is True
    return detail


async def _make_builder_cv(db, student) -> dict:
    return await cv_service.create_cv(
        db,
        principal=student,
        payload={"title": "Builder CV", "creation_mode": "blank_template"},
        ctx=CTX,
    )


def _header_id(detail: dict) -> uuid.UUID:
    return uuid.UUID(next(s for s in detail["sections"] if s["section_type"] == "header")["id"])


# --------------------------------------------------------------------------- #
# Uploaded CV: every edit / AI-mutation path is blocked                        #
# --------------------------------------------------------------------------- #


async def test_uploaded_cv_section_upsert_blocked(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    cv_id = uuid.UUID(detail["id"])
    with pytest.raises(UploadedCvReadOnlyError) as exc:
        await cv_section_service.upsert_section(
            db_session,
            principal=student,
            cv_id=cv_id,
            section_id=_header_id(detail),
            payload={"content": {"name": "Hacker"}},
            ctx=CTX,
        )
    assert exc.value.details["reason"] == "uploaded_cv_read_only"
    assert "duplicate" in exc.value.details["actions"]


async def test_uploaded_cv_create_section_blocked(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    with pytest.raises(UploadedCvReadOnlyError):
        await cv_section_service.create_section(
            db_session,
            principal=student,
            cv_id=uuid.UUID(detail["id"]),
            payload={"section_type": "custom", "title": "New", "content": {"items": []}},
            ctx=CTX,
        )


async def test_uploaded_cv_restore_version_blocked(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    version_id = uuid.UUID(detail["versions"][0]["id"])
    with pytest.raises(UploadedCvReadOnlyError):
        await cv_section_service.restore_version(
            db_session,
            principal=student,
            cv_id=uuid.UUID(detail["id"]),
            version_id=version_id,
            payload=None,
            ctx=CTX,
        )


async def test_uploaded_cv_canvas_update_blocked(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    with pytest.raises(UploadedCvReadOnlyError):
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(detail["id"]),
            payload={"page": {"margin": "narrow"}},
            ctx=CTX,
        )


async def test_uploaded_cv_ai_suggestion_blocked(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    with pytest.raises(UploadedCvReadOnlyError):
        await cv_ai_service.request_suggestion(
            db_session,
            principal=student,
            cv_id=uuid.UUID(detail["id"]),
            payload={"task_type": catalog.TASK_ATS_KEYWORDS, "job_id": str(uuid.uuid4())},
            ctx=CTX,
        )


async def test_uploaded_cv_ai_edit_command_blocked(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    with pytest.raises(UploadedCvReadOnlyError):
        await cv_ai_service.request_edit_command(
            db_session,
            principal=student,
            cv_id=uuid.UUID(detail["id"]),
            payload={"instruction": "rewrite my summary", "idempotency_key": new_key()},
            ctx=CTX,
        )


async def test_uploaded_cv_ai_accept_blocked(db_session) -> None:
    # Defense in depth: accept is guarded BEFORE the suggestion lookup, so even a
    # (hypothetical) pending suggestion could never be applied to an uploaded CV.
    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    with pytest.raises(UploadedCvReadOnlyError):
        await cv_ai_service.accept_suggestion(
            db_session,
            principal=student,
            cv_id=uuid.UUID(detail["id"]),
            suggestion_id=uuid.uuid4(),
            payload={"fact_confirmation": True},
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Reading an uploaded CV is never blocked                                      #
# --------------------------------------------------------------------------- #


async def test_uploaded_cv_read_still_allowed(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    got = await cv_service.get_cv(
        db_session,
        principal=student,
        cv_id=uuid.UUID(detail["id"]),
    )
    assert got["is_uploaded"] is True
    assert got["sections"]


# --------------------------------------------------------------------------- #
# TEMPLATE-created CVs stay fully editable                                     #
# --------------------------------------------------------------------------- #


async def test_builder_cv_still_editable(db_session) -> None:
    _u, student = await make_student(db_session)
    detail = await _make_builder_cv(db_session, student)
    res = await cv_section_service.upsert_section(
        db_session,
        principal=student,
        cv_id=uuid.UUID(detail["id"]),
        section_id=_header_id(detail),
        payload={"content": {"name": "Real Owner"}, "expected_version": detail["version"]},
        ctx=CTX,
    )
    assert res["cv_version"] == detail["version"] + 1


# --------------------------------------------------------------------------- #
# A DUPLICATE of an uploaded CV is an editable builder copy                     #
# --------------------------------------------------------------------------- #


async def test_duplicate_of_uploaded_cv_is_editable(db_session) -> None:
    _u, student = await make_student(db_session)
    uploaded = await _make_uploaded_cv(db_session, student)

    dup = await cv_creation_service.duplicate_cv(
        db_session,
        principal=student,
        cv_id=uuid.UUID(uploaded["id"]),
        payload={"idempotency_key": new_key()},
        ctx=CTX,
    )
    assert dup["is_uploaded"] is False
    assert dup["source_type"] == catalog.SOURCE_TYPE_FOR_MODE[catalog.CREATION_DUPLICATE]

    # The duplicated copy IS editable (it is a builder CV, not an uploaded one).
    res = await cv_section_service.upsert_section(
        db_session,
        principal=student,
        cv_id=uuid.UUID(dup["id"]),
        section_id=_header_id(dup),
        payload={"content": {"name": "Edited Copy"}, "expected_version": dup["version"]},
        ctx=CTX,
    )
    assert res["cv_version"] == dup["version"] + 1


# --------------------------------------------------------------------------- #
# The uploaded CV's own DB row confirms the guard target                       #
# --------------------------------------------------------------------------- #


async def test_uploaded_cv_source_type_value(db_session) -> None:
    from app.modules.documents.domain.models import CvProfile

    _u, student = await make_student(db_session)
    detail = await _make_uploaded_cv(db_session, student)
    row = (
        await db_session.execute(select(CvProfile).where(CvProfile.id == uuid.UUID(detail["id"])))
    ).scalar_one()
    assert row.source_type == "uploaded_import"
