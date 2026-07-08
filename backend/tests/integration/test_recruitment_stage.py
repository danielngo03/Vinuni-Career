"""Pipeline stage engine tests (ADR-0004 §6.6): /advance + /rollback.

Covers the foundational stage engine layered on the shipped review/reject subset:

- Happy-path advance through the seeded 3-stage ladder.
- Advance past the last stage -> 409; advance/rollback when not under_review -> 409.
- Rollback appends a ROLLED_BACK row + reopens at the prior stage; reason < 20 ->
  422; illegal (non-prior) target -> 409; 4th rollback -> 409.
- Optimistic version conflict -> 409; Idempotency-Key replay does not double-move.
- Cross-org -> 404.
- Anonymity preserved across advance/rollback (partner view stays redacted).
- Neutral student notification (no coded move/reason leaked; silent on a
  candidate_visible=false target).
- One audit row per move; review materializes stage-1; reject closes the row.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.notifications.domain.models import Notification
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    stage_service,
)
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    IllegalApplicationTransitionError,
    InvalidApplicationFieldError,
    RollbackLimitReachedError,
)
from app.modules.recruitment.domain import pipeline
from app.modules.recruitment.domain.models import CandidateStage, PipelineStage
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


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
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=is_anonymous),
        ctx=CTX,
    )
    return su, student, uuid.UUID(app["id"])


async def _stage_rows(db, app_id) -> list[CandidateStage]:
    return list(
        (
            await db.execute(
                select(CandidateStage)
                .where(CandidateStage.application_id == app_id)
                .order_by(CandidateStage.entered_at, CandidateStage.id)
            )
        ).scalars().all()
    )


async def _active_row(db, app_id) -> CandidateStage | None:
    return (
        await db.execute(
            select(CandidateStage).where(
                CandidateStage.application_id == app_id,
                CandidateStage.status == pipeline.STAGE_ACTIVE,
            )
        )
    ).scalars().first()


async def _stage(db, stage_id) -> PipelineStage:
    return (
        await db.execute(select(PipelineStage).where(PipelineStage.id == stage_id))
    ).scalar_one()


async def _template_stages_for_app(db, app_id) -> list[PipelineStage]:
    active = await _active_row(db, app_id)
    assert active is not None
    stage = await _stage(db, active.stage_id)
    return list(
        (
            await db.execute(
                select(PipelineStage)
                .where(PipelineStage.template_id == stage.template_id)
                .order_by(PipelineStage.sort_order)
            )
        ).scalars().all()
    )


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _feed_rows(db, *, recipient_id, notif_type) -> list[Notification]:
    return list(
        (
            await db.execute(
                select(Notification).where(
                    Notification.recipient_id == recipient_id,
                    Notification.notif_type == notif_type,
                )
            )
        ).scalars().all()
    )


# --------------------------------------------------------------------------- #
# Review materializes stage-1 / reject closes the stage row                   #
# --------------------------------------------------------------------------- #


async def test_review_materializes_stage_one(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)

    # Before review: no candidate_stages row.
    assert await _stage_rows(db_session, app_id) == []

    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    active = await _active_row(db_session, app_id)
    assert active is not None
    stage = await _stage(db_session, active.stage_id)
    assert stage.sort_order == 1 and stage.stage_type == "screening"


async def test_double_review_does_not_reset_position(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    # A re-review must NOT reset an advanced candidate back to stage 1.
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    active = await _active_row(db_session, app_id)
    stage = await _stage(db_session, active.stage_id)
    assert stage.sort_order == 2


async def test_reject_closes_open_stage_row(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await decision_service.reject_application(
        db_session, principal=partner, application_id=app_id,
        reason="not_qualified", ctx=CTX,
    )
    assert await _active_row(db_session, app_id) is None
    rows = await _stage_rows(db_session, app_id)
    assert len(rows) == 1
    assert rows[0].status == pipeline.STAGE_REJECTED
    assert rows[0].exit_kind == pipeline.EXIT_REJECTED
    assert rows[0].exited_at is not None


# --------------------------------------------------------------------------- #
# Advance happy path through the ladder                                        #
# --------------------------------------------------------------------------- #


async def test_advance_through_ladder(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )

    out1 = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out1["pipeline"]["position"] == 2
    assert out1["pipeline"]["current_stage"]["stage_type"] == "interview"
    assert out1["status"] == "under_review"  # coarse outcome unchanged

    out2 = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out2["pipeline"]["position"] == 3
    assert out2["pipeline"]["current_stage"]["is_terminal"] is True

    # History: stage1 PASSED, stage2 PASSED, stage3 ACTIVE.
    rows = await _stage_rows(db_session, app_id)
    assert [r.status for r in rows] == [
        pipeline.STAGE_PASSED, pipeline.STAGE_PASSED, pipeline.STAGE_ACTIVE
    ]
    assert await _audit_count(db_session, "application.stage_advanced") == 2

    # Student got a neutral advance notification (no internal stage/code leak).
    feed = await _feed_rows(
        db_session, recipient_id=su.id, notif_type="recruitment.application_stage_advanced"
    )
    assert len(feed) == 2
    blob = " ".join(f"{r.title} {r.body}" for r in feed)
    assert "interview" not in blob.lower() and "advance" not in blob.lower()


async def test_advance_from_no_active_row_lands_at_stage_one(db_session) -> None:
    """Pre-pipeline bug regression (ADR-0004 §2).

    An under_review application with NO ACTIVE candidate_stages row (the kanban
    "new" / pre-pipeline bucket — legacy apps reviewed before the stage engine, or
    any under_review app lacking a stage row) must land at STAGE 1 on the first
    advance (materialize-only), NOT skip to stage 2. A SECOND advance then moves to
    stage 2.
    """

    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )

    # Simulate the pre-pipeline state: under_review but with NO candidate_stages
    # row at all (e.g. reviewed before the stage engine existed). Delete the row
    # the review hook materialized so the next advance starts from no active row.
    for row in await _stage_rows(db_session, app_id):
        await db_session.delete(row)
    await db_session.commit()
    assert await _active_row(db_session, app_id) is None

    # First advance -> MATERIALIZE stage 1 and LAND there (must not skip to 2).
    out1 = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out1["pipeline"]["position"] == 1
    assert out1["pipeline"]["current_stage"]["sort_order"] == 1
    assert out1["pipeline"]["current_stage"]["stage_type"] == "screening"
    assert out1["status"] == "under_review"

    rows = await _stage_rows(db_session, app_id)
    assert [r.status for r in rows] == [pipeline.STAGE_ACTIVE]
    assert await _audit_count(db_session, "application.stage_advanced") == 1

    # Stage 1 is candidate-visible -> the student got the neutral notification.
    feed = await _feed_rows(
        db_session, recipient_id=su.id,
        notif_type="recruitment.application_stage_advanced",
    )
    assert len(feed) == 1

    # SECOND advance -> now moves stage 1 -> stage 2.
    out2 = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out2["pipeline"]["position"] == 2
    assert out2["pipeline"]["current_stage"]["stage_type"] == "interview"
    rows2 = await _stage_rows(db_session, app_id)
    assert [r.status for r in rows2] == [
        pipeline.STAGE_PASSED, pipeline.STAGE_ACTIVE
    ]


async def test_advance_no_row_submitted_is_409(db_session) -> None:
    """A submitted (never-reviewed) app has no stage row AND is not under_review;
    advance must still 409 — the materialize-on-first-advance entry only applies
    once the app is under_review."""

    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    assert await _stage_rows(db_session, app_id) == []
    with pytest.raises(IllegalApplicationTransitionError):
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )


async def test_advance_past_last_stage_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    # At the terminal Offer stage -> no next stage.
    with pytest.raises(IllegalApplicationTransitionError):
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )


async def test_advance_requires_under_review(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student, app_id = await _apply(db_session, job_id=job_id)
    # submitted (never reviewed) -> advance illegal.
    with pytest.raises(IllegalApplicationTransitionError):
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )
    # withdrawn -> advance illegal.
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id, ctx=CTX
    )
    with pytest.raises(IllegalApplicationTransitionError):
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )


async def test_advance_when_rejected_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await decision_service.reject_application(
        db_session, principal=partner, application_id=app_id,
        reason="position_filled", ctx=CTX,
    )
    with pytest.raises(IllegalApplicationTransitionError):
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Rollback                                                                     #
# --------------------------------------------------------------------------- #

_GOOD_REASON = "Cần phỏng vấn lại để đánh giá kỹ năng kỹ thuật."  # >= 20 chars


async def test_rollback_reopens_prior_stage(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )  # now at stage 2
    stages = await _template_stages_for_app(db_session, app_id)
    stage1_id = stages[0].id

    out = await stage_service.rollback_application_stage(
        db_session, principal=partner, application_id=app_id,
        target_stage_id=stage1_id, reason=_GOOD_REASON, ctx=CTX,
    )
    assert out["pipeline"]["position"] == 1
    assert out["pipeline"]["rollback_count"] == 1

    rows = await _stage_rows(db_session, app_id)
    # stage1 PASSED, stage2 ROLLED_BACK, stage1(new) ACTIVE.
    assert [r.status for r in rows] == [
        pipeline.STAGE_PASSED, pipeline.STAGE_ROLLED_BACK, pipeline.STAGE_ACTIVE
    ]
    rolled = rows[1]
    assert rolled.exit_kind == pipeline.EXIT_ROLLED_BACK
    assert rolled.reason == _GOOD_REASON
    assert await _audit_count(db_session, "application.stage_rolled_back") == 1

    # Student got the neutral re-review notification; the reason is NOT leaked.
    feed = await _feed_rows(
        db_session, recipient_id=su.id, notif_type="recruitment.application_under_rereview"
    )
    assert len(feed) == 1
    assert _GOOD_REASON not in f"{feed[0].title} {feed[0].body}"


async def test_rollback_reason_too_short_is_422(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    stages = await _template_stages_for_app(db_session, app_id)
    with pytest.raises(InvalidApplicationFieldError):
        await stage_service.rollback_application_stage(
            db_session, principal=partner, application_id=app_id,
            target_stage_id=stages[0].id, reason="too short", ctx=CTX,
        )


def test_rollback_schema_enforces_min_reason() -> None:
    from app.modules.recruitment.api.schemas import RollbackRequestBody
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RollbackRequestBody(target_stage_id=uuid.uuid4(), reason="short")
    ok = RollbackRequestBody(
        target_stage_id=uuid.uuid4(), reason=_GOOD_REASON, version=2
    )
    assert ok.version == 2


async def test_rollback_to_non_prior_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )  # at stage 1
    stages = await _template_stages_for_app(db_session, app_id)
    # Rollback to a LATER stage (stage 2) from stage 1 -> illegal.
    with pytest.raises(IllegalApplicationTransitionError):
        await stage_service.rollback_application_stage(
            db_session, principal=partner, application_id=app_id,
            target_stage_id=stages[1].id, reason=_GOOD_REASON, ctx=CTX,
        )
    # Rollback to the CURRENT stage (stage 1) -> illegal (not strictly prior).
    with pytest.raises(IllegalApplicationTransitionError):
        await stage_service.rollback_application_stage(
            db_session, principal=partner, application_id=app_id,
            target_stage_id=stages[0].id, reason=_GOOD_REASON, ctx=CTX,
        )


async def test_fourth_rollback_is_blocked(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    stages = await _template_stages_for_app(db_session, app_id)
    stage1_id = stages[0].id
    for _ in range(pipeline.MAX_ROLLBACKS):
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )
        await stage_service.rollback_application_stage(
            db_session, principal=partner, application_id=app_id,
            target_stage_id=stage1_id, reason=_GOOD_REASON, ctx=CTX,
        )
    # 4th rollback -> blocked (admin approval deferred).
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    with pytest.raises(RollbackLimitReachedError):
        await stage_service.rollback_application_stage(
            db_session, principal=partner, application_id=app_id,
            target_stage_id=stage1_id, reason=_GOOD_REASON, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Optimistic version / idempotency / cross-org                                #
# --------------------------------------------------------------------------- #


async def test_advance_version_conflict_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    with pytest.raises(ApplicationVersionConflictError):
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, version=999, ctx=CTX
        )


async def test_advance_idempotency_key_no_double_move(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    key = uuid.uuid4().hex
    out1 = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id,
        idempotency_key=key, ctx=CTX,
    )
    # Replay with the SAME key (stale version) returns the applied state, no 409,
    # no double advance.
    out2 = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id,
        idempotency_key=key, version=1, ctx=CTX,
    )
    assert out1["pipeline"]["position"] == out2["pipeline"]["position"] == 2
    # Exactly one move happened: one PASSED + one ACTIVE.
    rows = await _stage_rows(db_session, app_id)
    assert sum(r.status == pipeline.STAGE_ACTIVE for r in rows) == 1
    assert sum(r.status == pipeline.STAGE_PASSED for r in rows) == 1
    assert await _audit_count(db_session, "application.stage_advanced") == 1


async def test_cross_org_partner_gets_404(db_session) -> None:
    partner_a, _uni, job_id = await _setup_published(db_session, title="A Job")
    _pb_u, _pb_org, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner_a, application_id=app_id, ctx=CTX
    )
    with pytest.raises(ResourceNotFoundError):
        await stage_service.advance_application_stage(
            db_session, principal=partner_b, application_id=app_id, ctx=CTX
        )
    with pytest.raises(ResourceNotFoundError):
        await stage_service.rollback_application_stage(
            db_session, principal=partner_b, application_id=app_id,
            target_stage_id=uuid.uuid4(), reason=_GOOD_REASON, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Anonymity preserved across stage moves                                       #
# --------------------------------------------------------------------------- #


async def test_anonymity_preserved_across_moves(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id, is_anonymous=True)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    adv = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert adv["applicant"]["is_anonymous"] is True
    assert adv["applicant"]["revealed"] is False
    assert "email" not in adv["applicant"] and "user_id" not in adv["applicant"]
    assert su.email not in str(adv)

    stages = await _template_stages_for_app(db_session, app_id)
    rb = await stage_service.rollback_application_stage(
        db_session, principal=partner, application_id=app_id,
        target_stage_id=stages[0].id, reason=_GOOD_REASON, ctx=CTX,
    )
    assert rb["applicant"]["revealed"] is False
    assert su.email not in str(rb)

    # The partner detail view is likewise still redacted after the moves.
    view = await apply_service.get_application(
        db_session, principal=partner, application_id=app_id
    )
    assert view["applicant"]["revealed"] is False
    assert su.email not in str(view)


# --------------------------------------------------------------------------- #
# Silent notification when the target stage is not candidate-visible           #
# --------------------------------------------------------------------------- #


async def test_advance_into_hidden_stage_is_silent(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    # Hide stage 2 from candidates, then advance into it.
    stages = await _template_stages_for_app(db_session, app_id)
    stage2 = await _stage(db_session, stages[1].id)
    stage2.candidate_visible = False
    await db_session.commit()

    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    feed = await _feed_rows(
        db_session, recipient_id=su.id, notif_type="recruitment.application_stage_advanced"
    )
    assert feed == []  # silent: target stage not candidate-visible
    # The move itself still happened + was audited.
    assert await _audit_count(db_session, "application.stage_advanced") == 1
