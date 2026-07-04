"""Integration tests for the market intelligence read model (§3
``market_intelligence`` — university/restricted-admin only, aggregate-only).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.dashboards.application import market_intelligence_service as svc
from app.modules.opportunities.domain.models import Job
from app.shared.permissions import Principal

from tests.org_utils import make_org_with_admin


def _student() -> Principal:
    return Principal(
        user_id=uuid.uuid4(), persona="student", permissions=frozenset()
    )


async def _seed_active_jobs(db, *, org_id: uuid.UUID, posted_by: uuid.UUID) -> None:
    now = datetime.now(UTC)
    for i in range(6):
        db.add(
            Job(
                org_id=org_id,
                posted_by=posted_by,
                title=f"Data Analyst {i}",
                slug=f"data-analyst-{uuid.uuid4().hex[:10]}",
                description="Analyze data.",
                employment_type="full_time" if i < 4 else "internship",
                location_type="onsite",
                required_skills=["SQL", "Python"] if i < 5 else ["Excel"],
                salary_is_disclosed=(i < 3),
                status="active",
                published_at=now - timedelta(days=3),
            )
        )
    await db.commit()


class TestGate:
    async def test_student_denied(self, db_session) -> None:
        from app.shared.exceptions import PermissionDeniedError

        with pytest.raises(PermissionDeniedError):
            await svc.get_market_intelligence(
                db_session, principal=_student()
            )

    async def test_partner_denied(self, db_session) -> None:
        from app.shared.exceptions import PermissionDeniedError

        _u, _org, partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="Acme"
        )
        with pytest.raises(PermissionDeniedError):
            await svc.get_market_intelligence(db_session, principal=partner)


class TestReport:
    async def test_empty_platform_is_low_signal_without_narrative(
        self, db_session
    ) -> None:
        _u, _org, uni = await make_org_with_admin(
            db_session, org_type="university", display_name="VinUni"
        )
        data = await svc.get_market_intelligence(db_session, principal=uni)
        assert data["low_signal"] is True
        assert data["active_jobs"] == 0
        assert data["ai_narrative_available"] is False

    async def test_aggregates_and_offline_narrative(self, db_session) -> None:
        pu, porg, _partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="Acme"
        )
        _u, _org, uni = await make_org_with_admin(
            db_session, org_type="university", display_name="VinUni"
        )
        await _seed_active_jobs(db_session, org_id=porg.id, posted_by=pu.id)

        data = await svc.get_market_intelligence(db_session, principal=uni)

        assert data["active_jobs"] == 6
        assert data["jobs_last_30d"] == 6
        assert data["trend"] == "up"
        assert data["salary_disclosure_rate"] == 50
        assert data["employment_types"][0] == {"type": "full_time", "count": 4}
        assert data["top_skills"][0]["skill"] == "sql"
        # offline provider is deterministic and available → narrative present
        assert data["ai_narrative_available"] is True
        blob = str(data).lower()
        for leak in ("openrouter", "gpt", "model_alias", "prompt_tokens"):
            assert leak not in blob

    async def test_provider_failure_degrades_to_aggregates(
        self, db_session
    ) -> None:
        from unittest import mock

        pu, porg, _partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="Acme"
        )
        _u, _org, uni = await make_org_with_admin(
            db_session, org_type="university", display_name="VinUni"
        )
        await _seed_active_jobs(db_session, org_id=porg.id, posted_by=pu.id)

        with mock.patch.object(
            svc, "generate_note", mock.AsyncMock(side_effect=RuntimeError("down"))
        ):
            data = await svc.get_market_intelligence(db_session, principal=uni)

        assert data["active_jobs"] == 6
        assert data["ai_narrative"] is None
        assert data["ai_narrative_available"] is False
