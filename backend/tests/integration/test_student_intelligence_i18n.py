"""Localization of student job-intelligence guidance (vi/en) + audit #6 fix.

Covers:
  - vi vs en yield DIFFERENT localized ``improvement_actions`` /
    ``learning_gaps[].suggestion`` / competition ``guidance`` strings.
  - An already-applied student near the deadline still receives a
    deadline-related guidance line (not only the "already applied" line).
  - Default (no locale) resolves to vi.
  - Response contract keys are unchanged across locales.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.documents.domain.models import CvSection
from app.modules.opportunities.application import (
    job_service,
    moderation_service,
    student_intelligence_service,
)
from app.modules.recruitment.domain.models import Application
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_ready_cv, make_student
from tests.org_utils import make_org_with_admin

# Known locale marker phrases (substring checks) — must appear only in one locale.
_VI_MARKERS = ("Bổ sung bằng chứng", "Xây dựng một dự án", "Hạn nộp hồ sơ")
_EN_MARKERS = ("Add evidence for", "Build a small portfolio", "deadline")


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
        "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"],
        "preferred_skills": ["Redis"],
        "experience_min_years": None,
        "experience_max_years": None,
        "degree_required": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "application_deadline": None,
        "visibility": "public",
    }
    base.update(over)
    return base


async def _create_job(db, **over) -> tuple[uuid.UUID, uuid.UUID]:
    _u, org, admin = await make_org_with_admin(db)
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    created = await job_service.create_job(
        db, principal=admin, payload=_job_payload(**over), ctx=CTX
    )
    jid = uuid.UUID(created["id"])
    await job_service.submit_job(db, principal=admin, job_id=jid, ctx=CTX)
    await moderation_service.approve_job(db, principal=uni, job_id=jid, ctx=CTX)
    return jid, org.id


async def _seed(db, cv_id, section_type, items) -> None:
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    target = next(s for s in sections if s.section_type == section_type)
    target.content_json = {"items": items}
    await db.commit()


async def _weak_cv(db, student, *, title="Weak CV") -> str:
    """A CV weak enough to trigger gaps -> improvement_actions + learning_gaps."""

    cv = await make_ready_cv(db, student=student, title=title)
    await _seed(db, cv["id"], "skills", [{"text": "Python"}])
    return cv["id"]


def _all_guidance_blob(out: dict) -> str:
    parts: list[str] = []
    parts.extend(out["fit"]["improvement_actions"])
    parts.extend(g["suggestion"] for g in out["learning_gaps"])
    parts.extend(out["competition"]["guidance"])
    parts.extend(a["label"] for a in out["next_actions"])
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# vi vs en produce different localized guidance                                #
# --------------------------------------------------------------------------- #


async def test_vi_vs_en_localized_guidance_differs(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _weak_cv(db_session, student)
    job_id, _org_id = await _create_job(db_session)

    vi = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(cv_id),
        locale="vi",
    )
    en = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(cv_id),
        locale="en",
    )

    # There ARE gaps to talk about (otherwise the test is vacuous).
    assert vi["fit"]["improvement_actions"]
    assert vi["learning_gaps"]

    vi_blob = _all_guidance_blob(vi)
    en_blob = _all_guidance_blob(en)

    # A known VN phrase appears in vi and NOT en; a known EN phrase appears in en.
    assert "Bổ sung bằng chứng" in vi_blob
    assert "Xây dựng một dự án" in vi_blob
    assert "Add evidence for" in en_blob
    assert "Build a small portfolio" in en_blob

    # And the localized string values genuinely differ.
    assert vi["fit"]["improvement_actions"] != en["fit"]["improvement_actions"]
    assert (
        vi["learning_gaps"][0]["suggestion"] != en["learning_gaps"][0]["suggestion"]
    )
    assert [a["label"] for a in vi["next_actions"]] != [
        a["label"] for a in en["next_actions"]
    ]

    # next_actions codes stay identical across locales (frontend localizes by code).
    assert [a["action"] for a in vi["next_actions"]] == [
        a["action"] for a in en["next_actions"]
    ]


# --------------------------------------------------------------------------- #
# Default (no locale) -> vi                                                     #
# --------------------------------------------------------------------------- #


async def test_default_locale_is_vietnamese(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _weak_cv(db_session, student)
    job_id, _org_id = await _create_job(db_session)

    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(cv_id),
    )
    assert "Bổ sung bằng chứng" in " ".join(out["fit"]["improvement_actions"])
    assert "Xây dựng một dự án" in out["learning_gaps"][0]["suggestion"]


# --------------------------------------------------------------------------- #
# audit #6: already-applied + near-deadline still gets deadline guidance        #
# --------------------------------------------------------------------------- #


async def test_already_applied_near_deadline_still_has_deadline_guidance(
    db_session,
) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _weak_cv(db_session, student)
    deadline = datetime.now(tz=UTC) + timedelta(days=5)  # closing_soon window
    job_id, org_id = await _create_job(db_session, application_deadline=deadline)

    app = Application(
        id=uuid.uuid4(),
        job_id=job_id,
        applicant_id=student.user_id,
        org_id=org_id,
        status="submitted",
    )
    db_session.add(app)
    await db_session.commit()

    # English for a stable substring assertion.
    out = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(cv_id),
        locale="en",
    )
    guidance = out["competition"]["guidance"]
    assert out["apply_readiness"]["already_applied"] is True
    # "Already applied" line is present...
    assert any("already applied" in g.lower() for g in guidance)
    # ...but the deadline line is ALSO present (not swallowed by early return).
    assert any("deadline" in g.lower() for g in guidance)
    assert len(guidance) >= 2

    # vi equivalent also keeps the deadline line.
    out_vi = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(cv_id),
        locale="vi",
    )
    assert any("Hạn nộp hồ sơ" in g for g in out_vi["competition"]["guidance"])
    assert any("đã ứng tuyển" in g for g in out_vi["competition"]["guidance"])


# --------------------------------------------------------------------------- #
# Contract unchanged across locales                                            #
# --------------------------------------------------------------------------- #


async def test_contract_keys_unchanged_across_locales(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _weak_cv(db_session, student)
    job_id, _org_id = await _create_job(db_session)

    vi = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(cv_id),
        locale="vi",
    )
    en = await student_intelligence_service.student_intelligence_for_job(
        db_session, principal=student, job_id=job_id, cv_id=uuid.UUID(cv_id),
        locale="en",
    )

    assert set(vi.keys()) == set(en.keys())
    assert set(vi["fit"].keys()) == set(en["fit"].keys())
    assert set(vi["competition"].keys()) == set(en["competition"].keys())
    # No accidental new keys.
    assert "screening_questions" not in vi
    for expected in (
        "job_id", "selected_cv_id", "best_cv_id", "fit", "competition",
        "learning_gaps", "apply_readiness", "next_actions",
    ):
        assert expected in vi
    # Competition sub-object leaves the two caller-only keys popped.
    assert "_deadline_passed" not in vi["competition"]
    assert "_already_applied" not in vi["competition"]
