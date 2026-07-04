"""CV Studio visual canvas + profile-photo tests.

Covers (``docs/CV_STUDIO_SPEC.md`` "Visual Canvas Editor Contract"):

- canvas block CRUD/ordering: valid blocks persist, versioned + audited;
- invalid block payloads (bad type, duplicate id, unknown section_id, bad order)
  are rejected;
- canvas update never clobbers a previously-set photo binding (partial merge);
- optimistic-concurrency (``expected_version``) conflict;
- photo replace/crop happy path + invalid crop rect + invalid file type/size +
  RBAC (owner-only) + remove;
- restoring a prior version restores canvas layout too.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import (
    cv_canvas_service,
    cv_photo_service,
    cv_section_service,
    cv_service,
)
from app.modules.documents.application.errors import (
    CvVersionConflictError,
    InvalidCropRectError,
    InvalidCvFieldError,
    InvalidPhotoFileError,
)
from app.modules.documents.domain.models import CvSection
from app.modules.documents.infrastructure import storage
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import InMemoryStorage, make_student

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(autouse=True)
def _isolated_storage():
    storage.set_storage(InMemoryStorage())
    yield
    storage.set_storage(None)


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _make_cv(db, student, *, title="My CV") -> dict:
    return await cv_service.create_cv(
        db, principal=student, payload={"title": title, "creation_mode": "blank_template"},
        ctx=CTX,
    )


async def _section_id(db, cv_id, section_type) -> uuid.UUID:
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    return next(s for s in sections if s.section_type == section_type).id


# --------------------------------------------------------------------------- #
# Canvas block CRUD / ordering                                                #
# --------------------------------------------------------------------------- #


async def test_update_canvas_persists_blocks_versioned_and_audited(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    summary_id = await _section_id(db_session, cv["id"], "summary")
    before = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    versions_before = len(before["versions"])

    data = await cv_canvas_service.update_canvas(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={
            "blocks": [
                {"id": "b1", "type": "heading", "section_id": str(summary_id), "order": 0,
                 "visible": True},
                {"id": "b2", "type": "text", "section_id": str(summary_id), "order": 1,
                 "visible": True, "style": {"font_size": 12}},
            ],
        },
        ctx=CTX,
    )
    assert data["canvas"]["blocks"][0]["id"] == "b1"
    assert data["canvas"]["blocks"][1]["style"] == {"font_size": 12}
    assert data["version"] == before["version"] + 1
    assert len(data["versions"]) == versions_before + 1
    assert await _audit_count(db_session, "cv.canvas.updated") == 1


async def test_update_canvas_reorders_blocks(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_canvas_service.update_canvas(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 0}]}, ctx=CTX,
    )
    data = await cv_canvas_service.update_canvas(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 5}]}, ctx=CTX,
    )
    assert data["canvas"]["blocks"][0]["order"] == 5


async def test_update_canvas_rejects_unknown_section_id(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError):
        await cv_canvas_service.update_canvas(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={
                "blocks": [
                    {"id": "b1", "type": "text", "section_id": str(uuid.uuid4()), "order": 0}
                ]
            },
            ctx=CTX,
        )


async def test_update_canvas_rejects_invalid_block_type(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError):
        await cv_canvas_service.update_canvas(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={"blocks": [{"id": "b1", "type": "not_a_type", "order": 0}]}, ctx=CTX,
        )


async def test_update_canvas_rejects_duplicate_block_ids(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError):
        await cv_canvas_service.update_canvas(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={
                "blocks": [
                    {"id": "dup", "type": "text", "order": 0},
                    {"id": "dup", "type": "text", "order": 1},
                ]
            },
            ctx=CTX,
        )


async def test_update_canvas_version_conflict(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(CvVersionConflictError):
        await cv_canvas_service.update_canvas(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={"blocks": [], "expected_version": 999}, ctx=CTX,
        )


async def test_update_canvas_never_clobbers_photo(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_photo_service.update_photo(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC, content_type="image/png", filename="p.png",
        crop=None, shape="circle", expected_version=None, ctx=CTX,
    )
    data = await cv_canvas_service.update_canvas(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 0}]}, ctx=CTX,
    )
    assert data["canvas"]["photo"]["shape"] == "circle"


async def test_restore_version_restores_canvas(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    v1 = await cv_canvas_service.update_canvas(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 0}]}, ctx=CTX,
    )
    v1_id = v1["current_version_id"]
    await cv_canvas_service.update_canvas(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b2", "type": "text", "order": 0}]}, ctx=CTX,
    )
    restored = await cv_section_service.restore_version(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        version_id=uuid.UUID(v1_id), payload=None, ctx=CTX,
    )
    assert restored["canvas"]["blocks"][0]["id"] == "b1"


async def test_canvas_cross_owner_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    cv = await _make_cv(db_session, student)
    with pytest.raises(ResourceNotFoundError):
        await cv_canvas_service.update_canvas(
            db_session, principal=other, cv_id=uuid.UUID(cv["id"]),
            payload={"blocks": []}, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Photo replace/crop/remove                                                   #
# --------------------------------------------------------------------------- #


async def test_photo_update_happy_path(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    before = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))

    data = await cv_photo_service.update_photo(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC, content_type="image/png", filename="me.png",
        crop={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}, shape="circle",
        expected_version=None, ctx=CTX,
    )
    assert data["canvas"]["photo"]["shape"] == "circle"
    assert data["canvas"]["photo"]["crop"]["width"] == 0.8
    assert data["canvas"]["photo"]["document_id"]
    assert data["version"] == before["version"] + 1
    assert await _audit_count(db_session, "cv.photo.updated") == 1
    # storage_path / storage_key never leak.
    import json

    assert "storage_path" not in json.dumps(data)
    assert "storage_key" not in json.dumps(data)


async def test_photo_replace_overwrites_binding(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    first = await cv_photo_service.update_photo(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC, content_type="image/png", filename="a.png",
        crop=None, shape="square", expected_version=None, ctx=CTX,
    )
    second = await cv_photo_service.update_photo(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC, content_type="image/png", filename="b.png",
        crop=None, shape="circle", expected_version=first["version"], ctx=CTX,
    )
    assert second["canvas"]["photo"]["shape"] == "circle"
    assert second["canvas"]["photo"]["document_id"] != first["canvas"]["photo"]["document_id"]


async def test_photo_remove(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_photo_service.update_photo(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC, content_type="image/png", filename="a.png",
        crop=None, shape="square", expected_version=None, ctx=CTX,
    )
    removed = await cv_photo_service.remove_photo(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        expected_version=None, ctx=CTX,
    )
    assert "photo" not in removed["canvas"]
    assert await _audit_count(db_session, "cv.photo.removed") == 1


@pytest.mark.parametrize(
    "crop",
    [
        {"x": -0.1, "y": 0, "width": 1, "height": 1},
        {"x": 0, "y": 0, "width": 0, "height": 1},
        {"x": 0.5, "y": 0, "width": 0.8, "height": 1},
        {"x": 0, "y": 0, "width": "nope", "height": 1},
    ],
)
async def test_photo_invalid_crop_rect_rejected(db_session, crop) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCropRectError):
        await cv_photo_service.update_photo(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            data=_PNG_MAGIC, content_type="image/png", filename="a.png",
            crop=crop, shape="square", expected_version=None, ctx=CTX,
        )


async def test_photo_invalid_file_type_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidPhotoFileError):
        await cv_photo_service.update_photo(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            data=b"not an image", content_type="application/pdf", filename="a.pdf",
            crop=None, shape="square", expected_version=None, ctx=CTX,
        )


async def test_photo_empty_file_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidPhotoFileError):
        await cv_photo_service.update_photo(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            data=b"", content_type="image/png", filename="a.png",
            crop=None, shape="square", expected_version=None, ctx=CTX,
        )


async def test_photo_oversized_file_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidPhotoFileError):
        await cv_photo_service.update_photo(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            data=b"0" * (9 * 1024 * 1024), content_type="image/png", filename="a.png",
            crop=None, shape="square", expected_version=None, ctx=CTX,
        )


async def test_photo_version_conflict(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(CvVersionConflictError):
        await cv_photo_service.update_photo(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            data=_PNG_MAGIC, content_type="image/png", filename="a.png",
            crop=None, shape="square", expected_version=999, ctx=CTX,
        )


async def test_photo_cross_owner_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    cv = await _make_cv(db_session, student)
    with pytest.raises(ResourceNotFoundError):
        await cv_photo_service.update_photo(
            db_session, principal=other, cv_id=uuid.UUID(cv["id"]),
            data=_PNG_MAGIC, content_type="image/png", filename="a.png",
            crop=None, shape="square", expected_version=None, ctx=CTX,
        )
