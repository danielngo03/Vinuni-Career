"""CV extraction debits the student's AI energy — PAID tiers only, on success.

Mirrors ``tests/modules/opportunities/test_jd_metering.py`` for the student side:
the vision-LLM / text-LLM tiers charge ``FEATURE_CV_EXTRACTION`` (user scope) on a
successful, user-visible result; native-text / local-OCR extractions are free; a
vision call that produced nothing records a ``provider_failed`` (0-credit) cost
row; the charge is idempotent on the ingestion id; and a metering fault or a guest
never charges.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.ai.energy.constants import FEATURE_CV_EXTRACTION
from app.ai.energy.models import SCOPE_USER, AiEnergyAccount
from app.ai.energy.service import charge_units
from app.ai.extraction.cv_ingestion_cascade import IngestionOutcome
from app.ai.observability.billable_usage import AiBillableUsage
from app.modules.documents.application import extraction_metering
from app.shared.permissions import Principal
from sqlalchemy import func, select


def _student() -> Principal:
    return Principal(user_id=uuid.uuid4(), persona="student")


def _outcome(**kw) -> IngestionOutcome:
    base = {"accepted": True, "quality_code": "REVIEW_REQUIRED"}
    base.update(kw)
    return IngestionOutcome(**base)


async def _user_units(db_session, user_id) -> int:
    total = (
        await db_session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _user_rows(db_session, user_id) -> list[AiBillableUsage]:
    return list(
        (
            await db_session.execute(
                select(AiBillableUsage).where(AiBillableUsage.actor_user_id == user_id)
            )
        ).scalars()
    )


async def _charge(db_session, principal, outcome, *, resource_id=None):
    await extraction_metering.charge_extraction(
        db_session, principal, outcome,
        resource_type="cv_ingestion", resource_id=resource_id or uuid.uuid4(),
    )


# --------------------------------------------------------------------------- #
# Paid tiers charge on success (user scope); free tiers do not                  #
# --------------------------------------------------------------------------- #


async def test_vision_tier_charges_student_user_scope(db_session) -> None:
    p = _student()
    await _charge(db_session, p, _outcome(vision_used=True, vision_attempted=True))
    assert await _user_units(db_session, p.user_id) == charge_units(FEATURE_CV_EXTRACTION)
    row = (await _user_rows(db_session, p.user_id))[0]
    assert row.result_status == "success"
    assert row.billing_scope == SCOPE_USER
    assert row.actor_persona == "student"
    assert row.feature_key == FEATURE_CV_EXTRACTION
    assert row.org_id is None


async def test_text_llm_tier_charges_student(db_session) -> None:
    p = _student()
    await _charge(db_session, p, _outcome(llm_used=True))
    assert await _user_units(db_session, p.user_id) == charge_units(FEATURE_CV_EXTRACTION)


async def test_native_text_only_is_free(db_session) -> None:
    p = _student()
    await _charge(db_session, p, _outcome())  # no paid tier ran
    assert await _user_rows(db_session, p.user_id) == []


async def test_ocr_only_is_free(db_session) -> None:
    p = _student()
    # Local OCR read it (free); no vision call was ever attempted.
    await _charge(db_session, p, _outcome(ocr_used=True, vision_attempted=False))
    assert await _user_rows(db_session, p.user_id) == []


# --------------------------------------------------------------------------- #
# Attempted-but-failed vision: cost visibility, but the student pays nothing     #
# --------------------------------------------------------------------------- #


async def test_vision_attempted_but_no_output_records_zero(db_session) -> None:
    p = _student()
    # Vision spent tokens but yielded nothing; OCR salvaged the result.
    await _charge(
        db_session, p,
        _outcome(ocr_used=True, vision_used=False, vision_attempted=True),
    )
    rows = await _user_rows(db_session, p.user_id)
    assert len(rows) == 1
    assert rows[0].result_status == "provider_failed"
    assert rows[0].units_charged == 0
    assert await _user_units(db_session, p.user_id) == 0


async def test_ai_unavailable_outcome_never_charges(db_session) -> None:
    p = _student()
    await _charge(
        db_session, p,
        IngestionOutcome(
            accepted=False, quality_code="EXTRACTION_PENDING_AI", ai_unavailable=True
        ),
    )
    assert await _user_rows(db_session, p.user_id) == []


# --------------------------------------------------------------------------- #
# Idempotency on the ingestion id + guard rails                                 #
# --------------------------------------------------------------------------- #


async def test_charge_is_idempotent_per_ingestion(db_session) -> None:
    p = _student()
    rid = uuid.uuid4()
    await _charge(db_session, p, _outcome(vision_used=True), resource_id=rid)
    await _charge(db_session, p, _outcome(vision_used=True), resource_id=rid)
    # A redelivery / retry of the SAME ingestion charges exactly once.
    assert await _user_units(db_session, p.user_id) == charge_units(FEATURE_CV_EXTRACTION)
    success_rows = [
        r for r in await _user_rows(db_session, p.user_id) if r.result_status == "success"
    ]
    assert len(success_rows) == 1


async def test_guest_is_never_charged(db_session) -> None:
    guest = Principal(user_id=None, persona="guest")
    await _charge(db_session, guest, _outcome(vision_used=True))
    total = (
        await db_session.execute(select(func.count()).select_from(AiBillableUsage))
    ).scalar_one()
    assert total == 0


async def test_no_principal_is_never_charged(db_session) -> None:
    await extraction_metering.charge_extraction(
        db_session, None, _outcome(vision_used=True),
        resource_type="cv_ingestion", resource_id=uuid.uuid4(),
    )
    total = (
        await db_session.execute(select(func.count()).select_from(AiBillableUsage))
    ).scalar_one()
    assert total == 0


# --------------------------------------------------------------------------- #
# Preflight gate: withhold paid tiers only when weekly energy is exhausted       #
# --------------------------------------------------------------------------- #


async def test_preflight_open_for_fresh_student(db_session) -> None:
    p = _student()
    assert await extraction_metering.preflight_gate(db_session, principal=p) is False


async def test_preflight_gates_when_weekly_exhausted(db_session) -> None:
    p = _student()
    db_session.add(
        AiEnergyAccount(
            scope_type=SCOPE_USER, scope_id=p.user_id,
            weekly_allowance_units=1, wallet_units=0,
        )
    )
    db_session.add(
        AiBillableUsage(
            actor_user_id=p.user_id, actor_persona="student", billing_scope=SCOPE_USER,
            feature_key="chatbot", task_type="chatbot", units_charged=5,
            result_status="success", created_at=datetime.now(UTC),
        )
    )
    await db_session.flush()
    assert await extraction_metering.preflight_gate(db_session, principal=p) is True


async def test_preflight_open_for_guest(db_session) -> None:
    guest = Principal(user_id=None, persona="guest")
    assert await extraction_metering.preflight_gate(db_session, principal=guest) is False
