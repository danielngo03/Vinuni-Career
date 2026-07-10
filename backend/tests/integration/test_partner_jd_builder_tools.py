"""Tests for the conversational JD-builder tools (Lane B).

Covers ``draft_job_from_text`` (pasted-JD structuring through the gateway-based
extraction path) and ``validate_job_draft`` (deterministic, no-LLM slot-filling
validation), plus the FROZEN ``job_draft`` render-artifact contract now shared
by ``draft_job_from_attachment`` and ``draft_job_description``.

Offline/deterministic: the happy structuring path is exercised through the
documented ``jd_builder._run_extraction`` seam; the REAL extraction path is
exercised only through its user-safe failure branches (not-a-JD rejection is
deterministic; a valid JD offline → ``ai_unavailable`` — never fabricated).
"""

from __future__ import annotations

import uuid

from app.modules.ai_assistant.application.native_loop import available_specs
from app.modules.ai_assistant.application.tools import jd_builder, jd_jobs, partner
from app.modules.ai_assistant.application.tools.dispatch import (
    SUPPORTED_TOOL_NAMES,
    dispatch_tool,
)
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS
from app.shared.permissions import GUEST, Principal

from tests.auth_utils import register_verified
from tests.messaging_utils import make_partner
from tests.org_utils import add_member

_NEW_TOOLS = ("draft_job_from_text", "validate_job_draft")

_LEAK_KEYS = ("provider", "model", "token", "api_key", "storage_key", "prompt_version")

_LONG_DESCRIPTION = (
    "We are hiring a backend engineer to design, build, and operate the APIs "
    "powering our recruiting platform. You will work with product and data "
    "teams, own services end to end, and mentor junior engineers on testing "
    "and reliability practices across the stack."
)
assert len(_LONG_DESCRIPTION) >= 200


def _assert_no_leak(result: dict) -> None:
    for k in _LEAK_KEYS:
        assert k not in result, f"leaked {k!r} in tool result"


def _valid_draft_args(**over) -> dict:
    base = {
        "title": "Backend Engineer",
        "description": _LONG_DESCRIPTION,
        "employment_type": "full_time",
        "location_city": "Hanoi",
        "required_skills": ["Python", "SQL", "FastAPI"],
        "salary_min": 20_000_000,
        "salary_max": 35_000_000,
        "salary_currency": "VND",
        "experience_min_years": 1,
        "experience_max_years": 3,
    }
    base.update(over)
    return base


def _artifact(result: dict) -> dict:
    render = result.get("render")
    assert isinstance(render, dict), "job_draft render artifact missing"
    return render


def _assert_job_draft_artifact(result: dict) -> None:
    """The FROZEN contract every JD tool returns (frontend builds against it)."""

    render = _artifact(result)
    assert render["kind"] == "job_draft"
    assert set(render.keys()) == {"kind", "draft", "missing_required", "warnings", "ready"}
    assert isinstance(render["draft"], dict)
    assert isinstance(render["missing_required"], list)
    assert isinstance(render["ready"], bool)
    for w in render["warnings"]:
        assert set(w.keys()) == {"code", "message"}
    # The model sees the same fields (minus render).
    for key in ("draft", "missing_required", "warnings", "ready"):
        assert result[key] == render[key]


# --------------------------------------------------------------------------- #
# Registry / RBAC visibility                                                   #
# --------------------------------------------------------------------------- #


def test_jd_builder_tools_registered() -> None:
    for name in _NEW_TOOLS:
        assert name in TOOL_SPECS
        assert name in SUPPORTED_TOOL_NAMES
        spec = TOOL_SPECS[name]
        assert spec.permission_class == "read_only"
        assert spec.persona == ["partner_user"]
        assert "ai_recruiting:draft_jd" in spec.required_permissions
        assert spec.audit_event_type.startswith("TOOL_")
        assert spec.fallback


