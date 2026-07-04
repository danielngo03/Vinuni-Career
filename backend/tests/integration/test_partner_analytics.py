"""Partner recruiting-intelligence read models
(`docs/PARTNER_RBAC_ANALYTICS_SPEC.md` §"Recruiting Intelligence Read Models" /
§"Partner Dashboard V2 Contract").

Covers: job-metrics upsert hooks (detail view / save / apply-start+submitted),
candidate-access audit hooks (application opened / CV downloaded / reveal
requested / identity revealed viewed), the partner-ops dashboard's honest
degrade-when-locked / no-data-yet behavior, RBAC gating (admin wildcard vs a
non-admin member without the analytics grant), and tenant isolation.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.analytics.application import (
    partner_activity_feed_service,
    partner_candidate_access_service,
    partner_job_metrics_service,
    partner_ops_dashboard_service,
)
from app.modules.analytics.domain.partner_read_models import (
    PartnerCandidateAccessEvent,
    PartnerJobMetricDaily,
)
from app.modules.dashboards.application import partner_dashboard
from app.modules.documents.application import snapshot_service
from app.modules.opportunities.application import job_service, saved_jobs_service
from app.modules.recruitment.application import access, apply_service, reveal_service
from app.shared.exceptions import PermissionDeniedError
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job

_REVEAL_REASON = "We would like to learn more about your internship experience here."


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _setup_published(db, *, title="Live Job"):
    partner, porg, partner_principal = await make_org_with_admin(db, display_name="Analytics Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner_principal, uni_principal=uni, title=title
    )
    return partner_principal, porg, uni, job_id


# --------------------------------------------------------------------------- #
# partner_job_metrics_daily: write path                                       #
# --------------------------------------------------------------------------- #


async def test_record_job_metric_event_upserts_counters(db_session) -> None:
    org_id = uuid.uuid4()
    job_id = uuid.uuid4()

    await partner_job_metrics_service.record_job_metric_event(
        db_session, org_id=org_id, job_id=job_id, event_type="detail_view", source="organic",
    )
    await partner_job_metrics_service.record_job_metric_event(
        db_session, org_id=org_id, job_id=job_id, event_type="detail_view", source="organic",
    )
    await partner_job_metrics_service.record_job_metric_event(
        db_session, org_id=org_id, job_id=job_id, event_type="save_click", source="sponsored",
    )
    await db_session.commit()

    row = (
        await db_session.execute(
            select(PartnerJobMetricDaily).where(PartnerJobMetricDaily.job_id == job_id)
        )
    ).scalar_one()
    assert row.detail_views == 2
    assert row.save_clicks == 1
    assert row.src_organic == 2
    assert row.src_sponsored == 1


async def test_record_job_metric_event_unknown_type_is_a_safe_noop(db_session) -> None:
    org_id, job_id = uuid.uuid4(), uuid.uuid4()
    # Must never raise — bad input degrades to a no-op, not a broken request.
    await partner_job_metrics_service.record_job_metric_event(
        db_session, org_id=org_id, job_id=job_id, event_type="not_a_real_event",
    )
    await db_session.commit()
    rows = (
        await db_session.execute(
            select(PartnerJobMetricDaily).where(PartnerJobMetricDaily.job_id == job_id)
        )
    ).scalars().all()
    assert rows == []


async def test_job_detail_view_hook_records_metric(db_session) -> None:
    partner_principal, porg, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)

    await job_service.get_job(
        db_session, principal=student, job_id=job_id, user_agent="Mozilla/5.0 iPhone Mobile",
    )

    row = (
        await db_session.execute(
            select(PartnerJobMetricDaily).where(PartnerJobMetricDaily.job_id == job_id)
        )
    ).scalar_one()
    assert row.detail_views == 1
    assert row.org_id == porg.id

    # Owner viewing their own job is NOT a candidate engagement signal.
    await job_service.get_job(db_session, principal=partner_principal, job_id=job_id)
    row2 = (
        await db_session.execute(
            select(PartnerJobMetricDaily).where(PartnerJobMetricDaily.job_id == job_id)
        )
    ).scalar_one()
    assert row2.detail_views == 1  # unchanged


async def test_save_job_hook_records_save_click(db_session) -> None:
    _partner_principal, porg, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)

    await saved_jobs_service.save_job(db_session, principal=student, job_id=job_id)

    row = (
        await db_session.execute(
            select(PartnerJobMetricDaily).where(PartnerJobMetricDaily.job_id == job_id)
        )
    ).scalar_one()
    assert row.save_clicks == 1
    assert row.org_id == porg.id


async def test_apply_hook_records_apply_start_and_submitted(db_session) -> None:
    _partner_principal, porg, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)

    await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )

    row = (
        await db_session.execute(
            select(PartnerJobMetricDaily).where(PartnerJobMetricDaily.job_id == job_id)
        )
    ).scalar_one()
    assert row.apply_starts == 1
    assert row.applications_submitted == 1


# --------------------------------------------------------------------------- #
# partner_candidate_access_events                                             #
# --------------------------------------------------------------------------- #


async def test_candidate_access_events_recorded_for_open_download_reveal(db_session) -> None:
    partner_principal, _porg, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    application_id = uuid.UUID(app["id"])

    # Partner opens the application -> application_opened.
    await apply_service.get_application(
        db_session, principal=partner_principal, application_id=application_id,
    )
    # Partner requests reveal -> identity_reveal_requested.
    await reveal_service.request_reveal(
        db_session, principal=partner_principal, application_id=application_id,
        reason=_REVEAL_REASON, ctx=CTX,
    )
    # Student accepts.
    await reveal_service.respond_reveal(
        db_session, principal=student, application_id=application_id,
        decision="accepted", ctx=CTX,
    )
    # Partner re-opens (now revealed) -> application_opened + identity_revealed_viewed.
    await apply_service.get_application(
        db_session, principal=partner_principal, application_id=application_id,
    )
    # Partner downloads the CV -> cv_downloaded.
    await apply_service.get_application_cv_download(
        db_session, principal=partner_principal, application_id=application_id,
    )

    rows = (
        await db_session.execute(
            select(PartnerCandidateAccessEvent).where(
                PartnerCandidateAccessEvent.application_id == application_id
            )
        )
    ).scalars().all()
    event_types = [r.event_type for r in rows]
    assert event_types.count("application_opened") == 2
    assert "identity_reveal_requested" in event_types
    assert "identity_revealed_viewed" in event_types
    assert "cv_downloaded" in event_types
    # Applicant's own view of their own application never logs an access event.
    assert all(r.actor_id == partner_principal.user_id for r in rows)


async def test_detect_access_alerts_empty_when_under_threshold(db_session) -> None:
    partner_principal, porg, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    await apply_service.get_application_cv_download(
        db_session, principal=partner_principal, application_id=uuid.UUID(app["id"]),
    )
    alerts = await partner_candidate_access_service.detect_access_alerts(
        db_session, org_id=porg.id,
    )
    assert alerts == []  # a single download never trips the spike threshold


# --------------------------------------------------------------------------- #
# partner_activity_feed (derived from audit_logs)                             #
# --------------------------------------------------------------------------- #


async def test_activity_feed_shows_job_created_for_admin(db_session) -> None:
    partner_principal, porg, _uni, _job_id = await _setup_published(db_session, title="Feed Job")
    feed = await partner_activity_feed_service.list_partner_activity_feed(
        db_session, principal=partner_principal, org_id=porg.id, limit=20,
    )
    actions = {row["action"] for row in feed}
    assert "job.created" in actions
    assert "job.submit" in actions


async def test_activity_feed_hides_billing_without_grant(db_session) -> None:
    partner_principal, porg, _uni, _job_id = await _setup_published(db_session)
    from app.shared.audit import AuditContext, write_audit

    await write_audit(
        db_session, action="billing.subscription_requested", resource_type="subscription",
        context=AuditContext(actor_id=partner_principal.user_id, actor_org_id=porg.id),
        after={"plan": "premium"},
    )
    await db_session.commit()

    non_admin_user, _membership, non_admin = await add_member(
        db_session, org=porg, permissions=[("jobs", "read"), ("applications", "read")],
    )
    feed = await partner_activity_feed_service.list_partner_activity_feed(
        db_session, principal=non_admin, org_id=porg.id, limit=20,
    )
    assert all(row["action"] != "billing.subscription_requested" for row in feed)

    admin_feed = await partner_activity_feed_service.list_partner_activity_feed(
        db_session, principal=partner_principal, org_id=porg.id, limit=20,
    )
    assert any(row["action"] == "billing.subscription_requested" for row in admin_feed)


# --------------------------------------------------------------------------- #
# Partner Dashboard V2 (``GET /dashboards/partner/ops``)                      #
# --------------------------------------------------------------------------- #


async def test_ops_dashboard_admin_sees_unlocked_job_performance(db_session) -> None:
    partner_principal, _porg, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    await job_service.get_job(db_session, principal=student, job_id=job_id)

    data = await partner_ops_dashboard_service.get_partner_dashboard_ops(
        db_session, principal=partner_principal,
    )
    assert data["rbac_summary"]["is_org_admin"] is True
    assert data["job_performance"]["locked"] is False
    assert data["job_performance"]["basis"] == "job_metrics_daily"
    assert data["job_performance"]["items"][0]["detail_views"] == 1
    assert data["access_alerts"]["locked"] is False
    assert "todos" in data and "ai_recommendations" in data
    assert all(rec["advisory_only"] for rec in data["ai_recommendations"])


async def test_ops_dashboard_non_admin_without_grant_sees_locked_widgets(db_session) -> None:
    _partner_principal, porg, _uni, _job_id = await _setup_published(db_session)
    _user, _membership, non_admin = await add_member(
        db_session, org=porg, permissions=[("jobs", "read"), ("applications", "read")],
    )
    data = await partner_ops_dashboard_service.get_partner_dashboard_ops(
        db_session, principal=non_admin,
    )
    assert data["rbac_summary"]["is_org_admin"] is False
    assert data["rbac_summary"]["grants"]["analytics:view_job_metrics"] is False
    assert data["job_performance"]["locked"] is True
    assert data["job_performance"]["reason"] == "missing_grant"
    assert "job_performance" in data["rbac_summary"]["hidden_widgets"]


async def test_ops_dashboard_non_admin_with_grant_sees_honest_no_data_yet(db_session) -> None:
    _partner_principal, porg, _uni, _job_id = await _setup_published(db_session)
    _user, _membership, granted = await add_member(
        db_session, org=porg,
        permissions=[
            ("jobs", "read"), ("applications", "read"),
            ("analytics", "view_job_metrics"),
        ],
    )
    data = await partner_ops_dashboard_service.get_partner_dashboard_ops(
        db_session, principal=granted,
    )
    # No engagement events yet for this org -> honest fallback, never fabricated.
    assert data["metrics"]["engagement"]["available"] is False
    assert data["metrics"]["engagement"]["basis"] == "application_counts_only"
    assert data["job_performance"]["locked"] is False
    assert data["job_performance"]["basis"] == "application_counts_only"


async def test_ops_dashboard_wrong_persona_forbidden(db_session) -> None:
    _su, student = await make_student(db_session)
    with pytest.raises(PermissionDeniedError):
        await partner_ops_dashboard_service.get_partner_dashboard_ops(
            db_session, principal=student,
        )


async def test_ops_dashboard_tenant_isolation(db_session) -> None:
    partner_a, porg_a, uni, job_a = await _setup_published(db_session, title="Org A Job")
    _partner_b_user, porg_b, partner_b = await make_org_with_admin(db_session, display_name="Org B")

    _su, student = await make_student(db_session)
    await job_service.get_job(db_session, principal=student, job_id=job_a)

    data_b = await partner_ops_dashboard_service.get_partner_dashboard_ops(
        db_session, principal=partner_b,
    )
    assert data_b["job_performance"]["items"] == []
    assert data_b["metrics"]["engagement"]["available"] is False


# --------------------------------------------------------------------------- #
# v1 dashboard untouched (additive-only regression guard)                     #
# --------------------------------------------------------------------------- #


async def test_v1_partner_dashboard_still_works_unchanged(db_session) -> None:
    partner_principal, _porg, _uni, _job_id = await _setup_published(db_session)
    data = await partner_dashboard.get_partner_dashboard(db_session, principal=partner_principal)
    assert "metrics" in data and "org_name" in data
