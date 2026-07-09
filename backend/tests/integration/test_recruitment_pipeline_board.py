"""Partner pipeline kanban board read model (``GET /jobs/{job_id}/pipeline``).

Covers the board facade layered on the stage engine (ADR-0004 kanban data note):

- the board returns the template stages (columns) + a pre-pipeline "new" bucket;
- a submitted-but-unreviewed application lands in the "new" bucket (never lost);
- a reviewed candidate appears under its current stage; an advanced candidate
  moves buckets;
- terminal outcomes (rejected/withdrawn) drop off the active board;
- cross-org -> 404 (indistinguishable from missing);
- anonymity is preserved: pre-reveal a card carries only the ``UV-xxxx`` handle —
  never a name/email — and the revealed identity appears only after accept;
- the column COUNTS derive from ``candidate_stages`` ACTIVE rows (the
  proj_partner_pipeline fix), not ``applications.status``;
- the board loads in a BOUNDED number of queries (no per-application N+1).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    pipeline_board,
    reveal_service,
    stage_service,
)
from app.modules.recruitment.domain.models import PipelineStage
from app.shared.exceptions import ResourceNotFoundError
from sqlalchemy import event, select

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
        db,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=is_anonymous),
        ctx=CTX,
    )
    return su, student, uuid.UUID(app["id"])


async def _template_stages_for_app(db, app_id) -> list[PipelineStage]:
    from app.modules.recruitment.domain import pipeline
    from app.modules.recruitment.domain.models import CandidateStage

    active = (
        (
            await db.execute(
                select(CandidateStage).where(
                    CandidateStage.application_id == app_id,
                    CandidateStage.status == pipeline.STAGE_ACTIVE,
                )
            )
        )
        .scalars()
        .first()
    )
    assert active is not None
    stage = (
        await db.execute(select(PipelineStage).where(PipelineStage.id == active.stage_id))
    ).scalar_one()
    return list(
        (
            await db.execute(
                select(PipelineStage)
                .where(PipelineStage.template_id == stage.template_id)
                .order_by(PipelineStage.sort_order)
            )
        )
        .scalars()
        .all()
    )


def _column(board: dict, *, key: str) -> dict:
    return next(c for c in board["columns"] if c["key"] == key)


def _stage_column(board: dict, *, sort_order: int) -> dict:
    return next(c for c in board["columns"] if c.get("sort_order") == sort_order and c["stage_id"])


def _all_card_app_ids(board: dict) -> set[str]:
    return {card["application_id"] for col in board["columns"] for card in col["candidates"]}


@contextmanager
def _count_queries(db):
    """Count SQL statements executed on the session's sync engine."""

    counter = {"n": 0}
    engine = db.bind.sync_engine

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before)


async def _board(db, *, partner, job_id):
    return await pipeline_board.get_job_pipeline_board(db, principal=partner, job_id=job_id)


# --------------------------------------------------------------------------- #
# Columns + new bucket                                                         #
# --------------------------------------------------------------------------- #


