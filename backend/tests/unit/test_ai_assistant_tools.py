from __future__ import annotations

import uuid

from app.modules.ai_assistant.application.tools.dispatch import (
    SUPPORTED_TOOL_NAMES,
    _tool_not_permitted,
    _validate_tool_args,
)
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS
from app.shared.permissions import Principal


def _student() -> Principal:
    return Principal(user_id=uuid.uuid4(), persona="student", permissions=frozenset())


def _partner() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="partner_member",
        org_id=uuid.uuid4(),
        permissions=frozenset(),
    )


def test_tool_registry_and_dispatch_stay_in_sync() -> None:
    assert set(TOOL_SPECS) == set(SUPPORTED_TOOL_NAMES)


def test_partner_principal_may_not_dispatch_student_only_tool() -> None:
    # apply_job / get_my_cvs are persona=[STUDENT] — a partner must never reach them.
    assert _tool_not_permitted(_partner(), TOOL_SPECS["apply_job"]) is True
    assert _tool_not_permitted(_partner(), TOOL_SPECS["get_my_cvs"]) is True


def test_student_principal_may_not_dispatch_partner_only_tool() -> None:
    assert _tool_not_permitted(_student(), TOOL_SPECS["get_partner_pipeline_summary"]) is True
    assert _tool_not_permitted(_student(), TOOL_SPECS["draft_job_description"]) is True
    assert _tool_not_permitted(_student(), TOOL_SPECS["move_candidate_stage"]) is True


def test_persona_matched_and_shared_tools_are_permitted() -> None:
    # Own-persona tools pass the gate.
    assert _tool_not_permitted(_student(), TOOL_SPECS["apply_job"]) is False
    assert _tool_not_permitted(_partner(), TOOL_SPECS["get_partner_pipeline_summary"]) is False
    # Shared tools (default persona = all authenticated) pass for either persona.
    assert _tool_not_permitted(_student(), TOOL_SPECS["knowledge_base_query"]) is False
    assert _tool_not_permitted(_partner(), TOOL_SPECS["knowledge_base_query"]) is False


def test_guest_persona_is_rejected_from_persona_scoped_tools() -> None:
    guest = Principal(user_id=None, persona="guest", permissions=frozenset())
    # Guests never reach dispatch (auth gate), but the map returns no tool persona.
    assert _tool_not_permitted(guest, TOOL_SPECS["search_jobs"]) is True
    assert _tool_not_permitted(guest, TOOL_SPECS["knowledge_base_query"]) is True


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
