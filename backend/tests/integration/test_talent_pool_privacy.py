"""Passive talent-pool candidate cards are identified (masking removed).

The blind-screening mask + ``UV-xxxx`` handle depended on the anonymous-apply +
identity-reveal handshake, which was removed (owner decision 2026-07-10). A passive
candidate a viewer is allowed to see (by ``is_open_to_work`` + ``profile_visibility``)
is shown with their real name; the card never carries CONTACT PII (email/phone).
"""

from __future__ import annotations

from app.modules.student_profiles.application import profile_service, talent_pool_service

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin


async def _open_to_work_student(db, *, prefix: str):
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


async def _search(db, *, principal):
    result = await talent_pool_service.search_talent_pool(
        db, principal=principal, keyword=None, cursor=None, limit=20
    )
    return result["items"]


async def test_external_partner_sees_identified_candidates(db_session) -> None:
    su, _student = await _open_to_work_student(db_session, prefix="passive1")
    _pu, _org, partner = await make_org_with_admin(db_session, display_name="Recruiter Co")

    items = await _search(db_session, principal=partner)
    assert items
    card = items[0]
    assert card["display_name"] == su.full_name
    assert "identity_masked" not in card
    assert "anonymous_id" not in card
    # No CONTACT PII on the list card.
    assert "email" not in card and "phone" not in card
    assert card["is_open_to_work"] is True
    assert "location_city" in card


async def test_university_staff_see_identified_candidates(db_session) -> None:
    su, _student = await _open_to_work_student(db_session, prefix="passive3")
    _uu, _uorg, staff = await make_org_with_admin(db_session, org_type="university")

    items = await _search(db_session, principal=staff)
    assert items
    card = items[0]
    assert card["display_name"] == su.full_name
    assert "identity_masked" not in card
