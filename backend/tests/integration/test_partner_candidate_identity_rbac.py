"""Partner starter roles (GAP A) + ``candidate_identity`` enforcement (GAP B).

Two closed gaps in the partner RBAC stack:

- GAP A: partner-org creation now seeds ready-to-assign NON-system roles
  (Recruiter / Hiring Manager / Analyst / Coordinator) with sensible capability
  bundles, so a partner admin can delegate immediately without hand-building
  every role. University orgs are unchanged (Admin only).
- GAP B: the ``candidate_identity`` capability now actually restricts the
  sensitive paths. Reveal request gates on ``candidate_identity:request_reveal``
  (not the coarse ``applications:read``); partner CV *view* gates on
  ``candidate_identity:view_cv`` and CV *download* on
  ``candidate_identity:download_cv`` (defense-in-depth on top of the partner-of-org
  ``applications:read`` check). Every sensitive access still writes a
  ``partner_candidate_access_events`` row.

The seeded roles are only convenient bundles — every check gates on the
``resource:action`` grant, never a role name.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.analytics.application import partner_ops_dashboard_service
from app.modules.analytics.domain.partner_read_models import (
    PartnerCandidateAccessEvent,
)
from app.modules.documents.application import snapshot_service
from app.modules.organization.application import organization_service, rbac_service
from app.modules.organization.domain.models import (
    Membership,
    MembershipRole,
    Role,
)
from app.modules.recruitment.application import access, apply_service, reveal_service
from app.modules.users.application import user_service
from app.shared.audit import AuditContext
from app.shared.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import permission_checker
from sqlalchemy import func, select

from tests.auth_utils import CTX, register_verified
from tests.documents_utils import make_student
from tests.org_utils import email, make_org_with_admin, principal_for
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job

_STARTER_NAMES = {"Recruiter", "Hiring Manager", "Analyst", "Coordinator"}
_REVEAL_REASON = "We would like to move forward and learn more about this candidate."


@pytest.fixture(autouse=True)
def _authorizer():
    # The documents snapshot-download authorizer seam must be wired for the
    # watermarked partner CV path (mirrors the recruitment/analytics suites).
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _member_with_seeded_role(db, *, org, role_name: str, prefix: str = "member"):
    """Register a user and assign it the org's already-seeded ``role_name``.

    Proves the seeded starter roles are real, assignable rows (not just a
    capability list) — a partner admin can hand one to a new member as-is.
    """

    user = await register_verified(db, email=email(prefix))
    role = (
        await db.execute(
            select(Role).where(Role.org_id == org.id, Role.name == role_name)
        )
    ).scalar_one()
    identity = await user_service.add_identity(
        db, user_id=user.id, persona="partner_member", org_id=org.id
    )
    membership = Membership(
        user_id=user.id, org_id=org.id, identity_id=identity.id, status="active"
    )
    db.add(membership)
    await db.flush()
    db.add(MembershipRole(membership_id=membership.id, role_id=role.id))
    await db.commit()
    principal = await principal_for(db, user=user, org_id=org.id)
    return user, principal


async def _published_partner_org(db, *, display_name: str = "Recruiting Co"):
    _admin_user, org, admin = await make_org_with_admin(db, display_name=display_name)
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(db, partner_principal=admin, uni_principal=uni)
    return org, admin, uni, job_id


async def _anonymous_application(db, *, job_id):
    _su, student = await make_student(db, prefix="applicant")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    return student, uuid.UUID(app["id"])


async def _named_application(db, *, job_id):
    _su, student = await make_student(db, prefix="applicant")
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=False),
        ctx=CTX,
    )
    return student, uuid.UUID(app["id"])


# --------------------------------------------------------------------------- #
# GAP A: starter-role seeding                                                 #
# --------------------------------------------------------------------------- #


async def test_partner_org_creation_seeds_starter_roles(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Seeded Co")
    roles = await rbac_service.list_roles(db_session, principal=admin)
    by_name = {r["name"]: r for r in roles}

    assert set(by_name) == {"Admin", *_STARTER_NAMES}
    # Every starter role is an ORDINARY (editable/deletable) role.
    for name in _STARTER_NAMES:
        assert by_name[name]["is_system"] is False

    # Sampled capability per seeded role (drawn only from the real catalog).
    assert "candidate_identity:download_cv" in by_name["Recruiter"]["permissions"]
    assert "candidate_identity:request_reveal" in by_name["Recruiter"]["permissions"]
    # Hiring Manager may VIEW a CV but must NOT be able to DOWNLOAD it.
    assert "candidate_identity:view_cv" in by_name["Hiring Manager"]["permissions"]
    assert "candidate_identity:download_cv" not in by_name["Hiring Manager"]["permissions"]
    # Analyst reads metrics and holds NO candidate_identity at all.
    assert "analytics:export" in by_name["Analyst"]["permissions"]
    assert not any(
        p.startswith("candidate_identity:") for p in by_name["Analyst"]["permissions"]
    )
    # Coordinator handles interview/event logistics, no candidate_identity.
    assert "interviews:schedule" in by_name["Coordinator"]["permissions"]
    assert not any(
        p.startswith("candidate_identity:") for p in by_name["Coordinator"]["permissions"]
    )


async def test_partner_starter_roles_are_audited_on_creation(db_session) -> None:
    from app.shared.models import AuditLog

    _u, org, _admin = await make_org_with_admin(db_session, display_name="Audited Co")
    role_ids = (
        await db_session.execute(
            select(Role.id).where(Role.org_id == org.id, Role.name.in_(_STARTER_NAMES))
        )
    ).scalars().all()
    assert len(role_ids) == len(_STARTER_NAMES)
    audited = (
        await db_session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "role.created",
                AuditLog.resource_id.in_(role_ids),
            )
        )
    ).scalar_one()
    assert audited == len(_STARTER_NAMES)


async def test_university_org_creation_seeds_no_starter_roles(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    roles = await rbac_service.list_roles(db_session, principal=admin)
    assert {r["name"] for r in roles} == {"Admin"}


async def test_seed_partner_starter_roles_is_idempotent(db_session) -> None:
    _u, org, admin = await make_org_with_admin(db_session, display_name="Idem Co")
    before = {r["name"] for r in await rbac_service.list_roles(db_session, principal=admin)}

    seeded_again = await organization_service._seed_partner_starter_roles(
        db_session, org=org,
        audit_ctx=AuditContext(actor_id=admin.user_id, actor_org_id=org.id),
    )
    await db_session.commit()

    assert seeded_again == []  # nothing re-created
    after = {r["name"] for r in await rbac_service.list_roles(db_session, principal=admin)}
    assert after == before


# --------------------------------------------------------------------------- #
# GAP B: candidate_identity enforcement                                       #
# --------------------------------------------------------------------------- #


async def test_recruiter_role_can_request_reveal_and_view_download_cv(db_session) -> None:
    org, _admin, _uni, job_id = await _published_partner_org(db_session)
    student, app_id = await _anonymous_application(db_session, job_id=job_id)
    _u, recruiter = await _member_with_seeded_role(
        db_session, org=org, role_name="Recruiter"
    )

    # candidate_identity:request_reveal
    await reveal_service.request_reveal(
        db_session, principal=recruiter, application_id=app_id,
        reason=_REVEAL_REASON, ctx=CTX,
    )
    await reveal_service.respond_reveal(
        db_session, principal=student, application_id=app_id,
        decision="accepted", ctx=CTX,
    )
    # candidate_identity:view_cv
    view = await apply_service.get_application_cv_download(
        db_session, principal=recruiter, application_id=app_id, mode="view",
    )
    assert view["has_watermark"] is True
    # candidate_identity:download_cv
    dl = await apply_service.get_application_cv_download(
        db_session, principal=recruiter, application_id=app_id, mode="download",
    )
    assert dl["has_watermark"] is True

    # candidate_identity:view_revealed_identity -> Recruiter sees the real identity.
    detail = await apply_service.get_application(
        db_session, principal=recruiter, application_id=app_id,
    )
    assert detail["applicant"]["revealed"] is True

    # Sensitive-access audit trail keeps firing for every access.
    types = {
        e.event_type
        for e in (
            await db_session.execute(
                select(PartnerCandidateAccessEvent).where(
                    PartnerCandidateAccessEvent.application_id == app_id
                )
            )
        ).scalars().all()
    }
    assert {"identity_reveal_requested", "cv_previewed", "cv_downloaded"} <= types
    assert "identity_revealed_viewed" in types


async def test_hiring_manager_can_view_but_not_download_cv(db_session) -> None:
    org, _admin, _uni, job_id = await _published_partner_org(db_session)
    _student, app_id = await _named_application(db_session, job_id=job_id)
    _u, hm = await _member_with_seeded_role(
        db_session, org=org, role_name="Hiring Manager"
    )

    # view_cv -> allowed.
    view = await apply_service.get_application_cv_download(
        db_session, principal=hm, application_id=app_id, mode="view",
    )
    assert view["has_watermark"] is True
    # download_cv NOT granted -> 403 (action-scoped, same resource).
    with pytest.raises(PermissionDeniedError):
        await apply_service.get_application_cv_download(
            db_session, principal=hm, application_id=app_id, mode="download",
        )


async def test_analyst_role_denied_reveal_and_cv_but_can_read_analytics(
    db_session,
) -> None:
    org, _admin, _uni, job_id = await _published_partner_org(db_session)
    _student, app_id = await _anonymous_application(db_session, job_id=job_id)
    _u, analyst = await _member_with_seeded_role(
        db_session, org=org, role_name="Analyst"
    )

    # No candidate_identity -> reveal + CV view + CV download all denied.
    with pytest.raises(PermissionDeniedError):
        await reveal_service.request_reveal(
            db_session, principal=analyst, application_id=app_id,
            reason=_REVEAL_REASON, ctx=CTX,
        )
    with pytest.raises(PermissionDeniedError):
        await apply_service.get_application_cv_download(
            db_session, principal=analyst, application_id=app_id, mode="view",
        )
    with pytest.raises(PermissionDeniedError):
        await apply_service.get_application_cv_download(
            db_session, principal=analyst, application_id=app_id, mode="download",
        )

    # But analytics IS readable for the Analyst (the grant it DOES hold).
    assert permission_checker.can(
        analyst, "analytics", "view_job_metrics", resource_org_id=org.id
    )
    data = await partner_ops_dashboard_service.get_partner_dashboard_ops(
        db_session, principal=analyst,
    )
    assert data["job_performance"]["locked"] is False


async def test_admin_wildcard_passes_reveal_and_cv(db_session) -> None:
    org, admin, _uni, job_id = await _published_partner_org(db_session)
    student, app_id = await _anonymous_application(db_session, job_id=job_id)

    await reveal_service.request_reveal(
        db_session, principal=admin, application_id=app_id,
        reason=_REVEAL_REASON, ctx=CTX,
    )
    await reveal_service.respond_reveal(
        db_session, principal=student, application_id=app_id,
        decision="accepted", ctx=CTX,
    )
    view = await apply_service.get_application_cv_download(
        db_session, principal=admin, application_id=app_id, mode="view",
    )
    dl = await apply_service.get_application_cv_download(
        db_session, principal=admin, application_id=app_id, mode="download",
    )
    assert view["has_watermark"] is True
    assert dl["has_watermark"] is True


async def test_candidate_identity_grants_do_not_cross_org(db_session) -> None:
    _org_a, _admin_a, _uni, job_id = await _published_partner_org(
        db_session, display_name="Org A"
    )
    _student, app_id = await _anonymous_application(db_session, job_id=job_id)

    # A Recruiter in ANOTHER org holds full candidate_identity in its OWN org, but
    # that never reaches org A's application: cross-org is 404 (enumeration hiding),
    # never a 403 that would confirm the resource exists.
    _bu, org_b, _admin_b = await make_org_with_admin(db_session, display_name="Org B")
    _u, recruiter_b = await _member_with_seeded_role(
        db_session, org=org_b, role_name="Recruiter"
    )

    with pytest.raises(ResourceNotFoundError):
        await reveal_service.request_reveal(
            db_session, principal=recruiter_b, application_id=app_id,
            reason=_REVEAL_REASON, ctx=CTX,
        )
    with pytest.raises(ResourceNotFoundError):
        await apply_service.get_application_cv_download(
            db_session, principal=recruiter_b, application_id=app_id, mode="download",
        )
    with pytest.raises(ResourceNotFoundError):
        await apply_service.get_application_cv_download(
            db_session, principal=recruiter_b, application_id=app_id, mode="view",
        )
