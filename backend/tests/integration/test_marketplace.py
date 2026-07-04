"""Public career-marketplace backend tests (autopilot slice 1).

Covers the company directory, public company profile, public job search filters,
the embedded ``company`` block on public job rows, and the marketplace overview
aggregator — with an emphasis on RBAC/visibility leakage (only active partners,
never university/pending orgs or internal fields) and that sponsored/featured come
from the real flags.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.main import app
from app.modules.marketplace.application import overview_service
from app.modules.opportunities.application import job_service, moderation_service
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import company_directory_service
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import GUEST
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c

# Fields surfaced by directory_summary / company_block (the only allowed leak).
_DIRECTORY_FIELDS = {
    "id", "slug", "display_name", "logo_url", "industry", "company_size",
    "headquarters_city", "is_verified", "trust_level", "active_job_count",
    "rating",
}
# Internal org fields that must NEVER appear on a public projection.
_FORBIDDEN_ORG_FIELDS = {
    "status", "subscription_tier", "settings", "verified_by", "org_type",
    "logo_path", "version", "deleted_at",
}


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
        "screening_questions": [],
    }
    base.update(over)
    return base


async def _set_org_fields(db, org, **fields):
    for k, v in fields.items():
        setattr(org, k, v)
    db.add(org)
    await db.commit()


async def _publish(db, partner, uni, *, title="Live Job", **over) -> uuid.UUID:
    created = await job_service.create_job(
        db, principal=partner, payload=_payload(title, **over), ctx=CTX
    )
    await job_service.submit_job(
        db, principal=partner, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    await moderation_service.approve_job(
        db, principal=uni, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    return uuid.UUID(created["id"])


async def _flag(db, job_id: uuid.UUID, *, sponsored=False, featured=False):
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.is_sponsored = sponsored
    job.is_featured = featured
    db.add(job)
    await db.commit()


async def _set_published_at(db, job_id: uuid.UUID, day: _dt.date):
    """Backdate a job's ``published_at`` to noon UTC of ``day`` for trend fixtures."""
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.published_at = datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC)
    db.add(job)
    await db.commit()


# --------------------------------------------------------------------------- #
# Company directory list                                                      #
# --------------------------------------------------------------------------- #


async def test_directory_lists_only_active_partners(db_session) -> None:
    _u, partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    await _set_org_fields(db_session, partner, industry="technology")
    # A university org — must never appear in the public company directory.
    await make_org_with_admin(db_session, org_type="university", display_name="VinUni")
    # A pending partner — not yet active, must be hidden.
    _pu, pending, _pa = await make_org_with_admin(db_session, display_name="Pending Co")
    await _set_org_fields(db_session, pending, status="pending")

    items, next_cursor, limit, total = await company_directory_service.list_companies(
        db_session
    )
    slugs = {c["slug"] for c in items}
    assert partner.slug in slugs
    assert "vinuni" not in slugs and "pending-co" not in slugs
    assert total == 1 and next_cursor is None and limit > 0
    # No internal field leaks.
    for field in _FORBIDDEN_ORG_FIELDS:
        assert field not in items[0]
    assert set(items[0].keys()) == _DIRECTORY_FIELDS


async def test_directory_q_and_industry_filters(db_session) -> None:
    _u, acme, _a = await make_org_with_admin(db_session, display_name="Acme Robotics")
    await _set_org_fields(db_session, acme, industry="manufacturing")
    _u2, globex, _g = await make_org_with_admin(db_session, display_name="Globex Bank")
    await _set_org_fields(db_session, globex, industry="finance")

    by_name, _c, _l, total_name = await company_directory_service.list_companies(
        db_session, q="acme"
    )
    assert [c["slug"] for c in by_name] == [acme.slug] and total_name == 1

    # ``q`` also matches on industry text.
    by_ind_text, _c2, _l2, _t2 = await company_directory_service.list_companies(
        db_session, q="finance"
    )
    assert [c["slug"] for c in by_ind_text] == [globex.slug]

    # Exact industry filter.
    exact, _c3, _l3, total_ind = await company_directory_service.list_companies(
        db_session, industry="finance"
    )
    assert [c["slug"] for c in exact] == [globex.slug] and total_ind == 1


