"""Superadmin platform analytics API tests — P6 (TDD).

Coverage:
1. Non-superadmin (student) -> 403 on /kpis, /funnel, /growth.
2. Seeded events + users -> /funnel returns correct stage counts and conversion
   rates; no actor_id / PII in response.
3. Seeded events + users -> /growth returns per-day series, gap-filled with
   correct per-day signups / applications / active_users.
4. /kpis returns correct persona + job + application + event totals.
5. Empty window (range_days=1, no events today) -> zeros, no crash.
6. Privacy assertion: no actor_id, email, user rows, or raw properties in any
   response.

Run:
    cd backend && uv run pytest tests/modules/platform_admin/test_analytics.py -q
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from app.main import app
from app.modules.analytics.domain.models import AnalyticsEvent
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.modules.opportunities.domain.event_models import Event
from app.modules.opportunities.domain.models import Job
from app.modules.organization.domain.models import Organization
from app.modules.recruitment.domain.models import Application
from app.modules.users.domain.models import Identity, User
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Principal helpers (mirrors test_audit_read.py pattern)
# ---------------------------------------------------------------------------


def _superadmin_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="superadmin",
        org_id=None,
        is_superadmin=True,
        permissions=frozenset(),
    )


def _student_principal() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="student",
        org_id=uuid.uuid4(),
        is_superadmin=False,
        permissions=frozenset(),
    )


def _make_auth(principal: Principal) -> CurrentAuth:
    claims = AccessClaims(
        user_id=principal.user_id or uuid.uuid4(),
        session_id=uuid.uuid4(),
        identity_id=uuid.uuid4(),
        persona=principal.persona,
        org_id=principal.org_id,
        jti=uuid.uuid4(),
        expires_at=datetime.now(tz=UTC) + timedelta(minutes=30),
    )
    ctx = RequestContext(ip="127.0.0.1", user_agent="test")
    return CurrentAuth(principal=principal, claims=claims, ctx=ctx)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def superadmin_client() -> AsyncIterator[AsyncClient]:
    auth = _make_auth(_superadmin_principal())
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


@pytest.fixture
async def student_client() -> AsyncIterator[AsyncClient]:
    auth = _make_auth(_student_principal())
    app.dependency_overrides[get_current_auth] = lambda: auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c
    app.dependency_overrides.pop(get_current_auth, None)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=UTC)
_YESTERDAY = _NOW - timedelta(days=1)
_TWO_DAYS_AGO = _NOW - timedelta(days=2)


def _analytics_event(
    *,
    event_type: str,
    actor_id: uuid.UUID | None = None,
    properties: dict | None = None,
    occurred_at: datetime | None = None,
) -> AnalyticsEvent:
    return AnalyticsEvent(
        event_type=event_type,
        aggregate_type="job" if event_type.startswith("job") else "application",
        aggregate_id=uuid.uuid4(),
        actor_id=actor_id,
        actor_type="student",
        session_id=uuid.uuid4(),
        properties=properties or {},
        occurred_at=occurred_at or _NOW,
    )


def _make_user(*, created_at: datetime | None = None) -> User:
    return User(
        email=f"{uuid.uuid4().hex[:8]}@test.local",
        password_hash="x",
        is_active=True,
        created_at=created_at or _NOW,
    )


def _make_identity(*, user: User, persona: str) -> Identity:
    return Identity(user_id=user.id, persona=persona, org_id=None)


def _make_org() -> Organization:
    return Organization(
        display_name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:6]}",
        org_type="partner",
    )


def _make_job(*, org_id: uuid.UUID) -> Job:
    # posted_by, description, employment_type, location_type are non-nullable
    return Job(
        org_id=org_id,
        posted_by=uuid.uuid4(),
        title="Test Job",
        slug=f"test-job-{uuid.uuid4().hex[:6]}",
        description="A test job",
        status="active",
        employment_type="full_time",
        location_type="remote",
    )


def _make_application(
    *, job_id: uuid.UUID, applicant_id: uuid.UUID, org_id: uuid.UUID
) -> Application:
    return Application(
        job_id=job_id,
        applicant_id=applicant_id,
        org_id=org_id,
        status="submitted",
    )


def _make_event(*, org_id: uuid.UUID) -> Event:
    # created_by, description, format are non-nullable
    return Event(
        org_id=org_id,
        created_by=uuid.uuid4(),
        title="Test Event",
        slug=f"test-event-{uuid.uuid4().hex[:6]}",
        description="A test event",
        event_type="workshop",
        format="online",
        status="published",
        starts_at=_NOW + timedelta(days=7),
        ends_at=_NOW + timedelta(days=8),
    )


# ---------------------------------------------------------------------------
# Test 1: Non-superadmin -> 403 on all three endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kpis_non_superadmin_gets_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/analytics/kpis")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_funnel_non_superadmin_gets_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/analytics/funnel")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_growth_non_superadmin_gets_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/analytics/growth")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Test 2: Funnel — correct stage counts + conversion rates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_funnel_stage_counts_and_conversions(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Seeded events produce correct funnel stage counts and conversion rates."""

    actor = uuid.uuid4()

    # 3 job views, 2 job applies, 2 applications submitted
    for _ in range(3):
        db_session.add(_analytics_event(event_type="job.viewed", actor_id=actor))
    for _ in range(2):
        db_session.add(_analytics_event(event_type="job.applied", actor_id=actor))
    for _ in range(2):
        db_session.add(_analytics_event(event_type="application.submitted", actor_id=actor))
    # 1 under_review, 1 interview via status_changed
    db_session.add(
        _analytics_event(
            event_type="application.status_changed",
            actor_id=actor,
            properties={"status": "under_review"},
        )
    )
    db_session.add(
        _analytics_event(
            event_type="application.status_changed",
            actor_id=actor,
            properties={"status": "interview"},
        )
    )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/analytics/funnel", params={"range_days": 7})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body["data"]

    assert data["range_days"] == 7
    stages = {s["stage"]: s for s in data["stages"]}

    assert stages["job_views"]["count"] == 3
    assert stages["job_applies"]["count"] == 2
    assert stages["applications_submitted"]["count"] == 2
    assert stages["under_review"]["count"] == 1
    assert stages["interview"]["count"] == 1
    assert stages["offer"]["count"] == 0
    assert stages["hired"]["count"] == 0
    assert stages["rejected"]["count"] == 0

    # First stage has no conversion_from_previous
    assert stages["job_views"]["conversion_from_previous"] is None

    # job_applies / job_views = 2/3
    assert abs(stages["job_applies"]["conversion_from_previous"] - round(2 / 3, 4)) < 1e-6

    # applications_submitted / job_applies = 2/2 = 1.0
    assert stages["applications_submitted"]["conversion_from_previous"] == 1.0

    # under_review / applications_submitted = 1/2 = 0.5
    assert stages["under_review"]["conversion_from_previous"] == 0.5

    # interview / under_review = 1/1 = 1.0
    assert stages["interview"]["conversion_from_previous"] == 1.0

    # offer / interview = 0/1 = 0.0
    assert stages["offer"]["conversion_from_previous"] == 0.0


