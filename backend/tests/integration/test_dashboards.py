"""Persona dashboard read-model service tests.

Covers, per dashboard: correct persona allowed, wrong persona forbidden, real
counts match seeded data, scoping/tenant isolation (student A vs B; partner org
isolation; university sees pending across orgs), anonymous candidate handles on
the partner dashboard (no PII leak), empty-state shape (new user -> zeros +
appropriate next_actions), and single-widget failure tolerance.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.dashboards.application import (
    partner_dashboard,
    student_dashboard,
    university_dashboard,
)
from app.modules.documents.application import snapshot_service
from app.modules.opportunities.application import job_service, registration_service
from app.modules.organization.application import partner_registration_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    reveal_service,
)
from app.modules.recruitment.application import (
    dashboard_read as recruitment_read,
)
from app.modules.users.application import admin_users_service
from app.shared.exceptions import PermissionDeniedError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.events_utils import publish_event
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import (
    apply_payload,
    job_payload,
    make_builder_cv,
    publish_job,
)

_REVEAL_REASON = "We would like to learn more about your internship experience here."


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _register_pending_partner(db, *, company_name: str) -> None:
    await partner_registration_service.register_partner(
        db,
        payload={
            "company_name": company_name,
            "contact_name": "Jane Recruiter",
            "contact_email": f"{uuid.uuid4().hex[:10]}@newco.example.com",
        },
        ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Student dashboard                                                           #
# --------------------------------------------------------------------------- #


async def test_student_dashboard_empty_state(db_session) -> None:
    _su, student = await make_student(db_session)
    data = await student_dashboard.get_student_dashboard(db_session, principal=student)

    assert data["metrics"] == {
        "applications_total": 0,
        "applications_active": 0,
        "cv_count": 0,
        "alert_count": 0,
    }
    keys = {a["key"] for a in data["next_actions"]}
    # Identity-only profile: no "complete_profile" nudge; the setup nudge is CV-first.
    assert "complete_profile" not in keys
    assert "build_cv" in keys
    assert "create_alert" in keys  # nudge when no alerts exist
    assert "respond_reveal" not in keys
    assert data["applications_recent"] == []
    assert data["reveal_requests_pending"] == []


async def test_student_dashboard_real_counts_and_scoping(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _sa_u, student_a = await make_student(db_session, prefix="a")
    _sb_u, student_b = await make_student(db_session, prefix="b")
    sel_a = await make_builder_cv(db_session, student=student_a)
    sel_b = await make_builder_cv(db_session, student=student_b)

    app_a = await apply_service.apply_to_job(
        db_session, principal=student_a,
        payload=apply_payload(job_id=job_id, cv_selection=sel_a), ctx=CTX,
    )
    await apply_service.apply_to_job(
        db_session, principal=student_b,
        payload=apply_payload(job_id=job_id, cv_selection=sel_b), ctx=CTX,
    )

    data_a = await student_dashboard.get_student_dashboard(db_session, principal=student_a)
    assert data_a["metrics"]["applications_total"] == 1
    assert data_a["metrics"]["applications_active"] == 1
    assert data_a["metrics"]["cv_count"] == 1
    # Scoping: student A only sees their own application, never student B's.
    assert [r["id"] for r in data_a["applications_recent"]] == [app_a["id"]]
    row = data_a["applications_recent"][0]
    assert row["company_name"] and row["job_title"]
    assert row["status_label"]  # never a raw enum alone
    # Recommended jobs surface the seeded published role and carry an honest
    # ``source`` (the frontend labels the rail by it). Student A has a CV, so the
    # ranker personalizes (``source=recommended``); a CV-less student would get
    # ``source=recent``/``popular`` instead — never a silent mislabel.
    reco = data_a["recommended_jobs"]
    assert isinstance(reco, dict)
    assert reco["source"] in {"recommended", "recent", "popular"}
    assert len(reco["items"]) >= 1
    assert all("source" in item for item in reco["items"])


async def test_student_dashboard_pending_reveal_action(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    await reveal_service.request_reveal(
        db_session, principal=partner, application_id=uuid.UUID(app["id"]),
        reason=_REVEAL_REASON, ctx=CTX,
    )

    data = await student_dashboard.get_student_dashboard(db_session, principal=student)
    actions = {a["key"]: a for a in data["next_actions"]}
    assert actions["respond_reveal"]["count"] == 1
    assert len(data["reveal_requests_pending"]) == 1
    pending = data["reveal_requests_pending"][0]
    assert pending["application_id"] == app["id"]
    assert pending["company_name"] and pending["job_title"]


async def test_student_dashboard_wrong_persona_forbidden(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await student_dashboard.get_student_dashboard(db_session, principal=partner)


# --------------------------------------------------------------------------- #
# Partner dashboard                                                           #
# --------------------------------------------------------------------------- #


async def test_partner_dashboard_real_counts_and_anonymous_rows(db_session) -> None:
    pu, porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    active_job_id = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Live Role"
    )
    # A draft job (never submitted) and a pending-review job (submitted).
    await job_service.create_job(
        db_session, principal=partner, payload=job_payload("Draft Role"), ctx=CTX
    )
    pending = await job_service.create_job(
        db_session, principal=partner, payload=job_payload("Pending Role"), ctx=CTX
    )
    await job_service.submit_job(
        db_session, principal=partner, job_id=uuid.UUID(pending["id"]), ctx=CTX
    )

    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=active_job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )

    data = await partner_dashboard.get_partner_dashboard(db_session, principal=partner)
    assert data["org_name"] == "Partner Co"
    m = data["metrics"]
    assert m["jobs_active"] == 1
    assert m["jobs_draft"] == 1
    assert m["jobs_pending_review"] == 1
    assert m["applications_total"] == 1

    keys = {a["key"] for a in data["next_actions"]}
    assert {"jobs_in_draft", "jobs_pending_review", "post_job"} <= keys

    # jobs_attention shows the draft + pending jobs (not the live one).
    attention_titles = {j["title"] for j in data["jobs_attention"]}
    assert "Draft Role" in attention_titles and "Pending Role" in attention_titles
    assert "Live Role" not in attention_titles

    # PII guard: candidate rows are anonymous handles only — no name/email.
    assert len(data["applications_recent"]) == 1
    cand = data["applications_recent"][0]
    assert cand["candidate_handle"].startswith("UV-")
    assert "email" not in cand and "display_name" not in cand
    assert "candidate_name" not in cand and "user_id" not in cand


async def test_partner_dashboard_org_isolation(db_session) -> None:
    pa_u, pa_org, partner_a = await make_org_with_admin(db_session, display_name="Org A")
    _pb_u, _pb_org, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")

    await publish_job(
        db_session, partner_principal=partner_a, uni_principal=uni, title="A Role"
    )
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    a_job = await job_service.list_my_jobs(db_session, principal=partner_a)
    await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=uuid.UUID(a_job[0][0]["id"]), cv_selection=sel),
        ctx=CTX,
    )

    data_b = await partner_dashboard.get_partner_dashboard(db_session, principal=partner_b)
    assert data_b["metrics"]["jobs_active"] == 0
    assert data_b["metrics"]["applications_total"] == 0
    assert data_b["applications_recent"] == []


async def test_partner_dashboard_reveals_pending_response(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    await reveal_service.request_reveal(
        db_session, principal=partner, application_id=uuid.UUID(app["id"]),
        reason=_REVEAL_REASON, ctx=CTX,
    )
    data = await partner_dashboard.get_partner_dashboard(db_session, principal=partner)
    assert data["metrics"]["reveals_pending_response"] == 1
    assert {a["key"] for a in data["next_actions"]} >= {"respond_reveals"}


async def test_partner_dashboard_wrong_persona_forbidden(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await partner_dashboard.get_partner_dashboard(db_session, principal=student)


# --------------------------------------------------------------------------- #
# University dashboard                                                        #
# --------------------------------------------------------------------------- #


async def test_university_dashboard_sees_pending_across_orgs(db_session) -> None:
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _pa_u, _pa_org, partner_a = await make_org_with_admin(db_session, display_name="P A")
    _pb_u, _pb_org, partner_b = await make_org_with_admin(db_session, display_name="P B")

    # Two partners each submit a job for moderation (pending across orgs).
    for partner in (partner_a, partner_b):
        job = await job_service.create_job(
            db_session, principal=partner, payload=job_payload("Needs Review"), ctx=CTX
        )
        await job_service.submit_job(
            db_session, principal=partner, job_id=uuid.UUID(job["id"]), ctx=CTX
        )
    # One active job (partner A) to exercise jobs_active_total.
    await publish_job(
        db_session, partner_principal=partner_a, uni_principal=uni, title="Live"
    )
    await _register_pending_partner(db_session, company_name="Brand New Co")

    data = await university_dashboard.get_university_dashboard(db_session, principal=uni)
    m = data["metrics"]
    assert m["jobs_pending_moderation"] == 2
    assert m["partners_pending"] == 1
    assert m["partners_active"] >= 2  # the two approved partner orgs
    assert m["jobs_active_total"] == 1

    keys = {a["key"] for a in data["next_actions"]}
    assert {"review_jobs", "review_partners"} <= keys

    assert len(data["moderation_queue_recent"]) == 2
    queue_row = data["moderation_queue_recent"][0]
    assert queue_row["company_name"] and queue_row["title"]
    assert len(data["partner_requests_recent"]) == 1
    assert data["partner_requests_recent"][0]["company_name"] == "Brand New Co"


async def test_university_dashboard_superadmin_allowed(db_session) -> None:
    _su, student = await make_student(db_session)
    student.is_superadmin = True
    data = await university_dashboard.get_university_dashboard(db_session, principal=student)
    assert data["metrics"]["jobs_pending_moderation"] == 0


async def test_university_dashboard_partner_forbidden(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session)
    # Partner Admin holds *:* but the org-type gate keeps this surface uni-only.
    with pytest.raises(PermissionDeniedError):
        await university_dashboard.get_university_dashboard(db_session, principal=partner)


# --------------------------------------------------------------------------- #
# Failure tolerance                                                           #
# --------------------------------------------------------------------------- #


async def test_widget_failure_degrades_to_fallback(db_session, monkeypatch) -> None:
    _su, student = await make_student(db_session)

    async def _boom(*_a, **_k):
        raise RuntimeError("simulated widget failure")

    monkeypatch.setattr(recruitment_read, "count_student_applications", _boom)
    data = await student_dashboard.get_student_dashboard(db_session, principal=student)
    # The failing widget falls back to zero; the rest of the dashboard still loads.
    assert data["metrics"]["applications_total"] == 0
    assert data["metrics"]["applications_active"] == 0
    # Identity-only profile: the setup nudge is CV-first (no "complete_profile").
    assert {a["key"] for a in data["next_actions"]} >= {"build_cv"}


# --------------------------------------------------------------------------- #
# Pipeline overview                                                           #
# --------------------------------------------------------------------------- #


async def test_pipeline_overview_returns_per_job_counts(db_session) -> None:
    partner, uni, job_id = await _setup_published(db_session, title="Dev Job")
    # Publish a second job for the same partner org
    job_id2 = await publish_job(
        db_session, partner_principal=partner, uni_principal=uni, title="Design Job"
    )

    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)

    # Apply to both jobs
    await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id2, cv_selection=sel),
        ctx=CTX,
    )

    overview = await recruitment_read.pipeline_overview_for_org(
        db_session, org_id=partner.org_id
    )

    assert len(overview) == 2
    titles = {r["title"] for r in overview}
    assert titles == {"Dev Job", "Design Job"}
    for row in overview:
        assert row["active_total"] == 1
        assert row["rejected"] == 0
        assert row["withdrawn"] == 0
        assert row["total"] == 1


async def test_pipeline_overview_org_isolation(db_session) -> None:
    _partner, _uni, _job_id = await _setup_published(db_session, title="Isolated Job")

    _pu2, _porg2, partner2 = await make_org_with_admin(db_session, display_name="Other Co")

    overview = await recruitment_read.pipeline_overview_for_org(
        db_session, org_id=partner2.org_id
    )
    assert overview == []


# --------------------------------------------------------------------------- #
# Admin Users Service                                                         #
# --------------------------------------------------------------------------- #


async def test_admin_users_list_all(db_session) -> None:
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session)

    page = await admin_users_service.list_platform_users(db_session, principal=uni)
    ids = {item["id"] for item in page["items"]}
    assert str(student.user_id) in ids
    assert page["total"] >= 2
    assert page["page"] == 1


async def test_admin_users_filter_by_persona(db_session) -> None:
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session)

    page = await admin_users_service.list_platform_users(
        db_session, principal=uni, persona="student"
    )
    for item in page["items"]:
        assert item["persona"] == "student"


async def test_admin_users_suspend_and_unsuspend(db_session) -> None:
    import uuid as uuid_mod
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session)
    uid = uuid_mod.UUID(str(student.user_id))

    result = await admin_users_service.suspend_user(
        db_session, principal=uni, ctx=CTX, user_id=uid, reason="Policy violation"
    )
    assert result["is_active"] is False

    result = await admin_users_service.unsuspend_user(
        db_session, principal=uni, ctx=CTX, user_id=uid, reason="Reinstated after review"
    )
    assert result["is_active"] is True


async def test_admin_users_partner_forbidden(db_session) -> None:
    from app.shared.exceptions import PermissionDeniedError
    _pu, _porg, partner = await make_org_with_admin(db_session)
    with pytest.raises(PermissionDeniedError):
        await admin_users_service.list_platform_users(db_session, principal=partner)


@pytest.mark.asyncio
async def test_student_dashboard_upcoming_events(db_session) -> None:
    """upcoming_events widget shows the student's own future registered events."""
    _pu, _porg, organizer = await make_org_with_admin(db_session, display_name="EventCo")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await publish_event(db_session, organizer, uni)

    _su, student = await make_student(db_session)
    _su2, student2 = await make_student(db_session, prefix="s2")

    # student registers; student2 does NOT
    await registration_service.register(db_session, principal=student, event_id=event_id, ctx=CTX)

    data = await student_dashboard.get_student_dashboard(db_session, principal=student)
    assert "upcoming_events" in data
    assert len(data["upcoming_events"]) == 1
    ev = data["upcoming_events"][0]
    assert ev["event_id"] == str(event_id)
    assert ev["title"]
    assert ev["event_type_label"]  # never raw enum
    assert ev["format_label"]      # never raw enum
    assert ev["registration_status_label"]  # never raw enum
    assert ev["registration_status"] == "confirmed"

    # Scoping: student2 (not registered) sees empty list
    data2 = await student_dashboard.get_student_dashboard(db_session, principal=student2)
    assert data2["upcoming_events"] == []


@pytest.mark.asyncio
async def test_student_dashboard_upcoming_events_empty_by_default(db_session) -> None:
    """upcoming_events key always present even with no registrations."""
    _su, student = await make_student(db_session)
    data = await student_dashboard.get_student_dashboard(db_session, principal=student)
    assert "upcoming_events" in data
    assert data["upcoming_events"] == []


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


async def _setup_published(db, *, title="Live Job", **over):
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title, **over
    )
    return partner, uni, job_id
