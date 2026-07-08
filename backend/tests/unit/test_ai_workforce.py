"""Unit tests for the workforce coordinator's pure decomposition/aggregation
logic (§4.2). No DB, no Celery broker — offline, deterministic.
"""

from __future__ import annotations

import logging
import uuid

from app.ai.agents import coordinator
from app.ai.agents.models import RunStatus, SubtaskStatus
from app.shared.permissions import Principal


def test_decompose_bulk_screening_brief_one_subtask_per_application() -> None:
    app_ids = [str(uuid.uuid4()) for _ in range(3)]
    subtasks = coordinator.decompose_bulk_screening_brief(app_ids)

    assert [s.key for s in subtasks] == app_ids
    assert all(s.subtask_type == coordinator.SCREENING_BRIEF_SUBTASK_TYPE for s in subtasks)
    assert all(s.payload["application_id"] == s.key for s in subtasks)


def test_decompose_bulk_screening_brief_caps_at_max_subtasks() -> None:
    app_ids = [str(uuid.uuid4()) for _ in range(coordinator.MAX_SUBTASKS_PER_RUN + 10)]
    subtasks = coordinator.decompose_bulk_screening_brief(app_ids)

    assert len(subtasks) == coordinator.MAX_SUBTASKS_PER_RUN


def test_aggregate_screening_results_counts_success_and_failure() -> None:
    results_json = {
        "app-1": {
            "status": SubtaskStatus.SUCCESS.value,
            "result": {"bullets": ["a"], "suitability": "strong", "is_fallback": False},
            "error_code": None,
            "duration_ms": 12,
        },
        "app-2": {
            "status": SubtaskStatus.SUCCESS.value,
            "result": {"bullets": [], "suitability": "weak", "is_fallback": True},
            "error_code": None,
            "duration_ms": 8,
        },
        "app-3": {
            "status": SubtaskStatus.FAILED.value,
            "result": None,
            "error_code": "execution_error",
            "duration_ms": 5,
        },
    }

    summary = coordinator.aggregate_screening_results(results_json)

    assert summary["total"] == 3
    assert summary["succeeded"] == 2
    assert summary["failed"] == 1
    assert summary["strong_matches"] == 1
    assert len(summary["briefs"]) == 3
    failed_brief = next(b for b in summary["briefs"] if b["application_id"] == "app-3")
    assert failed_brief["is_fallback"] is True
    assert failed_brief["bullets"] == []


def test_aggregate_screening_results_empty_is_zeroed() -> None:
    summary = coordinator.aggregate_screening_results({})
    assert summary == {
        "total": 0,
        "succeeded": 0,
        "failed": 0,
        "strong_matches": 0,
        "briefs": [],
    }


def test_next_run_status_running_until_all_terminal() -> None:
    keys = ["a", "b"]
    results = {"a": {"status": SubtaskStatus.SUCCESS.value}}
    assert coordinator._next_run_status(keys, results) == RunStatus.RUNNING


def test_next_run_status_complete_when_all_success() -> None:
    keys = ["a", "b"]
    results = {
        "a": {"status": SubtaskStatus.SUCCESS.value},
        "b": {"status": SubtaskStatus.SUCCESS.value},
    }
    assert coordinator._next_run_status(keys, results) == RunStatus.COMPLETE


def test_next_run_status_partial_when_mixed() -> None:
    keys = ["a", "b"]
    results = {
        "a": {"status": SubtaskStatus.SUCCESS.value},
        "b": {"status": SubtaskStatus.FAILED.value},
    }
    assert coordinator._next_run_status(keys, results) == RunStatus.PARTIAL


def test_next_run_status_failed_when_all_failed() -> None:
    keys = ["a", "b"]
    results = {
        "a": {"status": SubtaskStatus.FAILED.value},
        "b": {"status": SubtaskStatus.FAILED.value},
    }
    assert coordinator._next_run_status(keys, results) == RunStatus.FAILED


def test_principal_serialize_roundtrip_preserves_fields() -> None:
    principal = Principal(
        user_id=uuid.uuid4(),
        persona="partner_admin",
        org_id=uuid.uuid4(),
        is_superadmin=False,
        permissions=frozenset({"applications:read", "jobs:read"}),
    )

    serialized = coordinator._serialize_principal(principal)
    restored = coordinator.deserialize_principal(serialized)

    assert restored.user_id == principal.user_id
    assert restored.persona == principal.persona
    assert restored.org_id == principal.org_id
    assert restored.is_superadmin == principal.is_superadmin
    assert restored.permissions == principal.permissions


