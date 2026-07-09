"""Central RBAC gate for AI-assistant tool dispatch (fail-closed).

Every dispatch path — native loop, legacy plan loop, confirmation replay,
chat_service — funnels through ``dispatch_tool``, which now re-checks
authorization before running ANY handler. These tests prove a persona/grant
mismatch can never execute a tool, even one the model named that it was never
offered.
"""

from __future__ import annotations

import pytest
from app.modules.ai_assistant.application.tools.authorization import (
    available_specs,
    is_authorized,
)
from app.modules.ai_assistant.application.tools.dispatch import dispatch_tool
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS
from app.shared.permissions import GUEST, Principal

from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin

# A partner-only, side-effecting tool a student must never reach.
_PARTNER_TOOL = "get_partner_pipeline_summary"
# A student-only tool a partner must never reach.
_STUDENT_TOOL = "get_my_applications"


@pytest.mark.asyncio
async def test_student_cannot_dispatch_partner_tool(db_session) -> None:
    _user, student = await make_student(db_session)

    result = await dispatch_tool(
        _PARTNER_TOOL, {}, session=db_session, principal=student
    )

    assert result == {"ok": False, "error": "not_authorized"}


@pytest.mark.asyncio
async def test_partner_cannot_dispatch_student_only_tool(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session, org_type="partner")

    result = await dispatch_tool(
        _STUDENT_TOOL, {}, session=db_session, principal=partner
    )

    assert result == {"ok": False, "error": "not_authorized"}


@pytest.mark.asyncio
async def test_guest_cannot_dispatch_any_tool(db_session) -> None:
    result = await dispatch_tool(
        "search_jobs", {"q": "x"}, session=db_session, principal=GUEST
    )

    assert result == {"ok": False, "error": "not_authorized"}


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected(db_session) -> None:
    _user, student = await make_student(db_session)

    result = await dispatch_tool(
        "definitely_not_a_tool", {}, session=db_session, principal=student
    )

    assert result == {"ok": False, "error": "unknown_tool"}


@pytest.mark.asyncio
async def test_partner_authorized_tool_is_not_blocked_by_the_gate(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session, org_type="partner")

    result = await dispatch_tool(
        _PARTNER_TOOL, {}, session=db_session, principal=partner
    )

    # It may still fail for data reasons, but it must NOT be an authz refusal —
    # the gate let it through to the handler.
    assert result.get("error") != "not_authorized"


def test_available_specs_partitions_by_persona() -> None:
    student = Principal(user_id=_uuid(), persona="student", permissions=frozenset())
    partner = Principal(
        user_id=_uuid(),
        persona="partner_member",
        org_id=_uuid(),
        permissions=frozenset({"*:*"}),
    )

    student_tools = {s.name for s in available_specs(student)}
    partner_tools = {s.name for s in available_specs(partner)}

    assert _STUDENT_TOOL in student_tools
    assert _PARTNER_TOOL not in student_tools
    assert _PARTNER_TOOL in partner_tools
    assert _STUDENT_TOOL not in partner_tools


def test_is_authorized_is_fail_closed_for_missing_grant() -> None:
    # A partner persona WITHOUT the required org grant fails the gate even though
    # the persona family matches.
    partner_no_grant = Principal(
        user_id=_uuid(), persona="partner_member", org_id=_uuid(), permissions=frozenset()
    )
    spec = TOOL_SPECS[_PARTNER_TOOL]  # requires applications:read
    assert is_authorized(partner_no_grant, spec) is False


def _uuid():
    import uuid

    return uuid.uuid4()
