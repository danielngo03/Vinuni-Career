"""Student CV↔job match tools + career-brief agent (offline provider, SQLite).

Covers, for the five new student render tools (``match_cv_to_jobs``,
``explain_job_fit``, ``compare_jobs``, ``show_cv``, ``compare_cvs``) plus the
``student_career_brief`` workforce agent:

- the FROZEN render-artifact shapes (``docs/superpowers/specs/2026-07-11-
  student-ai-power-design.md`` §3);
- the shared CV-resolution rule (0 CVs → helpful message; 1 → used silently;
  >1 → ``cv_picker`` with NO heavy CV data in model-visible fields);
- principal-scoping isolation (student A can never resolve student B's CV);
- handler-layer RBAC (a partner principal is refused ``student_only``);
- no provider/model/token/embedding leak in any tool payload.
"""

from __future__ import annotations

import json
import uuid

from app.ai.agents import workforce
from app.modules.ai_assistant.application.tools import student_match
from app.modules.ai_assistant.application.tools.dispatch import dispatch_tool
from app.modules.documents.domain.models import CvProfile, CvSection
from app.modules.opportunities.application import job_service, moderation_service
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_ready_cv, make_student
from tests.org_utils import make_org_with_admin

_FORBIDDEN = [
    "openrouter",
    "openai",
    "anthropic",
    "claude",
    "gpt-4",
    "gemini",
    "deepseek",
    "chat_cheap",
    "model_alias",
    "prompt_tokens",
    "completion_tokens",
    "storage_path",
    "storage_key",
    "confidence",
    "embedding",
]


def _assert_no_leak(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term}"


def _job_payload(**over) -> dict:
    base = {
        "title": "Backend Intern",
        "description": "We are hiring a backend intern to build REST APIs.",
        "requirements": "Experience with Python and FastAPI is required.",
        "benefits": None,
        "employment_type": "internship",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["PostgreSQL"],
        "salary_min": 10_000_000,
        "salary_max": 20_000_000,
        "salary_currency": "VND",
        "salary_is_disclosed": True,
        "headcount": 1,
        "visibility": "public",
    }
    base.update(over)
    return base


async def _create_job(db, *, title: str = "Backend Intern", **over) -> uuid.UUID:
    _u, _org, admin = await make_org_with_admin(db)
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    created = await job_service.create_job(
        db, principal=admin, payload=_job_payload(title=title, **over), ctx=CTX
    )
    jid = uuid.UUID(created["id"])
    await job_service.submit_job(db, principal=admin, job_id=jid, ctx=CTX)
    await moderation_service.approve_job(db, principal=uni, job_id=jid, ctx=CTX)
    return jid


async def _seed_section(db, cv_id: str, section_type: str, content: dict) -> None:
    """Set a CV section's content and bump the profile version (mirrors a real edit
    so job-fit reads the freshly-seeded content instead of the finalize snapshot)."""
    cid = uuid.UUID(cv_id)
    cv = (await db.execute(select(CvProfile).where(CvProfile.id == cid))).scalar_one()
    sections = (
        (await db.execute(select(CvSection).where(CvSection.cv_id == cid))).scalars().all()
    )
    target = next(s for s in sections if s.section_type == section_type)
    target.content_json = content
    cv.version += 1
    await db.commit()


async def _make_matchable_cv(db, student, *, title: str = "Backend CV") -> str:
    cv = await make_ready_cv(db, student=student, title=title)
    await _seed_section(
        db,
        cv["id"],
        "skills",
        {"items": [{"name": "Python", "level": 90}, {"name": "FastAPI", "level": 80}]},
    )
    await _seed_section(
        db,
        cv["id"],
        "experience",
        {"entries": [{"heading": "Backend Intern", "highlights": ["Built REST APIs in FastAPI."]}]},
    )
    return cv["id"]


# --------------------------------------------------------------------------- #
# show_cv + CV-resolution rule                                                 #
# --------------------------------------------------------------------------- #


