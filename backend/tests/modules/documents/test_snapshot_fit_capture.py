"""Apply-time capture of the deterministic CV-JD fit onto the immutable snapshot.

WS-5 foundation (student-ai phase 2): the chosen CV's deterministic fit vs the job
is FROZEN onto ``application_cv_snapshots`` at apply time so the competition
applicant-quality pool is the set of REAL applicants — point in time — instead of
fit-score VIEWERS (today's population bug). The captured score is deterministic
(no LLM, no energy) and never fabricated: it stays ``None`` when no deterministic
score can be computed (uploaded-document apply with no scoreable CV profile, or a
job that can no longer be scored).

Covers: (a) applying writes ``fit_score`` + ``scorer_version``; (b) immutability —
an idempotent replay returns the same frozen snapshot and no update API exists;
(c) two applies to DIFFERENT jobs freeze independent point-in-time scores; (d) the
no-eligible / degraded case leaves the fit ``None``.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.cv import job_fit
from app.modules.documents.application import (
    cv_lifecycle_service,
    cv_service,
    job_fit_service,
    snapshot_service,
    upload_service,
)
from app.modules.documents.domain.models import ApplicationCvSnapshot, CvProfile
from app.modules.documents.infrastructure import storage
from app.modules.recruitment.application import apply_service
from sqlalchemy import select
from tests.auth_utils import CTX
from tests.documents_utils import InMemoryStorage, cv_text_en, make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, publish_job


@pytest.fixture(autouse=True)
def _isolated_storage():
    """dict-backed storage so the uploaded-document path never touches the disk."""

    storage.set_storage(InMemoryStorage())
    yield
    storage.set_storage(None)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


async def _publish(db, *, title: str, **over) -> uuid.UUID:
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    return await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title, **over
    )


async def _ready_cv_with_skills(
    db, *, student, skills: list[str], title: str = "Skilled CV"
) -> dict:
    """A committed (``ready``) builder CV carrying a skills section, for scoring.

    Returns the ``cv_selection`` an apply payload expects (builder CV + the current
    finalized version id).
    """

    cv = await cv_service.create_cv(
        db, principal=student,
        payload={"title": title, "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(cv["id"])
    version = cv["version"]
    header = next(s for s in cv["sections"] if s["section_type"] == "header")
    res = await cv_service.upsert_section(
        db, principal=student, cv_id=cv_id, section_id=uuid.UUID(header["id"]),
        payload={"content": {"name": "Skilled Candidate"}, "expected_version": version},
        ctx=CTX,
    )
    version = res["cv_version"]
    skills_section = next(s for s in cv["sections"] if s["section_type"] == "skills")
    await cv_service.upsert_section(
        db, principal=student, cv_id=cv_id, section_id=uuid.UUID(skills_section["id"]),
        payload={
            "content": {"items": [{"name": s, "level": 80} for s in skills]},
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


async def _load_snapshot(db, snapshot_id: str) -> ApplicationCvSnapshot:
    return (
        await db.execute(
            select(ApplicationCvSnapshot).where(
                ApplicationCvSnapshot.id == uuid.UUID(snapshot_id)
            )
        )
    ).scalar_one()


async def _load_cv_profile(db, cv_id: str) -> CvProfile:
    return (
        await db.execute(select(CvProfile).where(CvProfile.id == uuid.UUID(cv_id)))
    ).scalar_one()


# --------------------------------------------------------------------------- #
# (a) apply writes fit_score + scorer_version                                 #
# --------------------------------------------------------------------------- #


async def test_apply_captures_fit_score_and_scorer_version(db_session) -> None:
    job_id = await _publish(
        db_session, title="Python Backend", required_skills=["python", "fastapi"]
    )
    _u, student = await make_student(db_session)
    sel = await _ready_cv_with_skills(
        db_session, student=student, skills=["Python", "FastAPI"]
    )

    out = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )

    snap = await _load_snapshot(db_session, out["snapshot_id"])
    assert snap.fit_score is not None
    assert 0 <= snap.fit_score <= 100
    # Deterministic scorer stamp is frozen alongside the score.
    assert snap.scorer_version == job_fit.SCORER_VERSION


# --------------------------------------------------------------------------- #
# (b) immutability — replay returns the same frozen snapshot                   #
# --------------------------------------------------------------------------- #


async def test_snapshot_fit_is_immutable_on_idempotent_replay(db_session) -> None:
    job_id = await _publish(
        db_session, title="Python Backend", required_skills=["python", "fastapi"]
    )
    _u, student = await make_student(db_session)
    sel = await _ready_cv_with_skills(
        db_session, student=student, skills=["Python", "FastAPI"]
    )
    payload = apply_payload(job_id=job_id, cv_selection=sel)

    out1 = await apply_service.apply_to_job(
        db_session, principal=student, payload=payload, ctx=CTX
    )
    snap1 = await _load_snapshot(db_session, out1["snapshot_id"])
    frozen = snap1.fit_score
    assert frozen is not None

    # Same idempotency key -> the SAME application + snapshot; the frozen fit is
    # never recomputed or overwritten.
    out2 = await apply_service.apply_to_job(
        db_session, principal=student, payload=payload, ctx=CTX
    )
    assert out2["snapshot_id"] == out1["snapshot_id"]
    snap2 = await _load_snapshot(db_session, out2["snapshot_id"])
    assert snap2.fit_score == frozen
    assert snap2.scorer_version == job_fit.SCORER_VERSION

    # The snapshot is structurally immutable — no update/delete API exists.
    assert not hasattr(snapshot_service, "update_application_cv_snapshot")
    assert not hasattr(snapshot_service, "delete_application_cv_snapshot")


# --------------------------------------------------------------------------- #
# (c) two applies to different jobs freeze independent point-in-time scores    #
# --------------------------------------------------------------------------- #


async def test_two_applies_capture_independent_point_in_time_scores(db_session) -> None:
    _u, student = await make_student(db_session)
    sel = await _ready_cv_with_skills(
        db_session, student=student, skills=["Python", "FastAPI", "PostgreSQL"]
    )
    strong_job = await _publish(
        db_session, title="Python Backend",
        required_skills=["python", "fastapi", "postgresql"],
    )
    weak_job = await _publish(
        db_session, title="Cloud Platform Engineer",
        required_skills=["kubernetes", "terraform", "aws"],
    )

    out_strong = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=strong_job, cv_selection=sel), ctx=CTX,
    )
    out_weak = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=weak_job, cv_selection=sel), ctx=CTX,
    )

    snap_strong = await _load_snapshot(db_session, out_strong["snapshot_id"])
    snap_weak = await _load_snapshot(db_session, out_weak["snapshot_id"])
    assert snap_strong.fit_score is not None
    assert snap_weak.fit_score is not None
    # Same CV, different jobs -> each snapshot froze its OWN job's deterministic fit.
    # The well-matched job scores strictly higher than the wrong-skills job, proving
    # the scores are per-job and independent, not a single shared value.
    assert snap_strong.fit_score > snap_weak.fit_score


# --------------------------------------------------------------------------- #
# (d) no-eligible / degraded -> fit stays None (never fabricated)             #
# --------------------------------------------------------------------------- #


async def test_deterministic_fit_none_for_unknown_job(db_session) -> None:
    _u, student = await make_student(db_session)
    sel = await _ready_cv_with_skills(db_session, student=student, skills=["Python"])
    cv = await _load_cv_profile(db_session, sel["cv_profile_id"])

    result = await job_fit_service.deterministic_fit_score(
        db_session,
        user_id=student.user_id,
        persona="student",
        job_id=uuid.uuid4(),  # no such job -> not scoreable
        cv=cv,
    )
    assert result is None


async def test_uploaded_document_apply_leaves_fit_none(db_session) -> None:
    _u, student = await make_student(db_session)
    up = await upload_service.upload_cv(
        db_session, principal=student, filename="cv.txt", data=cv_text_en(),
        content_type="text/plain", idempotency_key=uuid.uuid4().hex, ctx=CTX,
    )
    job_id = await _publish(db_session, title="Python Backend", required_skills=["python"])

    out = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(
            job_id=job_id,
            cv_selection={
                "type": "uploaded_document",
                "uploaded_document_id": up["document_id"],
            },
        ),
        ctx=CTX,
    )

    snap = await _load_snapshot(db_session, out["snapshot_id"])
    # An uploaded document has no scoreable CV profile -> honest None, not a
    # fabricated score; the snapshot content is still the uploaded original.
    assert snap.fit_score is None
    assert snap.scorer_version is None
    assert snap.snapshot_json.get("source_type") == "uploaded"
