"""Partner ATS read-model gaps (fast-follow): owner-jobs funnel counts + owner_name,
the ``application.cv_evaluated`` activity label, screening-question labels on the
partner application detail, and the candidate ``headline`` descriptor.

Each of these surfaced as a placeholder ("—" / raw English) in browser
verification; these tests pin the real backend contract behind them.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.analytics.application import partner_activity_feed_service as feed
from app.modules.documents.application import snapshot_service
from app.modules.documents.domain.models import ApplicationCvSnapshot
from app.modules.opportunities.application import job_service
from app.modules.opportunities.domain.models import Job
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
)
from app.shared.audit import AuditContext, write_audit
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _apply(db, *, job_id, prefix):
    _su, student = await make_student(db, prefix=prefix)
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student, payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX
    )
    return uuid.UUID(app["id"]), app


# --------------------------------------------------------------------------- #
# 1) Owner jobs read-model: unreviewed_count / in_pipeline_count / owner_name  #
# --------------------------------------------------------------------------- #


async def test_owner_jobs_mine_carries_funnel_counts_and_owner_name(db_session) -> None:
    _pu, _porg, admin = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=admin, uni_principal=uni)

    # Two applicants, both still ``submitted`` -> unreviewed=2, in_pipeline=0.
    app1, _ = await _apply(db_session, job_id=job_id, prefix="cand1")
    await _apply(db_session, job_id=job_id, prefix="cand2")

    items, _c, _l = await job_service.list_my_jobs(db_session, principal=admin)
    row = next(i for i in items if i["id"] == str(job_id))
    assert row["unreviewed_count"] == 2
    assert row["in_pipeline_count"] == 0
    # Poster display name is surfaced (never their email); posted_by id still present.
    assert row["owner_name"] == "Test User"
    assert row["posted_by"]
    assert "@" not in (row["owner_name"] or "")

    # Reviewing app1 moves it out of "unreviewed" and into an ACTIVE pipeline stage.
    await decision_service.review_application(
        db_session, principal=admin, application_id=app1, ctx=CTX
    )
    items2, _c2, _l2 = await job_service.list_my_jobs(db_session, principal=admin)
    row2 = next(i for i in items2 if i["id"] == str(job_id))
    assert row2["unreviewed_count"] == 1
    assert row2["in_pipeline_count"] == 1


async def test_owner_jobs_mine_zero_counts_when_no_applications(db_session) -> None:
    _pu, _porg, admin = await make_org_with_admin(db_session, display_name="Empty Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=admin, uni_principal=uni)

    items, _c, _l = await job_service.list_my_jobs(db_session, principal=admin)
    row = next(i for i in items if i["id"] == str(job_id))
    assert row["unreviewed_count"] == 0
    assert row["in_pipeline_count"] == 0


# --------------------------------------------------------------------------- #
# 3) ``application.cv_evaluated`` bilingual activity-feed label                 #
# --------------------------------------------------------------------------- #


def test_cv_evaluated_label_is_bilingual_not_humanized() -> None:
    vi = feed._label("application.cv_evaluated", locale="vi")
    en = feed._label("application.cv_evaluated", locale="en")
    assert vi == "Đã đánh giá CV ứng viên"
    assert en == "Evaluated a candidate CV"
    # NOT the humanize fallback ("Cv evaluated").
    assert en != "Cv evaluated"


async def test_cv_evaluated_row_renders_in_partner_activity_feed(db_session) -> None:
    _pu, porg, admin = await make_org_with_admin(db_session, display_name="Feed Co")
    await write_audit(
        db_session,
        action="application.cv_evaluated",
        resource_type="application",
        resource_id=uuid.uuid4(),
        context=AuditContext(actor_id=admin.user_id, actor_org_id=porg.id),
    )
    await db_session.commit()

    rows = await feed.list_partner_activity_feed(
        db_session, principal=admin, org_id=porg.id, locale="en"
    )
    match = next(r for r in rows if r["action"] == "application.cv_evaluated")
    assert match["action_label"] == "Evaluated a candidate CV"


# --------------------------------------------------------------------------- #
# 4) Screening-question labels on the partner application DETAIL                #
# --------------------------------------------------------------------------- #


async def test_screening_answers_carry_question_prompts_on_detail(db_session) -> None:
    _pu, _porg, admin = await make_org_with_admin(db_session, display_name="Screen Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=admin, uni_principal=uni)
    app_id, _ = await _apply(db_session, job_id=job_id, prefix="screencand")

    q1 = str(uuid.uuid4())
    # Define the job's screening questions (no migration: settings JSON) + stamp the
    # application's answers keyed by opaque question ids + one undefined key.
    job = (await db_session.execute(select(Job).where(Job.id == job_id))).scalar_one()
    job.settings = {
        **(job.settings or {}),
        "screening_questions": [
            {"id": q1, "prompt": "Bạn có thể bắt đầu khi nào?", "prompt_en": "When can you start?"},
        ],
    }
    from app.modules.recruitment.domain.models import Application

    app = (
        await db_session.execute(select(Application).where(Application.id == app_id))
    ).scalar_one()
    app.screening_answers = {q1: "Ngay lập tức", "legacy_key": "Yes"}
    await db_session.commit()

    # Default locale (vi) resolves the Vietnamese prompt.
    view = await apply_service.get_application(db_session, principal=admin, application_id=app_id)
    screening = {s["question_id"]: s for s in view["screening"]}
    assert screening[q1]["question"] == "Bạn có thể bắt đầu khi nào?"
    assert screening[q1]["answer"] == "Ngay lập tức"
    # An answer with no matching defined question keeps a null prompt (UI fallback).
    assert screening["legacy_key"]["question"] is None
    # Raw answers dict is still present for backward compatibility.
    assert view["screening_answers"][q1] == "Ngay lập tức"

    # locale="en" resolves the English prompt variant.
    view_en = await apply_service.get_application(
        db_session, principal=admin, application_id=app_id, locale="en"
    )
    screening_en = {s["question_id"]: s for s in view_en["screening"]}
    assert screening_en[q1]["question"] == "When can you start?"


async def test_screening_is_none_when_no_answers(db_session) -> None:
    _pu, _porg, admin = await make_org_with_admin(db_session, display_name="NoScreen Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=admin, uni_principal=uni)
    app_id, _ = await _apply(db_session, job_id=job_id, prefix="noscreen")

    view = await apply_service.get_application(db_session, principal=admin, application_id=app_id)
    assert view["screening"] is None


# --------------------------------------------------------------------------- #
# 5) Candidate ``headline`` = "grad-year · major"                              #
# --------------------------------------------------------------------------- #


def test_derive_headline_prefers_header_headline() -> None:
    body = {
        "sections": [
            {"section_type": "header", "content_json": {"name": "A", "headline": "Aspiring SWE"}},
            {
                "section_type": "education",
                "content_json": {"entries": [{"heading": "CS", "timeframe": "2021-2025"}]},
            },
        ]
    }
    assert snapshot_service._derive_headline(body) == "Aspiring SWE"


def test_derive_headline_grad_year_and_major_from_education() -> None:
    body = {
        "sections": [
            {"section_type": "header", "content_json": {"name": "A"}},
            {
                "section_type": "education",
                "content_json": {
                    "entries": [{"heading": "VinUniversity", "subheading": "Computer Science",
                                 "timeframe": "2021 - 2025"}]
                },
            },
        ]
    }
    assert snapshot_service._derive_headline(body) == "2025 · Computer Science"


def test_derive_headline_none_when_empty() -> None:
    assert snapshot_service._derive_headline({"sections": []}) is None
    assert snapshot_service._derive_headline({}) is None


async def test_headline_surfaces_on_partner_list_row(db_session) -> None:
    _pu, _porg, admin = await make_org_with_admin(db_session, display_name="HL Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=admin, uni_principal=uni)
    app_id, app = await _apply(db_session, job_id=job_id, prefix="hlcand")

    # Craft the immutable snapshot's structured content to carry an education entry.
    snap = (
        await db_session.execute(
            select(ApplicationCvSnapshot).where(
                ApplicationCvSnapshot.id == uuid.UUID(app["snapshot_id"])
            )
        )
    ).scalar_one()
    snap.snapshot_json = {
        "sections": [
            {
                "section_type": "education",
                "title": "Education",
                "content_json": {
                    "entries": [{"heading": "Computer Science", "timeframe": "2021 - 2025"}]
                },
            }
        ]
    }
    await db_session.commit()

    items, _c, _l = await apply_service.list_job_applications(
        db_session, principal=admin, job_id=job_id
    )
    row = next(i for i in items if i["id"] == str(app_id))
    assert row["applicant"]["headline"] == "2025 · Computer Science"