# ---------------------------------------------------------------------------
# Test 3: Growth — per-day series, gap-filled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_growth_series_gap_filled(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Growth series is gap-filled; per-day counts are correct."""

    # Signup yesterday
    user_y = _make_user(created_at=_YESTERDAY)
    db_session.add(user_y)

    # Signup today
    user_t = _make_user(created_at=_NOW)
    db_session.add(user_t)

    await db_session.flush()

    actor_y = uuid.uuid4()
    actor_t = uuid.uuid4()

    # 1 application submitted yesterday, 2 today
    db_session.add(
        _analytics_event(
            event_type="application.submitted", actor_id=actor_y, occurred_at=_YESTERDAY
        )
    )
    db_session.add(
        _analytics_event(event_type="application.submitted", actor_id=actor_t, occurred_at=_NOW)
    )
    db_session.add(
        _analytics_event(event_type="application.submitted", actor_id=actor_t, occurred_at=_NOW)
    )

    # 2 distinct actors active yesterday, 1 today
    db_session.add(
        _analytics_event(event_type="job.viewed", actor_id=actor_y, occurred_at=_YESTERDAY)
    )
    db_session.add(
        _analytics_event(event_type="job.viewed", actor_id=uuid.uuid4(), occurred_at=_YESTERDAY)
    )
    db_session.add(_analytics_event(event_type="job.viewed", actor_id=actor_t, occurred_at=_NOW))

    await db_session.commit()

    resp = await superadmin_client.get("/admin/analytics/growth", params={"range_days": 7})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body["data"]

    assert data["range_days"] == 7
    series = data["series"]

    # 7 rows — one per day
    assert len(series) == 7

    # Days are ascending YYYY-MM-DD strings
    days = [s["day"] for s in series]
    assert days == sorted(days)

    # Locate today and yesterday rows
    today_str = _NOW.date().isoformat()
    yesterday_str = _YESTERDAY.date().isoformat()

    by_day = {s["day"]: s for s in series}

    assert today_str in by_day
    assert yesterday_str in by_day

    t = by_day[today_str]
    y = by_day[yesterday_str]

    assert t["signups"] == 1
    assert t["applications"] == 2
    assert t["active_users"] == 1

    assert y["signups"] == 1
    assert y["applications"] == 1
    assert y["active_users"] == 2

    # All other days are zeros
    for day_str, row in by_day.items():
        if day_str not in (today_str, yesterday_str):
            assert row["signups"] == 0
            assert row["applications"] == 0
            assert row["active_users"] == 0


