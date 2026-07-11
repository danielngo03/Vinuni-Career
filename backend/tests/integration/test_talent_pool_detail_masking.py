"""Talent-pool PROFILE-DETAIL identity is no longer masked.

The anonymous-apply + identity-reveal handshake (and the blind-screening mask it
gated) was removed (owner decision 2026-07-10). A passive candidate that a viewer
is ALLOWED to see (by ``is_open_to_work`` + ``profile_visibility``) is shown with
their real name + avatar on both the LIST and the DETAIL read. Contact fields still
follow the per-field ``expose_email`` / ``expose_phone`` gate.
"""

from __future__ import annotations

import uuid

from app.modules.student_profiles.application import profile_service, talent_pool_service

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin


async def _public_open_student(db, *, prefix: str):
    su, student = await make_student(db, prefix=prefix)
    await profile_service.update_my_profile(
        db,
        principal=student,
        payload={
            "profile_visibility": "public",
            "is_open_to_work": True,
            "location_city": "Hanoi",
        },
        ctx=CTX,
    )
    return su, student


async def _profile_id(db, *, student) -> uuid.UUID:
    prof = await profile_service.get_my_profile(db, principal=student)
    return uuid.UUID(prof["id"])


async def _detail(db, *, principal, profile_id):
    return await profile_service.get_profile_for_viewer(
        db, principal=principal, profile_id=profile_id
    )


async def test_external_partner_detail_is_identified(db_session) -> None:
    su, student = await _public_open_student(db_session, prefix="detail_ident")
    pid = await _profile_id(db_session, student=student)
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co")

    detail = await _detail(db_session, principal=partner, profile_id=pid)

    # Real identity is shown — no mask, no UV-xxxx handle, no anonymous_id.
    assert detail["display_name"] == su.full_name
    assert "identity_masked" not in detail
    assert "anonymous_id" not in detail
    assert detail["user_id"] == str(student.user_id)
    assert detail["is_open_to_work"] is True
    assert detail["location_city"] == "Hanoi"


async def test_list_card_is_identified(db_session) -> None:
    su, student = await _public_open_student(db_session, prefix="list_ident")
    pid = await _profile_id(db_session, student=student)
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co 2")

    listing = await talent_pool_service.search_talent_pool(
        db_session, principal=partner, keyword=None, cursor=None, limit=20
    )
    card = next(c for c in listing["items"] if c["profile_id"] == str(pid))
    assert card["display_name"] == su.full_name
    assert "identity_masked" not in card
    assert "anonymous_id" not in card


async def test_vinuni_student_detail_is_identified(db_session) -> None:
    su, owner = await _public_open_student(db_session, prefix="detail_owner")
    pid = await _profile_id(db_session, student=owner)
    _vsu, viewer = await make_student(db_session, prefix="detail_viewer")

    detail = await _detail(db_session, principal=viewer, profile_id=pid)
    assert detail["display_name"] == su.full_name
    assert "user_id" in detail
