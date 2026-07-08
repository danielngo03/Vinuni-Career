"""JD original-language detection is resolved + persisted at create/update.

The stored ``language_code`` drives the student "translate this JD" affordance,
so it must always be a concrete language (never "mixed"/"unknown") and must
reflect the JD text even when the partner peppers a Vietnamese posting with
English tool/skill terms.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.opportunities.application import job_write_service
from app.modules.opportunities.domain import language_detection
from app.modules.opportunities.domain.language_detection import resolve_original_language
from app.modules.opportunities.domain.models import Job
from sqlalchemy import select

from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import CTX, job_payload

_VI_JD = (
    "Chúng tôi đang tuyển kỹ sư backend để xây dựng hệ thống API quy mô lớn. "
    "Yêu cầu kinh nghiệm với Python, Docker và React, có khả năng làm việc nhóm tốt."
)
_EN_JD = (
    "We are hiring a senior backend engineer to build large-scale API systems. "
    "Strong experience with Python, Docker, and AWS is required for this platform role."
)


# --------------------------------------------------------------------------- #
# resolve_original_language (pure)                                              #
# --------------------------------------------------------------------------- #


def test_resolve_vietnamese_with_english_terms() -> None:
    # A Vietnamese JD sprinkled with English tech terms must resolve to "vi".
    assert resolve_original_language(hint=None, text=_VI_JD) == "vi"


def test_resolve_english() -> None:
    assert resolve_original_language(hint=None, text=_EN_JD) == "en"


def test_concrete_hint_wins_over_text() -> None:
    # Partner explicitly marked it English (e.g. AI extraction detected_language).
    assert resolve_original_language(hint="en", text=_VI_JD) == "en"


def test_non_storable_hint_falls_through_to_heuristic() -> None:
    # "mixed" is not a storable language → ignore the hint, detect from text.
    assert resolve_original_language(hint="mixed", text=_VI_JD) == "vi"


def test_mixed_maps_to_vietnamese(monkeypatch) -> None:
    monkeypatch.setattr(language_detection, "detect_language", lambda _t: "mixed")
    assert resolve_original_language(hint=None, text="whatever") == "vi"


def test_unknown_falls_back_to_english(monkeypatch) -> None:
    monkeypatch.setattr(language_detection, "detect_language", lambda _t: "unknown")
    assert resolve_original_language(hint=None, text="hi") == "en"


# --------------------------------------------------------------------------- #
# create_job / update_job persistence                                           #
# --------------------------------------------------------------------------- #


async def _job(db_session, org_id) -> Job:
    return (
        await db_session.execute(select(Job).where(Job.org_id == org_id))
    ).scalar_one()


async def test_create_job_persists_detected_vietnamese(db_session) -> None:
    _, org, principal = await make_org_with_admin(db_session)
    await job_write_service.create_job(
        db_session,
        principal=principal,
        payload=job_payload(title="Kỹ sư Backend", description=_VI_JD),
        ctx=CTX,
    )
    job = await _job(db_session, org.id)
    assert job.language_code == "vi"


async def test_create_job_persists_detected_english(db_session) -> None:
    _, org, principal = await make_org_with_admin(db_session)
    await job_write_service.create_job(
        db_session,
        principal=principal,
        payload=job_payload(title="Backend Engineer", description=_EN_JD),
        ctx=CTX,
    )
    job = await _job(db_session, org.id)
    assert job.language_code == "en"


async def test_create_job_honors_language_hint(db_session) -> None:
    _, org, principal = await make_org_with_admin(db_session)
    # Vietnamese text but the partner/AI hint says English → hint wins.
    await job_write_service.create_job(
        db_session,
        principal=principal,
        payload=job_payload(description=_VI_JD, language_code="en"),
        ctx=CTX,
    )
    job = await _job(db_session, org.id)
    assert job.language_code == "en"


async def test_update_job_redetects_on_description_change(db_session) -> None:
    _, org, principal = await make_org_with_admin(db_session)
    created = await job_write_service.create_job(
        db_session,
        principal=principal,
        payload=job_payload(description=_VI_JD),
        ctx=CTX,
    )
    job = await _job(db_session, org.id)
    assert job.language_code == "vi"

    # Rewrite the JD into English → language re-detects to "en".
    await job_write_service.update_job(
        db_session,
        principal=principal,
        job_id=uuid.UUID(created["id"]),
        payload={"description": _EN_JD},
        ctx=CTX,
    )
    await db_session.refresh(job)
    assert job.language_code == "en"