async def test_board_returns_stages_and_new_bucket(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    board = await _board(db_session, partner=partner, job_id=job_id)

    # The seeded 3-stage ladder = three stage columns + a leading "new" column.
    assert [s["sort_order"] for s in board["stages"]] == [1, 2, 3]
    assert board["columns"][0]["key"] == "new"
    assert [c["stage_id"] is not None for c in board["columns"][1:]] == [True, True, True]
    assert board["job"]["id"] == str(job_id)
    assert board["candidate_cap"] == pipeline_board.BOARD_CANDIDATE_CAP
    assert board["truncated"] is False
    # Empty board: every column has zero candidates.
    assert all(col["count"] == 0 for col in board["columns"])


async def test_submitted_unreviewed_lands_in_new_bucket(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)

    board = await _board(db_session, partner=partner, job_id=job_id)
    new_col = _column(board, key="new")
    assert new_col["count"] == 1
    assert [c["application_id"] for c in new_col["candidates"]] == [str(app_id)]
    # Not yet in any stage column.
    assert all(col["count"] == 0 for col in board["columns"] if col["stage_id"])


# --------------------------------------------------------------------------- #
# Reviewed -> stage 1; advanced -> stage 2 (cards move buckets)               #
# --------------------------------------------------------------------------- #


async def test_reviewed_candidate_appears_under_current_stage(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )

    board = await _board(db_session, partner=partner, job_id=job_id)
    assert _column(board, key="new")["count"] == 0
    screening = _stage_column(board, sort_order=1)
    assert screening["count"] == 1
    card = screening["candidates"][0]
    assert card["application_id"] == str(app_id)
    assert card["position"] == 1
    assert card["stage_id"] == screening["stage_id"]
    assert card["entered_at"] is not None
    assert card["rollback_count"] == 0


async def test_advanced_candidate_moves_buckets(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )

    board = await _board(db_session, partner=partner, job_id=job_id)
    assert _stage_column(board, sort_order=1)["count"] == 0
    interview = _stage_column(board, sort_order=2)
    assert interview["count"] == 1
    assert interview["candidates"][0]["application_id"] == str(app_id)
    assert interview["candidates"][0]["position"] == 2


async def test_rejected_and_withdrawn_drop_off_active_board(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su1, _s1, rejected_id = await _apply(db_session, job_id=job_id, prefix="rej")
    _su2, withdrawer, withdrawn_id = await _apply(db_session, job_id=job_id, prefix="wd")
    await decision_service.review_application(
        db_session, principal=partner, application_id=rejected_id, ctx=CTX
    )
    await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=rejected_id,
        reason="not_qualified",
        ctx=CTX,
    )
    await decision_service.review_application(
        db_session, principal=partner, application_id=withdrawn_id, ctx=CTX
    )
    await apply_service.withdraw_application(
        db_session, principal=withdrawer, application_id=withdrawn_id, ctx=CTX
    )

    board = await _board(db_session, partner=partner, job_id=job_id)
    # Neither terminal application appears as a card anywhere on the board.
    assert _all_card_app_ids(board) == set()
    # But the coarse outcome counts are still surfaced in the summary.
    assert board["summary"]["rejected"] == 1
    assert board["summary"]["withdrawn"] == 1
    assert board["summary"]["active_total"] == 0


# --------------------------------------------------------------------------- #
# Stage counts derive from candidate_stages (proj_partner_pipeline fix)       #
# --------------------------------------------------------------------------- #


async def test_summary_counts_derive_from_candidate_stages(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    # Two reviewed (stage 1), one advanced (stage 2), one untouched (new).
    ids = []
    for i in range(4):
        _su, _student, app_id = await _apply(db_session, job_id=job_id, prefix=f"c{i}")
        ids.append(app_id)
    for app_id in ids[:3]:
        await decision_service.review_application(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=ids[2], ctx=CTX
    )

    board = await _board(db_session, partner=partner, job_id=job_id)
    stages = board["stages"]
    by_stage = board["summary"]["by_stage"]
    assert by_stage[stages[0]["id"]] == 2  # screening
    assert by_stage[stages[1]["id"]] == 1  # interview
    assert board["summary"]["new"] == 1
    assert board["summary"]["active_total"] == 4

    # The dashboard read facade returns the same authoritative counts.
    from app.modules.recruitment.application import dashboard_read

    job_counts = await dashboard_read.pipeline_counts_for_job(db_session, job_id=job_id)
    assert job_counts["by_stage"] == by_stage and job_counts["new"] == 1


async def test_org_pipeline_counts_rollup(db_session) -> None:
    partner, uni, job_a = await _setup_published(db_session, title="Job A")
    # Reuse the same partner org for a second job so the org rollup spans both.
    org_id = partner.org_id
    job_b = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Job B"
    )
    _su, _student, a1 = await _apply(db_session, job_id=job_a, prefix="a1")
    _su2, _s2, b1 = await _apply(db_session, job_id=job_b, prefix="b1")
    await decision_service.review_application(
        db_session, principal=partner, application_id=a1, ctx=CTX
    )

    from app.modules.recruitment.application import dashboard_read

    counts = await dashboard_read.pipeline_counts_for_org(db_session, org_id=org_id)
    # a1 reviewed -> stage 1; b1 still submitted -> new. Org rollup sees both.
    assert sum(counts["by_stage"].values()) == 1
    assert counts["new"] == 1
    assert counts["active_total"] == 2


# --------------------------------------------------------------------------- #
# RBAC: cross-org -> 404                                                       #
# --------------------------------------------------------------------------- #


async def test_cross_org_partner_gets_404(db_session) -> None:
    partner_a, _uni, job_id = await _setup_published(db_session, title="A Job")
    _pb_u, _pb_org, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    await _apply(db_session, job_id=job_id)
    with pytest.raises(ResourceNotFoundError):
        await pipeline_board.get_job_pipeline_board(db_session, principal=partner_b, job_id=job_id)


async def test_unknown_job_is_404(db_session) -> None:
    partner, _uni, _job_id = await _setup_published(db_session)
    with pytest.raises(ResourceNotFoundError):
        await pipeline_board.get_job_pipeline_board(
            db_session, principal=partner, job_id=uuid.uuid4()
        )


# --------------------------------------------------------------------------- #
# Anonymity preserved on the board                                            #
# --------------------------------------------------------------------------- #


async def test_anonymous_card_redacted_pre_reveal(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id, is_anonymous=True)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )

    board = await _board(db_session, partner=partner, job_id=job_id)
    card = _stage_column(board, sort_order=1)["candidates"][0]
    assert card["is_anonymous"] is True
    assert card["applicant"]["revealed"] is False
    # UV-handle present; no PII anywhere on the board.
    assert card["applicant"]["anonymous_id"].startswith("UV-")
    assert "email" not in card["applicant"]
    assert "user_id" not in card["applicant"]
    assert su.email not in str(board)
    assert (su.full_name or "ZZZ") not in str(board)
    assert card["cv_download_available"] is False


