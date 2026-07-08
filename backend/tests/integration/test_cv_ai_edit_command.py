"""Natural-language CV edit command (``ai-edit-command``) tests.

Covers (``docs/CV_STUDIO_SPEC.md`` "Natural-Language AI Editing"):

- request produces a pending structured diff and NEVER mutates the CV;
- deterministic operation validation (unknown section types / ops dropped, not
  trusted as CV content);
- accept reuses the standard suggestion accept pipeline: fact_confirmation gate,
  new cv_versions row, audit;
- reject leaves the CV unchanged;
- an unmappable model response degrades to a non-applicable, non-acceptable diff
  (no crash);
- provider failure -> AI_UNAVAILABLE (no stack trace);
- no provider/model/token leak; cross-owner 404; idempotent request.
"""

from __future__ import annotations

import json
import uuid

import pytest
from app.ai.gateway.base import AICompletion
from app.modules.documents.application import cv_ai_service, cv_service
from app.modules.documents.application.errors import (
    AiSourceRequiredError,
    SuggestionNotApplicableError,
)
from app.modules.documents.domain.models import CvSection
from app.shared.exceptions import AIUnavailableError, ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import make_student, new_key

_FORBIDDEN = [
    "openrouter", "openai", "anthropic", "claude", "gpt-4", "gemini", "deepseek",
    "chat_cheap", "reasoning_cheap", "model_alias", "prompt_tokens",
    "completion_tokens", "storage_path", "storage_key",
]


def _assert_no_leak(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term}"


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _make_cv(db, student, *, title="My CV") -> dict:
    return await cv_service.create_cv(
        db, principal=student, payload={"title": title, "creation_mode": "blank_template"},
        ctx=CTX,
    )


async def _seed_section_content(db, cv_id, section_type, items) -> uuid.UUID:
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    target = next(s for s in sections if s.section_type == section_type)
    target.content_json = {"items": items}
    await db.commit()
    return target.id


async def _seed_entry_content(db, cv_id, section_type, entries) -> uuid.UUID:
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    target = next(s for s in sections if s.section_type == section_type)
    target.content_json = {"entries": entries}
    await db.commit()
    return target.id


