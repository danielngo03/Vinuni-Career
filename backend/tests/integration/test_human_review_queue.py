"""Integration tests for the human review queue (AI_PRODUCT_SPEC §9.3).

Covers: enqueue + PENDING dedup, university-only listing, resolve/dismiss with
audit + already-reviewed conflict, JD-draft escalation wiring, and the
on-demand fraud scan endpoint path (service layer).
"""

from __future__ import annotations

import uuid
from unittest import mock

import pytest
from app.modules.moderation.application import (
    fraud_scan_service,
    review_queue_service,
)
from app.modules.moderation.domain.models import HumanReviewItem
from app.modules.opportunities.application import jd_ai_service, job_service
from app.shared.exceptions import ConflictError, PermissionDeniedError
from app.shared.permissions import Principal
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import job_payload


def _student() -> Principal:
    return Principal(user_id=uuid.uuid4(), persona="student", permissions=frozenset())


async def _enqueue(db, **over) -> HumanReviewItem:
    defaults: dict = {
        "source": review_queue_service.SOURCE_CONTENT,
        "resource_type": "job",
        "resource_id": uuid.uuid4(),
        "org_id": None,
        "severity": "high",
        "findings": {"content_check": {"flagged": True}},
    }
    defaults.update(over)
    item = await review_queue_service.enqueue(db, **defaults)
    assert item is not None
    return item


class TestEnqueue:
    async def test_enqueue_creates_pending_item(self, db_session) -> None:
        item = await _enqueue(db_session)
        assert item.status == "PENDING"
        assert item.findings_json["content_check"]["flagged"] is True

    async def test_enqueue_dedups_open_item_per_resource(self, db_session) -> None:
        rid = uuid.uuid4()
        first = await _enqueue(db_session, resource_id=rid)
        second = await _enqueue(db_session, resource_id=rid, findings={"content_check": {"v": 2}})
        assert second.id == first.id  # refreshed, not duplicated
        rows = (await db_session.execute(select(HumanReviewItem))).scalars().all()
        assert len(rows) == 1
        assert rows[0].findings_json == {"content_check": {"v": 2}}

    async def test_unknown_severity_downgrades_to_medium(self, db_session) -> None:
        item = await _enqueue(db_session, severity="catastrophic")
        assert item.severity == "medium"


class TestListAndDecide:
    async def test_university_admin_lists_and_resolves(self, db_session) -> None:
        _u, _org, uni = await make_org_with_admin(
            db_session, org_type="university", display_name="VinUni"
        )
        item = await _enqueue(db_session)

        items = await review_queue_service.list_items(db_session, principal=uni)
        assert [i.id for i in items] == [item.id]

        resolved = await review_queue_service.resolve_item(
            db_session, principal=uni, ctx=CTX, item_id=item.id, note="Đã gỡ tin."
        )
        assert resolved.status == "RESOLVED"
        assert resolved.reviewed_by == uni.user_id
        assert resolved.resolution_note == "Đã gỡ tin."

    async def test_dismiss_marks_false_positive(self, db_session) -> None:
        _u, _org, uni = await make_org_with_admin(
            db_session, org_type="university", display_name="VinUni"
        )
        item = await _enqueue(db_session)
        dismissed = await review_queue_service.dismiss_item(
            db_session, principal=uni, ctx=CTX, item_id=item.id
        )
        assert dismissed.status == "DISMISSED"

    async def test_double_decision_conflicts(self, db_session) -> None:
        _u, _org, uni = await make_org_with_admin(
            db_session, org_type="university", display_name="VinUni"
        )
        item = await _enqueue(db_session)
        await review_queue_service.resolve_item(db_session, principal=uni, ctx=CTX, item_id=item.id)
        with pytest.raises(ConflictError):
            await review_queue_service.dismiss_item(
                db_session, principal=uni, ctx=CTX, item_id=item.id
            )

    async def test_student_denied(self, db_session) -> None:
        with pytest.raises(PermissionDeniedError):
            await review_queue_service.list_items(db_session, principal=_student())

    async def test_partner_admin_denied(self, db_session) -> None:
        _u, _org, partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="Acme"
        )
        with pytest.raises(PermissionDeniedError):
            await review_queue_service.list_items(db_session, principal=partner)


