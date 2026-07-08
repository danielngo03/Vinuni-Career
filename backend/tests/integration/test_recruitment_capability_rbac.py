"""B-559: recruiting-capability RBAC catalog gaps (interviews/offers/scorecards/
candidate_identity/pipeline/ai_recruiting + expanded ``applications`` actions).

Before this fix, ``interview_service`` / ``offer_service`` / ``scorecard_service``
/ ``scorecard_ai_service`` / ``screening_brief_service`` gated real actions on a
resource string (``"recruitment"``) that was never in
``organization.domain.catalog.PERMISSION_CATALOG``. Because
``rbac_service._validate_permissions`` (via ``catalog.is_catalog_permission``)
rejects any tuple not in the catalog when a custom role is authored, NO non-admin
partner role could ever be granted these actions — only the Admin wildcard
(``*:*``) passed. This file proves:

- the catalog now accepts the new, correctly-named tuples via the real
  role-authoring API (``rbac_service.create_role``);
- the legacy ungranted ``("recruitment", ...)`` tuples are still rejected (the
  fix renamed the resource, it did not just widen the catalog);
- a custom role CAN be granted exactly one new capability and the grant is
  action-scoped (denied for a sibling action on the SAME resource);
- tenant isolation still holds for a granted capability across orgs;
- the Admin wildcard role still passes every new capability.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.organization.application import rbac_service
from app.modules.organization.application.errors import InvalidPermissionError
from app.modules.organization.domain import catalog
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    interview_service,
    offer_service,
    scorecard_ai_service,
    scorecard_service,
    screening_brief_service,
)
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import add_member, make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _scores(*, technical=4, communication=4, culture_fit=4, motivation=4) -> list[dict]:
    return [
        {"criterion_key": "technical", "score": technical},
        {"criterion_key": "communication", "score": communication},
        {"criterion_key": "culture_fit", "score": culture_fit},
        {"criterion_key": "motivation", "score": motivation},
    ]


async def _setup_reviewed(db, *, is_anonymous=False):
    """Published job + applied + reviewed (candidate ACTIVE at stage 1)."""

    _pu, porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=partner, uni_principal=uni)

    su, student = await make_student(db, prefix="student")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=is_anonymous),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db, principal=partner, application_id=app_id, ctx=CTX
    )
    return porg, partner, su, student, job_id, app_id


def _offer_kwargs(**over) -> dict:
    base = {
        "position_title": "Backend Engineer",
        "expiry_date": _now() + timedelta(days=7),
        "salary_amount": 20_000_000,
        "start_date": (_now() + timedelta(days=30)).date(),
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# Catalog acceptance via the real role-authoring API                          #
# --------------------------------------------------------------------------- #


_NEW_TUPLES: list[tuple[str, str]] = [
    ("interviews", "schedule"),
    ("interviews", "assign"),
    ("interviews", "complete"),
    ("interviews", "cancel"),
    ("interviews", "read"),
    ("offers", "create"),
    ("offers", "approve"),
    ("offers", "send"),
    ("offers", "rescind"),
    ("scorecards", "submit"),
    ("scorecards", "read"),
    ("candidate_identity", "request_reveal"),
    ("candidate_identity", "view_cv"),
    ("candidate_identity", "download_cv"),
    ("pipeline", "move_candidate"),
    ("pipeline", "rollback"),
    ("ai_recruiting", "suggest_scorecard"),
    ("ai_recruiting", "screen_candidate"),
    ("applications", "review"),
    ("applications", "reject"),
    ("applications", "bulk_review"),
    ("applications", "export"),
    ("jobs", "assign_owner"),
]


@pytest.mark.parametrize("resource,action", _NEW_TUPLES)
async def test_catalog_accepts_new_capability_tuple(db_session, resource, action) -> None:
    assert catalog.is_catalog_permission(resource, action) is True

    _u, _org, admin = await make_org_with_admin(db_session)
    role = await rbac_service.create_role(
        db_session, principal=admin, name=f"Role-{resource}-{action}",
        description=None, permissions=[(resource, action)], ctx=CTX,
    )
    assert f"{resource}:{action}" in role["permissions"]


async def test_catalog_still_rejects_legacy_ungranted_recruitment_resource(
    db_session,
) -> None:
    """The fix renamed the resource; it did not just widen the catalog to accept
    anything. The old, never-granted ``"recruitment"`` resource stays illegal."""

    assert catalog.is_catalog_permission("recruitment", "manage_interview") is False
    assert catalog.is_catalog_permission("recruitment", "schedule_interview") is False
    assert catalog.is_catalog_permission("recruitment", "create_offer") is False

    _u, _org, admin = await make_org_with_admin(db_session)
    with pytest.raises(InvalidPermissionError):
        await rbac_service.create_role(
            db_session, principal=admin, name="LegacyRole", description=None,
            permissions=[("recruitment", "manage_interview")], ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# A custom role CAN be granted exactly one capability (action-scoped)         #
# --------------------------------------------------------------------------- #


async def test_interviews_schedule_grant_allows_schedule_denies_assign_and_offers(
    db_session,
) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    _u, _m, scheduler = await add_member(
        db_session, org=org,
        permissions=[("applications", "read"), ("interviews", "schedule")],
    )

    out = await interview_service.schedule_interview(
        db_session, principal=scheduler, application_id=app_id,
        mode="onsite", scheduled_at=_now() + timedelta(days=2),
        assignee_ids=[], location="VinUni Campus", ctx=CTX,
    )
    iv_id = uuid.UUID(out["id"])

    # Same resource, sibling action -> denied (action-scoped, not resource-wide).
    with pytest.raises(PermissionDeniedError):
        await interview_service.set_assignees(
            db_session, principal=scheduler, application_id=app_id,
            interview_id=iv_id, assignee_ids=[], ctx=CTX,
        )
    # A different (also new) resource -> denied.
    with pytest.raises(PermissionDeniedError):
        await offer_service.create_offer(
            db_session, principal=scheduler, application_id=app_id, ctx=CTX,
            **_offer_kwargs(),
        )


async def test_offers_create_grant_allows_create_denies_approve_and_send(
    db_session,
) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    _u, _m, drafter = await add_member(
        db_session, org=org,
        permissions=[("applications", "read"), ("offers", "create")],
    )

    out = await offer_service.create_offer(
        db_session, principal=drafter, application_id=app_id, ctx=CTX,
        **_offer_kwargs(),
    )
    oid = uuid.UUID(out["id"])
    await offer_service.submit_offer(db_session, principal=drafter, offer_id=oid, ctx=CTX)

    with pytest.raises(PermissionDeniedError):
        await offer_service.approve_offer(
            db_session, principal=drafter, offer_id=oid, decision="approve", ctx=CTX,
        )

    # Approver role can approve but not send.
    _u2, _m2, approver = await add_member(
        db_session, org=org,
        permissions=[("applications", "read"), ("offers", "approve")],
    )
    approved = await offer_service.approve_offer(
        db_session, principal=approver, offer_id=oid, decision="approve", ctx=CTX,
    )
    assert approved["status"] == "approved"
    with pytest.raises(PermissionDeniedError):
        await offer_service.send_offer(
            db_session, principal=approver, offer_id=oid, ctx=CTX,
        )


async def test_scorecards_submit_grant_allows_submit_denies_read(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    _u, _m, reviewer = await add_member(
        db_session, org=org,
        permissions=[("applications", "read"), ("scorecards", "submit")],
    )

    out = await scorecard_service.submit_scorecard(
        db_session, principal=reviewer, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    assert out["mine"]["recommendation"] == "yes"

    with pytest.raises(PermissionDeniedError):
        await scorecard_service.list_scorecards(
            db_session, principal=reviewer, application_id=app_id,
        )


async def test_ai_recruiting_grant_is_scoped_per_action(db_session) -> None:
    org, partner, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    _u, _m, scorer = await add_member(
        db_session, org=org,
        permissions=[
            ("applications", "read"),
            ("ai_recruiting", "suggest_scorecard"),
        ],
    )

    result = await scorecard_ai_service.suggest_scorecard(
        db_session, principal=scorer, application_id=app_id,
        notes="Strong technical answers, clear communication.",
    )
    assert "criteria" in result

    # Same resource, sibling action (screening brief) -> denied.
    with pytest.raises(PermissionDeniedError):
        await screening_brief_service.generate_screening_brief(
            db_session, principal=scorer, application_id=app_id,
        )

    _u2, _m2, screener = await add_member(
        db_session, org=org,
        permissions=[
            ("applications", "read"),
            ("ai_recruiting", "screen_candidate"),
        ],
    )
    brief = await screening_brief_service.generate_screening_brief(
        db_session, principal=screener, application_id=app_id,
    )
    assert "bullets" in brief
    with pytest.raises(PermissionDeniedError):
        await scorecard_ai_service.suggest_scorecard(
            db_session, principal=screener, application_id=app_id,
            notes="Strong technical answers.",
        )


# --------------------------------------------------------------------------- #
# Tenant isolation still holds for a granted capability                       #
# --------------------------------------------------------------------------- #


async def test_interviews_schedule_grant_does_not_cross_org(db_session) -> None:
    org_a, partner_a, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    _bu, org_b, _partner_b = await make_org_with_admin(db_session, display_name="Org B")
    _u, _m, scheduler_b = await add_member(
        db_session, org=org_b,
        permissions=[("applications", "read"), ("interviews", "schedule")],
    )

    # Same capability, wrong org -> the cross-org application is invisible (404),
    # never a permission leak that would confirm the resource exists.
    with pytest.raises(ResourceNotFoundError):
        await interview_service.schedule_interview(
            db_session, principal=scheduler_b, application_id=app_id,
            mode="onsite", scheduled_at=_now() + timedelta(days=2),
            assignee_ids=[], location="Somewhere", ctx=CTX,
        )


async def test_offers_create_grant_does_not_cross_org(db_session) -> None:
    org_a, partner_a, _su, _student, _job, app_id = await _setup_reviewed(db_session)
    _bu, org_b, _partner_b = await make_org_with_admin(db_session, display_name="Org B2")
    _u, _m, drafter_b = await add_member(
        db_session, org=org_b,
        permissions=[("applications", "read"), ("offers", "create")],
    )
    with pytest.raises(ResourceNotFoundError):
        await offer_service.create_offer(
            db_session, principal=drafter_b, application_id=app_id, ctx=CTX,
            **_offer_kwargs(),
        )


# --------------------------------------------------------------------------- #
# Admin wildcard still passes every new capability                            #
# --------------------------------------------------------------------------- #


async def test_admin_wildcard_passes_every_new_recruiting_capability(db_session) -> None:
    org, admin, _su, _student, _job, app_id = await _setup_reviewed(db_session)

    iv = await interview_service.schedule_interview(
        db_session, principal=admin, application_id=app_id,
        mode="onsite", scheduled_at=_now() + timedelta(days=2),
        assignee_ids=[], location="VinUni Campus", ctx=CTX,
    )
    assert iv["status"] == "scheduled"

    offer_out = await offer_service.create_offer(
        db_session, principal=admin, application_id=app_id, ctx=CTX,
        **_offer_kwargs(),
    )
    oid = uuid.UUID(offer_out["id"])
    await offer_service.submit_offer(db_session, principal=admin, offer_id=oid, ctx=CTX)
    approved = await offer_service.approve_offer(
        db_session, principal=admin, offer_id=oid, decision="approve", ctx=CTX,
    )
    assert approved["status"] == "approved"
    sent = await offer_service.send_offer(db_session, principal=admin, offer_id=oid, ctx=CTX)
    assert sent["status"] == "sent"

    sc = await scorecard_service.submit_scorecard(
        db_session, principal=admin, application_id=app_id,
        recommendation="yes", scores=_scores(), ctx=CTX,
    )
    assert sc["mine"]["recommendation"] == "yes"
    listed = await scorecard_service.list_scorecards(
        db_session, principal=admin, application_id=app_id,
    )
    assert listed["mine"] is not None

    suggestion = await scorecard_ai_service.suggest_scorecard(
        db_session, principal=admin, application_id=app_id, notes="Great candidate.",
    )
    assert "criteria" in suggestion
    brief = await screening_brief_service.generate_screening_brief(
        db_session, principal=admin, application_id=app_id,
    )
    assert "bullets" in brief