async def test_show_cv_single_cv_renders_card(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _make_matchable_cv(db_session, student, title="My Backend CV")

    result = await student_match.show_cv(db_session, student, {})

    assert result["ok"] is True
    render = result["render"]
    assert render["kind"] == "cv_card"
    assert render["cv_id"] == cv_id
    assert render["source"] == "template"
    assert render["view_path"] == f"/student/cv/{cv_id}"
    assert render["is_default"] is True
    names = {s["name"] for s in render["top_skills"]}
    assert {"Python", "FastAPI"} <= names
    assert render["experience_count"] == 1
    _assert_no_leak(result)


async def test_show_cv_multiple_cvs_returns_picker_without_heavy_data(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student, title="CV One")
    await _make_matchable_cv(db_session, student, title="CV Two")

    result = await student_match.show_cv(db_session, student, {})

    assert result["ok"] is True
    assert result["needs_cv_selection"] is True
    # Model-visible fields carry only a short instruction — no CV titles/skills.
    assert set(result) == {"ok", "needs_cv_selection", "instruction", "render"}
    render = result["render"]
    assert render["kind"] == "cv_picker"
    assert render["pending_tool"] == "show_cv"
    assert "cv_id" not in render["pending_args"]
    assert len(render["cvs"]) == 2
    assert {c["title"] for c in render["cvs"]} == {"CV One", "CV Two"}


async def test_show_cv_zero_cvs_returns_helpful_message(db_session) -> None:
    _u, student = await make_student(db_session)

    result = await student_match.show_cv(db_session, student, {})

    assert result["ok"] is True
    assert result["no_cv"] is True
    assert "render" not in result


async def test_show_cv_invalid_cv_id_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student)

    result = await student_match.show_cv(db_session, student, {"cv_id": "not-a-uuid"})
    assert result == {"ok": False, "error": "invalid_cv_id"}


# --------------------------------------------------------------------------- #
# Principal-scoping isolation + handler RBAC                                    #
# --------------------------------------------------------------------------- #


async def test_student_a_cannot_resolve_student_b_cv(db_session) -> None:
    _ua, student_a = await make_student(db_session, prefix="alice")
    _ub, student_b = await make_student(db_session, prefix="bob")
    await _make_matchable_cv(db_session, student_a, title="Alice CV")
    b_cv_id = await _make_matchable_cv(db_session, student_b, title="Bob CV")

    # Alice asks to show Bob's CV id → not found in HER library (never Bob's card).
    result = await student_match.show_cv(db_session, student_a, {"cv_id": b_cv_id})
    assert result == {"ok": False, "error": "cv_not_found"}


async def test_partner_principal_refused_student_only(db_session) -> None:
    _u, _org, partner = await make_org_with_admin(db_session)

    result = await dispatch_tool(
        "match_cv_to_jobs", {}, session=db_session, principal=partner
    )
    assert result == {"ok": False, "error": "student_only"}


# --------------------------------------------------------------------------- #
# match_cv_to_jobs → job_match_list                                            #
# --------------------------------------------------------------------------- #