async def test_directory_active_job_count_is_visible_only(db_session) -> None:
    _u, partner, p_admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    # One published (visible) + one draft (not visible).
    await _publish(db_session, p_admin, uni, title="Visible Role")
    await job_service.create_job(
        db_session, principal=p_admin, payload=_payload("Draft Role"), ctx=CTX
    )

    items, _c, _l, _t = await company_directory_service.list_companies(db_session)
    assert items[0]["active_job_count"] == 1


async def test_directory_empty_state(db_session) -> None:
    items, next_cursor, _l, total = await company_directory_service.list_companies(
        db_session
    )
    assert items == [] and next_cursor is None and total == 0


# --------------------------------------------------------------------------- #
# Company detail                                                              #
# --------------------------------------------------------------------------- #


async def test_company_detail_includes_active_jobs(db_session) -> None:
    _u, partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    await _set_org_fields(
        db_session, partner, industry="technology", website_url="https://acme.test",
        description="We build robots.", founded_year=2010,
    )
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await _publish(db_session, p_admin, uni, title="Visible Role")

    data = await company_directory_service.get_company(db_session, slug=partner.slug)
    assert data["slug"] == partner.slug
    assert data["website_url"] == "https://acme.test"
    assert data["founded_year"] == 2010
    assert data["verified_at"] is not None  # make_org_with_admin verifies by default
    assert data["active_job_count"] == 1
    assert len(data["active_jobs"]) == 1
    job_row = data["active_jobs"][0]
    assert job_row["title"] == "Visible Role"
    # Embedded company block on each job row.
    assert job_row["company"]["slug"] == partner.slug
    # No internal org fields leak on the profile.
    for field in _FORBIDDEN_ORG_FIELDS:
        assert field not in data


async def test_company_detail_404_for_university_pending_and_missing(db_session) -> None:
    _uu, uni_org, _uni = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    _pu, pending, _pa = await make_org_with_admin(db_session, display_name="Pending Co")
    await _set_org_fields(db_session, pending, status="pending")

    with pytest.raises(ResourceNotFoundError):
        await company_directory_service.get_company(db_session, slug=uni_org.slug)
    with pytest.raises(ResourceNotFoundError):
        await company_directory_service.get_company(db_session, slug=pending.slug)
    with pytest.raises(ResourceNotFoundError):
        await company_directory_service.get_company(db_session, slug="does-not-exist")


# --------------------------------------------------------------------------- #
# Public job search filters + company block                                  #
# --------------------------------------------------------------------------- #


async def test_public_job_summary_includes_company_block(db_session) -> None:
    _u, partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await _publish(db_session, p_admin, uni, title="Backend Role")

    items, _c, _l, total = await job_service.list_public_jobs(db_session, principal=GUEST)
    assert total == 1
    block = items[0]["company"]
    assert block["slug"] == partner.slug
    assert block["display_name"] == "Acme Co"
    assert block["is_verified"] is True
    assert "logo_url" in block  # present (null until signed-asset endpoint exists)


async def test_public_job_search_filters(db_session) -> None:
    _u, _partner, p_admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await _publish(
        db_session, p_admin, uni, title="Senior Python Engineer",
        employment_type="full_time", location_type="remote",
        required_skills=["python", "fastapi"],
    )
    await _publish(
        db_session, p_admin, uni, title="Marketing Intern",
        employment_type="internship", location_type="onsite",
        required_skills=["seo", "content"],
    )

    # q on title.
    res, _c, _l, total = await job_service.list_public_jobs(
        db_session, principal=GUEST, q="python"
    )
    assert total == 1 and res[0]["title"] == "Senior Python Engineer"

    # q matches required_skills text only (title has no "seo").
    res_skill, _c2, _l2, total_skill = await job_service.list_public_jobs(
        db_session, principal=GUEST, q="seo"
    )
    assert total_skill == 1 and res_skill[0]["title"] == "Marketing Intern"

    # employment_type + location_type filters.
    res_et, _c3, _l3, total_et = await job_service.list_public_jobs(
        db_session, principal=GUEST, employment_type="internship"
    )
    assert total_et == 1 and res_et[0]["title"] == "Marketing Intern"
    res_lt, _c4, _l4, total_lt = await job_service.list_public_jobs(
        db_session, principal=GUEST, location_type="remote"
    )
    assert total_lt == 1 and res_lt[0]["title"] == "Senior Python Engineer"


