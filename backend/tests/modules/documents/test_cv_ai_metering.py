"""CV AI suggestions + natural-language edit command debit the STUDENT's energy.

Service-layer charge (mirrors ``jd_upload_service._meter_extraction``): a
model-backed suggestion / a successful edit-command diff charges one credit to the
student's user scope; the deterministic ATS/fabrication checks spend no tokens and
are free; a provider failure charges 0. No provider/model/token leakage.
"""

from __future__ import annotations

import json
import uuid

from app.ai.energy.service import charge_units
from app.ai.gateway.base import AICompletion
from app.ai.observability.models import AiBillableUsage
from app.modules.documents.application import cv_ai_service, cv_service
from app.modules.documents.domain.models import CvSection
from app.shared.exceptions import AIUnavailableError
from sqlalchemy import func, select
from tests.auth_utils import CTX
from tests.documents_utils import make_student, new_key


async def _user_units(db, user_id) -> int:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _rows(db, user_id) -> list[AiBillableUsage]:
    return list(
        (
            await db.execute(
                select(AiBillableUsage).where(AiBillableUsage.actor_user_id == user_id)
            )
        )
        .scalars()
        .all()
    )


async def _make_cv(db, student, *, title="My CV") -> dict:
    return await cv_service.create_cv(
        db, principal=student,
        payload={"title": title, "creation_mode": "blank_template"}, ctx=CTX,
    )


async def _seed(db, cv_id, section_type, items) -> uuid.UUID:
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    target = next(s for s in sections if s.section_type == section_type)
    target.content_json = {"items": items}
    await db.commit()
    return target.id


# --------------------------------------------------------------------------- #
# CV suggestion (FEATURE_CV_SUGGESTION) — model-backed task charges on success  #
# --------------------------------------------------------------------------- #


async def test_rewrite_suggestion_charges_student(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    sid = await _seed(db_session, cv["id"], "summary", [{"text": "built rest apis"}])

    await cv_ai_service.request_suggestion(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"task_type": "rewrite_cv_section", "target_section_id": str(sid),
                 "idempotency_key": new_key()},
        ctx=CTX,
    )

    assert await _user_units(db_session, student.user_id) == charge_units("cv_suggestion")
    rows = await _rows(db_session, student.user_id)
    assert len(rows) == 1
    assert rows[0].feature_key == "cv_suggestion"
    assert rows[0].billing_scope == "user"
    assert rows[0].result_status == "success"


async def test_deterministic_ats_task_is_free(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await _seed(db_session, cv["id"], "skills", [{"text": "python"}])

    # ATS keywords is deterministic (no model call) -> never charged.
    await cv_ai_service.request_suggestion(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"task_type": "ats_keyword_suggestions", "job_id": str(uuid.uuid4()),
                 "raw_notes": "python kubernetes", "idempotency_key": new_key()},
        ctx=CTX,
    )

    assert await _user_units(db_session, student.user_id) == 0
    assert await _rows(db_session, student.user_id) == []


async def test_suggestion_provider_failure_charges_zero(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    sid = await _seed(db_session, cv["id"], "summary", [{"text": "hello"}])

    class _Broken:
        async def complete(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr("app.ai.cv.llm.get_provider", lambda: _Broken())

    try:
        await cv_ai_service.request_suggestion(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={"task_type": "rewrite_cv_section", "target_section_id": str(sid),
                     "idempotency_key": new_key()},
            ctx=CTX,
        )
    except AIUnavailableError:
        pass

    assert await _user_units(db_session, student.user_id) == 0


# --------------------------------------------------------------------------- #
# Natural-language edit command (FEATURE_CV_EDIT_COMMAND)                        #
# --------------------------------------------------------------------------- #


class _FakeJsonProvider:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def complete(self, *a, **k):
        return AICompletion(text=json.dumps(self._payload), model_alias="x")


async def test_edit_command_charges_student(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    monkeypatch.setattr(
        "app.ai.cv.llm.get_provider",
        lambda: _FakeJsonProvider({"operations": [], "explanation": "no change needed"}),
    )

    await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "polish my summary", "idempotency_key": new_key()},
        ctx=CTX,
    )

    assert await _user_units(db_session, student.user_id) == charge_units("cv_edit_command")
    rows = await _rows(db_session, student.user_id)
    assert len(rows) == 1
    assert rows[0].feature_key == "cv_edit_command"
    assert rows[0].result_status == "success"


async def test_edit_command_provider_failure_charges_zero(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)

    class _Broken:
        async def complete(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr("app.ai.cv.llm.get_provider", lambda: _Broken())

    try:
        await cv_ai_service.request_edit_command(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={"instruction": "polish my summary", "idempotency_key": new_key()},
            ctx=CTX,
        )
    except AIUnavailableError:
        pass

    assert await _user_units(db_session, student.user_id) == 0
