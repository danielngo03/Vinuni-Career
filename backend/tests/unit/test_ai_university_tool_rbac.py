"""Central tool-RBAC gate + university tool registry (university control plane P3).

Proves the dispatch-level ``authorize_tool`` gate:
- does NOT regress existing student/partner tool access,
- correctly scopes university tools by persona family + catalog grant,
- lets superadmin through, and
- keeps the university tool registry entries §7-complete.

Pure/DB-free: exercises ``authorize_tool`` with hand-built principals.
"""

from __future__ import annotations

import uuid

from app.modules.ai_assistant.application.tools.dispatch import (
    SUPPORTED_TOOL_NAMES,
    authorize_tool,
)
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS
from app.shared.permissions import Principal


def _student(perms: set[str] | None = None) -> Principal:
    return Principal(
        user_id=uuid.uuid4(), persona="student", permissions=frozenset(perms or set())
    )


def _partner(perms: set[str] | None = None) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="partner_member",
        org_id=uuid.uuid4(),
        permissions=frozenset(perms or {"jobs:read"}),
    )


def _university(perms: set[str] | None = None) -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="university_staff",
        org_id=uuid.uuid4(),
        permissions=frozenset(perms or set()),
    )


def _superadmin() -> Principal:
    return Principal(
        user_id=uuid.uuid4(), persona="superadmin", is_superadmin=True,
        permissions=frozenset({"*"}),
    )


# --------------------------------------------------------------------------- #
# No regression: existing persona -> its tools still pass                      #
# --------------------------------------------------------------------------- #


def test_student_tools_still_authorized_for_students() -> None:
    student = _student()
    for name in ("get_my_cvs", "get_my_applications", "save_job", "apply_job"):
        assert authorize_tool(TOOL_SPECS[name], student) is True, name


def test_partner_tools_still_authorized_for_partners() -> None:
    partner = _partner()
    for name in ("get_partner_jobs", "get_partner_pipeline_summary", "move_candidate_stage"):
        assert authorize_tool(TOOL_SPECS[name], partner) is True, name


def test_shared_tools_authorized_for_every_authenticated_persona() -> None:
    for principal in (_student(), _partner(), _university({"jobs:moderate"})):
        assert authorize_tool(TOOL_SPECS["get_upcoming_events"], principal) is True
        assert authorize_tool(TOOL_SPECS["knowledge_base_query"], principal) is True


def test_cross_persona_denied_student_cannot_use_partner_tool() -> None:
    assert authorize_tool(TOOL_SPECS["get_partner_jobs"], _student()) is False


def test_cross_persona_denied_partner_cannot_use_student_tool() -> None:
    assert authorize_tool(TOOL_SPECS["get_my_cvs"], _partner()) is False


# --------------------------------------------------------------------------- #
# University tools: persona family + catalog grant enforcement                 #
# --------------------------------------------------------------------------- #


def test_university_read_tool_denied_without_grant() -> None:
    staff = _university(perms=set())  # authenticated staffer, no grants
    assert authorize_tool(TOOL_SPECS["get_moderation_queue"], staff) is False
    assert authorize_tool(TOOL_SPECS["get_at_risk_students"], staff) is False


def test_university_read_tool_allowed_with_matching_grant() -> None:
    assert authorize_tool(
        TOOL_SPECS["get_moderation_queue"], _university({"jobs:moderate"})
    ) is True
    assert authorize_tool(
        TOOL_SPECS["get_at_risk_students"], _university({"career_services_at_risk:read"})
    ) is True
    assert authorize_tool(
        TOOL_SPECS["get_pending_partner_registrations"], _university({"partners:read"})
    ) is True


def test_university_grant_is_tool_specific() -> None:
    # A moderation grant does NOT unlock the at-risk (career-services) tool.
    staff = _university({"jobs:moderate"})
    assert authorize_tool(TOOL_SPECS["get_moderation_queue"], staff) is True
    assert authorize_tool(TOOL_SPECS["get_at_risk_students"], staff) is False


def test_university_write_tools_require_moderate_grant() -> None:
    ungranted = _university(set())
    granted = _university({"jobs:moderate"})
    for name in ("approve_job_moderation", "request_job_changes"):
        assert authorize_tool(TOOL_SPECS[name], ungranted) is False, name
        assert authorize_tool(TOOL_SPECS[name], granted) is True, name


def test_university_cannot_use_student_or_partner_tools() -> None:
    staff = _university({"jobs:moderate"})
    assert authorize_tool(TOOL_SPECS["get_my_cvs"], staff) is False
    assert authorize_tool(TOOL_SPECS["get_partner_jobs"], staff) is False


def test_wildcard_grant_university_admin_passes_all_university_tools() -> None:
    # A university Admin holds ``*:*`` (not is_superadmin) and org_type=university.
    admin = _university({"*:*"})
    for name in (
        "get_moderation_queue",
        "get_pending_partner_registrations",
        "get_at_risk_students",
        "approve_job_moderation",
        "request_job_changes",
    ):
        assert authorize_tool(TOOL_SPECS[name], admin) is True, name


def test_superadmin_passes_any_tool() -> None:
    sa = _superadmin()
    for name in TOOL_SPECS:
        assert authorize_tool(TOOL_SPECS[name], sa) is True, name


def test_unauthenticated_principal_denied() -> None:
    guest = Principal(user_id=None, persona="guest")
    assert authorize_tool(TOOL_SPECS["get_moderation_queue"], guest) is False
    assert authorize_tool(TOOL_SPECS["get_upcoming_events"], guest) is False


# --------------------------------------------------------------------------- #
# Registry completeness                                                        #
# --------------------------------------------------------------------------- #

_UNIVERSITY_TOOLS = (
    "get_university_dashboard_summary",
    "get_moderation_queue",
    "get_pending_partner_registrations",
    "get_partner_overview",
    "get_at_risk_students",
    "get_cohort_summary",
    "get_career_services_report",
    "get_placement_outcomes_summary",
    "search_university_knowledge",
    "approve_job_moderation",
    "request_job_changes",
)


def test_university_tools_registered_and_dispatch_in_sync() -> None:
    for name in _UNIVERSITY_TOOLS:
        assert name in TOOL_SPECS, f"{name} missing from TOOL_SPECS"
        assert name in SUPPORTED_TOOL_NAMES, f"{name} missing from SUPPORTED_TOOL_NAMES"


def test_university_tools_declare_full_contract() -> None:
    from app.modules.ai_assistant.application.tools.specs import UNIVERSITY_STAFF

    for name in _UNIVERSITY_TOOLS:
        spec = TOOL_SPECS[name]
        assert spec.persona == [UNIVERSITY_STAFF], name
        assert "authenticated" in spec.required_permissions, name
        assert "role:university_staff" in spec.required_permissions, name
        assert spec.audit_event_type.startswith("TOOL_"), name
        assert spec.fallback.strip(), name


def test_university_write_tools_are_confirmation_gated() -> None:
    for name in ("approve_job_moderation", "request_job_changes"):
        spec = TOOL_SPECS[name]
        assert spec.permission_class == "confirmation_required", name
        assert spec.confirmation_copy is not None, name
        assert spec.side_effects, name