async def test_jd_builder_visibility_by_grant(db_session) -> None:
    _u, org, admin = await make_partner(db_session)
    _mu, _m, member = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    student_user = await register_verified(
        db_session, email=f"s_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    student = Principal(user_id=student_user.id, persona="student", permissions=frozenset())

    admin_tools = {s.name for s in available_specs(admin)}
    member_tools = {s.name for s in available_specs(member)}
    student_tools = {s.name for s in available_specs(student)}

    assert set(_NEW_TOOLS) <= admin_tools
    assert not set(_NEW_TOOLS) & member_tools  # no ai_recruiting:draft_jd grant
    assert not set(_NEW_TOOLS) & student_tools


async def test_jd_builder_guest_denied(db_session) -> None:
    for name in _NEW_TOOLS:
        res = await dispatch_tool(
            name,
            {"jd_text": "x" * 300} if name == "draft_job_from_text" else {},
            session=db_session,
            principal=GUEST,
        )
        assert res["ok"] is False


# --------------------------------------------------------------------------- #
# validate_job_draft — deterministic matrix                                    #
# --------------------------------------------------------------------------- #


async def test_validate_empty_draft_reports_all_required(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool("validate_job_draft", {}, session=db_session, principal=admin)
    assert res["ok"] is True
    assert res["missing_required"] == ["title", "description", "employment_type"]
    assert res["ready"] is False
    _assert_job_draft_artifact(res)
    _assert_no_leak(res)


async def test_validate_complete_draft_is_ready(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "validate_job_draft", _valid_draft_args(), session=db_session, principal=admin
    )
    assert res["ok"] is True
    assert res["missing_required"] == []
    assert res["ready"] is True
    codes = {w["code"] for w in res["warnings"]}
    assert not codes, f"unexpected warnings: {codes}"
    _assert_job_draft_artifact(res)


async def test_validate_flags_salary_range_and_currency(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "validate_job_draft",
        _valid_draft_args(salary_min=50_000_000, salary_max=10_000_000, salary_currency="DOGE"),
        session=db_session,
        principal=admin,
    )
    codes = {w["code"] for w in res["warnings"]}
    assert "salary_range_invalid" in codes
    assert "salary_currency_unknown" in codes
    assert res["ready"] is False  # structurally invalid values block readiness


async def test_validate_flags_experience_range(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "validate_job_draft",
        _valid_draft_args(experience_min_years=10, experience_max_years=2),
        session=db_session,
        principal=admin,
    )
    assert "experience_range_invalid" in {w["code"] for w in res["warnings"]}
    assert res["ready"] is False


async def test_validate_flags_invalid_employment_type(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "validate_job_draft",
        _valid_draft_args(employment_type="fulltime"),
        session=db_session,
        principal=admin,
    )
    assert res["missing_required"] == []  # present, just invalid
    assert "employment_type_invalid" in {w["code"] for w in res["warnings"]}
    assert res["ready"] is False


async def test_validate_advisory_warnings_do_not_block_ready(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "validate_job_draft",
        {
            "title": "Barista",
            "description": "Short description under two hundred characters.",
            "employment_type": "part_time",
            # no location, < 3 skills
        },
        session=db_session,
        principal=admin,
    )
    codes = {w["code"] for w in res["warnings"]}
    assert {"missing_location", "few_required_skills", "description_short"} <= codes
    assert res["ready"] is True  # advisory-only warnings never block


async def test_validate_bias_warning_is_advisory(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "validate_job_draft",
        _valid_draft_args(description=_LONG_DESCRIPTION + " This role is for males only."),
        session=db_session,
        principal=admin,
    )
    assert "bias_language" in {w["code"] for w in res["warnings"]}
    assert res["ready"] is True


# --------------------------------------------------------------------------- #
# draft_job_from_text                                                          #
# --------------------------------------------------------------------------- #


async def test_draft_from_text_rejects_non_jd(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    junk = "grocery list: milk, eggs, bread, coffee, bananas. " * 20
    res = await dispatch_tool(
        "draft_job_from_text", {"jd_text": junk}, session=db_session, principal=admin
    )
    assert res == {"ok": False, "error": "not_a_jd"}


async def test_draft_from_text_rejects_blank_as_not_jd(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "draft_job_from_text", {"jd_text": "hi"}, session=db_session, principal=admin
    )
    assert res["ok"] is False
    assert res["error"] == "not_a_jd"


async def test_draft_from_text_rejects_oversize(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "draft_job_from_text",
        {"jd_text": "x" * (jd_builder.MAX_JD_TEXT_CHARS + 1)},
        session=db_session,
        principal=admin,
    )
    assert res == {"ok": False, "error": "jd_text_too_long"}


async def test_draft_from_text_missing_arg_fails_validation(db_session) -> None:
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool("draft_job_from_text", {}, session=db_session, principal=admin)
    assert res["ok"] is False
    assert res["error"] == "missing_jd_text"


async def test_draft_from_text_offline_valid_jd_is_ai_unavailable(db_session) -> None:
    """A real JD offline reaches the gateway tier and degrades user-safely.

    It must NEVER produce a fabricated draft when the structuring model is
    unavailable (AI_REAL_CALLS_ENABLED=false in tests).
    """

    _u, _org, admin = await make_partner(db_session)
    jd_text = (
        "Tuyển dụng: Kỹ sư phần mềm backend. Mô tả công việc: xây dựng API cho "
        "nền tảng tuyển dụng. Trách nhiệm: phát triển dịch vụ, viết tài liệu. "
        "Yêu cầu: Python, SQL, 2 năm kinh nghiệm. Quyền lợi: bảo hiểm, thưởng. "
    ) * 3
    res = await dispatch_tool(
        "draft_job_from_text", {"jd_text": jd_text}, session=db_session, principal=admin
    )
    assert res["ok"] is False
    assert res["error"] == "ai_unavailable"
    assert "draft" not in res


async def test_draft_from_text_happy_path_via_seam(db_session, monkeypatch) -> None:
    _u, _org, admin = await make_partner(db_session)

    async def fake_extraction(jd_text: str) -> dict:
        return {
            "status": "ok",
            "title": "Data Analyst",
            "description": _LONG_DESCRIPTION,
            "employment_type": "full_time",
            "location_type": "hybrid",
            "location_city": "Hanoi",
            "required_skills": ["SQL", "Python", "Tableau"],
            "salary_min": 18_000_000,
            "salary_max": 30_000_000,
            "salary_currency": "VND",
            "seniority_level": "junior",
            "needs_review": True,
            # junk the normalizer must drop, never surface
            "employment_type_raw": "FT",
        }

    monkeypatch.setattr(jd_builder, "_run_extraction", fake_extraction)
    res = await dispatch_tool(
        "draft_job_from_text",
        {"jd_text": "đây là JD hợp lệ " * 30, "target_language": "vi"},
        session=db_session,
        principal=admin,
    )
    assert res["ok"] is True
    _assert_job_draft_artifact(res)
    draft = res["draft"]
    assert draft["title"] == "Data Analyst"
    assert draft["employment_type"] == "full_time"
    assert draft["required_skills"] == ["SQL", "Python", "Tableau"]
    assert "employment_type_raw" not in draft
    assert res["missing_required"] == []
    assert res["ready"] is True
    assert res["needs_review"] is True
    assert res["target_language"] == "vi"
    _assert_no_leak(res)


async def test_draft_from_text_invalid_extracted_enum_becomes_missing(
    db_session, monkeypatch
) -> None:
    _u, _org, admin = await make_partner(db_session)

    async def fake_extraction(jd_text: str) -> dict:
        return {
            "status": "ok",
            "title": "Cashier",
            "description": _LONG_DESCRIPTION,
            "employment_type": "freelance",  # not in the vocabulary → dropped
        }

    monkeypatch.setattr(jd_builder, "_run_extraction", fake_extraction)
    res = await dispatch_tool(
        "draft_job_from_text",
        {"jd_text": "another valid jd " * 30},
        session=db_session,
        principal=admin,
    )
    assert res["ok"] is True
    assert "employment_type" not in res["draft"]
    assert res["missing_required"] == ["employment_type"]
    assert res["ready"] is False


# --------------------------------------------------------------------------- #
# Frozen artifact on the pre-existing JD tools                                 #
# --------------------------------------------------------------------------- #


async def test_draft_job_from_attachment_returns_job_draft_artifact(
    db_session, monkeypatch
) -> None:
    from app.modules.ai_assistant.application import attachment_service
    from app.modules.opportunities.application import jd_upload_service

    _u, _org, admin = await make_partner(db_session)

    async def fake_get_owned_file(session, *, principal, attachment_id):
        return "jd.pdf", b"%PDF-fake"

    async def fake_extract(filename, data, content_type=None):
        return {
            "status": "ok",
            "title": "QA Engineer",
            "description": _LONG_DESCRIPTION + " This role is for males only.",
            "employment_type": "full_time",
            "needs_review": False,
        }

    monkeypatch.setattr(attachment_service, "get_owned_file", fake_get_owned_file)
    monkeypatch.setattr(jd_upload_service, "extract_jd_from_upload", fake_extract)

    res = await jd_jobs.draft_job_from_attachment(
        db_session, admin, {"attachment_id": str(uuid.uuid4())}
    )
    assert res["ok"] is True
    _assert_job_draft_artifact(res)
    assert res["draft"]["title"] == "QA Engineer"
    # Bias in the extracted description surfaces both as the frozen warning and
    # the backward-compatible flag.
    assert "bias_language" in {w["code"] for w in res["warnings"]}
    assert res["bias_flagged"] is True


async def test_draft_job_description_returns_job_draft_artifact(
    db_session, monkeypatch
) -> None:
    from app.modules.opportunities.application import jd_ai_service

    _u, _org, admin = await make_partner(db_session)

    async def fake_standalone(session, *, principal, payload):
        return {
            "draft": _LONG_DESCRIPTION,
            "bias_check": {"flagged": False, "requires_human_review": False},
        }

    monkeypatch.setattr(jd_ai_service, "draft_description_standalone", fake_standalone)
    res = await partner.draft_job_description(
        db_session,
        admin,
        {
            "title": "Marketing Intern",
            "employment_type": "internship",
            "location": "Hanoi",
            "required_skills": "SEO, Content, Analytics",
        },
    )
    assert res["ok"] is True
    _assert_job_draft_artifact(res)
    draft = res["draft"]
    assert draft["title"] == "Marketing Intern"
    assert draft["description"] == _LONG_DESCRIPTION
    assert draft["employment_type"] == "internship"
    assert draft["location_city"] == "Hanoi"
    assert draft["required_skills"] == ["SEO", "Content", "Analytics"]
    assert res["ready"] is True
    assert res["bias_flagged"] is False
