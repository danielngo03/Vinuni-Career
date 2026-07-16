"""Job language detection + pre-warmed JD translation contract.

Covers the write-path language detection (create/update), the approve-time
translation pre-warm, and the public-detail inline ``translation`` field the
student job-detail "instant translate" swap depends on.
"""

from __future__ import annotations

import uuid

from app.modules.opportunities.application import job_service, moderation_service
from app.modules.opportunities.domain.models import JobTranslation
from app.shared.permissions import GUEST
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin

# Vietnamese content rich enough for the diacritic heuristic to fire ("vi").
_VI_DESC = (
    "Chúng tôi đang tuyển dụng kỹ sư backend để xây dựng hệ thống API "
    "cho công ty và phát triển sản phẩm."
)
_EN_DESC = "We are hiring a backend engineer to build APIs and scale our platform."


def _payload(title: str = "Backend Intern", **over) -> dict:
    base = {
        "title": title,
        "description": "We are hiring a backend intern to build APIs.",
        "requirements": None,
        "benefits": None,
        "employment_type": "internship",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["python"],
        "preferred_skills": [],
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "visibility": "public",
    }
    base.update(over)
    return base


async def _publish(db, partner, uni, *, title="Live Job", **over) -> uuid.UUID:
    created = await job_service.create_job(
        db, principal=partner, payload=_payload(title, **over), ctx=CTX
    )
    await job_service.submit_job(db, principal=partner, job_id=uuid.UUID(created["id"]), ctx=CTX)
    await moderation_service.approve_job(
        db, principal=uni, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    return uuid.UUID(created["id"])


# --------------------------------------------------------------------------- #
# Change 1 — language detection persisted on write                            #
# --------------------------------------------------------------------------- #


async def test_create_detects_vietnamese_language(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    created = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload("Kỹ sư phần mềm Backend", description=_VI_DESC),
        ctx=CTX,
    )
    assert created["language_code"] == "vi"


async def test_create_detects_english_language(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    created = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload("Backend Engineer", description=_EN_DESC),
        ctx=CTX,
    )
    assert created["language_code"] == "en"


async def test_update_description_flips_language_vi_to_en(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    # English title + Vietnamese description still reads as "vi" (desc dominates).
    created = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload("Backend Engineer", description=_VI_DESC),
        ctx=CTX,
    )
    assert created["language_code"] == "vi"

    # Rewriting the description into English flips the detected language.
    updated = await job_service.update_job(
        db_session,
        principal=admin,
        job_id=uuid.UUID(created["id"]),
        payload={"description": _EN_DESC},
        ctx=CTX,
    )
    assert updated["language_code"] == "en"


# --------------------------------------------------------------------------- #
# Change 4/5 — public detail inlines the cached opposite-lang translation      #
# --------------------------------------------------------------------------- #


async def test_public_detail_inlines_cached_translation(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    # English job -> opposite target is "vi".
    job_id = await _publish(db_session, admin, uni, title="Backend Engineer", description=_EN_DESC)

    db_session.add(
        JobTranslation(
            job_id=job_id,
            target_lang="vi",
            title="Kỹ sư Backend",
            description="Chúng tôi đang tuyển kỹ sư backend.",
            requirements=None,
            benefits=None,
            translated_by="chat_cheap",
        )
    )
    await db_session.commit()

    detail = await job_service.get_job(db_session, principal=GUEST, job_id=job_id)
    assert detail["translation"] is not None
    assert detail["translation"]["target_lang"] == "vi"
    assert detail["translation"]["title"] == "Kỹ sư Backend"
    assert detail["translation"]["requirements"] is None
    # No provider/model internals leak into the inline translation.
    assert "translated_by" not in detail["translation"]


async def test_public_detail_translation_null_when_no_cache(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _publish(db_session, admin, uni, title="Backend Engineer", description=_EN_DESC)

    detail = await job_service.get_job(db_session, principal=GUEST, job_id=job_id)
    assert detail["translation"] is None


# --------------------------------------------------------------------------- #
# Change 3 — approve-time pre-warm                                             #
# --------------------------------------------------------------------------- #


async def test_approve_offline_does_not_prewarm_or_raise(db_session) -> None:
    """AI offline (default test env): approve commits, no JobTranslation written."""
    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    created = await job_service.create_job(db_session, principal=admin, payload=_payload(), ctx=CTX)
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db_session, principal=admin, job_id=job_id, ctx=CTX)

    approved = await moderation_service.approve_job(
        db_session, principal=uni, job_id=job_id, ctx=CTX
    )
    assert approved["status"] == "active"

    rows = (
        await db_session.execute(
            select(JobTranslation).where(JobTranslation.job_id == job_id)
        )
    ).scalars().all()
    assert rows == []


async def test_approve_prewarms_translation_when_ai_active(db_session, monkeypatch) -> None:
    """AI active (mocked): approve pre-warms the opposite-lang JobTranslation."""
    from app.ai.gateway import factory as ai_factory
    from app.modules.opportunities.application import translation_service

    monkeypatch.setattr(ai_factory, "real_provider_active", lambda: True)

    async def _fake_ai_translate(job, *, target_lang, session=None):  # noqa: ANN001
        return {
            "title": "Kỹ sư Backend",
            "description": "Bản dịch mô tả công việc.",
            "requirements": None,
            "benefits": None,
        }

    monkeypatch.setattr(translation_service, "_ai_translate", _fake_ai_translate)

    _u, _org, admin = await make_org_with_admin(db_session)
    _uu, _uorg, uni = await make_org_with_admin(db_session, org_type="university")
    # English job -> opposite is "vi".
    created = await job_service.create_job(
        db_session,
        principal=admin,
        payload=_payload("Backend Engineer", description=_EN_DESC),
        ctx=CTX,
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(db_session, principal=admin, job_id=job_id, ctx=CTX)
    await moderation_service.approve_job(db_session, principal=uni, job_id=job_id, ctx=CTX)

    rows = (
        await db_session.execute(
            select(JobTranslation).where(JobTranslation.job_id == job_id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_lang == "vi"
    assert rows[0].title == "Kỹ sư Backend"