def test_principal_serialize_never_leaks_provider_or_model_fields() -> None:
    """The serialized principal blob is stored in ``context_json`` — it must
    never accidentally carry provider/model/token internals (§1, §15)."""

    principal = Principal(user_id=uuid.uuid4(), persona="partner_admin")
    serialized = coordinator._serialize_principal(principal)

    forbidden = {"provider", "model", "model_alias", "api_key", "token", "prompt"}
    assert forbidden.isdisjoint(serialized.keys())


# --------------------------------------------------------------------------- #
# Student CV re-score (Task O / WS-11)                                         #
# --------------------------------------------------------------------------- #


def test_decompose_student_cv_rescore_one_subtask_per_job() -> None:
    job_ids = [str(uuid.uuid4()) for _ in range(3)]
    subtasks = coordinator.decompose_student_cv_rescore(job_ids)

    assert [s.key for s in subtasks] == job_ids
    assert all(s.subtask_type == coordinator.CV_RESCORE_SUBTASK_TYPE for s in subtasks)
    assert all(s.payload["job_id"] == s.key for s in subtasks)


def test_decompose_student_cv_rescore_caps_and_logs_overflow(caplog) -> None:
    job_ids = [
        str(uuid.uuid4())
        for _ in range(coordinator.MAX_RESCORE_SUBTASKS_PER_RUN + 5)
    ]
    with caplog.at_level(logging.WARNING, logger="app.ai.agents.coordinator"):
        subtasks = coordinator.decompose_student_cv_rescore(job_ids)

    # Capped — never silently truncated: the overflow is logged.
    assert len(subtasks) == coordinator.MAX_RESCORE_SUBTASKS_PER_RUN
    assert any(
        "rescore_candidates_capped" in rec.message for rec in caplog.records
    )


def test_decompose_student_cv_rescore_at_cap_does_not_log(caplog) -> None:
    job_ids = [
        str(uuid.uuid4())
        for _ in range(coordinator.MAX_RESCORE_SUBTASKS_PER_RUN)
    ]
    with caplog.at_level(logging.WARNING, logger="app.ai.agents.coordinator"):
        subtasks = coordinator.decompose_student_cv_rescore(job_ids)

    assert len(subtasks) == coordinator.MAX_RESCORE_SUBTASKS_PER_RUN
    assert not any(
        "rescore_candidates_capped" in rec.message for rec in caplog.records
    )


def test_aggregate_rescore_results_counts_refreshed_skipped_failed() -> None:
    results_json = {
        "job-1": {
            "status": SubtaskStatus.SUCCESS.value,
            "result": {
                "job_id": "job-1",
                "scored_cvs": 2,
                "recommended_cv_id": "cv-a",
                "signal": "ok",
                "skipped": None,
            },
        },
        "job-2": {
            "status": SubtaskStatus.SUCCESS.value,
            "result": {
                "job_id": "job-2",
                "scored_cvs": 0,
                "recommended_cv_id": None,
                "signal": "low_signal",
                "skipped": "no_active_cvs",
            },
        },
        "job-3": {
            "status": SubtaskStatus.FAILED.value,
            "result": None,
            "error_code": "execution_error",
        },
    }

    summary = coordinator.aggregate_rescore_results(results_json)

    assert summary["total"] == 3
    assert summary["refreshed"] == 1
    assert summary["skipped"] == 1
    assert summary["failed"] == 1
    assert len(summary["jobs"]) == 3
    refreshed = next(j for j in summary["jobs"] if j["job_id"] == "job-1")
    assert refreshed["recommended_cv_id"] == "cv-a"
    assert refreshed["scored_cvs"] == 2


def test_aggregate_rescore_results_empty_is_zeroed() -> None:
    summary = coordinator.aggregate_rescore_results({})
    assert summary == {
        "total": 0,
        "refreshed": 0,
        "skipped": 0,
        "failed": 0,
        "jobs": [],
    }


def test_aggregate_rescore_results_never_leaks_score_or_provider_internals() -> None:
    results_json = {
        "job-1": {
            "status": SubtaskStatus.SUCCESS.value,
            "result": {
                "job_id": "job-1",
                "scored_cvs": 1,
                "recommended_cv_id": "cv-a",
                "signal": "ok",
                "skipped": None,
            },
        }
    }
    summary = coordinator.aggregate_rescore_results(results_json)
    dumped = str(summary).lower()
    for forbidden in ("provider", "model", "token", "api_key", "prompt", "confidence"):
        assert forbidden not in dumped


def test_aggregate_dispatches_on_task_type() -> None:
    """A run's ``task_type`` selects its aggregator — never a branch inside one."""
    empty_rescore = coordinator._aggregate(coordinator.STUDENT_CV_RESCORE_TASK_TYPE, {})
    empty_screen = coordinator._aggregate(coordinator.BULK_SCREENING_TASK_TYPE, {})

    assert "refreshed" in empty_rescore
    assert "strong_matches" in empty_screen
