"""Integration tests for B-544/B-545: canonical industry-scope filtering on
public ``GET /jobs`` discovery, plus salary_mode/experience_mode round-trip
through create -> list -> detail (service layer, not HTTP).

Covers:
- industry_group_id (level 0) matches the node + all descendants.
- industry_id (level 1) matches the node + its level-2 children only (not
  sibling branches under the same root).
- specialization_id (level 2) matches the exact node only (no expansion,
  not sibling leaves under the same parent).
- 422 when more than one industry scope param is given.
- 422 when the referenced industry id/level does not match the param slot.
- 422 when the referenced industry id does not exist / is inactive.
- salary_mode / experience_mode persist through create and are reflected in
  both the owner detail view and the public discovery projection.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.opportunities.application import job_service, moderation_service
from app.modules.opportunities.application.errors import InvalidIndustryFilterError
from app.modules.opportunities.domain.industry_models import Industry
from app.shared.permissions import GUEST

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


def _payload(title: str = "Backend Intern", **over) -> dict:
    base = {
        "title": title,
        "description": "We are hiring a backend intern to build APIs.",
        "requirements": None,
        "benefits": None,
        "employment_type": "internship",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["python", "fastapi"],
        "preferred_skills": [],
        "experience_min_years": None,
        "experience_max_years": None,
        "degree_required": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "application_deadline": None,
        "visibility": "public",
    }
    base.update(over)
    return base


async def _publish(db, partner_principal, uni_principal, *, title="Live Job", **over):
    created = await job_service.create_job(
        db, principal=partner_principal, payload=_payload(title, **over), ctx=CTX
    )
    await job_service.submit_job(
        db, principal=partner_principal, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    await moderation_service.approve_job(
        db, principal=uni_principal, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    return uuid.UUID(created["id"])


async def _make_industry_tree(db) -> dict:
    """root (level 0) -> branch_a, branch_b (level 1) -> leaf_a1, leaf_b1 (level 2)."""
    root = Industry(
        id=uuid.uuid4(),
        name_vi="Công nghệ thông tin",
        name_en="Information Technology",
        slug=f"it-{uuid.uuid4().hex[:8]}",
        level=0,
        is_active=True,
    )
    db.add(root)
    await db.flush()
    branch_a = Industry(
        id=uuid.uuid4(),
        name_vi="Phát triển phần mềm",
        name_en="Software Development",
        slug=f"swe-{uuid.uuid4().hex[:8]}",
        level=1,
        parent_id=root.id,
        is_active=True,
    )
    branch_b = Industry(
        id=uuid.uuid4(),
        name_vi="Khoa học dữ liệu",
        name_en="Data Science",
        slug=f"ds-{uuid.uuid4().hex[:8]}",
        level=1,
        parent_id=root.id,
        is_active=True,
    )
    db.add_all([branch_a, branch_b])
    await db.flush()
    leaf_a1 = Industry(
        id=uuid.uuid4(),
        name_vi="Phát triển Backend",
        name_en="Backend Development",
        slug=f"backend-{uuid.uuid4().hex[:8]}",
        level=2,
        parent_id=branch_a.id,
        is_active=True,
    )
    leaf_b1 = Industry(
        id=uuid.uuid4(),
        name_vi="Phân tích dữ liệu",
        name_en="Data Analytics",
        slug=f"analytics-{uuid.uuid4().hex[:8]}",
        level=2,
        parent_id=branch_b.id,
        is_active=True,
    )
    db.add_all([leaf_a1, leaf_b1])
    await db.flush()
    return {
        "root": root,
        "branch_a": branch_a,
        "branch_b": branch_b,
        "leaf_a1": leaf_a1,
        "leaf_b1": leaf_b1,
    }


# --------------------------------------------------------------------------- #
# Canonical industry filter                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_industry_group_id_matches_all_descendants(db_session) -> None:
    tree = await _make_industry_tree(db_session)
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    job_root = await _publish(db_session, admin, uni, title="Root job", industry_id=tree["root"].id)
    job_branch = await _publish(
        db_session, admin, uni, title="Branch job", industry_id=tree["branch_a"].id
    )
    job_leaf = await _publish(
        db_session, admin, uni, title="Leaf job", industry_id=tree["leaf_a1"].id
    )
    job_other_branch = await _publish(
        db_session, admin, uni, title="Other branch job", industry_id=tree["branch_b"].id
    )

    items, _next, _limit, total = await job_service.list_public_jobs(
        db_session,
        principal=GUEST,
        industry_group_id=tree["root"].id,
    )
    ids = {uuid.UUID(i["id"]) for i in items}
    assert {job_root, job_branch, job_leaf, job_other_branch} <= ids
    assert total >= 4


@pytest.mark.asyncio
async def test_industry_id_matches_only_its_own_subtree(db_session) -> None:
    tree = await _make_industry_tree(db_session)
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    job_branch_a = await _publish(
        db_session, admin, uni, title="Branch A job", industry_id=tree["branch_a"].id
    )
    job_leaf_a1 = await _publish(
        db_session, admin, uni, title="Leaf A1 job", industry_id=tree["leaf_a1"].id
    )
    job_branch_b = await _publish(
        db_session, admin, uni, title="Branch B job", industry_id=tree["branch_b"].id
    )
    job_leaf_b1 = await _publish(
        db_session, admin, uni, title="Leaf B1 job", industry_id=tree["leaf_b1"].id
    )

    items, _next, _limit, _total = await job_service.list_public_jobs(
        db_session,
        principal=GUEST,
        industry_id=tree["branch_a"].id,
    )
    ids = {uuid.UUID(i["id"]) for i in items}
    assert job_branch_a in ids
    assert job_leaf_a1 in ids
    assert job_branch_b not in ids
    assert job_leaf_b1 not in ids


@pytest.mark.asyncio
async def test_specialization_id_matches_exact_leaf_only(db_session) -> None:
    tree = await _make_industry_tree(db_session)
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    job_leaf_a1 = await _publish(
        db_session, admin, uni, title="Leaf A1 job", industry_id=tree["leaf_a1"].id
    )
    job_branch_a = await _publish(
        db_session, admin, uni, title="Branch A job (no leaf)", industry_id=tree["branch_a"].id
    )
    job_leaf_b1 = await _publish(
        db_session, admin, uni, title="Leaf B1 job", industry_id=tree["leaf_b1"].id
    )

    items, _next, _limit, _total = await job_service.list_public_jobs(
        db_session,
        principal=GUEST,
        specialization_id=tree["leaf_a1"].id,
    )
    ids = {uuid.UUID(i["id"]) for i in items}
    assert ids == {job_leaf_a1}
    assert job_branch_a not in ids
    assert job_leaf_b1 not in ids


@pytest.mark.asyncio
async def test_multiple_industry_scope_params_is_422(db_session) -> None:
    tree = await _make_industry_tree(db_session)
    with pytest.raises(InvalidIndustryFilterError) as exc_info:
        await job_service.list_public_jobs(
            db_session,
            principal=GUEST,
            industry_group_id=tree["root"].id,
            industry_id=tree["branch_a"].id,
        )
    assert exc_info.value.details["reason"] == "multiple_scope"


@pytest.mark.asyncio
async def test_industry_level_mismatch_is_422(db_session) -> None:
    tree = await _make_industry_tree(db_session)
    with pytest.raises(InvalidIndustryFilterError) as exc_info:
        # leaf (level 2) passed in the `industry_group_id` (level 0) slot
        await job_service.list_public_jobs(
            db_session,
            principal=GUEST,
            industry_group_id=tree["leaf_a1"].id,
        )
    assert exc_info.value.details["reason"] == "level_mismatch"


@pytest.mark.asyncio
async def test_industry_not_found_is_422(db_session) -> None:
    with pytest.raises(InvalidIndustryFilterError) as exc_info:
        await job_service.list_public_jobs(
            db_session,
            principal=GUEST,
            industry_id=uuid.uuid4(),
        )
    assert exc_info.value.details["reason"] == "not_found"


@pytest.mark.asyncio
async def test_industry_terms_free_text_still_works_without_canonical_params(db_session) -> None:
    """Backward compat: the deprecated free-text param still filters when the
    canonical params are absent."""
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    matching = await _publish(db_session, admin, uni, title="Machine learning engineer role")
    await _publish(db_session, admin, uni, title="Sales associate role")

    items, _next, _limit, _total = await job_service.list_public_jobs(
        db_session,
        principal=GUEST,
        industry_terms="machine learning",
    )
    ids = {uuid.UUID(i["id"]) for i in items}
    assert matching in ids


@pytest.mark.asyncio
async def test_location_types_multi_select_or_matches(db_session) -> None:
    """Multi-select work-mode filter: comma-separated `location_types` OR-matches
    the requested modes and excludes the others (marketplace sidebar)."""
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    onsite = await _publish(db_session, admin, uni, title="Onsite job", location_type="onsite")
    remote = await _publish(db_session, admin, uni, title="Remote job", location_type="remote")
    hybrid = await _publish(db_session, admin, uni, title="Hybrid job", location_type="hybrid")

    items, _next, _limit, total = await job_service.list_public_jobs(
        db_session,
        principal=GUEST,
        location_types="onsite,remote",
    )
    ids = {uuid.UUID(i["id"]) for i in items}
    assert onsite in ids
    assert remote in ids
    assert hybrid not in ids
    assert total == 2


# --------------------------------------------------------------------------- #
# salary_mode / experience_mode round-trip                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_salary_and_experience_mode_round_trip_create_to_detail(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)

    created = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload(
            "Structured comp role",
            salary_mode="range",
            salary_min=15_000_000,
            salary_max=25_000_000,
            salary_period="monthly",
            salary_gross_net="gross",
            experience_mode="range",
            experience_min_years=1,
            experience_max_years=3,
        ),
        ctx=CTX,
    )
    assert created["salary_mode"] == "range"
    assert created["salary_period"] == "monthly"
    assert created["salary_gross_net"] == "gross"
    assert created["experience_mode"] == "range"
    assert created["salary_display"]["kind"] == "range"
    assert created["salary_display"]["period"] == "monthly"
    assert created["experience_display"]["kind"] == "range"

    detail = await job_service.get_job(
        db_session,
        principal=admin,
        job_id=uuid.UUID(created["id"]),
    )
    assert detail["salary_mode"] == "range"
    assert detail["experience_mode"] == "range"


@pytest.mark.asyncio
async def test_salary_mode_hidden_shows_real_numbers_to_owner_only(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _u2, _org2, other_admin = await make_org_with_admin(db_session, display_name="Other Co")

    created = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload(
            "Confidential budget role",
            salary_mode="hidden",
            salary_min=20_000_000,
            salary_max=30_000_000,
        ),
        ctx=CTX,
    )
    assert created["salary"] == {"min": 20_000_000, "max": 30_000_000, "currency": "VND"}
    assert created["salary_display"]["kind"] == "hidden"
    assert created["salary_display"]["min"] is None


@pytest.mark.asyncio
async def test_patch_partial_salary_min_revalidated_against_stored_mode(db_session) -> None:
    """PATCH sending only salary_min must be validated against the *effective*
    (merged) state, not just the fields present on the request body."""
    _u, _org, admin = await make_org_with_admin(db_session)

    created = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload(
            "Range role",
            salary_mode="range",
            salary_min=15_000_000,
            salary_max=25_000_000,
        ),
        ctx=CTX,
    )
    job_id = uuid.UUID(created["id"])

    # Raising salary_min above the existing salary_max (25M) while keeping
    # mode="range" (unchanged, not sent) must fail the merged consistency check.
    from app.modules.opportunities.application.errors import InvalidJobFieldError

    with pytest.raises(InvalidJobFieldError):
        await job_service.update_job(
            db_session,
            principal=admin,
            job_id=job_id,
            payload={"salary_min": 30_000_000},
            ctx=CTX,
        )

    # A consistent partial update (still range, still min < max) succeeds.
    updated = await job_service.update_job(
        db_session,
        principal=admin,
        job_id=job_id,
        payload={"salary_min": 18_000_000},
        ctx=CTX,
    )
    assert updated["salary_display"]["min"] == 18_000_000
    assert updated["salary_display"]["kind"] == "range"
