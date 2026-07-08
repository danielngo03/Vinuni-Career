"""Partner AI tool decorator — org-auth guard + standard error-code ladder (D4).

The partner tool handlers share one contract via ``@partner_tool``: an org-auth
guard and a standard exception ladder mapping ``ResourceNotFoundError`` ->
``not_found``, ``PermissionDeniedError`` / ``AuthRequiredError`` ->
``permission_denied``, and any other exception -> ``tool_failed``. These are the
stable, leakage-safe error codes the assistant surfaces to the recruiter, so a
regression in the mapping is a product-visible break — not just a refactor
detail. This locks the byte-identical codes in place after the decorator extraction.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.ai_assistant.application.tools import partner as partner_tools
from app.modules.ai_assistant.application.tools.partner import partner_tool
from app.shared.exceptions import (
    AuthRequiredError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal


def _partner() -> Principal:
    return Principal(
        user_id=uuid.uuid4(),
        persona="partner_member",
        org_id=uuid.uuid4(),
        permissions=frozenset(),
    )


def _guest() -> Principal:
    return Principal(user_id=None, persona="guest", permissions=frozenset())


def _no_org_partner() -> Principal:
    return Principal(
        user_id=uuid.uuid4(), persona="partner_member", permissions=frozenset()
    )


@partner_tool
async def _raiser(session, principal, args) -> dict:
    """Test double: raises ``args['exc']`` (or echoes back on success)."""
    exc = args.get("exc")
    if exc is not None:
        raise exc
    return {"ok": True, "echo": args.get("echo")}


async def test_decorator_maps_standard_exceptions_to_error_codes() -> None:
    p = _partner()
    assert (await _raiser(None, p, {"exc": ResourceNotFoundError()}))["error"] == "not_found"
    assert (
        await _raiser(None, p, {"exc": PermissionDeniedError()})
    )["error"] == "permission_denied"
    assert (
        await _raiser(None, p, {"exc": AuthRequiredError()})
    )["error"] == "permission_denied"
    # A non-mapped app error and an unexpected error both degrade to tool_failed.
    assert (await _raiser(None, p, {"exc": ConflictError()}))["error"] == "tool_failed"
    assert (await _raiser(None, p, {"exc": RuntimeError("boom")}))["error"] == "tool_failed"


async def test_decorator_passes_through_success() -> None:
    ok = await _raiser(None, _partner(), {"exc": None, "echo": "hi"})
    assert ok == {"ok": True, "echo": "hi"}


async def test_decorator_org_auth_guard_short_circuits() -> None:
    # Unauthenticated and authenticated-without-org both fail the guard BEFORE the
    # wrapped body runs (so the raising body never executes).
    for principal in (_guest(), _no_org_partner()):
        res = await _raiser(None, principal, {"exc": ResourceNotFoundError()})
        assert res == {"ok": False, "error": "partner_auth_required"}


@pytest.mark.parametrize(
    "handler",
    [
        partner_tools.search_partner_candidates,
        partner_tools.get_candidate_detail,
        partner_tools.draft_job_description,
        partner_tools.rewrite_job_description,
        partner_tools.suggest_scorecard,
        partner_tools.generate_screening_brief,
        partner_tools.analyze_attachment,
        partner_tools.move_candidate_stage,
    ],
)
async def test_real_partner_handlers_require_org_auth(handler) -> None:
    # The guard short-circuits before any DB/service work, so a None session is safe.
    res = await handler(None, _guest(), {})
    assert res == {"ok": False, "error": "partner_auth_required"}
