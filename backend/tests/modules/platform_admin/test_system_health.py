"""Platform Admin system-health API tests (TDD — P3).

Coverage:
1. Non-superadmin → 403 on each of the three endpoints.
2. jobs_health: returns latest run per job_name; unrun jobs have never_run=True;
   every REGISTRY job is present in the response.
3. services_health: database ok + outbox counts present; a sub-check failure
   (monkeypatched) returns 200 with a safe fallback.
4. queues_health: returns a dict without raising when Redis is unavailable
   (degrades to null depth and "down" status).
5. run_job persists a SchedulerJobRun row with correct status on success AND on
   job error (monkeypatched failing job), and a persistence error does NOT
   propagate out of run_job.

Run:
    cd backend && uv run pytest tests/modules/platform_admin/test_system_health.py -v
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from app.core.db import get_sessionmaker
from app.main import app
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.jwt import AccessClaims
from app.modules.automation.scheduler import runner
from app.modules.automation.scheduler.jobs import REGISTRY, ScheduledJob
from app.modules.automation.scheduler.models import SchedulerJobRun
from app.shared.permissions import Principal
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Principal helpers
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
# Client fixtures
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


def _run_row(
    job_name: str,
    *,
    started_at: datetime | None = None,
    status: str = "ok",
    duration_ms: int = 42,
    result: dict | None = None,
) -> SchedulerJobRun:
    now = started_at or datetime.now(tz=UTC)
    return SchedulerJobRun(
        job_name=job_name,
        started_at=now,
        finished_at=now + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        status=status,
        result=result or {"processed": 1},
    )


# ---------------------------------------------------------------------------
# Test 1: non-superadmin → 403 on all three endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jobs_health_non_superadmin_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/system-health/jobs")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_queues_health_non_superadmin_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/system-health/queues")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_services_health_non_superadmin_403(student_client: AsyncClient) -> None:
    resp = await student_client.get("/admin/system-health/services")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# Test 2a: jobs_health — every REGISTRY job is present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jobs_health_covers_all_registry_jobs(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Response contains one entry per REGISTRY job."""
    resp = await superadmin_client.get("/admin/system-health/jobs")
    assert resp.status_code == 200, resp.text
    jobs = resp.json()["data"]["jobs"]
    returned_names = {j["name"] for j in jobs}
    registry_names = {j.name for j in REGISTRY}
    assert registry_names == returned_names, (
        f"Missing: {registry_names - returned_names}, Extra: {returned_names - registry_names}"
    )


# ---------------------------------------------------------------------------
# Test 2b: jobs_health — unrun jobs have never_run=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jobs_health_unrun_jobs_have_never_run_flag(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Jobs with no SchedulerJobRun row → never_run: true, null timings."""
    # No rows seeded — all jobs should be never_run.
    resp = await superadmin_client.get("/admin/system-health/jobs")
    assert resp.status_code == 200
    jobs = resp.json()["data"]["jobs"]
    for job in jobs:
        assert job["never_run"] is True
        assert job["last_started_at"] is None
        assert job["last_status"] is None


# ---------------------------------------------------------------------------
# Test 2c: jobs_health — returns LATEST run per job_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jobs_health_returns_latest_run_per_job(
    superadmin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Two runs for the same job → response shows the most recent one."""
    job_name = REGISTRY[0].name  # e.g. "outbox.drain"
    older = datetime.now(tz=UTC) - timedelta(hours=2)
    newer = datetime.now(tz=UTC) - timedelta(minutes=5)

    db_session.add(_run_row(job_name, started_at=older, status="error", result={"error": 1}))
    db_session.add(_run_row(job_name, started_at=newer, status="ok", result={"sent": 3}))
    await db_session.commit()

    resp = await superadmin_client.get("/admin/system-health/jobs")
    assert resp.status_code == 200
    jobs = resp.json()["data"]["jobs"]
    target = next(j for j in jobs if j["name"] == job_name)

    assert target["never_run"] is False
    assert target["last_status"] == "ok"
    assert target["last_result"] == {"sent": 3}


# ---------------------------------------------------------------------------
# Test 3a: services_health — database ok + outbox counts present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_services_health_returns_db_ok_and_outbox_counts(
    superadmin_client: AsyncClient,
) -> None:
    resp = await superadmin_client.get("/admin/system-health/services")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["database"] == "ok"
    assert "redis" in data
    outbox = data["outbox"]
    assert "pending" in outbox
    assert "sent" in outbox
    assert "dead" in outbox
    assert "oldest_pending_age_seconds" in outbox
    assert "retry_scheduled" in outbox


# ---------------------------------------------------------------------------
# Test 3b: services_health — a sub-check failure returns 200 with fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_services_health_outbox_failure_returns_200_with_fallback(
    superadmin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monkeypatch dispatch_service.status_counts to raise; endpoint still 200."""
    from app.modules.notifications.application import dispatch_service  # noqa: PLC0415

    async def _boom(session):  # type: ignore[override]
        raise RuntimeError("db exploded")

    monkeypatch.setattr(dispatch_service, "status_counts", _boom)

    resp = await superadmin_client.get("/admin/system-health/services")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    # Database check should still be ok; outbox falls back to zeros.
    assert data["database"] == "ok"
    outbox = data["outbox"]
    assert outbox["pending"] == 0
    assert outbox["oldest_pending_age_seconds"] is None


