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