# ---------------------------------------------------------------------------
# Test 4: KPIs — correct totals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kpis_correct_totals(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """kpis returns per-persona identity counts + job + application + event totals."""

    org = _make_org()
    db_session.add(org)
    await db_session.flush()

    # 2 students
    for _ in range(2):
        u = _make_user()
        db_session.add(u)
        await db_session.flush()
        db_session.add(Identity(user_id=u.id, persona="student", org_id=None))

    # 1 partner_member
    u_pm = _make_user()
    db_session.add(u_pm)
    await db_session.flush()
    db_session.add(Identity(user_id=u_pm.id, persona="partner_member", org_id=org.id))

    # 1 university_staff
    u_us = _make_user()
    db_session.add(u_us)
    await db_session.flush()
    db_session.add(Identity(user_id=u_us.id, persona="university_staff", org_id=org.id))

    # 1 job
    job = _make_job(org_id=org.id)
    db_session.add(job)
    await db_session.flush()

    # 1 application (need a student user for applicant_id)
    applicant = _make_user()
    db_session.add(applicant)
    await db_session.flush()
    db_session.add(_make_application(job_id=job.id, applicant_id=applicant.id, org_id=org.id))

    # 1 published event
    db_session.add(_make_event(org_id=org.id))

    await db_session.commit()

    resp = await superadmin_client.get("/admin/analytics/kpis")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["students"] == 2
    assert data["partner_members"] == 1
    assert data["university_staff"] == 1
    assert data["jobs"] == 1
    assert data["applications"] == 1
    assert data["events"] == 1


# ---------------------------------------------------------------------------
# Test 5: Empty window — zeros, no crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_funnel_empty_window_returns_zeros(superadmin_client: AsyncClient) -> None:
    """Empty DB / no events in window -> funnel returns zeros, no 500."""

    resp = await superadmin_client.get("/admin/analytics/funnel", params={"range_days": 1})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["range_days"] == 1
    for stage in data["stages"]:
        assert stage["count"] == 0


@pytest.mark.asyncio
async def test_growth_empty_window_returns_zeros(superadmin_client: AsyncClient) -> None:
    """Empty DB -> growth returns all-zero series for requested window."""

    resp = await superadmin_client.get("/admin/analytics/growth", params={"range_days": 3})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["range_days"] == 3
    assert len(data["series"]) == 3
    for row in data["series"]:
        assert row["signups"] == 0
        assert row["applications"] == 0
        assert row["active_users"] == 0


@pytest.mark.asyncio
async def test_kpis_empty_db_returns_zeros(superadmin_client: AsyncClient) -> None:
    resp = await superadmin_client.get("/admin/analytics/kpis")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["students"] == 0
    assert data["jobs"] == 0
    assert data["applications"] == 0
    assert data["events"] == 0


# ---------------------------------------------------------------------------
# Test 6: Privacy — no actor_id, no PII, no per-user rows in any response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_funnel_response_contains_no_pii(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Funnel response must not expose actor_id, email, or raw properties."""

    actor = uuid.uuid4()
    db_session.add(
        _analytics_event(
            event_type="job.viewed",
            actor_id=actor,
            properties={"status": "published", "source": "search"},
        )
    )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/analytics/funnel", params={"range_days": 7})
    assert resp.status_code == 200
    text = resp.text

    # actor_id UUID must not appear anywhere in the response body
    assert str(actor) not in text
    assert "email" not in text
    assert "actor_id" not in text
    # raw properties keys must not be surfaced
    assert "source" not in text


@pytest.mark.asyncio
async def test_growth_response_contains_no_pii(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Growth response must not expose actor_id or per-user rows."""

    actor = uuid.uuid4()
    db_session.add(_analytics_event(event_type="job.viewed", actor_id=actor))
    await db_session.commit()

    resp = await superadmin_client.get("/admin/analytics/growth", params={"range_days": 7})
    assert resp.status_code == 200
    text = resp.text

    assert str(actor) not in text
    assert "actor_id" not in text
    assert "email" not in text


@pytest.mark.asyncio
async def test_kpis_response_contains_no_pii(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """KPIs response must not expose user IDs, emails, or any per-user row."""

    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(Identity(user_id=user.id, persona="student", org_id=None))
    await db_session.commit()

    resp = await superadmin_client.get("/admin/analytics/kpis")
    assert resp.status_code == 200
    text = resp.text

    assert str(user.id) not in text
    assert user.email not in text
    assert "actor_id" not in text


# ---------------------------------------------------------------------------
# Test 7: Zero-division safety — funnel with single non-zero stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_funnel_zero_division_guarded(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """When a predecessor stage is 0, conversion_from_previous must be 0.0, not crash."""

    # Only seed a status_changed/under_review with no job.viewed / job.applied
    db_session.add(
        _analytics_event(
            event_type="application.status_changed",
            properties={"status": "hired"},
        )
    )
    await db_session.commit()

    resp = await superadmin_client.get("/admin/analytics/funnel", params={"range_days": 7})
    assert resp.status_code == 200
    data = resp.json()["data"]

    stages = {s["stage"]: s for s in data["stages"]}
    # hired has 1 count; offer (predecessor) is 0 -> conversion must be 0.0
    assert stages["hired"]["count"] == 1
    assert stages["hired"]["conversion_from_previous"] == 0.0
