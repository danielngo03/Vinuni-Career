"""Read-model governance (B-558): the market-intelligence snapshot.

Covers refresh (scheduled write), stale-read fallback (live recompute, never a
500), and the reconciliation drift check.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.modules.dashboards.application import snapshot_service
from app.modules.dashboards.domain.models import MarketIntelligenceSnapshot
from app.modules.opportunities.domain.models import Job
from sqlalchemy import select

from tests.org_utils import make_org_with_admin


async def _seed_active_job(db, *, org_id: uuid.UUID, posted_by: uuid.UUID) -> None:
    db.add(
        Job(
            org_id=org_id,
            posted_by=posted_by,
            title="Data Analyst",
            slug=f"data-analyst-{uuid.uuid4().hex[:10]}",
            description="Analyze data.",
            employment_type="full_time",
            location_type="onsite",
            required_skills=["SQL"],
            salary_is_disclosed=True,
            status="active",
            published_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    await db.commit()


async def test_refresh_creates_snapshot(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)

    result = await snapshot_service.refresh(db_session)
    await db_session.commit()
    assert result == {"refreshed": 1}

    row = (
        await db_session.execute(
            select(MarketIntelligenceSnapshot).where(MarketIntelligenceSnapshot.id == 1)
        )
    ).scalar_one()
    assert row.report["active_jobs"] >= 1


async def test_read_for_display_uses_fresh_snapshot(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)
    await snapshot_service.refresh(db_session)
    await db_session.commit()

    # Add a second job WITHOUT refreshing — a fresh read must still return the
    # stale-but-not-yet-expired snapshot value, not silently recompute live.
    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)

    data = await snapshot_service.read_for_display(db_session)
    assert data["stale"] is False
    assert data["active_jobs"] == 1  # snapshot value, not the live count of 2


async def test_read_for_display_recomputes_when_expired(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)
    now = datetime.now(UTC)
    await snapshot_service.refresh(db_session, now=now)
    await db_session.commit()

    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)
    past_expiry = now + timedelta(
        seconds=get_settings().market_intelligence_stale_after_seconds + 1
    )

    data = await snapshot_service.read_for_display(db_session, now=past_expiry)
    assert data["stale"] is False  # recomputed live, so freshly correct
    assert data["active_jobs"] == 2

    row = (
        await db_session.execute(
            select(MarketIntelligenceSnapshot).where(MarketIntelligenceSnapshot.id == 1)
        )
    ).scalar_one()
    assert row.report["active_jobs"] == 2  # opportunistically persisted


async def test_read_for_display_falls_back_to_stale_snapshot_on_live_failure(
    db_session, monkeypatch
) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)
    now = datetime.now(UTC)
    await snapshot_service.refresh(db_session, now=now)
    await db_session.commit()

    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(snapshot_service, "_compute_report", _boom)
    past_expiry = now + timedelta(
        seconds=get_settings().market_intelligence_stale_after_seconds + 1
    )

    data = await snapshot_service.read_for_display(db_session, now=past_expiry)
    assert data["stale"] is True
    assert data["active_jobs"] == 1  # last known snapshot, never a 500


async def test_reconcile_detects_drift(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)
    await snapshot_service.refresh(db_session)
    await db_session.commit()

    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)
    result = await snapshot_service.reconcile(db_session)
    assert result == {"checked": 1, "drift": 1}


async def test_reconcile_no_drift_when_in_sync(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme")
    await _seed_active_job(db_session, org_id=org.id, posted_by=admin.user_id)
    await snapshot_service.refresh(db_session)
    await db_session.commit()

    result = await snapshot_service.reconcile(db_session)
    assert result == {"checked": 1, "drift": 0}


async def test_reconcile_no_snapshot_is_a_noop(db_session) -> None:
    result = await snapshot_service.reconcile(db_session)
    assert result == {"checked": 0, "drift": 0}
