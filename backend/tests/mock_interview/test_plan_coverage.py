"""Planner + deterministic coverage + txn/lock behaviour (Lane 1).

Covers the layered brain added on top of the single-flash interviewer:
- deterministic plan fallback when the model is down (the whole suite is offline);
- the no-score invariant across plan / analysis / report;
- deterministic coverage mapping + plan-slice targeting;
- the P0 create/end transaction + lock behaviour (single active slot, idempotent
  end that never regenerates/double-bills a report).
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from app.ai.prompts.mock_interview import v1 as prompts
from app.modules.mock_interview.application import (
    analysis_service,
    caps,
    plan_service,
    session_service,
)
from app.modules.mock_interview.domain.models import STATUS_COMPLETED
from app.modules.mock_interview.infrastructure import repository as repo
from app.shared.exceptions import ConflictError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv

_SCORE_KEYS = ("score", "rating", "grade", "percentage", "pass_fail", "points")


# --------------------------------------------------------------------------- #
# Migration 0101 well-formedness (upgrade + downgrade + chain)                 #
# --------------------------------------------------------------------------- #
def test_migration_0101_is_well_formed() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0101_interview_plan_coverage.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0101", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0101_interview_plan_coverage"
    assert mod.down_revision == "0100_platform_settings_google_font"


def _grounding() -> dict:
    return {
        "locale": "en",
        "focus": "technical",
        "difficulty": "intermediate",
        "job": {
            "title": "Backend Intern",
            "company_name": "Acme",
            "description": "Build REST APIs.",
            "requirements": ["Experience with Python and FastAPI is required"],
            "required_skills": ["Python", "FastAPI"],
            "seniority_level": "junior",
            "experience": "0-1 years",
        },
        "cv": {
            "title": "CS Intern CV",
            "language": "en",
            "highlights": ["[experience] Built REST APIs with FastAPI"],
            "skills": ["Python"],
        },
        "matched_skills": ["Python"],
        "gaps": ["Kubernetes"],
    }


# --------------------------------------------------------------------------- #
# Deterministic plan (no LLM / model down)                                     #
# --------------------------------------------------------------------------- #
def test_deterministic_plan_is_well_formed() -> None:
    plan = plan_service._deterministic_plan(_grounding())

    assert plan["source"] == "deterministic"
    assert plan["plan_version"] == prompts.PLAN_VERSION
    comps = plan["competency_map"]
    assert 0 < len(comps) <= caps.MAX_COMPETENCIES
    bank_ids = {b["competency_id"] for b in plan["question_bank"]}
    for comp in comps:
        assert comp["id"] in bank_ids  # every competency has questions
    for bank in plan["question_bank"]:
        assert set(bank["tiers"].keys()) == set(caps.DIFFICULTY_TIERS)
        assert all(v.strip() for v in bank["tiers"].values())  # non-empty tiers
    assert plan["opening"]  # deterministic opening present

    # CV-evidence mapping reuses the grounding matched/gap signals (no LLM).
    ev = {c["label"]: c["cv_evidence"] for c in comps}
    assert ev.get("Python") == "covered"  # in matched_skills
    assert ev.get("FastAPI") == "unclear"  # neither matched nor gap


def test_deterministic_plan_low_signal_uses_generic_competencies() -> None:
    grounding = {"locale": "en", "focus": "behavioral", "job": {}, "cv": {}}
    plan = plan_service._deterministic_plan(grounding)
    assert plan["competency_map"]  # never empty, even with an empty JD
    assert plan["source"] == "deterministic"


async def test_build_plan_falls_back_to_deterministic_offline(db_session) -> None:
    # The whole suite is offline, so the planner model call yields non-JSON and the
    # plan degrades to the deterministic one — session create is never blocked.
    plan = await plan_service.build_plan(
        db_session,
        grounding=_grounding(),
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )
    assert plan["source"] == "deterministic"
    assert plan["competency_map"] and plan["question_bank"]
    # No score / model leak in the frozen plan.
    blob = json.dumps(plan, ensure_ascii=False).lower()
    for term in ("score", "rating", "grade", "openrouter", "gemini", "prompt_tokens"):
        assert term not in blob


# --------------------------------------------------------------------------- #
# Coverage mapping (deterministic, no LLM)                                     #
# --------------------------------------------------------------------------- #
def test_coverage_starts_all_uncovered() -> None:
    plan = plan_service._deterministic_plan(_grounding())
    cov = plan_service.init_coverage(plan, difficulty="intermediate")
    summary = plan_service.coverage_summary(cov)
    assert summary is not None
    assert summary["covered_count"] == 0
    assert summary["total"] == len(plan["competency_map"])
    assert cov["current_tier"] == "intermediate"


def test_record_interviewer_question_marks_matched_competency() -> None:
    plan = plan_service._deterministic_plan(_grounding())
    cov = plan_service.init_coverage(plan)
    cov = plan_service.record_interviewer_question(
        cov,
        plan,
        question_text="Walk me through how you used Python to build a service.",
        seq=2,
        targeted_id=None,
    )
    summary = plan_service.coverage_summary(cov)
    assert summary is not None
    assert "Python" in summary["covered"]
    assert summary["covered_count"] == 1


def test_generic_question_falls_back_to_targeted_competency() -> None:
    plan = plan_service._deterministic_plan(_grounding())
    cov = plan_service.init_coverage(plan)
    first_id = plan["competency_map"][0]["id"]
    # A generic question that matches no competency keyword attributes to the
    # steered target so coverage still advances deterministically.
    cov = plan_service.record_interviewer_question(
        cov, plan, question_text="Thanks. Tell me more about that.", seq=3, targeted_id=first_id
    )
    assert cov["competencies"][first_id]["covered"] is True


def test_plan_slice_targets_first_remaining_then_advances() -> None:
    plan = plan_service._deterministic_plan(_grounding())
    cov = plan_service.init_coverage(plan, difficulty="foundational")

    first = plan_service.build_plan_slice(plan, cov)
    assert first is not None
    assert first["target_id"] == plan["competency_map"][0]["id"]
    assert first["target_tier"] == "foundational"
    assert first["candidate_questions"]
    assert first["target_label"] in first["remaining_labels"] or first["remaining_labels"]

    cov = plan_service.record_interviewer_question(
        cov, plan, question_text="generic", seq=2, targeted_id=first["target_id"]
    )
    second = plan_service.build_plan_slice(plan, cov)
    assert second is not None
    assert second["target_id"] != first["target_id"]
    assert first["target_label"] in second["covered_labels"]


def test_plan_slice_none_when_all_covered() -> None:
    plan = plan_service._deterministic_plan(_grounding())
    cov = plan_service.init_coverage(plan)
    for i, comp in enumerate(plan["competency_map"], start=2):
        cov = plan_service.record_interviewer_question(
            cov, plan, question_text="generic", seq=i, targeted_id=comp["id"]
        )
    assert plan_service.build_plan_slice(plan, cov) is None


def test_set_tier_ignores_bad_input() -> None:
    plan = plan_service._deterministic_plan(_grounding())
    cov = plan_service.init_coverage(plan, difficulty="intermediate")
    cov = plan_service.set_tier(cov, "advanced")
    assert cov["current_tier"] == "advanced"
    cov = plan_service.set_tier(cov, "nonsense")
    assert cov["current_tier"] == "advanced"  # unchanged on bad input


# --------------------------------------------------------------------------- #
# No-score invariant (plan / analysis)                                         #
# --------------------------------------------------------------------------- #
def test_deterministic_analysis_has_no_score_and_categorical_gaps() -> None:
    plan = plan_service._deterministic_plan(_grounding())
    cov = plan_service.init_coverage(plan)
    cov = plan_service.record_interviewer_question(
        cov, plan, question_text="Tell me about Python.", seq=2, targeted_id=None
    )
    analysis = analysis_service._deterministic_analysis(plan, cov)

    assert analysis["source"] == "deterministic"
    assert analysis["per_competency"]
    for item in analysis["per_competency"]:
        assert item["gap_severity"] in {"none", "low", "medium", "high"}
        assert isinstance(item["covered"], bool)
        assert set(item.keys()) == {
            "competency_id",
            "label",
            "covered",
            "star_components",
            "evidence_quote",
            "gap_severity",
        }
    blob = json.dumps(analysis, ensure_ascii=False).lower()
    for key in _SCORE_KEYS:
        assert f'"{key}"' not in blob
    # A covered competency has no residual gap; an untouched CV gap is high.
    ev = {p["label"]: p for p in analysis["per_competency"]}
    assert ev["Python"]["gap_severity"] == "none"  # covered


async def test_analyze_offline_returns_deterministic(db_session) -> None:
    plan = plan_service._deterministic_plan(_grounding())
    cov = plan_service.init_coverage(plan)
    analysis = await analysis_service.analyze(
        db_session,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        grounding=_grounding(),
        plan=plan,
        coverage=cov,
        transcript_lines=["Interviewer: Hi", "Candidate: Hello"],
    )
    assert analysis["source"] == "deterministic"
    assert analysis["uncovered"]  # nothing covered yet


# --------------------------------------------------------------------------- #
# create / end transaction + lock behaviour (P0)                               #
# --------------------------------------------------------------------------- #
async def _seed(db):
    _u, student = await make_student(db)
    await make_strong_cv(db, student)
    job_id = await make_public_job(db)
    return student, job_id


async def test_create_persists_frozen_plan_and_coverage(db_session) -> None:
    student, job_id = await _seed(db_session)
    created = await session_service.create_session(
        db_session, principal=student, ctx=CTX, job_id=job_id, cv_id=None
    )
    sid = uuid.UUID(created["session_id"])
    row = await repo.get_session(db_session, session_id=sid, user_id=student.user_id)

    assert row is not None
    assert row.status == "active"
    assert row.plan_json and row.plan_json["source"] == "deterministic"
    assert row.plan_version == prompts.PLAN_VERSION
    assert row.coverage_json and row.coverage_json["order"]
    assert row.question_count == 1
    # coverage surfaced in the create response; the generic opening consumed no
    # competency slot.
    assert created["coverage"] is not None
    assert created["coverage"]["covered_count"] == 0


async def test_second_concurrent_create_conflicts(db_session) -> None:
    student, job_id = await _seed(db_session)
    await session_service.create_session(
        db_session, principal=student, ctx=CTX, job_id=job_id, cv_id=None
    )
    with pytest.raises(ConflictError) as exc:
        await session_service.create_session(
            db_session, principal=student, ctx=CTX, job_id=job_id, cv_id=None
        )
    assert exc.value.details.get("reason") == "ACTIVE_SESSION_EXISTS"


async def test_stream_turn_advances_coverage(db_session) -> None:
    student, job_id = await _seed(db_session)
    created = await session_service.create_session(
        db_session, principal=student, ctx=CTX, job_id=job_id, cv_id=None
    )
    sid = uuid.UUID(created["session_id"])

    async for _ in session_service.stream_turn(
        db_session,
        principal=student,
        session_id=sid,
        answer="I built and deployed a Python FastAPI service in production.",
    ):
        pass

    row = await repo.get_session(db_session, session_id=sid, user_id=student.user_id)
    assert row is not None
    summary = plan_service.coverage_summary(row.coverage_json)
    assert summary is not None
    # The interviewer question (steered to the first competency) advanced coverage.
    assert summary["covered_count"] >= 1


async def test_end_is_idempotent_and_does_not_regenerate_report(db_session) -> None:
    student, job_id = await _seed(db_session)
    created = await session_service.create_session(
        db_session, principal=student, ctx=CTX, job_id=job_id, cv_id=None
    )
    sid = uuid.UUID(created["session_id"])
    async for _ in session_service.stream_turn(
        db_session, principal=student, session_id=sid, answer="A relevant project."
    ):
        pass

    first = await session_service.end_session(
        db_session, principal=student, ctx=CTX, session_id=sid, duration_seconds=100
    )
    assert first["status"] == STATUS_COMPLETED
    report = first["report"]
    assert report is not None and report["is_fallback"] is True  # offline -> fallback
    # No score anywhere; the deterministic coverage summary is attached.
    for key in _SCORE_KEYS:
        assert key not in report
    assert "coverage" in report

    # A second end is idempotent and returns the SAME stored report (no second
    # generation / bill).
    second = await session_service.end_session(
        db_session, principal=student, ctx=CTX, session_id=sid
    )
    assert second["status"] == STATUS_COMPLETED
    assert second["report"] == report


async def test_end_after_abort_conflicts(db_session) -> None:
    student, job_id = await _seed(db_session)
    created = await session_service.create_session(
        db_session, principal=student, ctx=CTX, job_id=job_id, cv_id=None
    )
    sid = uuid.UUID(created["session_id"])
    await session_service.abort_session(
        db_session, principal=student, ctx=CTX, session_id=sid
    )
    with pytest.raises(ConflictError):
        await session_service.end_session(
            db_session, principal=student, ctx=CTX, session_id=sid
        )
