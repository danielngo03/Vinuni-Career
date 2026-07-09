"""Identity-only student-profile service tests.

Owner decision (2026-07-06): the student profile is identity-only. It carries
name/email (from the account), phone/location, privacy gates, an avatar, and the
single ``is_open_to_work`` career signal — all career content lives in the
student's CVs. These tests cover: lazy own-profile read + slim update, the
``is_open_to_work`` toggle, avatar upload/serve/remove, invalid-visibility
rejection, optimistic version conflict, privacy enforcement on the
partner/community ``{id}`` read (public projection gates contact + omits the
identity's raw email/phone unless allowed; vinuni_only hidden from external
partner; private -> 404), the application-context interface seam, and audit on
writes.
"""

from __future__ import annotations

import pytest
from app.modules.documents.infrastructure import storage as storage_backend
from app.modules.student_profiles.application import avatar_service, profile_service
from app.modules.student_profiles.application.errors import (
    InvalidProfileFieldError,
    ProfileVersionConflictError,
)
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.student_profile_utils import get_profile_id

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
# Own profile read/update (identity-only)                                     #
# --------------------------------------------------------------------------- #


async def test_get_my_profile_lazy_creates_empty(db_session) -> None:
    _su, student = await make_student(db_session)
    me = await profile_service.get_my_profile(db_session, principal=student)
    assert me["profile_visibility"] == "vinuni_only"
    assert me["profile_visibility_label"]  # localized, never raw-only
    assert me["is_open_to_work"] is False
    # Identity-only: no career fields, no completion metric.
    assert "profile_completion" not in me
    assert "headline" not in me
    assert "education" not in me and "skills" not in me


async def test_update_identity_fields(db_session) -> None:
    _su, student = await make_student(db_session)
    out = await profile_service.update_my_profile(
        db_session,
        principal=student,
        payload={
            "phone": "+84900000000",
            "location_city": "Hanoi",
            "location_country": "Vietnam",
        },
        ctx=CTX,
    )
    assert out["phone"] == "+84900000000"
    assert out["location_city"] == "Hanoi"


async def test_is_open_to_work_toggle(db_session) -> None:
    _su, student = await make_student(db_session)
    me = await profile_service.get_my_profile(db_session, principal=student)
    assert me["is_open_to_work"] is False

    out = await profile_service.update_my_profile(
        db_session, principal=student, payload={"is_open_to_work": True}, ctx=CTX
    )
    assert out["is_open_to_work"] is True

    out2 = await profile_service.update_my_profile(
        db_session, principal=student, payload={"is_open_to_work": False}, ctx=CTX
    )
    assert out2["is_open_to_work"] is False


async def test_update_audited(db_session) -> None:
    _su, student = await make_student(db_session)
    await profile_service.update_my_profile(
        db_session, principal=student, payload={"phone": "+84911111111"}, ctx=CTX
    )
    assert await _audit_count(db_session, "student_profile.updated") == 1


