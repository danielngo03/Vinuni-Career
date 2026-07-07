"""Partner candidate-triage ranking service tests.

Covers the deterministic CV-JD applicant ranking
(``recruitment.candidate_ranking_service.rank_job_applicants``):

- happy path: the applicant whose CV clearly matches the JD skills ranks first
  with a higher deterministic ``fit_score``.
- both CV kinds: a builder-CV snapshot AND an uploaded-document snapshot are both
  scored by the adapter.
- RBAC/tenant: a cross-org caller -> 404; a same-org caller lacking
  ``applications:read`` -> 403.
- anonymity: an anonymous, not-yet-revealed applicant is masked (no name/email)
  but still receives a score.
- low-signal: a job with no usable requirements -> ``signal == "no_requirements"``
  and every ``fit_score`` null; an applicant with an empty snapshot -> null score
  but still listed.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import (
    cv_lifecycle_service,
    cv_service,
    snapshot_service,
)
from app.modules.documents.domain.models import CvParseRun, Document
from app.modules.opportunities.domain.models import Job
from app.modules.recruitment.application import access, apply_service, candidate_ranking_service
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, publish_job

MATCH_SKILLS = ["Python", "FastAPI", "PostgreSQL"]
NON_MATCH_SKILLS = ["Cooking", "Gardening", "Painting"]


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _setup_job(db, **over):
    _pu, porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db,
        partner_principal=partner,
        uni_principal=uni,
        title="Backend Engineer",
        required_skills=["python", "fastapi", "postgresql"],
        description="We are hiring a backend engineer to build Python FastAPI APIs.",
        **over,
    )
    return partner, porg, uni, job_id


async def _builder_cv_with_skills(db, *, student, skills, title="CV"):
    """A finalized (``ready``) builder CV whose skills section carries ``skills``."""

    cv = await cv_service.create_cv(
        db, principal=student,
        payload={"title": title, "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(cv["id"])
    version = cv["version"]
    header = next(s for s in cv["sections"] if s["section_type"] == "header")
    res = await cv_service.upsert_section(
        db, principal=student, cv_id=cv_id, section_id=uuid.UUID(header["id"]),
        payload={"content": {"name": "Test Candidate"}, "expected_version": version},
        ctx=CTX,
    )
    version = res["cv_version"]
    skills_sec = next(s for s in cv["sections"] if s["section_type"] == "skills")
    await cv_service.upsert_section(
        db, principal=student, cv_id=cv_id, section_id=uuid.UUID(skills_sec["id"]),
        payload={
            "content": {"items": [{"name": s, "level": 85} for s in skills]},
            "expected_version": version,
        },
        ctx=CTX,
    )
    detail = await cv_lifecycle_service.finalize_cv(
        db, principal=student, cv_id=cv_id, ctx=CTX,
    )
    return {
        "type": "builder_cv",
        "cv_profile_id": detail["id"],
        "cv_version_id": detail["current_version_id"],
        "uploaded_document_id": None,
    }


async def _uploaded_cv_selection(db, *, student_user, skills, empty=False):
    """A CV selection backed by a real Document + CvParseRun with extracted data."""

    doc = Document(
        user_id=student_user.id,
        doc_type="cv",
        original_name="cv.pdf",
        storage_path="test/cv.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        checksum_sha256="0" * 64,
        virus_scan_status="clean",
    )
    db.add(doc)
    await db.flush()
    if empty:
        extracted = {"contact": {"name": "Up Loaded", "email": "u@e.com", "phone": ""}}
    else:
        extracted = {
            "contact": {"name": "Up Loaded", "email": "u@e.com", "phone": ""},
            "skills": {"items": [{"name": s} for s in skills]},
            "experience": {
                "items": [{"text": "Backend developer building Python FastAPI APIs"}]
            },
        }
    run = CvParseRun(document_id=doc.id, status="succeeded", extracted_data=extracted)
    db.add(run)
    await db.flush()
    return {
        "type": "uploaded_document",
        "cv_profile_id": None,
        "cv_version_id": None,
        "uploaded_document_id": str(doc.id),
    }


async def _apply(db, *, student, job_id, cv_selection, is_anonymous=False):
    return await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(
            job_id=job_id, cv_selection=cv_selection, is_anonymous=is_anonymous
        ),
        ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #


async def test_ranking_orders_best_match_first(db_session) -> None:
    partner, _porg, _uni, job_id = await _setup_job(db_session)

    _ua, student_a = await make_student(db_session, prefix="match")
    _ub, student_b = await make_student(db_session, prefix="nomatch")
    sel_a = await _builder_cv_with_skills(db_session, student=student_a, skills=MATCH_SKILLS)
    sel_b = await _builder_cv_with_skills(
        db_session, student=student_b, skills=NON_MATCH_SKILLS
    )
    await _apply(db_session, student=student_a, job_id=job_id, cv_selection=sel_a)
    await _apply(db_session, student=student_b, job_id=job_id, cv_selection=sel_b)

    out = await candidate_ranking_service.rank_job_applicants(
        db_session, principal=partner, job_id=job_id, ctx=CTX,
    )

    assert out["job_id"] == str(job_id)
    assert out["scored_count"] == 2
    assert out["signal"] in ("ok", "low_signal")
    assert [i["rank"] for i in out["items"]] == [1, 2]

    top, second = out["items"]
    assert top["applicant"]["user_id"] == str(student_a.user_id)
    assert top["fit_score"] is not None and second["fit_score"] is not None
    assert top["fit_score"] > second["fit_score"]
    assert top["fit_band"] in ("strong", "good", "fair", "weak")
    # matched skills are JD-derived terms, never raw CV text / PII.
    assert any("python" in m.lower() for m in top["matched_skills"])


# --------------------------------------------------------------------------- #
# Both CV kinds scored by the adapter                                         #
# --------------------------------------------------------------------------- #


async def test_ranking_scores_builder_and_uploaded(db_session) -> None:
    partner, _porg, _uni, job_id = await _setup_job(db_session)

    ua, student_a = await make_student(db_session, prefix="builder")
    ub, student_b = await make_student(db_session, prefix="upload")
    sel_builder = await _builder_cv_with_skills(
        db_session, student=student_a, skills=MATCH_SKILLS
    )
    sel_uploaded = await _uploaded_cv_selection(
        db_session, student_user=ub, skills=MATCH_SKILLS
    )
    await _apply(db_session, student=student_a, job_id=job_id, cv_selection=sel_builder)
    await _apply(db_session, student=student_b, job_id=job_id, cv_selection=sel_uploaded)

    out = await candidate_ranking_service.rank_job_applicants(
        db_session, principal=partner, job_id=job_id, ctx=CTX,
    )

    assert out["scored_count"] == 2
    assert len(out["items"]) == 2
    # BOTH snapshot shapes were adapted + scored (no null, no crash).
    assert all(i["fit_score"] is not None for i in out["items"])
    scored_users = {i["applicant"]["user_id"] for i in out["items"]}
    assert scored_users == {str(ua.id), str(ub.id)}


# --------------------------------------------------------------------------- #
# RBAC / tenant isolation                                                     #
# --------------------------------------------------------------------------- #


async def test_ranking_cross_org_caller_404(db_session) -> None:
    _partner, _porg, _uni, job_id = await _setup_job(db_session)
    _ou, _oorg, other_partner = await make_org_with_admin(
        db_session, display_name="Other Co"
    )

    with pytest.raises(ResourceNotFoundError):
        await candidate_ranking_service.rank_job_applicants(
            db_session, principal=other_partner, job_id=job_id, ctx=CTX,
        )


async def test_ranking_missing_permission_403(db_session) -> None:
    _partner, porg, _uni, job_id = await _setup_job(db_session)
    # Same-org member WITHOUT applications:read (only an unrelated capability).
    _mu, _mem, member = await add_member(
        db_session, org=porg, permissions=[("scorecards", "read")]
    )

    with pytest.raises(PermissionDeniedError):
        await candidate_ranking_service.rank_job_applicants(
            db_session, principal=member, job_id=job_id, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Anonymity                                                                   #
# --------------------------------------------------------------------------- #


async def test_ranking_masks_anonymous_applicant_but_scores(db_session) -> None:
    partner, _porg, _uni, job_id = await _setup_job(db_session)

    _ua, student = await make_student(db_session, prefix="anon")
    sel = await _builder_cv_with_skills(db_session, student=student, skills=MATCH_SKILLS)
    await _apply(
        db_session, student=student, job_id=job_id, cv_selection=sel, is_anonymous=True
    )

    out = await candidate_ranking_service.rank_job_applicants(
        db_session, principal=partner, job_id=job_id, ctx=CTX,
    )

    assert len(out["items"]) == 1
    item = out["items"][0]
    identity = item["applicant"]
    # Masked: deterministic handle, NO name/email/user_id.
    assert identity["is_anonymous"] is True
    assert identity["revealed"] is False
    assert identity["anonymous_id"].startswith("UV-")
    assert "user_id" not in identity
    assert "email" not in identity
    # ...but still scored (the CV content is scored; only identity is masked).
    assert item["fit_score"] is not None
    assert out["scored_count"] == 1


# --------------------------------------------------------------------------- #
# Low signal: no requirements / empty snapshot                                #
# --------------------------------------------------------------------------- #


async def test_ranking_no_requirements_signal(db_session) -> None:
    partner, _porg, _uni, job_id = await _setup_job(db_session)
    _ua, student = await make_student(db_session, prefix="noreq")
    sel = await _builder_cv_with_skills(db_session, student=student, skills=MATCH_SKILLS)
    await _apply(db_session, student=student, job_id=job_id, cv_selection=sel)

    # Strip every requirement-bearing field so the JD yields zero usable terms.
    job = (
        await db_session.execute(select(Job).where(Job.id == job_id))
    ).scalar_one()
    job.title = ""
    job.description = ""  # NOT NULL column; empty string is falsy -> excluded from jd_text
    job.requirements = ""
    job.benefits = ""
    job.required_skills = []
    job.preferred_skills = []
    job.degree_required = None
    job.seniority_level = None
    job.candidate_requirements = {}
    await db_session.flush()

    out = await candidate_ranking_service.rank_job_applicants(
        db_session, principal=partner, job_id=job_id, ctx=CTX,
    )

    assert out["signal"] == "no_requirements"
    assert out["scored_count"] == 0
    assert len(out["items"]) == 1
    # Honest: no fabricated numbers when there is nothing to score against.
    assert out["items"][0]["fit_score"] is None
    assert out["items"][0]["fit_band"] is None
    assert out["items"][0]["rank"] == 1


async def test_ranking_empty_snapshot_listed_with_null_score(db_session) -> None:
    partner, _porg, _uni, job_id = await _setup_job(db_session)

    ua, student_a = await make_student(db_session, prefix="good")
    ub, student_b = await make_student(db_session, prefix="empty")
    sel_good = await _builder_cv_with_skills(
        db_session, student=student_a, skills=MATCH_SKILLS
    )
    sel_empty = await _uploaded_cv_selection(
        db_session, student_user=ub, skills=[], empty=True
    )
    await _apply(db_session, student=student_a, job_id=job_id, cv_selection=sel_good)
    await _apply(db_session, student=student_b, job_id=job_id, cv_selection=sel_empty)

    out = await candidate_ranking_service.rank_job_applicants(
        db_session, principal=partner, job_id=job_id, ctx=CTX,
    )

    assert out["scored_count"] == 1
    assert len(out["items"]) == 2  # both listed
    by_user = {i["applicant"].get("user_id"): i for i in out["items"]}
    assert by_user[str(ua.id)]["fit_score"] is not None
    # The empty-snapshot applicant is still listed, but with a null (honest) score.
    assert by_user[str(ub.id)]["fit_score"] is None
    # ...and ranked below the scored applicant.
    assert by_user[str(ua.id)]["rank"] < by_user[str(ub.id)]["rank"]