async def test_owner_projection_has_no_company_block(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    created = await job_service.create_job(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    detail = await job_service.get_job(
        db_session, principal=admin, job_id=uuid.UUID(created["id"])
    )
    # Owner detail is unchanged: no embedded company block.
    assert "company" not in detail


# --------------------------------------------------------------------------- #
# Marketplace overview                                                        #
# --------------------------------------------------------------------------- #


async def test_marketplace_overview_uses_real_flags(db_session) -> None:
    _u, partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    sponsored_id = await _publish(db_session, p_admin, uni, title="Sponsored Role")
    featured_id = await _publish(db_session, p_admin, uni, title="Featured Role")
    await _publish(db_session, p_admin, uni, title="Plain Role")
    await _flag(db_session, sponsored_id, sponsored=True)
    await _flag(db_session, featured_id, featured=True)

    data = await overview_service.get_overview(db_session)

    assert {c["title"] for c in data["sponsored_jobs"]} == {"Sponsored Role"}
    assert {c["title"] for c in data["featured_jobs"]} == {"Featured Role"}
    assert len(data["recent_jobs"]) == 3
    assert data["recent_jobs"][0]["company"]["slug"] == partner.slug

    # Metrics shape.
    metrics = data["metrics"]
    assert metrics is not None
    assert metrics["active_jobs"] == 3
    assert metrics["companies"] == 1
    assert metrics["open_for_applications"] == 3

    # Spotlight companies are public directory summaries (no internal leak).
    assert data["spotlight_companies"][0]["slug"] == partner.slug
    for field in _FORBIDDEN_ORG_FIELDS:
        assert field not in data["spotlight_companies"][0]


async def test_marketplace_overview_no_fabricated_inventory(db_session) -> None:
    # No jobs at all -> sponsored/featured/recent empty, metrics all zero.
    data = await overview_service.get_overview(db_session)
    assert data["sponsored_jobs"] == []
    assert data["featured_jobs"] == []
    assert data["recent_jobs"] == []
    assert data["spotlight_companies"] == []
    assert data["metrics"] == {
        "active_jobs": 0, "companies": 0, "open_for_applications": 0
    }
    # Trend is real-but-empty: 30 zero buckets, zero new jobs, and a NULL delta
    # (no prior-period history -> never a fabricated 0% or +100%).
    trend = data["jobs_trend"]
    assert trend["new_jobs_30d"] == 0
    assert trend["delta_pct"] is None
    assert len(trend["series"]) == 30
    assert all(b["count"] == 0 for b in trend["series"])
    assert all(set(b.keys()) == {"date", "count"} for b in trend["series"])


async def test_marketplace_trend_series_reflects_published_days(db_session) -> None:
    # Seed jobs published on known UTC days, then assert the series buckets and
    # the new_jobs_30d count match exactly — never inflated.
    _u, _partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    today = datetime.now(tz=UTC).date()

    # 2 jobs published today, 1 published 5 days ago (all still active/visible).
    j_today_a = await _publish(db_session, p_admin, uni, title="Today A")
    j_today_b = await _publish(db_session, p_admin, uni, title="Today B")
    j_old = await _publish(db_session, p_admin, uni, title="Five Days Ago")
    await _set_published_at(db_session, j_old, today - timedelta(days=5))

    data = await overview_service.get_overview(db_session)
    trend = data["jobs_trend"]

    assert trend["new_jobs_30d"] == 3
    series = {b["date"]: b["count"] for b in trend["series"]}
    assert series[today.isoformat()] == 2
    assert series[(today - timedelta(days=5)).isoformat()] == 1
    # Every other in-window day is zero (no fabricated activity).
    assert sum(b["count"] for b in trend["series"]) == 3
    assert len(trend["series"]) == 30
    # The series matches the live active_jobs count for the same predicate.
    assert data["metrics"]["active_jobs"] == 3
    assert {j_today_a, j_today_b, j_old}  # ids used


async def test_marketplace_trend_delta_known_fixture(db_session) -> None:
    # Current 30-day window = 3 jobs; prior 30-day window = 2 jobs.
    # Honest delta = (3 - 2) / 2 * 100 = +50.0%.
    _u, _partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    today = datetime.now(tz=UTC).date()

    # Current window (last 30 days): 3 jobs.
    for n in range(3):
        jid = await _publish(db_session, p_admin, uni, title=f"Cur {n}")
        await _set_published_at(db_session, jid, today - timedelta(days=n))
    # Prior window (days 30..59 ago): 2 jobs.
    for n in (35, 50):
        jid = await _publish(db_session, p_admin, uni, title=f"Prior {n}")
        await _set_published_at(db_session, jid, today - timedelta(days=n))

    data = await overview_service.get_overview(db_session)
    trend = data["jobs_trend"]
    assert trend["new_jobs_30d"] == 3  # prior-window jobs excluded from the count
    assert trend["delta_pct"] == 50.0
    # Prior-window jobs are outside the 30-bucket sparkline.
    assert sum(b["count"] for b in trend["series"]) == 3


async def test_marketplace_trend_null_delta_on_insufficient_history(db_session) -> None:
    # Jobs only in the current window, none in the prior period -> delta is NULL,
    # not a fabricated +100%. The series still renders.
    _u, _partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    today = datetime.now(tz=UTC).date()
    for n in range(2):
        jid = await _publish(db_session, p_admin, uni, title=f"New {n}")
        await _set_published_at(db_session, jid, today - timedelta(days=n))

    trend = (await overview_service.get_overview(db_session))["jobs_trend"]
    assert trend["new_jobs_30d"] == 2
    assert trend["delta_pct"] is None
    assert sum(b["count"] for b in trend["series"]) == 2


async def test_marketplace_trend_null_on_failure_metrics_survive(
    db_session, monkeypatch
) -> None:
    # If the trend aggregate raises, jobs_trend is None (strip hides the sparkline)
    # but the other three metrics still resolve — no 500, no fabrication.
    async def _boom(*_a, **_k):
        raise RuntimeError("group-by failed")

    monkeypatch.setattr(
        "app.modules.opportunities.application.public_read.published_per_day", _boom
    )
    data = await overview_service.get_overview(db_session)
    assert data["jobs_trend"] is None
    assert data["metrics"] == {
        "active_jobs": 0, "companies": 0, "open_for_applications": 0
    }


# --------------------------------------------------------------------------- #
# HTTP contract (routes mounted, envelopes, status codes)                      #
# --------------------------------------------------------------------------- #


async def test_http_company_endpoints_contract(client, db_session) -> None:
    _u, partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    await _set_org_fields(db_session, partner, industry="technology")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    await _publish(db_session, p_admin, uni, title="Role A")

    listing = await client.get("/companies")
    assert listing.status_code == 200
    body = listing.json()
    assert {"next_cursor", "limit", "total"} <= set(body["page"].keys())
    assert body["data"][0]["slug"] == partner.slug

    detail = await client.get(f"/companies/{partner.slug}")
    assert detail.status_code == 200
    assert detail.json()["data"]["active_jobs"][0]["title"] == "Role A"

    missing = await client.get("/companies/no-such-company")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


async def test_http_marketplace_overview_contract(client, db_session) -> None:
    resp = await client.get("/marketplace/overview")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {
        "metrics", "jobs_trend", "sponsored_jobs", "featured_jobs", "recent_jobs",
        "spotlight_companies", "upcoming_events", "sponsored_events",
        "featured_events",
        # Spec §8 explicit recommendation/sponsored/curated rails.
        "hero_campaign", "recommended_jobs", "recommended_events",
        "sponsored_banner", "employer_spotlight", "popular_roles", "trust_modules",
    }
    # Empty marketplace: recommendation rails hide-if-empty, hero/banner null,
    # trust modules are static (no fabricated metrics).
    assert data["recommended_jobs"]["items"] == []
    assert data["recommended_jobs"]["source"] in {"recent", "popular"}
    assert data["hero_campaign"] is None and data["sponsored_banner"] is None
    assert data["popular_roles"] == []
    assert all("key" in m for m in data["trust_modules"])


async def test_marketplace_metrics_null_on_failure(db_session, monkeypatch) -> None:
    # If a metric query raises, the strip is hidden (metrics=None), never faked.
    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "app.modules.opportunities.application.public_read.count_visible_jobs", _boom
    )
    data = await overview_service.get_overview(db_session)
    assert data["metrics"] is None
    # The rest of the payload still resolves.
    assert data["sponsored_jobs"] == []