async def test_update_invalid_visibility_rejected(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(InvalidProfileFieldError):
        await profile_service.update_my_profile(
            db_session,
            principal=student,
            payload={"profile_visibility": "everyone"},
            ctx=CTX,
        )


async def test_update_invalid_contact_gate_rejected(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(InvalidProfileFieldError):
        await profile_service.update_my_profile(
            db_session,
            principal=student,
            payload={"show_email": "sometimes"},
            ctx=CTX,
        )


async def test_update_optimistic_version_conflict(db_session) -> None:
    _su, student = await make_student(db_session)
    me = await profile_service.get_my_profile(db_session, principal=student)
    # Stale expected_version -> conflict.
    with pytest.raises(ProfileVersionConflictError):
        await profile_service.update_my_profile(
            db_session,
            principal=student,
            payload={"phone": "+84900000000", "expected_version": me["version"] + 5},
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Privacy / partner-visibility on the {id} read                                #
# --------------------------------------------------------------------------- #


async def _setup_student(db_session, *, prefix: str, visibility: str, **profile):
    _su, student = await make_student(db_session, prefix=prefix)
    await profile_service.update_my_profile(
        db_session,
        principal=student,
        payload={
            "location_city": "Hanoi",
            "profile_visibility": visibility,
            "is_open_to_work": True,
            **profile,
        },
        ctx=CTX,
    )
    pid = await get_profile_id(db_session, principal=student)
    return student, pid


async def test_public_profile_partner_view_hides_contact(db_session) -> None:
    _student, pid = await _setup_student(
        db_session, prefix="pub", visibility="public", show_email="hidden"
    )
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Partner Co")

    view = await profile_service.get_profile_for_viewer(
        db_session, principal=partner, profile_id=pid
    )
    assert "email" not in view  # show_email=hidden -> never exposed
    assert "phone" not in view
    # An external partner gets the blind-screening mask on this passive path — the
    # candidate stays anonymous (UV- handle) until the recruitment reveal flow.
    assert view["identity_masked"] is True
    assert view["location_city"] == "Hanoi"
    assert view["is_open_to_work"] is True


async def test_public_profile_exposes_email_when_public(db_session) -> None:
    _su, student = await make_student(db_session, prefix="pubmail")
    await profile_service.update_my_profile(
        db_session,
        principal=student,
        payload={"profile_visibility": "public", "show_email": "public"},
        ctx=CTX,
    )
    pid = await get_profile_id(db_session, principal=student)
    # A VinUni community viewer (a fellow student) is NOT blind-screened, so the
    # student's public-gated email is exposed to them. External PARTNERS are masked
    # on this passive path and never receive contact (blind-screening) — covered by
    # tests/integration/test_talent_pool_detail_masking.py.
    _vu, viewer = await make_student(db_session, prefix="pubmail_viewer")
    view = await profile_service.get_profile_for_viewer(
        db_session, principal=viewer, profile_id=pid
    )
    assert view["identity_masked"] is False
    assert view["email"] == _su.email


async def test_private_profile_returns_404_to_partner(db_session) -> None:
    _student, pid = await _setup_student(db_session, prefix="priv", visibility="private")
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="P3")
    with pytest.raises(ResourceNotFoundError):
        await profile_service.get_profile_for_viewer(db_session, principal=partner, profile_id=pid)


async def test_vinuni_only_hidden_from_external_partner_but_visible_to_student(
    db_session,
) -> None:
    _student, pid = await _setup_student(db_session, prefix="vin", visibility="vinuni_only")
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="P4")
    # External partner cannot see a vinuni_only profile -> 404.
    with pytest.raises(ResourceNotFoundError):
        await profile_service.get_profile_for_viewer(db_session, principal=partner, profile_id=pid)
    # A fellow VinUni student can see the public projection.
    _vu, viewer_student = await make_student(db_session, prefix="viewer")
    view = await profile_service.get_profile_for_viewer(
        db_session, principal=viewer_student, profile_id=pid
    )
    assert view["location_city"] == "Hanoi"
    assert view["is_open_to_work"] is True


async def test_owner_sees_own_full_profile_via_id_route(db_session) -> None:
    _su, student = await make_student(db_session, prefix="owner")
    await profile_service.update_my_profile(
        db_session, principal=student, payload={"phone": "+84900000000"}, ctx=CTX
    )
    pid = await get_profile_id(db_session, principal=student)
    view = await profile_service.get_profile_for_viewer(
        db_session, principal=student, profile_id=pid
    )
    # Owner gets the full view: raw phone + email present.
    assert view["phone"] == "+84900000000"
    assert view["email"] == _su.email


# --------------------------------------------------------------------------- #
# Application-context interface seam                                           #
# --------------------------------------------------------------------------- #


async def test_application_context_reveals_invited_contact_only_when_accepted(
    db_session,
) -> None:
    su, student = await make_student(db_session, prefix="appctx")
    await profile_service.update_my_profile(
        db_session,
        principal=student,
        payload={"show_email": "invited", "phone": "+84900000000", "show_phone": "invited"},
        ctx=CTX,
    )
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="P5")

    not_revealed = await profile_service.get_profile_for_application_context(
        db_session,
        viewer_principal=partner,
        applicant_user_id=su.id,
        reveal_accepted=False,
    )
    assert not_revealed is not None
    assert "email" not in not_revealed and "phone" not in not_revealed

    revealed = await profile_service.get_profile_for_application_context(
        db_session,
        viewer_principal=partner,
        applicant_user_id=su.id,
        reveal_accepted=True,
    )
    assert revealed is not None
    assert revealed["email"] == su.email
    assert revealed["phone"] == "+84900000000"


async def test_application_context_none_without_profile(db_session) -> None:
    su, _student = await make_student(db_session, prefix="noprof")
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="P6")
    # No profile materialized yet -> the seam returns None (never fabricates one).
    result = await profile_service.get_profile_for_application_context(
        db_session,
        viewer_principal=partner,
        applicant_user_id=su.id,
        reveal_accepted=True,
    )
    assert result is None


# --------------------------------------------------------------------------- #
# Avatar upload / remove / serve                                                #
# --------------------------------------------------------------------------- #


