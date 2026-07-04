"""Student-profile service tests.

Covers: lazy own-profile read + update, deterministic completion %, education /
experience / skills / links CRUD owner-only (cross-owner 404), skill uniqueness,
optimistic version conflict, privacy enforcement on the partner/community view
(public projection hides completion + gates contact; vinuni_only hidden from
external partner; private -> 404), the application-context interface seam, the
profile_import CV wiring, and audit on writes.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import cv_service
from app.modules.documents.infrastructure import storage as storage_backend
from app.modules.student_profiles.application import (
    avatar_service,
    profile_service,
    section_service,
)
from app.modules.student_profiles.application.errors import (
    DuplicateSkillError,
    InvalidProfileFieldError,
    ProfileVersionConflictError,
)
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.student_profile_utils import (
    add_education,
    add_experience,
    add_link,
    add_skill,
    get_profile_id,
)

# Minimal valid image bytes.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
NOT_AN_IMAGE = b"this is not an image"


class _MemoryStorage:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> None:
        self._data[key] = data

    def load(self, key: str) -> bytes:
        try:
            return self._data[key]
        except KeyError as exc:
            raise storage_backend.StorageError("object not found") from exc

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


@pytest.fixture
def memory_storage():
    backend = _MemoryStorage()
    storage_backend.set_storage(backend)
    yield backend
    storage_backend.set_storage(None)


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Own profile read/update + completion                                        #
# --------------------------------------------------------------------------- #


async def test_get_my_profile_lazy_creates_empty(db_session) -> None:
    _su, student = await make_student(db_session)
    me = await profile_service.get_my_profile(db_session, principal=student)
    assert me["profile_completion"] == 0
    assert me["profile_visibility"] == "vinuni_only"
    assert me["profile_visibility_label"]  # localized, never raw-only
    assert me["education"] == [] and me["skills"] == []


async def test_completion_rises_with_filled_sections(db_session) -> None:
    _su, student = await make_student(db_session)

    # headline + summary -> 15 + 15 = 30
    out = await profile_service.update_my_profile(
        db_session,
        principal=student,
        payload={"headline": "AI Engineer @ VinUni", "summary": "Builder of things."},
        ctx=CTX,
    )
    assert out["profile_completion"] == 30

    await add_education(db_session, principal=student)  # +20 -> 50
    await add_skill(db_session, principal=student, name="Python")  # <3 skills, no bump
    me = await profile_service.get_my_profile(db_session, principal=student)
    assert me["profile_completion"] == 50

    await add_skill(db_session, principal=student, name="FastAPI")
    await add_skill(db_session, principal=student, name="SQLAlchemy")  # 3 skills -> +15 = 65
    await add_link(db_session, principal=student)  # +10 -> 75
    await add_experience(db_session, principal=student)  # +15 -> 90
    me2 = await profile_service.update_my_profile(
        db_session,
        principal=student,
        payload={"is_open_to_work": True, "open_to_work_types": ["internship"]},
        ctx=CTX,
    )
    assert me2["profile_completion"] == 100


async def test_update_audited(db_session) -> None:
    _su, student = await make_student(db_session)
    await profile_service.update_my_profile(
        db_session, principal=student, payload={"headline": "Hi"}, ctx=CTX
    )
    assert await _audit_count(db_session, "student_profile.updated") == 1


async def test_update_invalid_visibility_rejected(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(InvalidProfileFieldError):
        await profile_service.update_my_profile(
            db_session, principal=student,
            payload={"profile_visibility": "everyone"}, ctx=CTX,
        )


async def test_update_optimistic_version_conflict(db_session) -> None:
    _su, student = await make_student(db_session)
    me = await profile_service.get_my_profile(db_session, principal=student)
    # Stale expected_version -> conflict.
    with pytest.raises(ProfileVersionConflictError):
        await profile_service.update_my_profile(
            db_session, principal=student,
            payload={"headline": "X", "expected_version": me["version"] + 5}, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Child CRUD + ownership                                                       #
# --------------------------------------------------------------------------- #


async def test_education_crud_and_audit(db_session) -> None:
    _su, student = await make_student(db_session)
    created = await add_education(db_session, principal=student)
    assert created["institution"] == "VinUniversity"
    assert created["sort_order"] == 10

    updated = await section_service.update_item(
        db_session, kind="education", principal=student,
        child_id=uuid.UUID(created["id"]),
        payload={"degree": "BSc CS (Honours)", "expected_version": created["version"]},
        ctx=CTX,
    )
    assert updated["degree"] == "BSc CS (Honours)"
    assert updated["version"] == created["version"] + 1

    items = await section_service.list_items(
        db_session, kind="education", principal=student
    )
    assert len(items) == 1

    deleted = await section_service.delete_item(
        db_session, kind="education", principal=student,
        child_id=uuid.UUID(created["id"]), ctx=CTX,
    )
    assert deleted["deleted"] is True
    after = await section_service.list_items(
        db_session, kind="education", principal=student
    )
    assert after == []
    assert await _audit_count(db_session, "student_education.created") == 1
    assert await _audit_count(db_session, "student_education.deleted") == 1


async def test_duplicate_skill_rejected(db_session) -> None:
    _su, student = await make_student(db_session)
    await add_skill(db_session, principal=student, name="Python")
    with pytest.raises(DuplicateSkillError):
        await add_skill(db_session, principal=student, name="python")  # case-insensitive


async def test_cross_owner_child_update_and_delete_404(db_session) -> None:
    _sa, student_a = await make_student(db_session, prefix="a")
    _sb, student_b = await make_student(db_session, prefix="b")
    edu = await add_education(db_session, principal=student_a)

    # Student B cannot update or delete student A's education item -> 404.
    with pytest.raises(ResourceNotFoundError):
        await section_service.update_item(
            db_session, kind="education", principal=student_b,
            child_id=uuid.UUID(edu["id"]), payload={"degree": "hijack"}, ctx=CTX,
        )
    with pytest.raises(ResourceNotFoundError):
        await section_service.delete_item(
            db_session, kind="education", principal=student_b,
            child_id=uuid.UUID(edu["id"]), ctx=CTX,
        )


async def test_invalid_link_rejected(db_session) -> None:
    _su, student = await make_student(db_session)
    from app.shared.exceptions import ValidationFailedError

    with pytest.raises(ValidationFailedError):
        await section_service.create_item(
            db_session, kind="link", principal=student,
            payload={"url": "ftp://nope"}, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Privacy / partner-visibility on the {id} read                                #
# --------------------------------------------------------------------------- #


async def _setup_filled_student(db_session, *, prefix: str, visibility: str, **profile):
    _su, student = await make_student(db_session, prefix=prefix)
    await profile_service.update_my_profile(
        db_session, principal=student,
        payload={"headline": "Headline", "summary": "Summary",
                 "profile_visibility": visibility, **profile},
        ctx=CTX,
    )
    await add_education(db_session, principal=student)
    await add_skill(db_session, principal=student, name="Python")
    pid = await get_profile_id(db_session, principal=student)
    return student, pid


async def test_public_profile_partner_view_hides_completion_and_contact(db_session) -> None:
    student, pid = await _setup_filled_student(
        db_session, prefix="pub", visibility="public", show_email="hidden"
    )
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Partner Co")

    view = await profile_service.get_profile_for_viewer(
        db_session, principal=partner, profile_id=pid
    )
    assert "profile_completion" not in view  # owner-only metric
    assert "email" not in view  # show_email=hidden -> never exposed
    assert "phone" not in view
    assert view["headline"] == "Headline"
    assert view["skills"][0]["name"] == "Python"
    # Public education projection drops private GPA + notes.
    assert "gpa" not in view["education"][0]


async def test_public_profile_exposes_email_when_public(db_session) -> None:
    _su, student = await make_student(db_session, prefix="pubmail")
    await profile_service.update_my_profile(
        db_session, principal=student,
        payload={"profile_visibility": "public", "show_email": "public"}, ctx=CTX,
    )
    pid = await get_profile_id(db_session, principal=student)
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="P2")
    view = await profile_service.get_profile_for_viewer(
        db_session, principal=partner, profile_id=pid
    )
    assert view["email"] == _su.email


async def test_private_profile_returns_404_to_partner(db_session) -> None:
    _student, pid = await _setup_filled_student(
        db_session, prefix="priv", visibility="private"
    )
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="P3")
    with pytest.raises(ResourceNotFoundError):
        await profile_service.get_profile_for_viewer(
            db_session, principal=partner, profile_id=pid
        )


async def test_vinuni_only_hidden_from_external_partner_but_visible_to_student(
    db_session,
) -> None:
    _student, pid = await _setup_filled_student(
        db_session, prefix="vin", visibility="vinuni_only"
    )
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="P4")
    # External partner cannot see a vinuni_only profile -> 404.
    with pytest.raises(ResourceNotFoundError):
        await profile_service.get_profile_for_viewer(
            db_session, principal=partner, profile_id=pid
        )
    # A fellow VinUni student can see the public projection.
    _vu, viewer_student = await make_student(db_session, prefix="viewer")
    view = await profile_service.get_profile_for_viewer(
        db_session, principal=viewer_student, profile_id=pid
    )
    assert view["headline"] == "Headline"
    assert "profile_completion" not in view


async def test_owner_sees_own_full_profile_via_id_route(db_session) -> None:
    _su, student = await make_student(db_session, prefix="owner")
    await profile_service.update_my_profile(
        db_session, principal=student, payload={"headline": "H"}, ctx=CTX
    )
    pid = await get_profile_id(db_session, principal=student)
    view = await profile_service.get_profile_for_viewer(
        db_session, principal=student, profile_id=pid
    )
    assert "profile_completion" in view  # owner gets the full view


# --------------------------------------------------------------------------- #
# Application-context interface seam                                           #
# --------------------------------------------------------------------------- #


async def test_application_context_reveals_invited_contact_only_when_accepted(
    db_session,
) -> None:
    su, student = await make_student(db_session, prefix="appctx")
    await profile_service.update_my_profile(
        db_session, principal=student,
        payload={"show_email": "invited", "phone": "+84900000000",
                 "show_phone": "invited"},
        ctx=CTX,
    )
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="P5")

    not_revealed = await profile_service.get_profile_for_application_context(
        db_session, viewer_principal=partner, applicant_user_id=su.id,
        reveal_accepted=False,
    )
    assert not_revealed is not None
    assert "email" not in not_revealed and "phone" not in not_revealed

    revealed = await profile_service.get_profile_for_application_context(
        db_session, viewer_principal=partner, applicant_user_id=su.id,
        reveal_accepted=True,
    )
    assert revealed is not None
    assert revealed["email"] == su.email
    assert revealed["phone"] == "+84900000000"


# --------------------------------------------------------------------------- #
# profile_import CV wiring                                                     #
# --------------------------------------------------------------------------- #


async def test_profile_import_pulls_real_structured_data(db_session) -> None:
    _su, student = await make_student(db_session, prefix="import")
    await profile_service.update_my_profile(
        db_session, principal=student,
        payload={"headline": "AI Engineer", "summary": "Loves backends."}, ctx=CTX,
    )
    await add_education(db_session, principal=student, institution="VinUniversity")
    await add_experience(db_session, principal=student, company="Example Tech")
    await add_skill(db_session, principal=student, name="Python")

    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"creation_mode": "profile_import", "title": "My CV"}, ctx=CTX,
    )
    sections = {s["section_type"]: s for s in cv["sections"]}

    edu_items = sections["education"]["content"]["items"]
    assert edu_items and edu_items[0]["institution"] == "VinUniversity"
    exp_items = sections["experience"]["content"]["items"]
    assert exp_items and exp_items[0]["company_name"] == "Example Tech"
    skill_items = sections["skills"]["content"]["items"]
    assert any(s["name"] == "Python" for s in skill_items)
    summary_items = sections["summary"]["content"]["items"]
    assert any("AI Engineer" in i["text"] for i in summary_items)


async def test_profile_import_falls_back_without_profile(db_session) -> None:
    su, student = await make_student(db_session, prefix="noprofile")
    cv = await cv_service.create_cv(
        db_session, principal=student,
        payload={"creation_mode": "profile_import", "title": "Fallback CV"}, ctx=CTX,
    )
    sections = {s["section_type"]: s for s in cv["sections"]}
    summary_items = sections["summary"]["content"]["items"]
    # Falls back to the user's name/email seed.
    assert any(su.email in i["text"] for i in summary_items)


# --------------------------------------------------------------------------- #
# Avatar upload / remove / serve                                                #
# --------------------------------------------------------------------------- #


async def test_avatar_upload_stores_url_and_audits(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu1")
    result = await avatar_service.upload_avatar(
        db_session, principal=student,
        filename="photo.png", data=PNG_BYTES, content_type="image/png", ctx=CTX,
    )
    assert result["avatar_url"] is not None
    assert "avatar" in result["avatar_url"]
    # Audit logged.
    count = await _audit_count(db_session, "student_profile.avatar_updated")
    assert count == 1


async def test_avatar_upload_replaces_old_file(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu2")
    await avatar_service.upload_avatar(
        db_session, principal=student,
        filename="a.png", data=PNG_BYTES, content_type="image/png", ctx=CTX,
    )
    await avatar_service.upload_avatar(
        db_session, principal=student,
        filename="b.jpg", data=JPEG_BYTES, content_type="image/jpeg", ctx=CTX,
    )
    # Only one avatar per student; storage holds exactly one active key.
    assert len(memory_storage._data) == 1


async def test_avatar_upload_rejects_non_image(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu3")
    with pytest.raises(ValidationFailedError):
        await avatar_service.upload_avatar(
            db_session, principal=student,
            filename="resume.txt", data=NOT_AN_IMAGE, content_type="text/plain", ctx=CTX,
        )


async def test_avatar_upload_rejects_empty_file(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu4")
    with pytest.raises(ValidationFailedError):
        await avatar_service.upload_avatar(
            db_session, principal=student,
            filename="empty.png", data=b"", content_type="image/png", ctx=CTX,
        )


async def test_avatar_remove_clears_and_audits(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu5")
    await avatar_service.upload_avatar(
        db_session, principal=student,
        filename="x.png", data=PNG_BYTES, content_type="image/png", ctx=CTX,
    )
    result = await avatar_service.remove_avatar(
        db_session, principal=student, ctx=CTX,
    )
    assert result["avatar_url"] is None
    assert not memory_storage._data  # storage cleared
    count = await _audit_count(db_session, "student_profile.avatar_removed")
    assert count == 1


async def test_avatar_remove_is_idempotent(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu6")
    # No avatar set — remove should not raise.
    result = await avatar_service.remove_avatar(
        db_session, principal=student, ctx=CTX,
    )
    assert result["avatar_url"] is None


async def test_avatar_serve_returns_bytes(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu7")
    await avatar_service.upload_avatar(
        db_session, principal=student,
        filename="x.png", data=PNG_BYTES, content_type="image/png", ctx=CTX,
    )
    profile_id = await get_profile_id(db_session, principal=student)
    blob = await avatar_service.serve_avatar(db_session, profile_id=profile_id)
    assert blob.content == PNG_BYTES
    assert blob.media_type == "image/png"


async def test_avatar_serve_404_when_no_avatar(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu8")
    profile_id = await get_profile_id(db_session, principal=student)
    with pytest.raises(ResourceNotFoundError):
        await avatar_service.serve_avatar(db_session, profile_id=profile_id)


async def test_profile_response_includes_avatar_url(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu9")
    # Before upload: avatar_url is None.
    me = await profile_service.get_my_profile(db_session, principal=student)
    assert me["avatar_url"] is None
    # After upload: avatar_url is set.
    await avatar_service.upload_avatar(
        db_session, principal=student,
        filename="photo.png", data=PNG_BYTES, content_type="image/png", ctx=CTX,
    )
    me2 = await profile_service.get_my_profile(db_session, principal=student)
    assert me2["avatar_url"] is not None
