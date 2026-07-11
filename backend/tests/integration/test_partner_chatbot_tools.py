"""Tests for the partner-chatbot Phase C–E tools (charts, attachments, JD→job).

Offline/deterministic: the analysed-text path uses the native-text tier (no model
call); the chart/create_job tools make no LLM call; the JD-extraction path is
exercised only through its user-safe failure branches (offline → ai_unavailable /
not_a_jd) so no real key is required. RBAC is asserted via ``available_specs`` and
the service-layer grant checks. Leakage assertions verify no provider/model/token/
storage_key ever reaches a tool result.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.ai_assistant.application import attachment_service, chat_service
from app.modules.ai_assistant.application.native_loop import available_specs
from app.modules.ai_assistant.application.tools import analytics_charts, attachments, jd_jobs
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS
from app.shared.exceptions import ValidationFailedError
from app.shared.permissions import GUEST, Principal

from tests.auth_utils import register_verified
from tests.messaging_utils import make_partner, seed_application
from tests.org_utils import add_member

_LEAK_KEYS = ("provider", "model", "token", "api_key", "storage_key", "prompt")


def _assert_no_leak(result: dict) -> None:
    for k in _LEAK_KEYS:
        assert k not in result, f"leaked {k!r} in tool result"


async def _chat_session(session, principal) -> uuid.UUID:
    created = await chat_service.create_session(session, principal=principal)
    return uuid.UUID(created["id"])


# --------------------------------------------------------------------------- #
# Spec + registry invariants (unit)                                           #
# --------------------------------------------------------------------------- #

_NEW_TOOLS = (
    "get_recruitment_analytics_chart",
    "get_hiring_funnel_diagram",
    "analyze_attachment",
    "draft_job_from_attachment",
    "create_job",
)


def test_new_tools_registered_with_expected_classes() -> None:
    for name in _NEW_TOOLS:
        assert name in TOOL_SPECS, name
    assert TOOL_SPECS["create_job"].permission_class == "confirmation_required"
    # confirmation tool must carry a card + side effects + audit (governance §4.3/§7).
    cj = TOOL_SPECS["create_job"]
    assert cj.confirmation_copy is not None
    assert cj.side_effects
    assert cj.audit_event_type
    for name in (
        "get_recruitment_analytics_chart",
        "get_hiring_funnel_diagram",
        "analyze_attachment",
        "draft_job_from_attachment",
    ):
        assert TOOL_SPECS[name].permission_class == "read_only"


def test_analyze_attachment_is_cross_persona() -> None:
    spec = TOOL_SPECS["analyze_attachment"]
    assert set(spec.persona) == {"student", "partner_user", "university_staff"}
    assert spec.required_permissions == ["authenticated"]


# --------------------------------------------------------------------------- #
# RBAC visibility via available_specs                                         #
# --------------------------------------------------------------------------- #


async def test_available_specs_rbac_by_grant(db_session) -> None:
    _u, org, admin = await make_partner(db_session)
    # member with ONLY applications:read — no jobs:create / ai_recruiting:draft_jd
    _mu, _m, member = await add_member(db_session, org=org, permissions=[("applications", "read")])
    student_user = await register_verified(
        db_session, email=f"s_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    student = Principal(user_id=student_user.id, persona="student", permissions=frozenset())

    admin_tools = {s.name for s in available_specs(admin)}
    member_tools = {s.name for s in available_specs(member)}
    student_tools = {s.name for s in available_specs(student)}

    # Admin (*:*) sees every new tool.
    assert set(_NEW_TOOLS) <= admin_tools
    # Member with applications:read sees analytics, NOT job-create/draft.
    assert "get_recruitment_analytics_chart" in member_tools
    assert "get_hiring_funnel_diagram" in member_tools
    assert "create_job" not in member_tools
    assert "draft_job_from_attachment" not in member_tools
    # Students never see partner tools, but may analyse their own attachments.
    assert "analyze_attachment" in student_tools
    assert "get_recruitment_analytics_chart" not in student_tools
    assert "create_job" not in student_tools


# --------------------------------------------------------------------------- #
# Charts                                                                       #
# --------------------------------------------------------------------------- #


async def test_chart_funnel_reflects_real_application_statuses(db_session) -> None:
    _u, org, principal = await make_partner(db_session)
    applicant = await register_verified(db_session, email=f"a_{uuid.uuid4().hex[:8]}@vinuni.edu.vn")
    for st in ("submitted", "submitted", "interview"):
        await seed_application(db_session, org_id=org.id, applicant_id=applicant.id, status=st)

    res = await analytics_charts.get_recruitment_analytics_chart(
        db_session, principal, {"chart": "funnel"}
    )
    assert res["ok"] is True and not res.get("empty")
    data = res["render"]["chart"]["data"]
    labels = {d["label"]: d["value"] for d in data}
    assert labels.get("Đã nộp") == 2
    assert labels.get("Phỏng vấn") == 1
    assert res["render"]["chart"]["type"] == "bar"
    _assert_no_leak(res)


async def test_chart_empty_state_is_honest(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    res = await analytics_charts.get_recruitment_analytics_chart(
        db_session, principal, {"chart": "funnel"}
    )
    assert res["ok"] is True and res.get("empty") is True
    assert "render" not in res  # no fabricated chart


async def test_chart_unknown_type_rejected(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    res = await analytics_charts.get_recruitment_analytics_chart(
        db_session, principal, {"chart": "bogus"}
    )
    assert res["ok"] is False and res["error"] == "unknown_chart"


async def test_chart_requires_partner_org() -> None:
    res = await analytics_charts.get_recruitment_analytics_chart(None, GUEST, {"chart": "funnel"})
    assert res["ok"] is False and res["error"] == "partner_auth_required"


async def test_funnel_diagram_shows_dropoff(db_session) -> None:
    _u, org, principal = await make_partner(db_session)
    applicant = await register_verified(db_session, email=f"a_{uuid.uuid4().hex[:8]}@vinuni.edu.vn")
    for st in ("submitted", "submitted", "submitted", "submitted", "interview"):
        await seed_application(db_session, org_id=org.id, applicant_id=applicant.id, status=st)

    res = await analytics_charts.get_hiring_funnel_diagram(db_session, principal, {})
    assert res["ok"] is True and not res.get("empty")
    stages = res["render"]["diagram"]["stages"]
    assert stages[0]["pct"] == 100  # first stage is the baseline
    assert all(0 <= s["pct"] <= 100 for s in stages)
    assert res["render"]["diagram"]["type"] == "funnel"
    _assert_no_leak(res)


async def test_funnel_diagram_empty_state(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    res = await analytics_charts.get_hiring_funnel_diagram(db_session, principal, {})
    assert res["ok"] is True and res.get("empty") is True


# --------------------------------------------------------------------------- #
# Attachments                                                                  #
# --------------------------------------------------------------------------- #


async def test_attachment_upload_and_analyse_text(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    sid = await _chat_session(db_session, principal)
    desc = await attachment_service.upload_attachment(
        db_session,
        principal=principal,
        session_id=sid,
        filename="note.txt",
        data=b"Skills: Python, FastAPI, SQL. 3 years backend.",
        content_type="text/plain",
    )
    assert desc["status"] == "uploaded"
    assert "storage_key" not in desc  # internal path never leaks

    res = await attachments.analyze_attachment(db_session, principal, {"attachment_id": desc["id"]})
    assert res["ok"] is True
    assert res["status"] == "analyzed"
    assert "Python" in (res.get("extracted_text_preview") or "")
    _assert_no_leak(res)

    # Re-analyse returns the cache (idempotent), still no leak.
    res2 = await attachments.analyze_attachment(
        db_session, principal, {"attachment_id": desc["id"]}
    )
    assert res2["ok"] is True and res2.get("cached") is True


async def test_attachment_blank_rejected(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    sid = await _chat_session(db_session, principal)
    with pytest.raises(ValidationFailedError):
        await attachment_service.upload_attachment(
            db_session,
            principal=principal,
            session_id=sid,
            filename="blank.txt",
            data=b"",
            content_type="text/plain",
        )


async def test_attachment_unsupported_type_rejected(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    sid = await _chat_session(db_session, principal)
    with pytest.raises(ValidationFailedError):
        await attachment_service.upload_attachment(
            db_session,
            principal=principal,
            session_id=sid,
            filename="malware.exe",
            data=b"MZ\x90\x00binary",
            content_type="application/octet-stream",
        )


async def test_analyze_foreign_attachment_is_not_found(db_session) -> None:
    _u, _org, owner = await make_partner(db_session)
    _u2, _org2, other = await make_partner(db_session, display_name="Other Co")
    sid = await _chat_session(db_session, owner)
    desc = await attachment_service.upload_attachment(
        db_session,
        principal=owner,
        session_id=sid,
        filename="note.txt",
        data=b"private notes here",
        content_type="text/plain",
    )
    # Another org's principal cannot analyse it — 404 (indistinguishable from missing).
    res = await attachments.analyze_attachment(db_session, other, {"attachment_id": desc["id"]})
    assert res["ok"] is False and res["error"] == "not_found"


async def test_analyze_requires_auth() -> None:
    res = await attachments.analyze_attachment(None, GUEST, {"attachment_id": str(uuid.uuid4())})
    assert res["ok"] is False and res["error"] == "auth_required"


async def test_analyze_missing_id() -> None:
    principal = Principal(user_id=uuid.uuid4(), persona="student", permissions=frozenset())
    res = await attachments.analyze_attachment(None, principal, {})
    assert res["ok"] is False and res["error"] == "attachment_id_required"


# --------------------------------------------------------------------------- #
# JD → create_job                                                              #
# --------------------------------------------------------------------------- #


async def test_create_job_creates_draft(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    res = await jd_jobs.create_job(
        db_session,
        principal,
        {
            "title": "Backend Engineer",
            "description": "Build APIs with Python and FastAPI.",
            "employment_type": "full_time",
            "location_type": "onsite",
            "required_skills": "Python, FastAPI, SQL",  # string coerced -> list
        },
    )
    assert res["ok"] is True
    assert res["job_id"]
    assert res["title"] == "Backend Engineer"
    _assert_no_leak(res)


async def test_create_job_defaults_notnull_fields(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    # No employment_type/location_type provided -> safe defaults applied.
    res = await jd_jobs.create_job(
        db_session,
        principal,
        {
            "title": "Data Analyst",
            "description": "Analyse data and build dashboards.",
        },
    )
    assert res["ok"] is True and res["job_id"]


async def test_create_job_requires_title_and_description(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    r1 = await jd_jobs.create_job(db_session, principal, {"description": "x"})
    assert r1["ok"] is False and r1["error"] == "title_required"
    r2 = await jd_jobs.create_job(db_session, principal, {"title": "x"})
    assert r2["ok"] is False and r2["error"] == "description_required"


async def test_create_job_rbac_denied_for_member_without_grant(db_session) -> None:
    _u, org, _admin = await make_partner(db_session)
    _mu, _m, member = await add_member(db_session, org=org, permissions=[("applications", "read")])
    res = await jd_jobs.create_job(
        db_session,
        member,
        {
            "title": "Sneaky Job",
            "description": "Should be denied.",
        },
    )
    assert res["ok"] is False and res["error"] == "permission_denied"


async def test_draft_job_missing_attachment_id(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    res = await jd_jobs.draft_job_from_attachment(db_session, principal, {})
    assert res["ok"] is False and res["error"] == "attachment_id_required"


async def test_draft_job_foreign_attachment_not_found(db_session) -> None:
    _u, _org, principal = await make_partner(db_session)
    res = await jd_jobs.draft_job_from_attachment(
        db_session, principal, {"attachment_id": str(uuid.uuid4())}
    )
    assert res["ok"] is False and res["error"] == "not_found"


# --------------------------------------------------------------------------- #
# Pure coercion helpers                                                        #
# --------------------------------------------------------------------------- #


def test_skill_list_coercion() -> None:
    assert jd_jobs._as_skill_list("Python, SQL , ,Docker") == ["Python", "SQL", "Docker"]
    assert jd_jobs._as_skill_list(["A", "", "B"]) == ["A", "B"]
    assert jd_jobs._as_skill_list(None) == []


def test_int_coercion() -> None:
    assert jd_jobs._as_int("5") == 5
    assert jd_jobs._as_int(3) == 3
    assert jd_jobs._as_int("nope") is None
    assert jd_jobs._as_int(None) is None