async def test_avatar_upload_stores_url_and_audits(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu1")
    result = await avatar_service.upload_avatar(
        db_session,
        principal=student,
        filename="photo.png",
        data=PNG_BYTES,
        content_type="image/png",
        ctx=CTX,
    )
    assert result["avatar_url"] is not None
    assert "avatar" in result["avatar_url"]
    count = await _audit_count(db_session, "student_profile.avatar_updated")
    assert count == 1


async def test_avatar_upload_replaces_old_file(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu2")
    await avatar_service.upload_avatar(
        db_session,
        principal=student,
        filename="a.png",
        data=PNG_BYTES,
        content_type="image/png",
        ctx=CTX,
    )
    await avatar_service.upload_avatar(
        db_session,
        principal=student,
        filename="b.jpg",
        data=JPEG_BYTES,
        content_type="image/jpeg",
        ctx=CTX,
    )
    # Only one avatar per student; storage holds exactly one active key.
    assert len(memory_storage._data) == 1


async def test_avatar_upload_rejects_non_image(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu3")
    with pytest.raises(ValidationFailedError):
        await avatar_service.upload_avatar(
            db_session,
            principal=student,
            filename="resume.txt",
            data=NOT_AN_IMAGE,
            content_type="text/plain",
            ctx=CTX,
        )


async def test_avatar_upload_rejects_empty_file(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu4")
    with pytest.raises(ValidationFailedError):
        await avatar_service.upload_avatar(
            db_session,
            principal=student,
            filename="empty.png",
            data=b"",
            content_type="image/png",
            ctx=CTX,
        )


async def test_avatar_remove_clears_and_audits(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu5")
    await avatar_service.upload_avatar(
        db_session,
        principal=student,
        filename="x.png",
        data=PNG_BYTES,
        content_type="image/png",
        ctx=CTX,
    )
    result = await avatar_service.remove_avatar(
        db_session,
        principal=student,
        ctx=CTX,
    )
    assert result["avatar_url"] is None
    assert not memory_storage._data  # storage cleared
    count = await _audit_count(db_session, "student_profile.avatar_removed")
    assert count == 1


async def test_avatar_remove_is_idempotent(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu6")
    # No avatar set — remove should not raise.
    result = await avatar_service.remove_avatar(
        db_session,
        principal=student,
        ctx=CTX,
    )
    assert result["avatar_url"] is None


async def test_avatar_serve_returns_bytes(db_session, memory_storage) -> None:
    _su, student = await make_student(db_session, prefix="avu7")
    await avatar_service.upload_avatar(
        db_session,
        principal=student,
        filename="x.png",
        data=PNG_BYTES,
        content_type="image/png",
        ctx=CTX,
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
        db_session,
        principal=student,
        filename="photo.png",
        data=PNG_BYTES,
        content_type="image/png",
        ctx=CTX,
    )
    me2 = await profile_service.get_my_profile(db_session, principal=student)
    assert me2["avatar_url"] is not None


# --------------------------------------------------------------------------- #
# Talent pool search (identity-only: open-to-work + visibility)               #
# --------------------------------------------------------------------------- #


async def test_talent_search_returns_open_to_work_students(db_session) -> None:
    from app.modules.student_profiles.application import talent_pool_service

    _su, student = await make_student(db_session, prefix="talent1")
    await profile_service.update_my_profile(
        db_session,
        principal=student,
        payload={"profile_visibility": "public", "is_open_to_work": True, "location_city": "Hanoi"},
        ctx=CTX,
    )
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co")

    result = await talent_pool_service.search_talent_pool(
        db_session, principal=partner, keyword=None, cursor=None, limit=20
    )
    items = result["items"]
    assert any(i["is_open_to_work"] for i in items)
    card = items[0]
    # Identity-only card: no career fields, no completion.
    assert "profile_id" in card and "display_name" in card
    assert "headline" not in card and "major" not in card
    assert "profile_completion" not in card


async def test_talent_search_excludes_not_open_to_work(db_session) -> None:
    from app.modules.student_profiles.application import talent_pool_service

    _su, student = await make_student(db_session, prefix="talent2")
    await profile_service.update_my_profile(
        db_session,
        principal=student,
        payload={"profile_visibility": "public", "is_open_to_work": False},
        ctx=CTX,
    )
    pid = str(await get_profile_id(db_session, principal=student))
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter2")

    result = await talent_pool_service.search_talent_pool(
        db_session, principal=partner, keyword=None, cursor=None, limit=20
    )
    assert all(i["profile_id"] != pid for i in result["items"])


async def test_talent_search_requires_partner_or_staff(db_session) -> None:
    from app.modules.student_profiles.application import talent_pool_service
    from app.shared.exceptions import PermissionDeniedError

    _su, student = await make_student(db_session, prefix="talent3")
    with pytest.raises(PermissionDeniedError):
        await talent_pool_service.search_talent_pool(
            db_session, principal=student, keyword=None, cursor=None, limit=20
        )
