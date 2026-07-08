"""Student offer comparison + on-demand negotiation guidance (WS-15, Task N).

Covers:

- deterministic side-by-side of the student's OWN offers (position, company, their
  disclosed comp, deadline, status) enriched with the internal salary benchmark —
  FREE, no AI, no energy charged;
- owner-only RBAC (another student never sees these offers / comp);
- the AI negotiation narrative is ON-DEMAND + confirmation-gated (``confirm=false``
  -> ``409 confirmation_required``), and when AI is off degrades to deterministic
  tips with NO energy charge;
- with the (offline, fake) provider forced on, the narrative is produced, energy
  is metered exactly once (idempotent per offer-set), the disclaimer is always
  present, and no provider/model/token/guarantee leaks into the payload.
"""

from __future__ import annotations

import json
import uuid

import pytest
from app.modules.documents.application import snapshot_service
from app.modules.recruitment.application import (
    access,
    apply_service,
    decision_service,
    offer_compare_service,
    offer_service,
)
from app.modules.recruitment.application.errors import ConfirmationRequiredError
from app.modules.recruitment.domain import offer as offer_domain

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job

# Leakage guard: none of these internal terms may ever appear in a student payload.
_FORBIDDEN = [
    "openrouter", "openai", "anthropic", "claude", "gpt-4", "gemini", "deepseek",
    "chat_cheap", "reasoning_cheap", "model_alias", "prompt_tokens",
    "completion_tokens", "usd", "token", "provider",
]

# Guarantee-language the advisory narrative must never assert.
_GUARANTEE_TERMS = ["guarantee", "guaranteed", "đảm bảo", "chắc chắn sẽ", "cam kết"]


def _assert_no_leak(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term!r}"


@pytest.fixture(autouse=True)
def _authorizer():
    access.install_authorizer()
    yield
    snapshot_service.set_snapshot_access_authorizer(None)


async def _sent_offer_for(
    db, *, partner, uni, student, sel, title, salary_amount, job_title="Live Job",
):
    """Publish a job, apply+review, then drive an offer all the way to ``sent``."""

    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=job_title,
    )
    app = await apply_service.apply_to_job(
        db, principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel), ctx=CTX,
    )
    app_id = uuid.UUID(app["id"])
    await decision_service.review_application(
        db, principal=partner, application_id=app_id, ctx=CTX,
    )
    from datetime import UTC, datetime, timedelta

    created = await offer_service.create_offer(
        db, principal=partner, application_id=app_id,
        position_title=title, expiry_date=datetime.now(UTC) + timedelta(days=7),
        salary_amount=salary_amount, ctx=CTX,
    )
    oid = uuid.UUID(created["id"])
    await offer_service.submit_offer(db, principal=partner, offer_id=oid, ctx=CTX)
    await offer_service.approve_offer(
        db, principal=partner, offer_id=oid, decision="approve", ctx=CTX,
    )
    await offer_service.send_offer(db, principal=partner, offer_id=oid, ctx=CTX)
    return oid


async def _two_offers(db):
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Acme Corp")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    _su, student = await make_student(db)
    sel = await make_builder_cv(db, student=student)
    await _sent_offer_for(
        db, partner=partner, uni=uni, student=student, sel=sel,
        title="Software Engineer", salary_amount=25_000_000, job_title="SWE Role",
    )
    await _sent_offer_for(
        db, partner=partner, uni=uni, student=student, sel=sel,
        title="Data Scientist", salary_amount=40_000_000, job_title="DS Role",
    )
    return student


# --------------------------------------------------------------------------- #
# Deterministic comparison (free)                                              #
# --------------------------------------------------------------------------- #


async def test_compare_returns_side_by_side_with_benchmark(db_session) -> None:
    student = await _two_offers(db_session)

    out = await offer_compare_service.compare_offers(
        db_session, principal=student, locale="en",
    )
    assert out["count"] == 2
    assert out["comparable"] is True
    titles = {row["position_title"] for row in out["offers"]}
    assert titles == {"Software Engineer", "Data Scientist"}

    for row in out["offers"]:
        assert row["company_name"] == "Acme Corp"
        # Owner sees their own decrypted comp.
        assert row["salary_amount"] in (25_000_000, 40_000_000)
        assert row["comp_summary"] is not None
        # Internal benchmark resolved + directly comparable (VND monthly).
        assert row["benchmark"]["found"] is True
        assert row["benchmark"]["position_vs_market"] in (
            "below_market", "within_market", "above_market",
        )
        assert row["status"] == offer_domain.STATUS_SENT
    _assert_no_leak(out)


async def test_compare_is_owner_only(db_session) -> None:
    await _two_offers(db_session)
    # A DIFFERENT student sees no offers (never another student's comp).
    _su2, other = await make_student(db_session, prefix="other")
    out = await offer_compare_service.compare_offers(
        db_session, principal=other, locale="en",
    )
    assert out["count"] == 0
    assert out["offers"] == []


