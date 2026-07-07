"""Bulk-advance pipeline action (``docs/BUSINESS_LOGIC.md`` §3.6).

``decision_service.bulk_advance_applications`` runs the SAME gated per-item
transaction as ``stage_service.advance_application_stage`` for a batch of
candidates. These tests cover the wrapper's aggregation + per-item ``results``
contract and its safety invariants:

- happy path: every under_review candidate moves one stage; counts + results.
- mixed: a still-``submitted`` (not under_review) candidate is ``skipped``
  (``not_advanceable``) — never force-advanced.
- gate: a stage whose ``required_action = scorecard`` is unmet reports the
  candidate as ``blocked`` (``scorecard_required``) and does NOT advance it.
- idempotency: a batch ``Idempotency-Key`` replay does not double-advance.
- tenant isolation: a cross-org application id is ``skipped`` (``not_found``),
  never advanced and never enumerable.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    stage_service,
)
from app.modules.recruitment.domain import pipeline, scorecard
from app.modules.recruitment.domain.models import CandidateStage, PipelineStage
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _setup_published(db, *, title="Live Job", **over):
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title, **over
    )
    return partner, uni, job_id


async def _apply(db, *, job_id, prefix="student", is_anonymous=False):
    su, student = await make_student(db, prefix=prefix)
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=is_anonymous),
        ctx=CTX,
    )
    return su, student, uuid.UUID(app["id"])


async def _reviewed(db, *, job_id, partner, prefix):
    """Apply + move to under_review (materializes stage-1)."""
    _su, _student, app_id = await _apply(db, job_id=job_id, prefix=prefix)
    await decision_service.review_application(
        db, principal=partner, application_id=app_id, ctx=CTX
    )
    return app_id


async def _active_stage_order(db, app_id) -> int | None:
    active = (
        await db.execute(
            select(CandidateStage).where(
                CandidateStage.application_id == app_id,
                CandidateStage.status == pipeline.STAGE_ACTIVE,
            )
        )
    ).scalars().first()
    if active is None:
        return None
    stage = (
        await db.execute(select(PipelineStage).where(PipelineStage.id == active.stage_id))
    ).scalar_one()
    return stage.sort_order


async def _set_current_action(db, app_id, action: str) -> None:
    active = await stage_service._active_stage(db, application_id=app_id)
    assert active is not None
    stage = (
        await db.execute(select(PipelineStage).where(PipelineStage.id == active.stage_id))
    ).scalar_one()
    stage.required_action = action
    await db.commit()


# --------------------------------------------------------------------------- #
# Happy path                                                                   #
# --------------------------------------------------------------------------- #


async def test_bulk_advance_moves_all_reviewed(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    a1 = await _reviewed(db_session, job_id=job_id, partner=partner, prefix="s1")
    a2 = await _reviewed(db_session, job_id=job_id, partner=partner, prefix="s2")

    out = await decision_service.bulk_advance_applications(
        db_session, principal=partner, application_ids=[a1, a2], ctx=CTX
    )

    assert out["advanced"] == 2
    assert out["blocked"] == 0 and out["skipped"] == 0 and out["errors"] == 0
    assert {r["outcome"] for r in out["results"]} == {"advanced"}
    assert await _active_stage_order(db_session, a1) == 2
    assert await _active_stage_order(db_session, a2) == 2


# --------------------------------------------------------------------------- #
# Mixed: a submitted (not under_review) candidate is skipped, not advanced     #
# --------------------------------------------------------------------------- #


async def test_bulk_advance_skips_not_under_review(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    reviewed = await _reviewed(db_session, job_id=job_id, partner=partner, prefix="ok")
    # Applied but NOT reviewed -> still `submitted`, not advanceable.
    _su, _student, submitted = await _apply(db_session, job_id=job_id, prefix="raw")

    out = await decision_service.bulk_advance_applications(
        db_session, principal=partner, application_ids=[reviewed, submitted], ctx=CTX
    )

    assert out["advanced"] == 1 and out["skipped"] == 1
    by_id = {r["application_id"]: r for r in out["results"]}
    assert by_id[str(reviewed)]["outcome"] == "advanced"
    assert by_id[str(submitted)]["outcome"] == "skipped"
    assert by_id[str(submitted)]["reason"] == "not_advanceable"
    # The submitted candidate never entered the pipeline.
    assert await _active_stage_order(db_session, submitted) is None


# --------------------------------------------------------------------------- #
# Gate: an unmet scorecard gate blocks (never force-advances)                  #
# --------------------------------------------------------------------------- #


async def test_bulk_advance_blocked_by_scorecard_gate(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    gated = await _reviewed(db_session, job_id=job_id, partner=partner, prefix="gate")
    await _set_current_action(db_session, gated, scorecard.ACTION_SCORECARD)

    out = await decision_service.bulk_advance_applications(
        db_session, principal=partner, application_ids=[gated], ctx=CTX
    )

    assert out["advanced"] == 0 and out["blocked"] == 1
    res = out["results"][0]
    assert res["outcome"] == "blocked"
    assert res["reason"] == "scorecard_required"
    assert res["submitted"] == 0 and res["required"] >= 1
    # The candidate stays put — the gate is never bypassed.
    assert await _active_stage_order(db_session, gated) == 1


# --------------------------------------------------------------------------- #
# Idempotency: a batch key replay does not double-advance                      #
# --------------------------------------------------------------------------- #


async def test_bulk_advance_idempotency_key_no_double_move(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    app_id = await _reviewed(db_session, job_id=job_id, partner=partner, prefix="idem")

    key = "batch-abc"
    await decision_service.bulk_advance_applications(
        db_session, principal=partner, application_ids=[app_id], ctx=CTX, idempotency_key=key
    )
    assert await _active_stage_order(db_session, app_id) == 2

    # Replay with the SAME batch key -> the item is deduped, position unchanged.
    out = await decision_service.bulk_advance_applications(
        db_session, principal=partner, application_ids=[app_id], ctx=CTX, idempotency_key=key
    )
    assert await _active_stage_order(db_session, app_id) == 2
    assert out["errors"] == 0


# --------------------------------------------------------------------------- #
# Tenant isolation: a cross-org id is skipped (not_found), never advanced      #
# --------------------------------------------------------------------------- #


async def test_bulk_advance_cross_org_skipped(db_session) -> None:
    partner_a, _uni, job_a = await _setup_published(db_session, title="A")
    # A separate partner org with its own reviewed application.
    partner_b, _uni_b, job_b = await _setup_published(db_session, title="B")
    foreign = await _reviewed(db_session, job_id=job_b, partner=partner_b, prefix="b1")
    mine = await _reviewed(db_session, job_id=job_a, partner=partner_a, prefix="a1")

    out = await decision_service.bulk_advance_applications(
        db_session, principal=partner_a, application_ids=[mine, foreign], ctx=CTX
    )

    assert out["advanced"] == 1 and out["skipped"] == 1
    by_id = {r["application_id"]: r for r in out["results"]}
    assert by_id[str(mine)]["outcome"] == "advanced"
    assert by_id[str(foreign)]["outcome"] == "skipped"
    assert by_id[str(foreign)]["reason"] == "not_found"
    # The foreign candidate was NOT advanced by the cross-org caller.
    assert await _active_stage_order(db_session, foreign) == 1