class _FakeJsonProvider:
    """A fake provider returning a fixed JSON completion (no network)."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def complete(self, *args, **kwargs):
        return AICompletion(text=json.dumps(self._payload), model_alias="fake")


def _patch_provider(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr("app.ai.cv.llm.get_provider", lambda: _FakeJsonProvider(payload))


# --------------------------------------------------------------------------- #
# Happy path: update an existing item                                         #
# --------------------------------------------------------------------------- #


async def test_edit_command_produces_pending_diff_without_mutating_cv(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await _seed_section_content(
        db_session, cv["id"], "summary", [{"text": "junior dev"}]
    )
    seeded = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    version_before = seeded["version"]

    _patch_provider(
        monkeypatch,
        {
            "operations": [
                {
                    "op": "update_item_text",
                    "section_type": "summary",
                    "item_index": 0,
                    "text": "Data analyst intern candidate",
                }
            ],
            "explanation": "Updated the summary for data analyst roles.",
        },
    )

    res = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={
            "instruction": "make this summary more suitable for data analyst roles",
            "idempotency_key": new_key(),
        },
        ctx=CTX,
    )
    assert res["status"] == "pending"
    assert res["task_type"] == "ai_edit_command"
    assert res["diff"]["applicable"] is True
    assert res["diff"]["requires_fact_confirmation"] is True
    after_items = res["diff"]["after"]["sections"][0]["content"]["items"]
    assert after_items[0]["text"] == "Data analyst intern candidate"
    _assert_no_leak(res)

    # NEVER mutates the CV on request.
    cv_now = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    assert cv_now["version"] == version_before
    summary = next(s for s in cv_now["sections"] if s["section_type"] == "summary")
    assert summary["content"]["items"][0]["text"] == "junior dev"


async def test_edit_command_accept_creates_version_and_audit(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await _seed_section_content(db_session, cv["id"], "summary", [{"text": "junior dev"}])
    before = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    versions_before = len(before["versions"])

    _patch_provider(
        monkeypatch,
        {
            "operations": [
                {
                    "op": "update_item_text",
                    "section_type": "summary",
                    "item_index": 0,
                    "text": "Data analyst intern candidate",
                }
            ],
            "explanation": "Updated the summary.",
        },
    )
    sug = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "tailor for data analyst", "idempotency_key": new_key()},
        ctx=CTX,
    )
    accepted = await cv_ai_service.accept_suggestion(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        suggestion_id=uuid.UUID(sug["suggestion_id"]),
        payload={"fact_confirmation": True, "idempotency_key": new_key()},
        ctx=CTX,
    )
    assert len(accepted["versions"]) == versions_before + 1
    assert accepted["versions"][0]["change_source"] == "ai_suggestion"
    summary = next(s for s in accepted["sections"] if s["section_type"] == "summary")
    assert summary["content"]["items"][0]["text"] == "Data analyst intern candidate"
    assert await _audit_count(db_session, "cv.ai_edit_command.requested") == 1
    assert await _audit_count(db_session, "cv.ai_suggestion.accepted") == 1


async def test_edit_command_reject_leaves_cv_unchanged(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await _seed_section_content(db_session, cv["id"], "summary", [{"text": "junior dev"}])

    _patch_provider(
        monkeypatch,
        {
            "operations": [
                {"op": "update_item_text", "section_type": "summary", "item_index": 0,
                 "text": "Something else"}
            ],
            "explanation": "x",
        },
    )
    sug = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "change it", "idempotency_key": new_key()}, ctx=CTX,
    )
    rejected = await cv_ai_service.reject_suggestion(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        suggestion_id=uuid.UUID(sug["suggestion_id"]), ctx=CTX,
    )
    assert rejected["status"] == "rejected"
    cv_now = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    summary = next(s for s in cv_now["sections"] if s["section_type"] == "summary")
    assert summary["content"]["items"][0]["text"] == "junior dev"


# --------------------------------------------------------------------------- #
# Entry-based sections (experience/education/projects) — B-595                  #
# --------------------------------------------------------------------------- #


_ENTRIES = [
    {"heading": "Intern", "subheading": "Acme", "timeframe": "2023",
     "location": "", "note": "", "highlights": ["Built APIs", "Wrote tests"]},
    {"heading": "Analyst", "subheading": "Beta", "timeframe": "2022",
     "location": "", "note": "", "highlights": ["Analysed data"]},
]


async def test_edit_command_updates_entry_highlight_pending_then_accept(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await _seed_entry_content(db_session, cv["id"], "experience",
                              [dict(e, highlights=list(e["highlights"])) for e in _ENTRIES])
    before = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    versions_before = len(before["versions"])

    _patch_provider(
        monkeypatch,
        {
            "operations": [
                {"op": "update_highlight", "section_type": "experience",
                 "entry_index": 0, "highlight_index": 0,
                 "text": "Built REST APIs with FastAPI"}
            ],
            "explanation": "Made the first experience bullet more specific.",
        },
    )
    sug = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "rewrite my first experience bullet",
                 "idempotency_key": new_key()},
        ctx=CTX,
    )
    assert sug["diff"]["applicable"] is True
    after_entries = sug["diff"]["after"]["sections"][0]["content"]["entries"]
    assert after_entries[0]["highlights"][0] == "Built REST APIs with FastAPI"
    assert after_entries[0]["highlights"][1] == "Wrote tests"  # untouched
    _assert_no_leak(sug)

    # Nothing is mutated before accept.
    mid = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    exp = next(s for s in mid["sections"] if s["section_type"] == "experience")
    assert exp["content"]["entries"][0]["highlights"][0] == "Built APIs"

    # Accepting applies the entry diff and creates a new version.
    accepted = await cv_ai_service.accept_suggestion(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        suggestion_id=uuid.UUID(sug["suggestion_id"]),
        payload={"fact_confirmation": True, "idempotency_key": new_key()}, ctx=CTX,
    )
    assert len(accepted["versions"]) == versions_before + 1
    exp2 = next(s for s in accepted["sections"] if s["section_type"] == "experience")
    assert exp2["content"]["entries"][0]["highlights"][0] == "Built REST APIs with FastAPI"


async def test_edit_command_reorders_entries(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await _seed_entry_content(db_session, cv["id"], "experience",
                              [dict(e, highlights=list(e["highlights"])) for e in _ENTRIES])

    _patch_provider(
        monkeypatch,
        {
            "operations": [
                {"op": "reorder_entries", "section_type": "experience", "order": [1, 0]}
            ],
            "explanation": "Moved the most recent role to the top.",
        },
    )
    sug = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "put my analyst role first", "idempotency_key": new_key()},
        ctx=CTX,
    )
    assert sug["diff"]["applicable"] is True
    headings = [e["heading"] for e in sug["diff"]["after"]["sections"][0]["content"]["entries"]]
    assert headings == ["Analyst", "Intern"]


# --------------------------------------------------------------------------- #
# Reorder operation                                                            #
# --------------------------------------------------------------------------- #


async def test_edit_command_reorders_sections(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await _seed_section_content(db_session, cv["id"], "projects", [{"text": "built a thing"}])
    await _seed_section_content(db_session, cv["id"], "experience", [{"text": "worked somewhere"}])

    _patch_provider(
        monkeypatch,
        {
            "operations": [
                {"op": "reorder_sections", "order": ["projects", "experience"]},
            ],
            "explanation": "Moved projects above experience.",
        },
    )
    res = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={
            "instruction": "move projects above experience for this internship",
            "idempotency_key": new_key(),
        },
        ctx=CTX,
    )
    after = {s["section_type"]: s["sort_order"] for s in res["diff"]["after"]["sections"]}
    assert after["projects"] < after["experience"]


# --------------------------------------------------------------------------- #
# Unmappable / malformed model response degrades gracefully                    #
# --------------------------------------------------------------------------- #


async def test_edit_command_unmappable_request_not_applicable(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)

    _patch_provider(
        monkeypatch, {"operations": [], "explanation": "This request is not CV-related."}
    )
    res = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "what's the weather today", "idempotency_key": new_key()},
        ctx=CTX,
    )
    assert res["diff"]["applicable"] is False
    with pytest.raises(SuggestionNotApplicableError):
        await cv_ai_service.accept_suggestion(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            suggestion_id=uuid.UUID(res["suggestion_id"]),
            payload={"fact_confirmation": True}, ctx=CTX,
        )


async def test_edit_command_unknown_section_type_dropped(db_session, monkeypatch) -> None:
    # The model is never trusted: an operation naming a section that does not
    # exist on THIS CV is silently dropped, never injected as a new section.
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)

    _patch_provider(
        monkeypatch,
        {
            "operations": [
                {"op": "update_item_text", "section_type": "not_a_real_section",
                 "item_index": 0, "text": "hacked"},
            ],
            "explanation": "x",
        },
    )
    res = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "hack it", "idempotency_key": new_key()}, ctx=CTX,
    )
    assert res["diff"]["applicable"] is False
    blob = json.dumps(res)
    assert "hacked" not in blob


# --------------------------------------------------------------------------- #
# Required-input validation                                                    #
# --------------------------------------------------------------------------- #


async def test_edit_command_requires_instruction(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(AiSourceRequiredError):
        await cv_ai_service.request_edit_command(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={"instruction": "   "}, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Idempotent request                                                           #
# --------------------------------------------------------------------------- #


async def test_edit_command_is_idempotent(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await _seed_section_content(db_session, cv["id"], "summary", [{"text": "hello"}])
    _patch_provider(
        monkeypatch,
        {
            "operations": [
                {"op": "update_item_text", "section_type": "summary", "item_index": 0,
                 "text": "Hi there"}
            ],
            "explanation": "x",
        },
    )
    key = new_key()
    r1 = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "polish it", "idempotency_key": key}, ctx=CTX,
    )
    r2 = await cv_ai_service.request_edit_command(
        db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
        payload={"instruction": "polish it", "idempotency_key": key}, ctx=CTX,
    )
    assert r1["suggestion_id"] == r2["suggestion_id"]


# --------------------------------------------------------------------------- #
# Fallback: provider unavailable -> AI_UNAVAILABLE (no stack trace)            #
# --------------------------------------------------------------------------- #


async def test_edit_command_provider_unavailable_returns_ai_unavailable(
    db_session, monkeypatch
) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)

    class _BrokenProvider:
        async def complete(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr("app.ai.cv.llm.get_provider", lambda: _BrokenProvider())

    with pytest.raises(AIUnavailableError):
        await cv_ai_service.request_edit_command(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={"instruction": "polish it", "idempotency_key": new_key()}, ctx=CTX,
        )


async def test_edit_command_malformed_json_returns_ai_unavailable(db_session, monkeypatch) -> None:
    class _GarbageProvider:
        async def complete(self, *a, **k):
            return AICompletion(text="not json at all", model_alias="fake")

    monkeypatch.setattr("app.ai.cv.llm.get_provider", lambda: _GarbageProvider())
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(AIUnavailableError):
        await cv_ai_service.request_edit_command(
            db_session, principal=student, cv_id=uuid.UUID(cv["id"]),
            payload={"instruction": "polish it", "idempotency_key": new_key()}, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Ownership: cross-owner returns 404                                          #
# --------------------------------------------------------------------------- #


async def test_edit_command_cross_owner_404(db_session, monkeypatch) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    cv = await _make_cv(db_session, student)
    _patch_provider(monkeypatch, {"operations": [], "explanation": "x"})
    with pytest.raises(ResourceNotFoundError):
        await cv_ai_service.request_edit_command(
            db_session, principal=other, cv_id=uuid.UUID(cv["id"]),
            payload={"instruction": "polish it", "idempotency_key": new_key()}, ctx=CTX,
        )
