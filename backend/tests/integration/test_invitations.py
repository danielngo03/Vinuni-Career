"""Job application invitations — partner sends, student lists + responds."""

from __future__ import annotations

import pytest
from app.modules.recruitment.application import invitation_service
from app.shared.exceptions import ConflictError, ResourceNotFoundError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import publish_job

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup(db_session):
    """Create partner + university + student + published job."""
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Acme Corp")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session)
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)
    return partner, uni, student, job_id


# ---------------------------------------------------------------------------
# send_invite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_invite_creates_record(db_session) -> None:
    partner, _uni, student, job_id = await _setup(db_session)

    inv = await invitation_service.send_invite(
        db_session,
        principal=partner,
        job_id=job_id,
        student_id=student.user_id,
        message="We think you'd be a great fit!",
    )

    assert inv["status"] == "pending"
    assert inv["job_id"] == str(job_id)
    assert inv["message"] == "We think you'd be a great fit!"
    assert inv["company_name"]  # non-empty
    assert inv["job_title"]  # non-empty


@pytest.mark.asyncio
async def test_send_invite_duplicate_raises_conflict(db_session) -> None:
    partner, _uni, student, job_id = await _setup(db_session)

    await invitation_service.send_invite(
        db_session,
        principal=partner,
        job_id=job_id,
        student_id=student.user_id,
    )
    with pytest.raises(ConflictError):
        await invitation_service.send_invite(
            db_session,
            principal=partner,
            job_id=job_id,
            student_id=student.user_id,
        )


@pytest.mark.asyncio
async def test_send_invite_requires_partner(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Acme")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session)
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)

    # student cannot send invitations
    from app.shared.exceptions import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        await invitation_service.send_invite(
            db_session,
            principal=student,
            job_id=job_id,
            student_id=student.user_id,
        )


# ---------------------------------------------------------------------------
# list_student_invitations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_invitations_returns_pending(db_session) -> None:
    partner, _uni, student, job_id = await _setup(db_session)
    _su2, student2 = await make_student(db_session, prefix="s2")

    await invitation_service.send_invite(
        db_session,
        principal=partner,
        job_id=job_id,
        student_id=student.user_id,
    )

    invites = await invitation_service.list_student_invitations(
        db_session,
        principal=student,
    )
    assert len(invites) == 1
    assert invites[0]["status"] == "pending"

    # student2 sees nothing
    invites2 = await invitation_service.list_student_invitations(
        db_session,
        principal=student2,
    )
    assert invites2 == []


# ---------------------------------------------------------------------------
# respond_invitation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_respond_accept_marks_accepted_and_returns_apply_url(db_session) -> None:
    partner, _uni, student, job_id = await _setup(db_session)

    inv = await invitation_service.send_invite(
        db_session,
        principal=partner,
        job_id=job_id,
        student_id=student.user_id,
    )
    result = await invitation_service.respond_invitation(
        db_session,
        principal=student,
        invitation_id=inv["id"],
        response="accepted",
        ctx=CTX,
    )

    assert result["status"] == "accepted"
    assert result["responded_at"] is not None
    assert "apply_url" in result
    assert str(job_id) in result["apply_url"]


@pytest.mark.asyncio
async def test_respond_decline_marks_declined(db_session) -> None:
    partner, _uni, student, job_id = await _setup(db_session)

    inv = await invitation_service.send_invite(
        db_session,
        principal=partner,
        job_id=job_id,
        student_id=student.user_id,
    )
    result = await invitation_service.respond_invitation(
        db_session,
        principal=student,
        invitation_id=inv["id"],
        response="declined",
        ctx=CTX,
    )

    assert result["status"] == "declined"
    assert "apply_url" not in result


@pytest.mark.asyncio
async def test_respond_twice_raises_conflict(db_session) -> None:
    partner, _uni, student, job_id = await _setup(db_session)

    inv = await invitation_service.send_invite(
        db_session,
        principal=partner,
        job_id=job_id,
        student_id=student.user_id,
    )
    await invitation_service.respond_invitation(
        db_session,
        principal=student,
        invitation_id=inv["id"],
        response="declined",
    )
    with pytest.raises(ConflictError):
        await invitation_service.respond_invitation(
            db_session,
            principal=student,
            invitation_id=inv["id"],
            response="accepted",
        )


@pytest.mark.asyncio
async def test_respond_wrong_student_raises_not_found(db_session) -> None:
    partner, _uni, student, job_id = await _setup(db_session)
    _su2, student2 = await make_student(db_session, prefix="s2")

    inv = await invitation_service.send_invite(
        db_session,
        principal=partner,
        job_id=job_id,
        student_id=student.user_id,
    )
    # student2 cannot respond to student's invitation
    with pytest.raises(ResourceNotFoundError):
        await invitation_service.respond_invitation(
            db_session,
            principal=student2,
            invitation_id=inv["id"],
            response="accepted",
        )