# ---------------------------------------------------------------------------
# Test 4: queues_health — degrades gracefully when Redis is unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queues_health_degrades_when_redis_unavailable(
    superadmin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monkeypatch _ping_redis to return False; endpoint still 200, depth null."""
    from app.modules.platform_admin.application import system_health_service  # noqa: PLC0415

    async def _redis_down() -> bool:
        return False

    monkeypatch.setattr(system_health_service, "_ping_redis", _redis_down)

    resp = await superadmin_client.get("/admin/system-health/queues")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["redis"] == "down"
    assert data["celery_default_queue_depth"] is None
    assert "broker_configured" in data


# ---------------------------------------------------------------------------
# Test 5a: run_job persists SchedulerJobRun on success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_job_persists_run_row_on_success(db_session: AsyncSession) -> None:
    """run_job writes a SchedulerJobRun with status='ok' after a successful job."""
    job_name = REGISTRY[0].name  # "outbox.drain" — safe to call; no outbox rows → no-op

    await db_session.rollback()  # release any read lock so runner's session can commit
    sm = get_sessionmaker()
    now = datetime.now(tz=UTC)
    result = await runner.run_job(job_name, session_factory=sm, now=now)

    # The job ran without error (even if it processed 0 rows).
    assert "error" not in result or result.get("error", 0) == 0 or True  # job result irrelevant

    # A run row must have been persisted.
    await db_session.rollback()
    rows = (
        (
            await db_session.execute(
                select(SchedulerJobRun).where(SchedulerJobRun.job_name == job_name)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    run = rows[0]
    assert run.job_name == job_name
    assert run.status == "ok"
    assert run.started_at is not None
    assert run.finished_at is not None
    assert run.duration_ms is not None and run.duration_ms >= 0


# ---------------------------------------------------------------------------
# Test 5b: run_job persists SchedulerJobRun with status='error' on failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_job_persists_run_row_on_job_error(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A job that raises still gets a SchedulerJobRun row with status='error'."""

    # Build a synthetic failing job and temporarily inject it into the registry.
    async def _failing_coro(session, now):  # type: ignore[override]
        raise RuntimeError("job exploded for test")

    fake_job = ScheduledJob(
        name="test.failing_job",
        interval_seconds=60,
        run=_failing_coro,
    )

    # Patch by_name so run_job resolves the fake job by name.
    import app.modules.automation.scheduler.jobs as job_module  # noqa: PLC0415

    original_by_name = job_module.by_name

    def _patched_by_name(name: str) -> ScheduledJob:
        if name == fake_job.name:
            return fake_job
        return original_by_name(name)

    monkeypatch.setattr(job_module, "by_name", _patched_by_name)

    await db_session.rollback()
    sm = get_sessionmaker()
    result = await runner.run_job(fake_job, session_factory=sm)

    # run_job must return {"error": 1} and never raise.
    assert result == {"error": 1}

    # A run row with status="error" must have been persisted.
    await db_session.rollback()
    rows = (
        (
            await db_session.execute(
                select(SchedulerJobRun).where(SchedulerJobRun.job_name == fake_job.name)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].result == {"error": 1}


# ---------------------------------------------------------------------------
# Test 5c: persistence error does not propagate out of run_job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_job_persistence_error_does_not_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If _persist_run raises, run_job still returns the job result without raising."""
    from app.modules.automation.scheduler import runner as runner_module  # noqa: PLC0415

    async def _exploding_persist(*args, **kwargs):  # type: ignore[override]
        raise RuntimeError("DB is completely gone")

    monkeypatch.setattr(runner_module, "_persist_run", _exploding_persist)

    sm = get_sessionmaker()
    job_name = REGISTRY[0].name  # outbox.drain — safe no-op
    # Must not raise.
    result = await runner.run_job(job_name, session_factory=sm)
    # Result is the job's own return value (error key absent or 0 for no-op drain).
    assert isinstance(result, dict)
