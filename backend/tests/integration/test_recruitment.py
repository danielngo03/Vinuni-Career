"""Recruitment apply-flow service tests.

Covers: apply happy path (creates the immutable CV snapshot + links snapshot_id),
apply to non-visible/closed job rejected, duplicate active apply rejected, submit
idempotency replay, withdraw idempotency, student sees only own applications,
partner sees only own-org job applications (cross-org 404), anonymous applicant
redacted in the partner view until reveal accepted, partner watermarked CV
download + non-partner 404 + anonymous-unrevealed download blocked, and audit on
writes.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.documents.domain.models import ApplicationCvSnapshot
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.opportunities.application import job_service
from app.modules.opportunities.domain.models import Job
from app.modules.recruitment.application import access, apply_service, export_service, reveal_service
from app.modules.recruitment.application.errors import (
    DuplicateApplicationError,
    RevealNotAvailableError,
)
from app.modules.recruitment.domain.models import Application
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import (
    apply_payload,
    job_payload,
    make_builder_cv,
    publish_job,
)


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _setup_published(db, *, title="Live Job", **over):
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title, **over
    )
    return partner, uni, job_id


# --------------------------------------------------------------------------- #
# Apply happy path                                                            #
# --------------------------------------------------------------------------- #


async def test_apply_creates_immutable_snapshot_and_links(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)

    out = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    assert out["status"] == "submitted"
    assert out["status_label"]  # localized, never raw-only
    assert out["snapshot_id"] is not None

    # The snapshot is linked to the application and immutable (no update/delete API).
    snap = (
        await db_session.execute(
            select(ApplicationCvSnapshot).where(
                ApplicationCvSnapshot.id == uuid.UUID(out["snapshot_id"])
            )
        )
    ).scalar_one()
    assert str(snap.application_id) == out["id"]
    assert not hasattr(snapshot_service, "update_application_cv_snapshot")

    assert await _audit_count(db_session, "application.created") == 1
    assert await _audit_count(db_session, "cv.snapshot.created") == 1

    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "application.received"
            )
        )
    ).scalars().all()
    assert len(outbox) == 1


# --------------------------------------------------------------------------- #
# Closed / non-visible job                                                    #
# --------------------------------------------------------------------------- #


async def test_apply_to_draft_job_rejected(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session)
    draft = await job_service.create_job(
        db_session, principal=partner, payload=job_payload("Draft"), ctx=CTX
    )
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    with pytest.raises(ResourceNotFoundError):
        await apply_service.apply_to_job(
            db_session, principal=student,
            payload=apply_payload(job_id=uuid.UUID(draft["id"]), cv_selection=sel),
            ctx=CTX,
        )


async def test_apply_to_closed_job_rejected(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    await job_service.close_job(db_session, principal=partner, job_id=job_id, ctx=CTX)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    with pytest.raises(ResourceNotFoundError):
        await apply_service.apply_to_job(
            db_session, principal=student,
            payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Duplicate + idempotency                                                     #
# --------------------------------------------------------------------------- #


async def test_duplicate_active_apply_rejected(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    # A second apply with a DIFFERENT idempotency key is a genuine duplicate.
    with pytest.raises(DuplicateApplicationError):
        await apply_service.apply_to_job(
            db_session, principal=student,
            payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
        )


async def test_apply_idempotency_replay_returns_same(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    payload = apply_payload(job_id=job_id, cv_selection=sel)
    a1 = await apply_service.apply_to_job(
        db_session, principal=student, payload=dict(payload), ctx=CTX
    )
    a2 = await apply_service.apply_to_job(
        db_session, principal=student, payload=dict(payload), ctx=CTX
    )
    assert a1["id"] == a2["id"]
    count = (
        await db_session.execute(select(func.count()).select_from(Application))
    ).scalar_one()
    assert count == 1


# --------------------------------------------------------------------------- #
# Withdraw                                                                    #
# --------------------------------------------------------------------------- #


async def test_withdraw_is_idempotent(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    w1 = await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id, ctx=CTX
    )
    w2 = await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id, ctx=CTX
    )
    assert w1["status"] == "withdrawn" and w2["status"] == "withdrawn"
    assert await _audit_count(db_session, "application.withdrawn") == 1


async def _job_application_count(db, job_id: uuid.UUID) -> int:
    return (
        await db.execute(select(Job.application_count).where(Job.id == job_id))
    ).scalar_one()


async def test_apply_increments_then_withdraw_decrements_count(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)

    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    assert await _job_application_count(db_session, job_id) == 1

    await apply_service.withdraw_application(
        db_session, principal=student, application_id=uuid.UUID(app["id"]), ctx=CTX
    )
    assert await _job_application_count(db_session, job_id) == 0


async def test_re_withdraw_does_not_double_decrement_count(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)

    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id, ctx=CTX
    )
    # Idempotent re-withdraw must NOT decrement again (no drift below the real total).
    await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id, ctx=CTX
    )
    count = await _job_application_count(db_session, job_id)
    assert count == 0  # floored, never negative


async def test_two_applies_then_one_withdraw_leaves_count_one(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _s1, student_a = await make_student(db_session, prefix="a")
    _s2, student_b = await make_student(db_session, prefix="b")
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
    assert await _job_application_count(db_session, job_id) == 2

    await apply_service.withdraw_application(
        db_session, principal=student_a, application_id=uuid.UUID(app_a["id"]), ctx=CTX
    )
    assert await _job_application_count(db_session, job_id) == 1


# --------------------------------------------------------------------------- #
# Tenant isolation                                                            #
# --------------------------------------------------------------------------- #


async def test_student_sees_only_own_applications(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _s1, student_a = await make_student(db_session, prefix="a")
    _s2, student_b = await make_student(db_session, prefix="b")
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
    items_a, _c, _l = await apply_service.list_my_applications(
        db_session, principal=student_a
    )
    assert [i["id"] for i in items_a] == [app_a["id"]]

    # Student B cannot read student A's application detail -> 404.
    with pytest.raises(ResourceNotFoundError):
        await apply_service.get_application(
            db_session, principal=student_b, application_id=uuid.UUID(app_a["id"])
        )


async def test_partner_sees_only_own_org_job_applications(db_session) -> None:
    partner_a, _uni, job_id = await _setup_published(db_session, title="A Job")
    _pb_u, _pb_org, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )

    items, _c, _l = await apply_service.list_job_applications(
        db_session, principal=partner_a, job_id=job_id
    )
    assert [i["id"] for i in items] == [app["id"]]

    # Cross-org partner cannot list another org's job applications -> 404.
    with pytest.raises(ResourceNotFoundError):
        await apply_service.list_job_applications(
            db_session, principal=partner_b, job_id=job_id
        )


# --------------------------------------------------------------------------- #
# Anonymous redaction + reveal                                                #
# --------------------------------------------------------------------------- #


async def test_anonymous_applicant_redacted_until_reveal(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])

    items, _c, _l = await apply_service.list_job_applications(
        db_session, principal=partner, job_id=job_id
    )
    applicant = items[0]["applicant"]
    assert applicant["is_anonymous"] is True and applicant["revealed"] is False
    assert applicant["anonymous_id"].startswith("UV-")
    assert "email" not in applicant
    assert items[0]["cover_letter"] is None
    assert items[0]["cv_download_available"] is False

    # Partner requests reveal (reason >= 20 chars), student accepts.
    await reveal_service.request_reveal(
        db_session, principal=partner, application_id=app_id,
        reason="We would like to learn more about your internship experience.", ctx=CTX,
    )
    await reveal_service.respond_reveal(
        db_session, principal=student, application_id=app_id, decision="accepted", ctx=CTX,
    )

    items2, _c2, _l2 = await apply_service.list_job_applications(
        db_session, principal=partner, job_id=job_id
    )
    applicant2 = items2[0]["applicant"]
    assert applicant2["revealed"] is True
    assert applicant2["email"] == su.email
    assert items2[0]["cv_download_available"] is True
    assert await _audit_count(db_session, "application.reveal_requested") == 1
    assert await _audit_count(db_session, "application.reveal_responded") == 1


async def test_reveal_reason_too_short_rejected(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    with pytest.raises(ValidationFailedError):
        await reveal_service.request_reveal(
            db_session, principal=partner, application_id=uuid.UUID(app["id"]),
            reason="too short", ctx=CTX,
        )


async def test_reveal_on_non_anonymous_rejected(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=False),
        ctx=CTX,
    )
    with pytest.raises(RevealNotAvailableError):
        await reveal_service.request_reveal(
            db_session, principal=partner, application_id=uuid.UUID(app["id"]),
            reason="We would like to learn more about your experience here.", ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Partner watermarked CV download                                            #
# --------------------------------------------------------------------------- #


async def test_partner_cv_download_watermarked_and_non_partner_404(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])

    # Owner self-download is not watermarked.
    own = await apply_service.get_application_cv_download(
        db_session, principal=student, application_id=app_id
    )
    assert own["has_watermark"] is False

    # Authorized partner download IS watermarked.
    partner_dl = await apply_service.get_application_cv_download(
        db_session, principal=partner, application_id=app_id
    )
    assert partner_dl["has_watermark"] is True

    # A non-partner third party cannot download -> 404.
    _ou, outsider = await make_student(db_session, prefix="outsider")
    with pytest.raises(ResourceNotFoundError):
        await apply_service.get_application_cv_download(
            db_session, principal=outsider, application_id=app_id
        )


async def test_anonymous_unrevealed_partner_download_blocked(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    # PDF download blocked until reveal accepted.
    with pytest.raises(ResourceNotFoundError):
        await apply_service.get_application_cv_download(
            db_session, principal=partner, application_id=uuid.UUID(app["id"])
        )


# --------------------------------------------------------------------------- #
# Application CSV export (B-322)                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_export_csv_returns_rows_for_partner(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session, prefix="exp1")
    sel = await make_builder_cv(db_session, student=student)
    await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )

    csv_text = await export_service.export_applications_csv(
        db_session, principal=partner, job_id=job_id
    )

    lines = [l for l in csv_text.splitlines() if l.strip()]
    assert lines[0].startswith("application_id"), "first line must be CSV header"
    assert len(lines) >= 2, "expected at least one data row"
    assert "is_anonymous" in lines[0]


@pytest.mark.asyncio
async def test_export_csv_cross_org_raises_not_found(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _ou, _oorg, outsider = await make_org_with_admin(db_session, display_name="Other Co")

    from app.shared.exceptions import ResourceNotFoundError as RNFE
    with pytest.raises(RNFE):
        await export_service.export_applications_csv(
            db_session, principal=outsider, job_id=job_id
        )


@pytest.mark.asyncio
async def test_export_csv_anonymous_unrevealed_redacted(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session, prefix="anon_exp")
    sel = await make_builder_cv(db_session, student=student)
    await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )

    csv_text = await export_service.export_applications_csv(
        db_session, principal=partner, job_id=job_id
    )
    lines = [l for l in csv_text.splitlines() if l.strip()]
    # Data row(s) for the anonymous applicant must not contain any email
    data_rows = lines[1:]
    assert any("UV-" in row for row in data_rows), "anonymous label must use UV- prefix"
    # The email column (3rd column, index 2) must be empty for unrevealed anon
    import csv as _csv, io as _io
    reader = list(_csv.reader(_io.StringIO(csv_text)))
    email_col_idx = reader[0].index("email")
    anon_rows = [r for r in reader[1:] if r[email_col_idx] == ""]
    assert len(anon_rows) >= 1, "unrevealed anonymous applicant must have blank email"


# --------------------------------------------------------------------------- #
# Withdraw hardening: reason + version conflict (E36 B-551)                   #
# --------------------------------------------------------------------------- #


async def test_withdraw_with_reason_recorded_in_audit_and_timeline(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])

    out = await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id,
        reason="Accepted another offer.", ctx=CTX,
    )
    assert out["status"] == "withdrawn"

    row = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "application.withdrawn")
        )
    ).scalar_one()
    assert row.after_snapshot["reason"] == "Accepted another offer."

    # The withdraw response itself doesn't carry the timeline (only the detail
    # read does); fetch the detail projection to verify it.
    detail = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    events = detail["timeline"]
    assert [e["event_type"] for e in events] == ["submitted", "withdrawn"]
    assert all("metadata" not in e for e in events)
    assert all(set(e.keys()) == {"event_type", "label", "occurred_at"} for e in events)


async def test_withdraw_version_conflict_is_409(db_session) -> None:
    from app.modules.recruitment.application.errors import ApplicationVersionConflictError

    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])

    with pytest.raises(ApplicationVersionConflictError):
        await apply_service.withdraw_application(
            db_session, principal=student, application_id=app_id,
            version=999, ctx=CTX,
        )
    # Correct version still withdraws.
    out = await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id,
        version=app["version"], ctx=CTX,
    )
    assert out["status"] == "withdrawn"


async def test_duplicate_apply_409_includes_existing_application_id_and_status(
    db_session,
) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    first = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    with pytest.raises(DuplicateApplicationError) as exc:
        await apply_service.apply_to_job(
            db_session, principal=student,
            payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
        )
    assert exc.value.details == {
        "reason": "duplicate_application",
        "application_id": first["id"],
        "status": "submitted",
    }


# --------------------------------------------------------------------------- #
# Real application timeline (E36 B-551 / docs/DATA_MODEL.md §32)              #
# --------------------------------------------------------------------------- #


async def test_application_timeline_records_submit_review_reject_sequence(
    db_session,
) -> None:
    from app.modules.recruitment.application import decision_service

    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Decider Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)

    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])

    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await decision_service.reject_application(
        db_session, principal=partner, application_id=app_id,
        reason="not_qualified", note="Internal-only note.", ctx=CTX,
    )

    out = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    assert [e["event_type"] for e in out["timeline"]] == [
        "submitted",
        "under_review",
        "rejected",
    ]
    assert out["next_action"] == "no_action_rejected"
    assert out["can_withdraw"] is False


async def test_student_timeline_never_exposes_partner_rejection_note_or_stage_metadata(
    db_session,
) -> None:
    from app.modules.recruitment.application import decision_service, stage_service

    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await publish_job(db_session, partner_principal=partner, uni_principal=uni)

    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    app = await apply_service.apply_to_job(
        db_session, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    # Advance once (materializes stage-1 then advances to stage-2), exercising the
    # ``stage_advanced`` event, before rejecting.
    await stage_service.advance_application_stage(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    await decision_service.reject_application(
        db_session, principal=partner, application_id=app_id,
        reason="experience_mismatch", note="Do not tell the candidate this.", ctx=CTX,
    )

    out = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    for event in out["timeline"]:
        assert set(event.keys()) == {"event_type", "label", "occurred_at"}
        assert "metadata" not in event
        assert "reason" not in event
        assert "Do not tell the candidate this." not in str(event)
        assert "experience_mismatch" not in str(event)


# --------------------------------------------------------------------------- #
# Missing/non-owned CV -> 404 (apply-flow ownership check; documents module)   #
# --------------------------------------------------------------------------- #


async def test_apply_with_non_owned_cv_selection_is_404(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _s1, owner = await make_student(db_session, prefix="owner")
    _s2, other = await make_student(db_session, prefix="other")
    sel = await make_builder_cv(db_session, student=owner)

    with pytest.raises(ResourceNotFoundError):
        await apply_service.apply_to_job(
            db_session, principal=other,
            payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
        )
