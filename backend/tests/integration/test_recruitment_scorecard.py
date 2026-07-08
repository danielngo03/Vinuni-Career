"""Scorecard evaluation tests (ADR-0005 §7 first slice).

Covers the partner-internal scorecard surface layered on the ADR-0004 stage engine:

- submit happy path (scores -> overall mean + recommendation); upsert edits own
  (version bump, no duplicate row); a second reviewer creates a separate row.
- ANCHORING (BUSINESS_LOGIC §3.4): reviewer B cannot see A's scores until B
  submits their own for that stage (only the submitted COUNT before then).
- withdraw is author-only + excluded from the gate and the aggregate.
- required_action=scorecard advance gate: 0 -> 409 scorecard_required
  ({submitted:0, required:1}); >= 1 -> advances; a manual stage is unaffected.
- cross-org submit/list -> 404; missing/invalid recommendation or score -> 422.
- ANONYMITY: the student application projection carries NO scorecard/evaluation
  field after a submit; reviewer identity is a partner member, not the student.
- audit row per submit / update / withdraw; the board aggregate is partner-only
  and gate_met is correct.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    pipeline_board,
    scorecard_service,
    stage_service,
)
from app.modules.recruitment.application.errors import (
    IllegalApplicationTransitionError,
    InvalidApplicationFieldError,
    ScorecardRequiredError,
)
from app.modules.recruitment.domain import scorecard
from app.modules.recruitment.domain.models import (
    PipelineStage,
    Scorecard,
    ScorecardScore,
)
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _scores(*, technical=4, communication=4, culture_fit=4, motivation=4) -> list[dict]:
    return [
        {"criterion_key": "technical", "score": technical},
        {"criterion_key": "communication", "score": communication},
        {"criterion_key": "culture_fit", "score": culture_fit},
        {"criterion_key": "motivation", "score": motivation},
    ]


async def _setup_reviewed(db, *, is_anonymous=False):
    """Published job + applied + reviewed (candidate ACTIVE at stage 1)."""

    pu, porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=partner, uni_principal=uni)

    su, student = await make_student(db, prefix="student")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=is_anonymous),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db, principal=partner, application_id=app_id, ctx=CTX
    )
    return porg, partner, su, student, job_id, app_id


async def _current_stage(db, app_id) -> PipelineStage:
    active = await stage_service._active_stage(db, application_id=app_id)
    assert active is not None
    return (
        await db.execute(select(PipelineStage).where(PipelineStage.id == active.stage_id))
    ).scalar_one()


async def _set_current_action(db, app_id, action: str) -> None:
    stage = await _current_stage(db, app_id)
    stage.required_action = action
    await db.commit()


async def _scorecard_rows(db, app_id) -> list[Scorecard]:
    return list(
        (
            await db.execute(
                select(Scorecard).where(Scorecard.application_id == app_id)
            )
        ).scalars().all()
    )


async def _score_rows_for(db, scorecard_id) -> list[ScorecardScore]:
    return list(
        (
            await db.execute(
                select(ScorecardScore).where(
                    ScorecardScore.scorecard_id == scorecard_id
                )
            )
        ).scalars().all()
    )


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _second_reviewer(db, org):
    _u, _m, principal = await add_member(
        db,
        org=org,
        permissions=[
            ("applications", "read"),
            ("scorecards", "submit"),
            ("scorecards", "read"),
        ],
    )
    return principal


# --------------------------------------------------------------------------- #
# Submit + upsert + overall                                                    #
# --------------------------------------------------------------------------- #


async def test_submit_creates_scorecard_with_overall_mean(db_session) -> None:
    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)

    out = await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="strong_yes",
        scores=_scores(technical=5, communication=4, culture_fit=3, motivation=2),
        comment="Solid candidate.", ctx=CTX,
    )
    assert out["mine"]["recommendation"] == "strong_yes"
    assert out["mine"]["overall_score"] == 3.5  # mean(5,4,3,2)
    assert out["mine"]["is_mine"] is True
    assert {s["criterion_key"] for s in out["mine"]["scores"]} == scorecard.DEFAULT_CRITERION_KEYS
    assert out["aggregate"]["submitted_count"] == 1

    rows = await _scorecard_rows(db_session, app_id)
    assert len(rows) == 1
    assert rows[0].status == scorecard.SCORECARD_SUBMITTED
    assert len(await _score_rows_for(db_session, rows[0].id)) == 4
    assert await _audit_count(db_session, "application.scorecard_submitted") == 1


async def test_resubmit_upserts_same_row_and_bumps_version(db_session) -> None:
    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="yes", scores=_scores(technical=3), ctx=CTX,
    )
    out2 = await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="strong_yes", scores=_scores(technical=5, communication=5,
        culture_fit=5, motivation=5), ctx=CTX,
    )
    # Same single row, edited in place; version bumped; scores replaced (no dupes).
    rows = await _scorecard_rows(db_session, app_id)
    assert len(rows) == 1
    assert rows[0].version == 2
    assert rows[0].recommendation == "strong_yes"
    assert out2["mine"]["overall_score"] == 5.0
    assert len(await _score_rows_for(db_session, rows[0].id)) == 4
    assert await _audit_count(db_session, "application.scorecard_submitted") == 1
    assert await _audit_count(db_session, "application.scorecard_updated") == 1


async def test_second_reviewer_creates_distinct_row(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    reviewer_b = await _second_reviewer(db_session, org)

    await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    out = await scorecard_service.submit_scorecard(
        db_session, principal=reviewer_b, application_id=app_id,
        recommendation="no", scores=_scores(technical=2), ctx=CTX,
    )
    rows = await _scorecard_rows(db_session, app_id)
    assert len(rows) == 2
    assert {r.submitted_by_user_id for r in rows} == {partner.user_id, reviewer_b.user_id}
    # B has submitted -> B sees A among "scorecards"; aggregate counts both.
    assert out["aggregate"]["submitted_count"] == 2
    assert len(out["scorecards"]) == 1


# --------------------------------------------------------------------------- #
# Anchoring-bias visibility (BUSINESS_LOGIC §3.4)                              #
# --------------------------------------------------------------------------- #


async def test_anchoring_hides_others_until_caller_submits(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    reviewer_b = await _second_reviewer(db_session, org)

    await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="strong_yes", scores=_scores(technical=5), ctx=CTX,
    )

    # B has NOT submitted: sees only the round-progress count, never A's scores.
    before = await scorecard_service.list_scorecards(
        db_session, principal=reviewer_b, application_id=app_id
    )
    assert before["mine"] is None
    assert before["scorecards"] == []  # A's card is hidden
    assert before["aggregate"]["submitted_count"] == 1  # knows the round is open
    assert before["aggregate"]["avg_overall"] is None  # score-derived fields withheld
    assert before["aggregate"]["recommendation_summary"] == {}

    # B submits -> now sees A's scorecard + the full aggregate.
    await scorecard_service.submit_scorecard(
        db_session, principal=reviewer_b, application_id=app_id,
        recommendation="no", scores=_scores(technical=2), ctx=CTX,
    )
    after = await scorecard_service.list_scorecards(
        db_session, principal=reviewer_b, application_id=app_id
    )
    assert after["mine"] is not None
    assert len(after["scorecards"]) == 1
    assert after["aggregate"]["submitted_count"] == 2
    assert after["aggregate"]["avg_overall"] is not None
    assert after["aggregate"]["recommendation_summary"]["strong_yes"] == 1


# --------------------------------------------------------------------------- #
# Withdraw                                                                     #
# --------------------------------------------------------------------------- #


async def test_withdraw_excludes_from_gate_and_aggregate(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    await _set_current_action(db_session, app_id, scorecard.ACTION_SCORECARD)

    out = await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    sc_id = uuid.UUID(out["mine"]["id"])
    assert out["aggregate"]["gate_met"] is True

    res = await scorecard_service.withdraw_scorecard(
        db_session, principal=partner, application_id=app_id, scorecard_id=sc_id, ctx=CTX,
    )
    assert res["mine"] is None
    assert res["aggregate"]["submitted_count"] == 0
    assert res["aggregate"]["gate_met"] is False

    # Row retained (soft) for audit; advance now blocked again.
    rows = await _scorecard_rows(db_session, app_id)
    assert len(rows) == 1 and rows[0].status == scorecard.SCORECARD_WITHDRAWN
    assert await _audit_count(db_session, "application.scorecard_withdrawn") == 1
    with pytest.raises(ScorecardRequiredError):
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )


async def test_withdraw_other_reviewers_card_is_404(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    reviewer_b = await _second_reviewer(db_session, org)
    out = await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    sc_id = uuid.UUID(out["mine"]["id"])
    # B may not withdraw A's scorecard — indistinguishable from not found.
    with pytest.raises(ResourceNotFoundError):
        await scorecard_service.withdraw_scorecard(
            db_session, principal=reviewer_b, application_id=app_id,
            scorecard_id=sc_id, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Advance gate (required_action = scorecard)                                   #
# --------------------------------------------------------------------------- #


async def test_advance_blocked_without_scorecard_then_allowed(db_session) -> None:
    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    await _set_current_action(db_session, app_id, scorecard.ACTION_SCORECARD)

    with pytest.raises(ScorecardRequiredError) as exc:
        await stage_service.advance_application_stage(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )
    assert exc.value.details == {
        "reason": "scorecard_required", "submitted": 0, "required": 1,
    }

    # Submit one scorecard on the current (scorecard-gated) stage -> gate met.
    await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    out = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out["pipeline"]["position"] == 2


async def test_manual_stage_advance_unaffected(db_session) -> None:
    """The seeded ladder is all-manual; advance must not require a scorecard."""

    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    out = await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out["pipeline"]["position"] == 2
    # No scorecard rows were needed or created.
    assert await _scorecard_rows(db_session, app_id) == []


# --------------------------------------------------------------------------- #
# RBAC / validation                                                           #
# --------------------------------------------------------------------------- #


async def test_cross_org_submit_and_list_are_404(db_session) -> None:
    _org, _partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    _bu, _borg, partner_b = await make_org_with_admin(db_session, display_name="Org B")

    with pytest.raises(ResourceNotFoundError):
        await scorecard_service.submit_scorecard(
            db_session, principal=partner_b, application_id=app_id,
            recommendation="yes", scores=_scores(), ctx=CTX,
        )
    with pytest.raises(ResourceNotFoundError):
        await scorecard_service.list_scorecards(
            db_session, principal=partner_b, application_id=app_id
        )


async def test_invalid_recommendation_is_422(db_session) -> None:
    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    with pytest.raises(InvalidApplicationFieldError):
        await scorecard_service.submit_scorecard(
            db_session, principal=partner, application_id=app_id,
            recommendation="maybe", scores=_scores(), ctx=CTX,
        )


async def test_missing_criterion_is_422(db_session) -> None:
    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    partial = _scores()[:3]  # only 3 of the 4 required criteria
    with pytest.raises(InvalidApplicationFieldError):
        await scorecard_service.submit_scorecard(
            db_session, principal=partner, application_id=app_id,
            recommendation="yes", scores=partial, ctx=CTX,
        )


async def test_score_out_of_range_is_422(db_session) -> None:
    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    with pytest.raises(InvalidApplicationFieldError):
        await scorecard_service.submit_scorecard(
            db_session, principal=partner, application_id=app_id,
            recommendation="yes", scores=_scores(technical=6), ctx=CTX,
        )


async def test_submit_requires_active_stage(db_session) -> None:
    """A submitted (never-reviewed) app has no active stage -> 409."""

    pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)
    su, student = await make_student(db_session, prefix="student")
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    with pytest.raises(IllegalApplicationTransitionError):
        await scorecard_service.submit_scorecard(
            db_session, principal=partner, application_id=uuid.UUID(app["id"]),
            recommendation="yes", scores=_scores(), ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Anonymity / partner-only board                                              #
# --------------------------------------------------------------------------- #


async def test_student_projection_has_no_evaluation(db_session) -> None:
    _org, partner, _su, student, _job, app_id = await _setup_reviewed(db_session)
    await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="strong_yes", scores=_scores(technical=5),
        comment="internal note", ctx=CTX,
    )
    # The student's own application view must carry NO scorecard/evaluation field.
    view = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    assert "pipeline" not in view
    assert "evaluation" not in view
    blob = str(view).lower()
    assert "scorecard" not in blob
    assert "recommendation" not in blob
    assert "strong_yes" not in blob
    assert "internal note" not in blob


async def test_partner_projection_carries_evaluation(db_session) -> None:
    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    await _set_current_action(db_session, app_id, scorecard.ACTION_SCORECARD)
    # Partner detail before a scorecard -> gate not met.
    view = await apply_service.get_application(
        db_session, principal=partner, application_id=app_id
    )
    assert view["pipeline"]["evaluation"]["gate_met"] is False
    assert view["pipeline"]["current_stage"]["required_action"] == scorecard.ACTION_SCORECARD


async def test_board_evaluation_partner_only_and_gate_met(db_session) -> None:
    _org, partner, _su, _student, job_id, app_id = await _setup_reviewed(db_session)
    await _set_current_action(db_session, app_id, scorecard.ACTION_SCORECARD)

    board = await pipeline_board.get_job_pipeline_board(
        db_session, principal=partner, job_id=job_id
    )
    card = _find_card(board, app_id)
    assert card["evaluation"]["gate_met"] is False
    assert card["evaluation"]["submitted_count"] == 0

    await scorecard_service.submit_scorecard(
        db_session, principal=partner, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    board2 = await pipeline_board.get_job_pipeline_board(
        db_session, principal=partner, job_id=job_id
    )
    card2 = _find_card(board2, app_id)
    assert card2["evaluation"]["gate_met"] is True
    assert card2["evaluation"]["submitted_count"] == 1


def _find_card(board: dict, app_id: uuid.UUID) -> dict:
    for column in board["columns"]:
        for card in column["candidates"]:
            if card["application_id"] == str(app_id):
                return card
    raise AssertionError("card not found on board")


async def test_advance_gate_required_unchanged_for_manual(db_session) -> None:
    """``pipeline.action_satisfied`` legacy stays manual-only; the gate honors it."""

    _org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    stage = await _current_stage(db_session, app_id)
    gate = await scorecard_service.evaluate_advance_gate(
        db_session, application_id=app_id, stage=stage
    )
    assert gate.allowed is True and gate.required == 0