async def test_match_cv_to_jobs_renders_match_list(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _make_matchable_cv(db_session, student)
    await _create_job(db_session, title="Backend Intern")

    result = await student_match.match_cv_to_jobs(db_session, student, {})

    assert result["ok"] is True
    render = result["render"]
    assert render["kind"] == "job_match_list"
    assert render["cv_id"] == cv_id
    assert render["total"] >= 1
    item = render["items"][0]
    assert isinstance(item["fit_score"], int)
    assert item["fit_band"] in {"strong", "good", "fair", "weak"}
    assert item["view_path"].startswith("/jobs/")
    assert isinstance(item["is_saved"], bool)
    _assert_no_leak(result)


async def test_match_cv_to_jobs_zero_cvs_helpful(db_session) -> None:
    _u, student = await make_student(db_session)
    await _create_job(db_session)

    result = await student_match.match_cv_to_jobs(db_session, student, {})
    assert result["ok"] is True
    assert result["no_cv"] is True


# --------------------------------------------------------------------------- #
# explain_job_fit → fit_breakdown                                              #
# --------------------------------------------------------------------------- #


async def test_explain_job_fit_renders_breakdown(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _make_matchable_cv(db_session, student)
    job_id = await _create_job(db_session)

    result = await student_match.explain_job_fit(
        db_session, student, {"job_id": str(job_id)}
    )

    assert result["ok"] is True
    render = result["render"]
    assert render["kind"] == "fit_breakdown"
    assert render["cv_id"] == cv_id
    assert render["job_id"] == str(job_id)
    assert render["fit_band"] in {"strong", "good", "fair", "weak"}
    for miss in render["missing_skills"]:
        assert miss["importance"] in {"high", "medium", "low"}
    assert isinstance(render["suggestions"], list)
    _assert_no_leak(result)


async def test_explain_job_fit_invalid_job(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student)

    result = await student_match.explain_job_fit(db_session, student, {"job_id": "nope"})
    assert result == {"ok": False, "error": "invalid_job_id"}


async def test_explain_job_fit_unknown_job_not_found(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student)

    result = await student_match.explain_job_fit(
        db_session, student, {"job_id": str(uuid.uuid4())}
    )
    assert result == {"ok": False, "error": "job_not_found"}


# --------------------------------------------------------------------------- #
# compare_jobs → job_compare                                                   #
# --------------------------------------------------------------------------- #


async def test_compare_jobs_side_by_side(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student)
    j1 = await _create_job(db_session, title="Backend Intern")
    j2 = await _create_job(db_session, title="Data Intern", required_skills=["SQL", "Python"])

    result = await student_match.compare_jobs(
        db_session, student, {"job_ids": [str(j1), str(j2)]}
    )

    assert result["ok"] is True
    assert result["has_fit"] is True
    render = result["render"]
    assert render["kind"] == "job_compare"
    assert len(render["jobs"]) == 2
    label_keys = {row["label_key"] for row in render["rows"]}
    assert "fit" in label_keys
    assert "salary" in label_keys
    for row in render["rows"]:
        assert len(row["values"]) == 2  # aligned one value per job
    _assert_no_leak(result)


async def test_compare_jobs_requires_two_to_four(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student)
    j1 = await _create_job(db_session)

    result = await student_match.compare_jobs(db_session, student, {"job_ids": [str(j1)]})
    assert result == {"ok": False, "error": "need_2_to_4_jobs"}


async def test_compare_jobs_missing_ids(db_session) -> None:
    _u, student = await make_student(db_session)
    result = await student_match.compare_jobs(db_session, student, {})
    assert result == {"ok": False, "error": "job_ids_required"}


# --------------------------------------------------------------------------- #
# compare_cvs → cv_compare                                                     #
# --------------------------------------------------------------------------- #


async def test_compare_cvs_for_job_recommends_one(db_session) -> None:
    _u, student = await make_student(db_session)
    strong = await _make_matchable_cv(db_session, student, title="Strong CV")
    weak = await make_ready_cv(db_session, student=student, title="Empty CV")
    job_id = await _create_job(db_session)

    result = await student_match.compare_cvs(
        db_session, student, {"job_id": str(job_id)}
    )

    assert result["ok"] is True
    render = result["render"]
    assert render["kind"] == "cv_compare"
    assert render["job_id"] == str(job_id)
    ids = {c["cv_id"] for c in render["cvs"]}
    assert {strong, weak["id"]} <= ids
    assert render["recommended_cv_id"] in ids
    for entry in render["cvs"]:
        assert entry["fit_band"] in {"strong", "good", "fair", "weak", None}
    _assert_no_leak(result)


async def test_compare_cvs_no_job_ranks_by_strength(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student, title="Rich CV")
    await make_ready_cv(db_session, student=student, title="Bare CV")

    result = await student_match.compare_cvs(db_session, student, {})

    assert result["ok"] is True
    render = result["render"]
    assert render["kind"] == "cv_compare"
    assert render["job_id"] is None
    assert all(c["fit_score"] is None for c in render["cvs"])
    assert render["recommended_cv_id"] is not None


async def test_compare_cvs_zero_cvs_helpful(db_session) -> None:
    _u, student = await make_student(db_session)
    result = await student_match.compare_cvs(db_session, student, {})
    assert result["ok"] is True
    assert result["no_cv"] is True


# --------------------------------------------------------------------------- #
# Dispatch integration (arg validation + render pop contract)                  #
# --------------------------------------------------------------------------- #


async def test_dispatch_explain_job_fit_missing_required_arg(db_session) -> None:
    _u, student = await make_student(db_session)
    result = await dispatch_tool("explain_job_fit", {}, session=db_session, principal=student)
    assert result == {"ok": False, "error": "missing_job_id"}


async def test_dispatch_show_cv_returns_render_block(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student)
    result = await dispatch_tool("show_cv", {}, session=db_session, principal=student)
    assert result["ok"] is True
    assert result["render"]["kind"] == "cv_card"


# --------------------------------------------------------------------------- #
# student_career_brief workforce agent (deterministic offline)                 #
# --------------------------------------------------------------------------- #


async def test_student_career_brief_deterministic_render(db_session) -> None:
    _u, student = await make_student(db_session)
    await _make_matchable_cv(db_session, student)
    await _create_job(db_session, title="Backend Intern")
    await _create_job(db_session, title="Python Developer", required_skills=["Python"])

    result = await workforce.student_career_brief(db_session, principal=student)

    assert result["ok"] is True
    render = result["render"]
    assert render["kind"] == "career_brief"
    assert isinstance(render["top_matches"], list) and render["top_matches"]
    for match in render["top_matches"]:
        assert match["fit_band"] in {"strong", "good", "fair", "weak"}
    assert isinstance(render["summary"], str) and render["summary"]
    _assert_no_leak(result)


async def test_student_career_brief_no_cv_is_empty(db_session) -> None:
    _u, student = await make_student(db_session)
    result = await workforce.student_career_brief(db_session, principal=student)
    assert result["ok"] is True
    assert result["empty"] is True
