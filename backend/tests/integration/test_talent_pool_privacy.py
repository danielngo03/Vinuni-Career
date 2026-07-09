"""Passive talent-pool candidate-identity protection.

An external partner recruiter browsing the passive pool gets a BLIND-SCREENING
view: the candidate's real name and identifying photo are withheld and replaced by
an opaque ``UV-xxxx`` handle, so passive candidates stay anonymous until they
choose to engage. The student's own institution (university staff / superadmin)
keeps the identified view for the audience the student opted into.
"""

from __future__ import annotations

from app.modules.student_profiles.application import profile_service, talent_pool_service

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin


async def _open_to_work_student(db, *, prefix: str):
    _su, student = await make_student(db, prefix=prefix)
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
    return student


async def _search(db, *, principal):
    result = await talent_pool_service.search_talent_pool(
        db, principal=principal, keyword=None, cursor=None, limit=20
    )
    return result["items"]


async def test_external_partner_sees_masked_candidates(db_session) -> None:
    await _open_to_work_student(db_session, prefix="passive1")
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co")

    items = await _search(db_session, principal=partner)
    assert items
    card = items[0]
    assert card["identity_masked"] is True
    assert card["display_name"].startswith("UV-")
    assert card["display_name"] == card["anonymous_id"]
    assert card["avatar_url"] is None
    # Coarse fit signal is still available for screening.
    assert card["is_open_to_work"] is True
    assert "location_city" in card


async def test_masked_handle_is_stable(db_session) -> None:
    await _open_to_work_student(db_session, prefix="passive2")
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co 2")

    first = (await _search(db_session, principal=partner))[0]["display_name"]
    second = (await _search(db_session, principal=partner))[0]["display_name"]
    assert first == second and first.startswith("UV-")


async def test_university_staff_see_identified_candidates(db_session) -> None:
    student = await _open_to_work_student(db_session, prefix="passive3")
    _uu, _uorg, staff = await make_org_with_admin(db_session, org_type="university")

    items = await _search(db_session, principal=staff)
    assert items
    card = items[0]
    # Internal governance keeps the identified view (not the UV- handle).
    assert card["identity_masked"] is False
    assert not card["display_name"].startswith("UV-")
    assert student is not None
