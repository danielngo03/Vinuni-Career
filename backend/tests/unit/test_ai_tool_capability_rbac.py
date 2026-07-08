"""Grantable partner capabilities on candidate-access + JD-drafting tools (B4).

Candidate-access and JD-drafting assistant tools declare grantable
``resource:action`` capabilities (per docs/PARTNER_RBAC_ANALYTICS_SPEC.md)
instead of a blanket ``role:partner_user``. The dispatch persona+capability gate
(`_tool_not_permitted`) enforces them: a partner without the grant is denied,
a partner with the grant (or Partner Admin `*:*`) is allowed, and a student is
still persona-denied before the capability check even runs.
"""

from __future__ import annotations

import uuid

from app.modules.ai_assistant.application.tools.dispatch import _tool_not_permitted
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS
from app.shared import personas
from app.shared.permissions import Principal

# tool name -> the grantable capability it now requires.
_CAPABILITY_TOOLS: dict[str, str] = {
    "search_partner_candidates": "pipeline:read",
    "get_candidate_detail": "pipeline:read",
    "move_candidate_stage": "ai_recruiting:move_candidate_with_confirmation",
    "draft_job_description": "ai_recruiting:draft_jd",
    "rewrite_job_description": "ai_recruiting:draft_jd",
}


def _partner(*perms: str) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona=personas.PARTNER_MEMBER,
        org_id=uuid.uuid4(),
        permissions=frozenset(perms),
    )


def test_capability_tools_declare_a_resource_action_grant() -> None:
    # Each gated tool declares its resource:action capability (not just a role).
    for tool_name, capability in _CAPABILITY_TOOLS.items():
        perms = TOOL_SPECS[tool_name].required_permissions
        assert capability in perms, f"{tool_name} must declare {capability}"
        assert "role:partner_user" in perms  # persona role still required too


def test_partner_without_capability_is_denied_the_tool() -> None:
    # A recruiter with only jobs:read (a bare partner) is denied every gated tool.
    bare = _partner("jobs:read")
    for tool_name in _CAPABILITY_TOOLS:
        assert _tool_not_permitted(bare, TOOL_SPECS[tool_name]) is True, tool_name


def test_partner_with_capability_is_allowed_the_tool() -> None:
    for tool_name, capability in _CAPABILITY_TOOLS.items():
        granted = _partner(capability)
        assert _tool_not_permitted(granted, TOOL_SPECS[tool_name]) is False, tool_name


def test_partner_admin_wildcard_passes_every_gated_tool() -> None:
    admin = _partner("*:*")
    for tool_name in _CAPABILITY_TOOLS:
        assert _tool_not_permitted(admin, TOOL_SPECS[tool_name]) is False, tool_name


def test_student_is_still_persona_denied_before_capability_check() -> None:
    student = Principal(user_id=uuid.uuid4(), persona=personas.STUDENT)
    for tool_name in _CAPABILITY_TOOLS:
        assert _tool_not_permitted(student, TOOL_SPECS[tool_name]) is True, tool_name
