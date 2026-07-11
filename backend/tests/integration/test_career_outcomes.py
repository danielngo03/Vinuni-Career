"""Career-outcomes materializer tests (ADR-0007 deferred ``offer.accepted`` consumer).

Drives the consumer *as scheduled* through ``runner.tick(only=[...])`` (never the
domain function directly), proving:

- accepting an offer emits ``offer.accepted`` -> the sweep materializes EXACTLY one
  ``career_outcome_record`` at ``trust_level=4`` / ``source='system_estimate'`` with
  the payload fields, cross-checked against the accepted application/offer;
- idempotent: a re-tick does NOT duplicate (dedupe on the ``published_at`` processed
  marker AND the unique ``source_event_id``);
- NO salary / NO student PII in the materialized record;
- a non-``offer.accepted`` outbox event is ignored.

Reuses the offer-accept flow helpers from ``test_recruitment_offers`` so the event
is emitted by the real service path, not hand-rolled.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.db import get_sessionmaker
from app.modules.automation.scheduler import runner
from app.modules.career_outcomes.application import read_service
from app.modules.career_outcomes.domain.models import CareerOutcomeRecord
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import access, offer_service
from app.modules.recruitment.domain import offer as offer_domain
from app.modules.recruitment.domain.models import Application, Offer
from app.shared.exceptions import PermissionDeniedError
from app.shared.models import OutboxEvent
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.integration.test_recruitment_offers import (
    _SALARY,
    _now,
    _setup_reviewed,
    _to_sent,
)
from tests.org_utils import make_org_with_admin

_JOB = "career_outcomes.materialize_sweep"


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _accept_offer(db_session) -> tuple[uuid.UUID, uuid.UUID]:
    """Run the real offer-accept flow; return ``(application_id, offer_id)``."""

    partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    sent = await _to_sent(db_session, partner=partner, app_id=app_id)
    oid = uuid.UUID(sent["id"])
    out = await offer_service.respond_offer(
        db_session,
        principal=student,
        offer_id=oid,
        decision="accepted",
        idempotency_key="co-accept",
        ctx=CTX,
    )
    assert out["status"] == offer_domain.STATUS_ACCEPTED
    return app_id, oid


async def _sweep() -> dict:
    # Drive the consumer exactly as the scheduler would; fresh sessionmaker so the
    # tick reads the committed event (as the worker process does).
    res = await runner.tick(_now(), session_factory=get_sessionmaker(), only=[_JOB])
    return res[_JOB]


async def test_accept_materializes_one_outcome_trust_level_4(db_session) -> None:
    app_id, oid = await _accept_offer(db_session)

    await db_session.rollback()
    res = await _sweep()
    assert res["materialized"] == 1
    assert res.get("deduped", 0) == 0

    async with get_sessionmaker()() as fresh:
        rows = (await fresh.execute(select(CareerOutcomeRecord))).scalars().all()
        assert len(rows) == 1
        rec = rows[0]

        # Trust + source semantics (DATA_MODEL §27 / BUSINESS_LOGIC §13).
        assert rec.trust_level == 4
        assert rec.source == "system_estimate"
        assert rec.outcome_type == "hired"

        # Payload fields, cross-checked against the accepted application/offer.
        assert rec.application_id == app_id
        assert rec.offer_id == oid
        assert rec.position_title == "Backend Engineer"
        assert rec.recorded_at is not None

        offer = (await fresh.execute(select(Offer).where(Offer.id == oid))).scalar_one()
        app_row = (
            await fresh.execute(select(Application).where(Application.id == app_id))
        ).scalar_one()
        assert rec.org_id == app_row.org_id
        assert rec.employer_org_id == app_row.org_id
        assert rec.start_date == offer.start_date

        # source_event_id ties the record to the originating outbox event.
        event = (
            await fresh.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == "offer.accepted")
            )
        ).scalar_one()
        assert rec.source_event_id == event.id
        # The event is marked processed (published_at stamped).
        assert event.published_at is not None


async def test_no_salary_or_student_pii_in_record(db_session) -> None:
    await _accept_offer(db_session)
    await db_session.rollback()
    await _sweep()

    async with get_sessionmaker()() as fresh:
        rec = (await fresh.execute(select(CareerOutcomeRecord))).scalar_one()
        # The materialized record carries no salary and no student identity column.
        blob = {c.name: getattr(rec, c.name) for c in rec.__table__.columns}
        as_text = str(blob).lower()
        assert "salary" not in as_text
        assert str(_SALARY) not in str(blob)
        assert "student_id" not in blob
        assert "salary_amount" not in blob


async def test_sweep_is_idempotent_no_duplicate(db_session) -> None:
    await _accept_offer(db_session)

    await db_session.rollback()
    first = await _sweep()
    assert first["materialized"] == 1

    # Re-tick: the event is already processed (published_at) AND the unique
    # source_event_id would block a duplicate -> no new record.
    await db_session.rollback()
    second = await _sweep()
    assert second["materialized"] == 0

    async with get_sessionmaker()() as fresh:
        count = (
            await fresh.execute(select(func.count()).select_from(CareerOutcomeRecord))
        ).scalar_one()
        assert count == 1


async def test_non_offer_accepted_event_is_ignored(db_session) -> None:
    # An unrelated generic outbox event must NOT be materialized.
    db_session.add(
        OutboxEvent(
            aggregate_type="application",
            aggregate_id=uuid.uuid4(),
            event_type="application.reviewed",
            payload={"application_id": str(uuid.uuid4())},
        )
    )
    await db_session.commit()

    await db_session.rollback()
    res = await _sweep()
    assert res["materialized"] == 0

    async with get_sessionmaker()() as fresh:
        count = (
            await fresh.execute(select(func.count()).select_from(CareerOutcomeRecord))
        ).scalar_one()
        assert count == 0
        # The non-target event was left untouched (not marked processed).
        ev = (
            await fresh.execute(
                select(OutboxEvent).where(OutboxEvent.event_type == "application.reviewed")
            )
        ).scalar_one()
        assert ev.published_at is None


# --------------------------------------------------------------------------- #
# University read API (RBAC + aggregates + PII-free, friendly labels)         #
# --------------------------------------------------------------------------- #


async def _materialize_one(db_session) -> None:
    await _accept_offer(db_session)
    await db_session.rollback()
    res = await _sweep()
    assert res["materialized"] == 1


async def test_kpi_university_sees_aggregates(db_session) -> None:
    await _materialize_one(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    async with get_sessionmaker()() as fresh:
        kpi = await read_service.get_kpi(fresh, principal=uni)

    assert kpi["total_outcomes"] == 1
    # trust-level 4 (system-estimated) carries a friendly label, not a raw int.
    lvl4 = next(b for b in kpi["by_trust_level"] if b["trust_level"] == 4)
    assert lvl4["count"] == 1
    assert lvl4["label"] in {"Ước tính từ hệ thống", "System-estimated"}
    # top employer resolves a real display name (Partner Co from the setup).
    assert kpi["top_employers"][0]["count"] == 1
    assert kpi["top_employers"][0]["employer_name"] == "Partner Co"
    # recent record: friendly outcome label + employer name, no raw enum / salary.
    rec = kpi["recent"][0]
    assert rec["outcome"] in {"Đã tuyển dụng", "Hired"}
    assert rec["employer_name"] == "Partner Co"
    blob = str(kpi)
    assert "system_estimate" not in blob
    assert str(_SALARY) not in blob
    assert "student_id" not in blob


async def test_kpi_partner_forbidden(db_session) -> None:
    await _materialize_one(db_session)
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="ACME")

    async with get_sessionmaker()() as fresh:
        with pytest.raises(PermissionDeniedError):
            await read_service.get_kpi(fresh, principal=partner)


async def test_kpi_student_forbidden(db_session) -> None:
    await _materialize_one(db_session)
    _su, student = await make_student(db_session, prefix="co-student")

    async with get_sessionmaker()() as fresh:
        with pytest.raises(PermissionDeniedError):
            await read_service.get_kpi(fresh, principal=student)


async def test_kpi_superadmin_allowed(db_session) -> None:
    await _materialize_one(db_session)
    _su, student = await make_student(db_session, prefix="co-admin")
    student.is_superadmin = True

    async with get_sessionmaker()() as fresh:
        kpi = await read_service.get_kpi(fresh, principal=student)
    assert kpi["total_outcomes"] == 1


async def test_records_list_is_pii_free_and_labelled(db_session) -> None:
    await _materialize_one(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    async with get_sessionmaker()() as fresh:
        out = await read_service.list_records(fresh, principal=uni)

    assert out["count"] == 1
    item = out["items"][0]
    assert item["employer_name"] == "Partner Co"
    assert item["trust_label"] in {"Ước tính từ hệ thống", "System-estimated"}
    assert item["outcome"] in {"Đã tuyển dụng", "Hired"}
    # No raw enum codes / salary / student identity reach the response.
    blob = str(out)
    assert "system_estimate" not in blob
    assert str(_SALARY) not in blob
    assert "student_id" not in blob
