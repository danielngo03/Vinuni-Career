from __future__ import annotations

from app.modules.ai_assistant.application.tools.dispatch import (
    SUPPORTED_TOOL_NAMES,
    _validate_tool_args,
)
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS


def test_tool_registry_and_dispatch_stay_in_sync() -> None:
    assert set(TOOL_SPECS) == set(SUPPORTED_TOOL_NAMES)


def test_mutating_tools_require_confirmation() -> None:
    assert TOOL_SPECS["save_job"].permission_class == "confirmation_required"
    assert TOOL_SPECS["apply_job"].permission_class == "confirmation_required"


def test_tool_arg_validator_rejects_missing_required_args() -> None:
    valid, error = _validate_tool_args("get_salary_benchmark", {})

    assert valid is False
    assert error == "missing_role"


def test_tool_arg_validator_accepts_valid_optional_args() -> None:
    valid, error = _validate_tool_args(
        "get_salary_benchmark",
        {"role": "software engineer", "experience_years": 2},
    )

    assert valid is True
    assert error is None


def test_new_student_match_tools_are_read_only_student_scoped() -> None:
    for name in ("match_cv_to_jobs", "explain_job_fit", "compare_jobs", "show_cv", "compare_cvs"):
        spec = TOOL_SPECS[name]
        assert spec.permission_class == "read_only"
        assert spec.persona == ["student"]
        assert "role:student" in spec.required_permissions
        assert spec.audit_event_type


def test_student_write_tools_require_confirmation() -> None:
    for name in ("set_job_alert", "register_for_event"):
        spec = TOOL_SPECS[name]
        assert spec.permission_class == "confirmation_required"
        assert spec.confirmation_copy is not None
        assert spec.side_effects
        assert spec.persona == ["student"]


def test_apply_and_attachment_not_advertised_to_students() -> None:
    # Owner 2026-07-11: no apply / no upload in the student chat.
    assert TOOL_SPECS["apply_job"].persona == []
    assert "student" not in TOOL_SPECS["analyze_attachment"].persona


def test_explain_job_fit_requires_job_id() -> None:
    valid, error = _validate_tool_args("explain_job_fit", {})
    assert valid is False
    assert error == "missing_job_id"


def test_compare_jobs_accepts_job_ids_list() -> None:
    valid, error = _validate_tool_args(
        "compare_jobs", {"job_ids": [str(__import__("uuid").uuid4())]}
    )
    assert valid is True
    assert error is None