class TestJdDraftEscalation:
    async def test_high_risk_draft_escalates_to_queue(self, db_session) -> None:
        _u, org, partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="Acme"
        )
        created = await job_service.create_job(
            db_session, principal=partner, payload=job_payload(), ctx=CTX
        )
        job_id = uuid.UUID(created["id"])

        biased_draft = "Vị trí này chỉ tuyển nam, ngoại hình ưa nhìn."
        with mock.patch.object(
            jd_ai_service, "generate_note", mock.AsyncMock(return_value=biased_draft)
        ):
            result = await jd_ai_service.draft_description(
                db_session, principal=partner, job_id=job_id, payload={}
            )

        assert result["bias_check"]["requires_human_review"] is True
        rows = (await db_session.execute(select(HumanReviewItem))).scalars().all()
        assert len(rows) == 1
        assert rows[0].source == review_queue_service.SOURCE_BIAS
        assert rows[0].resource_id == job_id

    async def test_clean_draft_does_not_escalate(self, db_session) -> None:
        _u, org, partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="Acme"
        )
        created = await job_service.create_job(
            db_session, principal=partner, payload=job_payload(), ctx=CTX
        )
        clean_draft = "Tuyển kỹ sư backend 2 năm kinh nghiệm Python."
        with mock.patch.object(
            jd_ai_service, "generate_note", mock.AsyncMock(return_value=clean_draft)
        ):
            await jd_ai_service.draft_description(
                db_session,
                principal=partner,
                job_id=uuid.UUID(created["id"]),
                payload={},
            )
        rows = (await db_session.execute(select(HumanReviewItem))).scalars().all()
        assert rows == []


class TestFraudScan:
    async def test_scam_job_on_new_org_escalates(self, db_session) -> None:
        _u, _org, partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="FreshCo"
        )
        created = await job_service.create_job(
            db_session,
            principal=partner,
            payload=job_payload(
                description=(
                    "Vui lòng nộp phí hồ sơ 200k. Nhắn tin qua Zalo trước để được nhận việc."
                )
            ),
            ctx=CTX,
        )
        _uu, _uorg, uni = await make_org_with_admin(
            db_session, org_type="university", display_name="VinUni"
        )

        result = await fraud_scan_service.scan_job(
            db_session, principal=uni, job_id=uuid.UUID(created["id"])
        )

        # new org (0.25) + fee flagged (0.45) + off-platform contact (0.20) = 0.90
        assert result["risk_level"] == "high"
        assert result["escalated"] is True
        assert "risk_score" not in result  # raw score never in the response
        rows = (await db_session.execute(select(HumanReviewItem))).scalars().all()
        assert any(r.source == review_queue_service.SOURCE_FRAUD for r in rows)

    async def test_clean_job_not_escalated(self, db_session) -> None:
        _u, _org, partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="CleanCo"
        )
        created = await job_service.create_job(
            db_session, principal=partner, payload=job_payload(), ctx=CTX
        )
        _uu, _uorg, uni = await make_org_with_admin(
            db_session, org_type="university", display_name="VinUni"
        )
        result = await fraud_scan_service.scan_job(
            db_session, principal=uni, job_id=uuid.UUID(created["id"])
        )
        assert result["escalated"] is False
        assert result["requires_human_review"] is False

    async def test_partner_cannot_run_fraud_scan(self, db_session) -> None:
        _u, _org, partner = await make_org_with_admin(
            db_session, org_type="partner", display_name="Acme"
        )
        created = await job_service.create_job(
            db_session, principal=partner, payload=job_payload(), ctx=CTX
        )
        with pytest.raises(PermissionDeniedError):
            await fraud_scan_service.scan_job(
                db_session, principal=partner, job_id=uuid.UUID(created["id"])
            )