async def test_revealed_identity_appears_after_accept(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, student, app_id = await _apply(db_session, job_id=job_id, is_anonymous=True)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await reveal_service.request_reveal(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="Chúng tôi muốn xác minh thông tin ứng viên để mời phỏng vấn.",
        ctx=CTX,
    )
    await reveal_service.respond_reveal(
        db_session,
        principal=student,
        application_id=app_id,
        decision="accepted",
        ctx=CTX,
    )

    board = await _board(db_session, partner=partner, job_id=job_id)
    card = _stage_column(board, sort_order=1)["candidates"][0]
    assert card["applicant"]["revealed"] is True
    assert card["applicant"]["email"] == su.email
    assert card["cv_download_available"] is True


# --------------------------------------------------------------------------- #
# No N+1: the board loads in a bounded number of queries                       #
# --------------------------------------------------------------------------- #


async def test_board_query_count_is_bounded(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    # Mix of buckets + a revealed card to exercise every batched lookup.
    for i in range(6):
        _su, _student, app_id = await _apply(db_session, job_id=job_id, prefix=f"q{i}")
        if i < 4:
            await decision_service.review_application(
                db_session, principal=partner, application_id=app_id, ctx=CTX
            )
        if i < 2:
            await stage_service.advance_application_stage(
                db_session, principal=partner, application_id=app_id, ctx=CTX
            )

    # Warm path: count queries for an N=6 board.
    with _count_queries(db_session) as small:
        await _board(db_session, partner=partner, job_id=job_id)

    # Add many more candidates; the query count must NOT grow with N (no per-card
    # fetch loop). A small fixed ceiling proves the board is batched.
    for i in range(20):
        _su, _student, app_id = await _apply(db_session, job_id=job_id, prefix=f"big{i}")
        await decision_service.review_application(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )

    with _count_queries(db_session) as large:
        board = await _board(db_session, partner=partner, job_id=job_id)

    assert board["summary"]["active_total"] == 26
    # Query count is bounded and independent of candidate count.
    assert large["n"] == small["n"]
    assert large["n"] <= 12
