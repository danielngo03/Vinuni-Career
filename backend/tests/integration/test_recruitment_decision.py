"""Partner application decision-status machine + outcome notification tests.

Covers the Phase-1.5 decision subset (``decision_service``):

- Legal transitions: review (``submitted -> under_review``), reject from both
  ``submitted`` and ``under_review``.
- Illegal transitions: review/reject a ``withdrawn`` -> 409; review a ``rejected``
  -> 409.
- Validation: reject without a reason / invalid reason code -> 422 (HTTP schema).
- Org isolation: a partner of org B gets 404 on org A's application.
- Optimistic concurrency: stale ``version`` -> 409.
- Idempotency: re-review / re-reject -> 200 no-op, exactly ONE notification total.
- Audit: one row per transition; reject audit carries the reason in metadata.
- Student notification: exactly one neutral in-app row per transition; the reason
  code and the partner note never appear in the title/body.
- Projection split: partner projection exposes reason/note/last_status_at; the
  student projection exposes only status/status_label/last_status_at.
- Anonymity: a decision never reveals the anonymous student's identity.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.notifications.domain.models import Notification, NotificationOutbox
from app.modules.recruitment.application import access, apply_service, decision_service
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    IllegalApplicationTransitionError,
)
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _setup_published(db, *, title="Live Job", **over):
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title, **over
    )
    return partner, uni, job_id


async def _apply(db, *, job_id, prefix="student", is_anonymous=False):
    su, student = await make_student(db, prefix=prefix)
    sel = await make_builder_cv(db, student=student)
    app = await apply_service.apply_to_job(
        db,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=is_anonymous),
        ctx=CTX,
    )
    return su, student, uuid.UUID(app["id"])


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _feed_rows(db, *, recipient_id, notif_type) -> list[Notification]:
    return list(
        (
            await db.execute(
                select(Notification).where(
                    Notification.recipient_id == recipient_id,
                    Notification.notif_type == notif_type,
                )
            )
        )
        .scalars()
        .all()
    )


async def _outbox_count(db, *, template_key) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.template_key == template_key)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Legal transitions                                                           #
# --------------------------------------------------------------------------- #


async def test_review_submitted_to_under_review(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)

    out = await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert out["status"] == "under_review"
    assert out["status_label"]  # localized, never raw-only
    assert out["last_status_at"] is not None
    assert await _audit_count(db_session, "application.reviewed") == 1


async def test_reject_from_submitted(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)

    out = await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="not_qualified",
        note="Junior for this role",
        ctx=CTX,
    )
    assert out["status"] == "rejected"
    assert out["rejection_reason"] == "not_qualified"
    assert out["rejection_note"] == "Junior for this role"
    assert await _audit_count(db_session, "application.rejected") == 1


async def test_reject_from_under_review(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    out = await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="experience_mismatch",
        ctx=CTX,
    )
    assert out["status"] == "rejected"
    assert out["rejection_reason"] == "experience_mismatch"


async def test_reject_frees_active_slot_allows_reapply(db_session) -> None:
    """``rejected`` is inactive, so the student may apply to the same job again."""

    partner, _uni, job_id = await _setup_published(db_session)
    su, student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="position_filled",
        ctx=CTX,
    )
    sel = await make_builder_cv(db_session, student=student)
    again = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel),
        ctx=CTX,
    )
    assert again["status"] == "submitted"
    assert again["id"] != str(app_id)


# --------------------------------------------------------------------------- #
# Illegal transitions                                                         #
# --------------------------------------------------------------------------- #


async def test_review_withdrawn_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student, app_id = await _apply(db_session, job_id=job_id)
    await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id, ctx=CTX
    )
    with pytest.raises(IllegalApplicationTransitionError):
        await decision_service.review_application(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )


async def test_reject_withdrawn_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student, app_id = await _apply(db_session, job_id=job_id)
    await apply_service.withdraw_application(
        db_session, principal=student, application_id=app_id, ctx=CTX
    )
    with pytest.raises(IllegalApplicationTransitionError):
        await decision_service.reject_application(
            db_session,
            principal=partner,
            application_id=app_id,
            reason="other",
            ctx=CTX,
        )


async def test_review_rejected_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="incomplete",
        ctx=CTX,
    )
    with pytest.raises(IllegalApplicationTransitionError):
        await decision_service.review_application(
            db_session, principal=partner, application_id=app_id, ctx=CTX
        )


# --------------------------------------------------------------------------- #
# Validation (HTTP schema enforces the coded enum -> 422)                      #
# --------------------------------------------------------------------------- #


def test_reject_schema_requires_coded_reason() -> None:
    """The reject body schema enforces the coded enum; FastAPI maps this to 422.

    Validation happens at the HTTP boundary (Pydantic) before the service runs, so
    a missing or out-of-vocabulary ``reason`` never reaches ``reject_application``.
    """

    from app.modules.recruitment.api.schemas import RejectRequestBody
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RejectRequestBody()  # missing required reason
    with pytest.raises(ValidationError):
        RejectRequestBody(reason="made_up_code")  # not in the coded enum
    # A valid code passes and round-trips the optional fields.
    ok = RejectRequestBody(reason="not_qualified", note="x", version=3)
    assert ok.reason == "not_qualified" and ok.version == 3


# --------------------------------------------------------------------------- #
# Org isolation                                                               #
# --------------------------------------------------------------------------- #


async def test_cross_org_partner_gets_404(db_session) -> None:
    partner_a, _uni, job_id = await _setup_published(db_session, title="A Job")
    _pb_u, _pb_org, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    _su, _student, app_id = await _apply(db_session, job_id=job_id)

    with pytest.raises(ResourceNotFoundError):
        await decision_service.review_application(
            db_session, principal=partner_b, application_id=app_id, ctx=CTX
        )
    with pytest.raises(ResourceNotFoundError):
        await decision_service.reject_application(
            db_session,
            principal=partner_b,
            application_id=app_id,
            reason="other",
            ctx=CTX,
        )
    # The legitimate org-A partner can still act.
    out = await decision_service.review_application(
        db_session, principal=partner_a, application_id=app_id, ctx=CTX
    )
    assert out["status"] == "under_review"


# --------------------------------------------------------------------------- #
# Optimistic version conflict                                                 #
# --------------------------------------------------------------------------- #


async def test_review_version_conflict_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    with pytest.raises(ApplicationVersionConflictError):
        await decision_service.review_application(
            db_session, principal=partner, application_id=app_id, version=999, ctx=CTX
        )


async def test_reject_version_conflict_is_409(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    with pytest.raises(ApplicationVersionConflictError):
        await decision_service.reject_application(
            db_session,
            principal=partner,
            application_id=app_id,
            reason="other",
            version=999,
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Idempotency (no duplicate notification)                                     #
# --------------------------------------------------------------------------- #


async def test_double_review_idempotent_single_notification(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id)

    r1 = await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    r2 = await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    assert r1["status"] == r2["status"] == "under_review"
    assert await _audit_count(db_session, "application.reviewed") == 1
    assert await _outbox_count(db_session, template_key="application.under_review") == 1
    rows = await _feed_rows(
        db_session, recipient_id=su.id, notif_type="recruitment.application_under_review"
    )
    assert len(rows) == 1


async def test_double_reject_idempotent_single_notification(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id)

    await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="not_qualified",
        note="first note",
        ctx=CTX,
    )
    # Replay with a different reason/note must NOT overwrite or re-notify.
    out2 = await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="other",
        note="second note",
        ctx=CTX,
    )
    assert out2["rejection_reason"] == "not_qualified"
    assert out2["rejection_note"] == "first note"
    assert await _audit_count(db_session, "application.rejected") == 1
    assert await _outbox_count(db_session, template_key="application.rejected") == 1
    rows = await _feed_rows(
        db_session, recipient_id=su.id, notif_type="recruitment.application_rejected"
    )
    assert len(rows) == 1


# --------------------------------------------------------------------------- #
# Neutral student copy (no reason code / note leakage)                        #
# --------------------------------------------------------------------------- #


async def test_student_notification_neutral_no_reason_leak(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id)
    secret_note = "Candidate failed the take-home test badly"

    await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="not_qualified",
        note=secret_note,
        ctx=CTX,
    )
    rows = await _feed_rows(
        db_session, recipient_id=su.id, notif_type="recruitment.application_rejected"
    )
    assert len(rows) == 1
    blob = f"{rows[0].title} {rows[0].body}"
    assert "not_qualified" not in blob
    assert secret_note not in blob
    assert rows[0].title and rows[0].body  # friendly localized copy present


async def test_review_notification_exists_and_neutral(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    rows = await _feed_rows(
        db_session, recipient_id=su.id, notif_type="recruitment.application_under_review"
    )
    assert len(rows) == 1
    assert "under_review" not in f"{rows[0].title} {rows[0].body}"


# --------------------------------------------------------------------------- #
# Audit metadata carries the reason                                           #
# --------------------------------------------------------------------------- #


async def test_reject_audit_metadata_has_reason(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, _student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="position_filled",
        ctx=CTX,
    )
    row = (
        (
            await db_session.execute(
                select(AuditLog).where(AuditLog.action == "application.rejected")
            )
        )
        .scalars()
        .one()
    )
    assert row.after_snapshot["rejection_reason"] == "position_filled"
    assert row.after_snapshot["status"] == "rejected"


# --------------------------------------------------------------------------- #
# Projection split: partner sees reason/note, student does not                #
# --------------------------------------------------------------------------- #


async def test_projection_split_partner_vs_student(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student, app_id = await _apply(db_session, job_id=job_id)
    await decision_service.reject_application(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="incomplete",
        note="missing transcript",
        ctx=CTX,
    )

    partner_view = await apply_service.get_application(
        db_session, principal=partner, application_id=app_id
    )
    assert partner_view["rejection_reason"] == "incomplete"
    assert partner_view["rejection_note"] == "missing transcript"
    assert partner_view["last_status_at"] is not None
    assert partner_view["status_label"]

    student_view = await apply_service.get_application(
        db_session, principal=student, application_id=app_id
    )
    assert student_view["status"] == "rejected"
    assert student_view["status_label"]
    assert student_view["last_status_at"] is not None
    assert "rejection_reason" not in student_view
    assert "rejection_note" not in student_view


# --------------------------------------------------------------------------- #
# Anonymity preserved across a decision                                       #
# --------------------------------------------------------------------------- #


async def test_anonymous_identity_not_revealed_by_decision(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    su, _student, app_id = await _apply(db_session, job_id=job_id, is_anonymous=True)
    await decision_service.review_application(
        db_session, principal=partner, application_id=app_id, ctx=CTX
    )
    view = await apply_service.get_application(db_session, principal=partner, application_id=app_id)
    applicant = view["applicant"]
    assert applicant["is_anonymous"] is True and applicant["revealed"] is False
    assert "email" not in applicant
    assert "user_id" not in applicant
    assert su.email not in str(view)
