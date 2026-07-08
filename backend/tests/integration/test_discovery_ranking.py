"""Recommendation/ranking layer tests (Discovery/Ads rescue — slice 2).

Service- + HTTP-level coverage of the honesty + source-separation contract:

- recommendations carry ``reason_codes`` + ``score`` + ``source``;
- a no-signal "recommended" list honestly falls back to ``source=recent``/``popular``
  (never a silent mislabel);
- sponsored fills a defined slot but does NOT reorder/override organic ordering
  (organic subsequence preserved + sponsored separately tagged + disclosed);
- a guest uses ``discovery_session`` coarse tags for reason codes;
- eligibility reuses the SAME visibility predicate as ``GET /jobs`` (no hidden /
  expired / unmoderated leak);
- diversity (no same-company back-to-back when avoidable);
- similar-jobs deterministic + eligibility-filtered + 404 on a hidden seed;
- overview rails are populated from real data + hide-if-empty;
- admin discovery health: privacy-safe aggregates + RBAC gate;
- no provider/model/confidence leak; recommendations are public/optional-auth with
  no cross-student leak.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.main import app
from app.modules.advertising.domain.models import SponsoredPlacement
from app.modules.dashboards.application import student_dashboard
from app.modules.discovery.application import health_service, ranking_service
from app.modules.discovery.domain import ranking
from app.modules.documents.domain.models import CvSection
from app.modules.marketplace.application import overview_service
from app.modules.opportunities.application import job_service, moderation_service
from app.modules.opportunities.domain.models import Job
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import GUEST, Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import make_builder_cv, publish_job

_FORBIDDEN = [
    "openrouter", "openai", "anthropic", "claude", "gpt-4", "gemini", "deepseek",
    "chat_cheap", "reasoning_cheap", "model_alias", "prompt_tokens",
    "completion_tokens", "storage_path", "storage_key", "confidence", "embedding",
]


def _assert_no_leak(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term}"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


async def _university(db):
    _u, _org, uni = await make_org_with_admin(db, org_type="university")
    return uni


async def _partner(db, name: str):
    _u, _org, partner = await make_org_with_admin(db, display_name=name)
    return partner


async def _backdate(db, job_id: uuid.UUID, *, days: int) -> None:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.published_at = datetime.now(tz=UTC) - timedelta(days=days)
    db.add(job)
    await db.commit()


async def _set_deadline(db, job_id: uuid.UUID, *, days: int) -> None:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.application_deadline = datetime.now(tz=UTC) + timedelta(days=days)
    db.add(job)
    await db.commit()


async def _seed_cv_skills(db, cv_id: str, text: str) -> None:
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    target = next(s for s in sections if s.section_type == "skills")
    target.content_json = {"items": [{"text": text}]}
    await db.commit()


async def _seed_active_sponsored(db, *, partner, target_id: uuid.UUID) -> uuid.UUID:
    now = datetime.now(tz=UTC)
    placement = SponsoredPlacement(
        org_id=partner.org_id,
        created_by=partner.user_id,
        target_type="job",
        target_id=target_id,
        placement_type="sponsored",
        package_id=uuid.uuid4(),  # FK not enforced on the SQLite test path
        price_amount="3000000.00",
        currency="VND",
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=13),
        status="active",
        disclosure_confirmed=True,
        paid_at=now,
        activated_at=now,
    )
    db.add(placement)
    await db.commit()
    await db.refresh(placement)
    return placement.id


# --------------------------------------------------------------------------- #
# reason_codes + score + source                                               #
# --------------------------------------------------------------------------- #


async def test_authenticated_recommendations_carry_reason_score_source(db_session) -> None:
    partner = await _partner(db_session, "Acme Co")
    uni = await _university(db_session)
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Python Backend Intern", required_skills=["python", "fastapi"],
    )
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    await _seed_cv_skills(db_session, sel["cv_profile_id"], "Python, FastAPI, SQL")

    out = await ranking_service.recommend_jobs(
        db_session, principal=student, q="python", limit=10
    )
    assert out["source"] == ranking.SOURCE_RECOMMENDED
    assert out["personalized"] is True
    assert len(out["items"]) == 1
    item = out["items"][0]
    assert isinstance(item["score"], int) and 0 <= item["score"] <= 100
    assert item["source"] == ranking.SOURCE_RECOMMENDED
    codes = {r["code"] for r in item["reason_codes"]}
    assert ranking.REASON_MATCHES_SEARCH in codes
    # A student with a CV gets a best-CV recommendation for the job.
    assert item["recommended_cv_id"] == sel["cv_profile_id"]
    assert item["sponsored_disclosure"] is None
    _assert_no_leak(out)


async def test_no_signal_list_falls_back_to_recent_not_mislabeled(db_session) -> None:
    partner = await _partner(db_session, "Acme Co")
    uni = await _university(db_session)
    await publish_job(db_session, partner_principal=partner, uni_principal=uni, title="Role")

    # Guest, no session tags, no query -> NO signal -> honest fallback.
    out = await ranking_service.recommend_jobs(db_session, principal=GUEST)
    assert out["source"] in {ranking.SOURCE_RECENT, ranking.SOURCE_POPULAR}
    assert out["personalized"] is False
    assert out["items"], "should still surface honest recent/popular inventory"
    for item in out["items"]:
        assert item["source"] in {ranking.SOURCE_RECENT, ranking.SOURCE_POPULAR}
        codes = {r["code"] for r in item["reason_codes"]}
        # Never a personalization claim on a no-signal list.
        assert ranking.REASON_MATCHES_SEARCH not in codes
        assert ranking.REASON_CV_FIT not in codes
        assert codes <= {ranking.REASON_RECENT, ranking.REASON_POPULAR}


# --------------------------------------------------------------------------- #
# Sponsored slot separation (the load-bearing honesty rule)                   #
# --------------------------------------------------------------------------- #


async def test_sponsored_fills_slot_without_reordering_organic(db_session) -> None:
    uni = await _university(db_session)
    # Three organic jobs from DISTINCT companies, backdated for a deterministic
    # recency order A(newest) -> B -> C.
    pa = await _partner(db_session, "Org A")
    pb = await _partner(db_session, "Org B")
    pc = await _partner(db_session, "Org C")
    a = await publish_job(db_session, partner_principal=pa, uni_principal=uni, title="Job A")
    b = await publish_job(db_session, partner_principal=pb, uni_principal=uni, title="Job B")
    c = await publish_job(db_session, partner_principal=pc, uni_principal=uni, title="Job C")
    await _backdate(db_session, a, days=0)
    await _backdate(db_session, b, days=1)
    await _backdate(db_session, c, days=2)

    # A separate sponsored job from a 4th company, live now.
    pd = await _partner(db_session, "Org D")
    d = await publish_job(db_session, partner_principal=pd, uni_principal=uni, title="Sponsored D")
    placement_id = await _seed_active_sponsored(db_session, partner=pd, target_id=d)

    out = await ranking_service.recommend_jobs(db_session, principal=GUEST, limit=10)
    items = out["items"]

    # Organic subsequence keeps EXACT recency order A, B, C (never reordered).
    organic = [it for it in items if it["source"] != ranking.SOURCE_SPONSORED]
    assert [it["id"] for it in organic] == [str(a), str(b), str(c)]

    # The sponsored item occupies a defined slot, is tagged + disclosed, and the
    # sponsored job does NOT also appear in the organic stream.
    sponsored = [it for it in items if it["source"] == ranking.SOURCE_SPONSORED]
    assert len(sponsored) == 1
    sp = sponsored[0]
    assert sp["id"] == str(d)
    assert sp["sponsored_disclosure"] is not None
    assert sp["sponsored_disclosure"]["is_sponsored"] is True
    assert sp["sponsored_disclosure"]["label"]  # non-empty localized label
    assert sp["placement_id"] == str(placement_id)
    assert str(d) not in [it["id"] for it in organic]
    # The sponsored item is placed at the defined top slot (position 0).
    assert items[0]["source"] == ranking.SOURCE_SPONSORED


async def test_sponsored_target_hidden_is_dropped_no_leak(db_session) -> None:
    uni = await _university(db_session)
    pd = await _partner(db_session, "Org D")
    # A placement that is "active" but its target job was never published (draft).
    created = await job_service.create_job(
        db_session, principal=pd, payload={
            "title": "Hidden Sponsored", "description": "x", "employment_type": "internship",
            "location_type": "onsite", "location_city": "Hanoi", "location_country": "Vietnam",
            "required_skills": [], "preferred_skills": [], "salary_currency": "VND",
            "salary_is_disclosed": False, "headcount": 1, "visibility": "public",
        }, ctx=CTX,
    )
    await _seed_active_sponsored(
        db_session, partner=pd, target_id=uuid.UUID(created["id"])
    )
    # Plus one real organic job so the list is non-empty.
    pa = await _partner(db_session, "Org A")
    await publish_job(db_session, partner_principal=pa, uni_principal=uni, title="Real Job")

    out = await ranking_service.recommend_jobs(db_session, principal=GUEST, limit=10)
    ids = {it["id"] for it in out["items"]}
    assert created["id"] not in ids  # hidden sponsored target never leaks
    assert all(it["source"] != ranking.SOURCE_SPONSORED for it in out["items"])


# --------------------------------------------------------------------------- #
# Guest session-signal reasons                                                #
# --------------------------------------------------------------------------- #


async def test_guest_session_search_term_drives_reason(db_session) -> None:
    partner = await _partner(db_session, "Acme Co")
    uni = await _university(db_session)
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Data Analyst Intern", required_skills=["sql", "excel"],
    )
    # Guest with a recorded search term (from the discovery_session coarse tags).
    out = await ranking_service.recommend_jobs(
        db_session, principal=GUEST, cookie_tags={"search_terms": ["data analyst"]}
    )
    assert out["source"] == ranking.SOURCE_RECOMMENDED
    assert out["personalized"] is True
    codes = {r["code"] for it in out["items"] for r in it["reason_codes"]}
    assert ranking.REASON_MATCHES_SEARCH in codes


# --------------------------------------------------------------------------- #
# Eligibility = the SAME predicate as /jobs                                   #
# --------------------------------------------------------------------------- #


async def test_eligibility_excludes_hidden_and_expired(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    visible = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Visible"
    )
    # A draft (never approved) job -> not publicly visible.
    await job_service.create_job(
        db_session, principal=partner, payload={
            "title": "Draft", "description": "x", "employment_type": "internship",
            "location_type": "onsite", "location_city": "Hanoi", "location_country": "Vietnam",
            "required_skills": [], "preferred_skills": [], "salary_currency": "VND",
            "salary_is_disclosed": False, "headcount": 1, "visibility": "public",
        }, ctx=CTX,
    )
    # An expired (past-deadline) published job -> excluded by the predicate.
    expired = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Expired"
    )
    await _set_deadline(db_session, expired, days=-1)

    out = await ranking_service.recommend_jobs(db_session, principal=GUEST, limit=20)
    ids = {it["id"] for it in out["items"]}
    assert ids == {str(visible)}

    # Cross-check: identical to the public /jobs visible set.
    public, _c, _l, total = await job_service.list_public_jobs(db_session, principal=GUEST)
    assert {j["id"] for j in public} == ids and total == 1


# --------------------------------------------------------------------------- #
# Diversity                                                                   #
# --------------------------------------------------------------------------- #


async def test_diversity_avoids_same_company_back_to_back(db_session) -> None:
    uni = await _university(db_session)
    org_a = await _partner(db_session, "Org A")
    org_b = await _partner(db_session, "Org B")
    a1 = await publish_job(
        db_session, partner_principal=org_a, uni_principal=uni,
        title="Python One", required_skills=["python"],
    )
    a2 = await publish_job(
        db_session, partner_principal=org_a, uni_principal=uni,
        title="Python Two", required_skills=["python"],
    )
    b1 = await publish_job(
        db_session, partner_principal=org_b, uni_principal=uni,
        title="Python Three", required_skills=["python"],
    )
    await _backdate(db_session, a1, days=0)
    await _backdate(db_session, a2, days=1)
    await _backdate(db_session, b1, days=2)

    # A query signal makes this a real recommended list (score-sorted -> A1,A2,B1),
    # then diversity breaks the A,A adjacency.
    out = await ranking_service.recommend_jobs(db_session, principal=GUEST, q="python")
    orgs = [it["org_id"] for it in out["items"]]
    assert len(out["items"]) == 3
    assert all(orgs[i] != orgs[i + 1] for i in range(len(orgs) - 1)), orgs
    assert {it["id"] for it in out["items"]} == {str(a1), str(a2), str(b1)}


# --------------------------------------------------------------------------- #
# Similar jobs                                                                #
# --------------------------------------------------------------------------- #


async def test_similar_jobs_deterministic_and_eligible(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    seed = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Backend Engineer", required_skills=["python", "fastapi"],
    )
    similar = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Backend Developer", required_skills=["python", "django"],
    )
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Marketing Intern", required_skills=["seo"],
    )

    out1 = await ranking_service.similar_jobs(db_session, principal=GUEST, job_id=seed)
    out2 = await ranking_service.similar_jobs(db_session, principal=GUEST, job_id=seed)
    ids = [it["id"] for it in out1["items"]]
    assert str(similar) in ids
    assert str(seed) not in ids  # the seed never recommends itself
    # Deterministic order.
    assert ids == [it["id"] for it in out2["items"]]
    # The similar item carries a genuine overlap reason.
    sim = next(it for it in out1["items"] if it["id"] == str(similar))
    codes = {r["code"] for r in sim["reason_codes"]}
    assert ranking.REASON_SKILL_MATCH in codes or ranking.REASON_SIMILAR_ROLE in codes
    assert sim["source"] == ranking.SOURCE_RECOMMENDED
    _assert_no_leak(out1)


async def test_similar_jobs_404_on_hidden_seed(db_session) -> None:
    partner = await _partner(db_session, "Acme Co")
    draft = await job_service.create_job(
        db_session, principal=partner, payload={
            "title": "Draft", "description": "x", "employment_type": "internship",
            "location_type": "onsite", "location_city": "Hanoi", "location_country": "Vietnam",
            "required_skills": [], "preferred_skills": [], "salary_currency": "VND",
            "salary_is_disclosed": False, "headcount": 1, "visibility": "public",
        }, ctx=CTX,
    )
    with pytest.raises(ResourceNotFoundError):
        await ranking_service.similar_jobs(
            db_session, principal=GUEST, job_id=uuid.UUID(draft["id"])
        )


# --------------------------------------------------------------------------- #
# Overview rails (real data + hide-if-empty)                                  #
# --------------------------------------------------------------------------- #


async def test_overview_rails_populated_and_hide_if_empty(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Software Engineer", required_skills=["python"],
    )
    sponsored_job = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Sponsored Eng"
    )
    placement_id = await _seed_active_sponsored(
        db_session, partner=partner, target_id=sponsored_job
    )

    data = await overview_service.get_overview(db_session)
    # Recommended rail is present + honestly labelled.
    assert data["recommended_jobs"]["items"]
    assert data["recommended_jobs"]["source"] in {"recent", "popular", "recommended"}
    # Hero campaign from a REAL active placement, with disclosure.
    assert data["hero_campaign"] is not None
    assert data["hero_campaign"]["placement_id"] == str(placement_id)
    assert data["hero_campaign"]["sponsored_disclosure"]["is_sponsored"] is True
    # Popular roles is a real aggregate (software_engineering family present).
    families = {r["role_family"] for r in data["popular_roles"]}
    assert "software_engineering" in families
    # Trust modules are static + metric-free.
    assert all(set(m.keys()) == {"key"} for m in data["trust_modules"])
    _assert_no_leak(data)


# --------------------------------------------------------------------------- #
# Student dashboard source fix                                                #
# --------------------------------------------------------------------------- #


async def test_student_dashboard_recommended_carries_source_fallback(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(db_session, partner_principal=partner, uni_principal=uni, title="Role")
    _su, student = await make_student(db_session)  # NO CV, NO preferences

    data = await student_dashboard.get_student_dashboard(db_session, principal=student)
    reco = data["recommended_jobs"]
    assert isinstance(reco, dict)
    # No CV / preferences -> honest recent/popular fallback, never "recommended".
    assert reco["source"] in {"recent", "popular"}
    assert reco["personalized"] is False
    for item in reco["items"]:
        assert item["source"] in {"recent", "popular"}


# --------------------------------------------------------------------------- #
# Admin discovery health: privacy-safe aggregates + RBAC                      #
# --------------------------------------------------------------------------- #


async def test_admin_health_aggregates_and_privacy(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    sponsored_job = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Eng"
    )
    await _seed_active_sponsored(db_session, partner=partner, target_id=sponsored_job)

    data = await health_service.get_discovery_health(db_session, principal=uni)
    assert set(data.keys()) == {
        "rails", "empty_rails", "sponsored", "events", "policy_flags"
    }
    assert data["sponsored"]["active_count"] >= 1
    assert data["rails"]["recommended_jobs_available"] >= 1
    # Privacy: only aggregate counts — no user id / email / session id anywhere.
    blob = json.dumps(data).lower()
    assert str(uni.user_id) not in blob
    assert "email" not in blob and "user_id" not in blob and "session_id" not in blob
    _assert_no_leak(data)


async def test_admin_health_rbac_blocks_student(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await health_service.get_discovery_health(db_session, principal=student)


async def test_admin_health_rbac_blocks_partner(db_session) -> None:
    partner = await _partner(db_session, "Acme Co")
    with pytest.raises(PermissionDeniedError):
        await health_service.get_discovery_health(db_session, principal=partner)


# --------------------------------------------------------------------------- #
# HTTP contract (routes mounted; static-path precedence; optional auth)        #
# --------------------------------------------------------------------------- #


async def test_http_recommendations_and_similar_routes(client, db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Backend Engineer", required_skills=["python", "fastapi"],
    )

    # /jobs/recommendations is matched as a STATIC path (never captured by
    # /jobs/{job_id} -> would be a 422 UUID error).
    reco = await client.get("/jobs/recommendations")
    assert reco.status_code == 200
    body = reco.json()["data"]
    assert {"source", "personalized", "items"} <= set(body.keys())

    similar = await client.get(f"/jobs/{job_id}/similar")
    assert similar.status_code == 200
    assert "items" in similar.json()["data"]

    # The normal job-detail route still resolves (not shadowed).
    detail = await client.get(f"/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["title"] == "Backend Engineer"


async def test_http_admin_health_requires_auth(client) -> None:
    resp = await client.get("/admin/discovery/health")
    assert resp.status_code in (401, 403)