async def test_compare_single_offer_not_comparable(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, display_name="Solo Co")
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    await _sent_offer_for(
        db_session, partner=partner, uni=uni, student=student, sel=sel,
        title="Software Engineer", salary_amount=25_000_000,
    )
    out = await offer_compare_service.compare_offers(
        db_session, principal=student, locale="vi",
    )
    assert out["count"] == 1
    assert out["comparable"] is False


# --------------------------------------------------------------------------- #
# Negotiation guidance — confirmation gate + AI-off fallback                    #
# --------------------------------------------------------------------------- #


async def test_negotiation_requires_confirmation(db_session) -> None:
    student = await _two_offers(db_session)
    with pytest.raises(ConfirmationRequiredError) as exc:
        await offer_compare_service.negotiation_guidance(
            db_session, principal=student, confirm=False, ctx=CTX, locale="en",
        )
    assert exc.value.http_status == 409
    assert exc.value.details["reason"] == "confirmation_required"


async def test_negotiation_ai_off_returns_tips_no_charge(db_session) -> None:
    from app.ai.observability.models import AiBillableUsage
    from sqlalchemy import func, select

    student = await _two_offers(db_session)
    out = await offer_compare_service.negotiation_guidance(
        db_session, principal=student, confirm=True, ctx=CTX, locale="en",
    )
    # Default offline provider -> deterministic tips, no narrative, no charge.
    assert out["ai_available"] is False
    assert out["guidance"] is None
    assert out["tips"]
    assert out["disclaimer"]
    assert len(out["offers"]) == 2

    charged = (
        await db_session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.feature_key == "offer_negotiation",
            )
        )
    ).scalar_one()
    assert int(charged) == 0
    _assert_no_leak(out)


# --------------------------------------------------------------------------- #
# Negotiation guidance — AI on (offline fake provider) is metered + safe        #
# --------------------------------------------------------------------------- #


async def test_negotiation_ai_on_is_metered_and_safe(db_session, monkeypatch) -> None:
    from app.ai.observability.models import AiBillableUsage
    from sqlalchemy import func, select

    student = await _two_offers(db_session)

    # Force the AI gate on and stub the gateway with a deterministic, safe line so
    # NO real model call happens. The energy charge is recorded explicitly by the
    # service on success (not by the stubbed generate_note).
    monkeypatch.setattr(
        offer_compare_service, "real_provider_active", lambda: True
    )

    async def _fake_generate(**kwargs):
        return "Cân nhắc tổng thu nhập và sự phù hợp trước khi phản hồi lịch sự."

    monkeypatch.setattr(offer_compare_service, "generate_note", _fake_generate)

    out = await offer_compare_service.negotiation_guidance(
        db_session, principal=student, confirm=True, ctx=CTX, locale="vi",
    )
    assert out["ai_available"] is True
    assert out["guidance"]
    # The disclaimer is ALWAYS attached so the product never implies a guaranteed
    # outcome (it itself says "does not guarantee" — that negation is expected).
    assert out["disclaimer"]
    assert "không đảm bảo" in out["disclaimer"]
    # The advisory NARRATIVE itself must not PROMISE an outcome.
    guidance_lower = out["guidance"].lower()
    for term in _GUARANTEE_TERMS:
        assert term not in guidance_lower, f"guarantee-language in narrative: {term!r}"
    _assert_no_leak(out)

    # Metered exactly once for the offer-set.
    charged = (
        await db_session.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.feature_key == "offer_negotiation",
                AiBillableUsage.actor_user_id == student.user_id,
            )
        )
    ).scalar_one()
    assert int(charged) == 2  # FEATURE_OFFER_NEGOTIATION unit cost


async def test_negotiation_ai_on_is_idempotent_per_offer_set(
    db_session, monkeypatch
) -> None:
    from app.ai.observability.models import AiBillableUsage
    from sqlalchemy import func, select

    student = await _two_offers(db_session)
    monkeypatch.setattr(
        offer_compare_service, "real_provider_active", lambda: True
    )

    async def _fake_generate(**kwargs):
        return "Advisory guidance grounded in the internal benchmark."

    monkeypatch.setattr(offer_compare_service, "generate_note", _fake_generate)

    await offer_compare_service.negotiation_guidance(
        db_session, principal=student, confirm=True, ctx=CTX, locale="en",
    )
    await offer_compare_service.negotiation_guidance(
        db_session, principal=student, confirm=True, ctx=CTX, locale="en",
    )

    # The same unchanged offer-set is charged at most once (idempotency key).
    total = (
        await db_session.execute(
            select(func.count()).select_from(AiBillableUsage).where(
                AiBillableUsage.feature_key == "offer_negotiation",
                AiBillableUsage.actor_user_id == student.user_id,
            )
        )
    ).scalar_one()
    assert int(total) == 1


async def test_negotiation_no_offers_returns_no_offers(db_session) -> None:
    _su, student = await make_student(db_session)
    out = await offer_compare_service.negotiation_guidance(
        db_session, principal=student, confirm=True, ctx=CTX, locale="en",
    )
    assert out["guidance"] is None
    assert out["ai_available"] is False
    assert out["ai_unavailable_reason"] == "no_offers"
    assert out["offers"] == []
