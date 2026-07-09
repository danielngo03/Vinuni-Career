"""Recruitment apply-flow hardening tests.

Two backlog items:

- **B-603** — real anonymous-apply CV redaction. The anonymous partner PRE-REVEAL
  snapshot copy (``ApplicationCvSnapshot.redacted_json``) must strip identifying
  PII (header contact + inline email/phone patterns) while PRESERVING the evaluable
  professional content (skills, experience headings/bullets, education). The
  ORIGINAL immutable ``snapshot_json`` stays un-redacted so an accepted reveal still
  exposes the true identity. Non-anonymous applications are never redacted.
- **B-593** — a concurrent apply race (two requests with DIFFERENT idempotency keys
  hitting the ``(job, applicant)`` unique-active index) returns a clean ``409``
  (``DuplicateApplicationError``), never a raw ``500``.
"""

from __future__ import annotations

import json
import uuid

import pytest
from app.modules.documents.domain.models import ApplicationCvSnapshot
from app.modules.recruitment.application import apply_service, reveal_service
from app.modules.recruitment.application.apply_service import (
    _redact_snapshot,
    _scrub_pii_text,
)
from app.modules.recruitment.application.errors import DuplicateApplicationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import apply_payload, make_builder_cv, publish_job


async def _setup_published(db, *, title="Live Job", **over):
    _pu, _porg, partner = await make_org_with_admin(db, display_name="Partner Co")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title=title, **over
    )
    return partner, uni, job_id


# --------------------------------------------------------------------------- #
# B-603 — pure redaction (header + entries + text + skills shapes)            #
# --------------------------------------------------------------------------- #


def _rich_snapshot() -> dict:
    """A builder-CV snapshot carrying identity + evaluable content in every shape."""

    return {
        "title": "Nguyen Van A - CV",
        "language": "vi",
        "source_type": "blank_template",
        "canvas": {},
        "sections": [
            {
                "section_type": "header",
                "title": "Header",
                "is_visible": True,
                "content_json": {
                    "name": "Nguyen Van A",
                    "headline": "Backend Engineer",
                    "email": "nguyen.van.a@example.com",
                    "phone": "+84 912 345 678",
                    "location": "Hanoi, Vietnam",
                    "links": [
                        {"label": "github.com/realperson", "url": "https://github.com/realperson"}
                    ],
                },
            },
            {
                "section_type": "summary",
                "title": "Summary",
                "is_visible": True,
                "content_json": {
                    "text": "Backend engineer. Reach me at nguyen.van.a@example.com "
                    "or 0987 654 321."
                },
            },
            {
                "section_type": "experience",
                "title": "Experience",
                "is_visible": True,
                "content_json": {
                    "entries": [
                        {
                            "heading": "Software Intern",
                            "subheading": "Example Tech",
                            "timeframe": "2024 - 2025",
                            "location": "Hanoi",
                            "highlights": [
                                "Built REST APIs with FastAPI and PostgreSQL.",
                                "Direct line 0912345678 / nguyen.van.a@example.com",
                            ],
                        }
                    ]
                },
            },
            {
                "section_type": "skills",
                "title": "Skills",
                "is_visible": True,
                "content_json": {
                    "items": [{"name": "Python", "level": 85}, {"name": "FastAPI", "level": 70}]
                },
            },
        ],
    }


def test_redact_snapshot_strips_pii_but_keeps_evaluable_content() -> None:
    original = _rich_snapshot()
    out = _redact_snapshot(original)

    # The ORIGINAL immutable snapshot is never mutated (reveal serves this).
    assert original["title"] == "Nguyen Van A - CV"
    assert original["sections"][0]["content_json"]["email"] == "nguyen.van.a@example.com"

    blob = json.dumps(out, ensure_ascii=False)
    # No identifying PII survives anywhere in the redacted copy.
    assert "Nguyen Van A" not in blob
    assert "nguyen.van.a@example.com" not in blob
    assert "0912345678" not in blob
    assert "912 345 678" not in blob
    assert "987 654 321" not in blob
    assert "github.com/realperson" not in blob
    assert "Hanoi, Vietnam" not in blob  # header location removed
    assert out["title"] == "[Ẩn danh]"
    assert out["redacted"] is True

    # Header: contact block removed, anonymous label + professional headline kept.
    header = next(s for s in out["sections"] if s["section_type"] == "header")["content_json"]
    assert header["name"] == "[Ẩn danh]"
    for field in ("email", "phone", "location", "links"):
        assert field not in header
    assert header["headline"] == "Backend Engineer"

    # Free text (summary): PII scrubbed, professional text preserved.
    summary = next(s for s in out["sections"] if s["section_type"] == "summary")["content_json"]
    assert "Backend engineer." in summary["text"]
    assert "@" not in summary["text"]

    # Experience entry: heading/subheading/date range + non-PII bullet preserved,
    # PII inside a highlight scrubbed.
    exp = next(s for s in out["sections"] if s["section_type"] == "experience")["content_json"]
    entry = exp["entries"][0]
    assert entry["heading"] == "Software Intern"
    assert entry["subheading"] == "Example Tech"
    assert entry["timeframe"] == "2024 - 2025"  # date range NOT mistaken for a phone
    assert entry["location"] == "Hanoi"  # job location (not the person's) kept
    assert any("Built REST APIs with FastAPI" in h for h in entry["highlights"])
    joined = " ".join(entry["highlights"])
    assert "0912345678" not in joined and "@" not in joined

    # Skills: names + numeric levels (evaluable) preserved untouched.
    skills = next(s for s in out["sections"] if s["section_type"] == "skills")["content_json"]
    assert {i["name"]: i["level"] for i in skills["items"]} == {"Python": 85, "FastAPI": 70}


def test_redact_snapshot_is_idempotent_and_deterministic() -> None:
    once = _redact_snapshot(_rich_snapshot())
    twice = _redact_snapshot(once)
    assert twice == once
    # Deterministic: same input -> same output.
    assert _redact_snapshot(_rich_snapshot()) == once


def test_redact_snapshot_uploaded_document_shape() -> None:
    # Uploaded-CV snapshot: no header section; title is the original file name.
    snapshot = {
        "title": "Le Thi B CV.pdf",
        "source_type": "uploaded",
        "document_id": str(uuid.uuid4()),
        "sections": [
            {
                "title": "Experience",
                "content_json": {
                    "items": [{"text": "Data intern. Reach b.le@example.com / 0901234567."}]
                },
            }
        ],
    }
    out = _redact_snapshot(snapshot)
    assert out["title"] == "[Ẩn danh]"
    text = out["sections"][0]["content_json"]["items"][0]["text"]
    assert "Data intern." in text
    assert "b.le@example.com" not in text
    assert "0901234567" not in text


def test_scrub_preserves_dates_gpa_and_scrubs_phones() -> None:
    # False-positive guard: dates, GPA, percentages, short digit runs survive.
    for keep in ("2020 - 2023", "01/2020 - 12/2023", "GPA 3.8/4.0", "Top 10%", "5 years"):
        assert _scrub_pii_text(keep) == keep
    # Real phone numbers (>= 9 digits) are scrubbed; surrounding text preserved.
    for phone in ("0912345678", "+84 912 345 678", "0912-345-678", "0912 345 678"):
        assert _scrub_pii_text(f"call {phone} today") == "call [đã ẩn] today"
    # A parenthesised country code still has all its digits removed.
    scrubbed = _scrub_pii_text("(+84) 912 345 678")
    assert not any(ch.isdigit() for ch in scrubbed)


# --------------------------------------------------------------------------- #
# B-603 — integration: anonymous stores redacted copy, original stays intact  #
# --------------------------------------------------------------------------- #


async def _make_cv_with_pii(session, *, student) -> dict:
    """Build + finalize a builder CV whose header/experience/summary carry real PII."""

    from app.modules.documents.application import cv_lifecycle_service, cv_service

    cv = await cv_service.create_cv(
        session,
        principal=student,
        payload={"title": "Real Candidate - CV", "creation_mode": "blank_template"},
        ctx=CTX,
    )
    cv_id = uuid.UUID(cv["id"])
    by_type = {s["section_type"]: s for s in cv["sections"]}
    version = cv["version"]

    async def _upsert(section_type: str, content: dict) -> None:
        nonlocal version
        detail = await cv_service.upsert_section(
            session,
            principal=student,
            cv_id=cv_id,
            section_id=uuid.UUID(by_type[section_type]["id"]),
            payload={"content": content, "expected_version": version},
            ctx=CTX,
        )
        version = detail["cv_version"]

    await _upsert(
        "header",
        {
            "name": "Real Candidate Name",
            "headline": "Backend Engineer",
            "email": "real.person@example.com",
            "phone": "+84 912 345 678",
            "location": "Hanoi, Vietnam",
            "links": [{"label": "github.com/realperson", "url": "https://github.com/realperson"}],
        },
    )
    await _upsert(
        "summary",
        {"text": "Backend engineer. Reach me at real.person@example.com or 0912 345 678."},
    )
    await _upsert(
        "experience",
        {
            "entries": [
                {
                    "heading": "Software Intern",
                    "subheading": "Example Tech",
                    "timeframe": "2024 - 2025",
                    "location": "Hanoi",
                    "highlights": [
                        "Built REST APIs with FastAPI and PostgreSQL.",
                        "Direct line 0912345678 / real.person@example.com",
                    ],
                }
            ]
        },
    )
    await _upsert(
        "skills", {"items": [{"name": "Python", "level": 85}, {"name": "FastAPI", "level": 70}]}
    )

    detail = await cv_lifecycle_service.finalize_cv(
        session, principal=student, cv_id=cv_id, ctx=CTX
    )
    return {
        "type": "builder_cv",
        "cv_profile_id": detail["id"],
        "cv_version_id": detail["current_version_id"],
        "uploaded_document_id": None,
    }


async def _load_snapshot(db, snapshot_id: str) -> ApplicationCvSnapshot:
    return (
        await db.execute(
            select(ApplicationCvSnapshot).where(ApplicationCvSnapshot.id == uuid.UUID(snapshot_id))
        )
    ).scalar_one()


async def test_anonymous_apply_stores_redacted_snapshot_copy(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await _make_cv_with_pii(db_session, student=student)

    out = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    snap = await _load_snapshot(db_session, out["snapshot_id"])

    # The ORIGINAL immutable snapshot still carries the true identity (reveal serves
    # this un-redacted copy).
    original = json.dumps(snap.snapshot_json, ensure_ascii=False)
    assert "Real Candidate Name" in original
    assert "real.person@example.com" in original
    assert "0912" in original

    # A redacted partner-preview copy exists and leaks no identifying PII.
    assert snap.redacted_json is not None
    redacted = json.dumps(snap.redacted_json, ensure_ascii=False)
    assert "Real Candidate Name" not in redacted
    assert "real.person@example.com" not in redacted
    assert "0912345678" not in redacted
    assert "912 345 678" not in redacted
    assert "github.com/realperson" not in redacted

    header = next(s for s in snap.redacted_json["sections"] if s["section_type"] == "header")[
        "content_json"
    ]
    assert header["name"] == "[Ẩn danh]"
    for field in ("email", "phone", "location", "links"):
        assert field not in header

    # Evaluable professional content is preserved for the partner to assess.
    assert "Software Intern" in redacted
    assert "Example Tech" in redacted
    assert "Built REST APIs with FastAPI" in redacted
    skills = next(s for s in snap.redacted_json["sections"] if s["section_type"] == "skills")[
        "content_json"
    ]
    assert {i["name"]: i["level"] for i in skills["items"]} == {"Python": 85, "FastAPI": 70}


async def test_non_anonymous_apply_leaves_snapshot_unredacted(db_session) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await _make_cv_with_pii(db_session, student=student)

    out = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=False),
        ctx=CTX,
    )
    snap = await _load_snapshot(db_session, out["snapshot_id"])

    # A non-anonymous application is never redacted — full content is retained.
    assert snap.redacted_json is None
    assert "Real Candidate Name" in json.dumps(snap.snapshot_json, ensure_ascii=False)


async def test_reveal_serves_unredacted_original_snapshot(db_session) -> None:
    partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await _make_cv_with_pii(db_session, student=student)

    out = await apply_service.apply_to_job(
        db_session,
        principal=student,
        payload=apply_payload(job_id=job_id, cv_selection=sel, is_anonymous=True),
        ctx=CTX,
    )
    app_id = uuid.UUID(out["id"])
    await reveal_service.request_reveal(
        db_session,
        principal=partner,
        application_id=app_id,
        reason="We would like to learn more about your internship experience.",
        ctx=CTX,
    )
    await reveal_service.respond_reveal(
        db_session, principal=student, application_id=app_id, decision="accepted", ctx=CTX
    )

    # After reveal the immutable original still holds the true identity untouched —
    # redaction was only ever applied to the separate ``redacted_json`` copy.
    snap = await _load_snapshot(db_session, out["snapshot_id"])
    assert "Real Candidate Name" in json.dumps(snap.snapshot_json, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# B-593 — concurrent apply race returns a clean 409 (not a 500)               #
# --------------------------------------------------------------------------- #


async def test_concurrent_apply_race_returns_409_not_500(db_session, monkeypatch) -> None:
    _partner, _uni, job_id = await _setup_published(db_session)
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)

    # A true race: both requests clear the in-transaction ``_active_duplicate``
    # pre-check, then the Postgres partial unique index ``uq_applications_active``
    # rejects the loser's INSERT with an IntegrityError. SQLite unit tests don't
    # carry that partial index, so we force the exact IntegrityError the DB would
    # raise on the application-insert flush (the FIRST flush in ``apply_to_job``).
    real_flush = db_session.flush
    state = {"calls": 0}

    async def flaky_flush(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise IntegrityError(
                "INSERT INTO applications ...",
                {},
                Exception("UNIQUE constraint failed: uq_applications_active"),
            )
        return await real_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", flaky_flush)

    with pytest.raises(DuplicateApplicationError) as exc:
        await apply_service.apply_to_job(
            db_session,
            principal=student,
            payload=apply_payload(job_id=job_id, cv_selection=sel),
            ctx=CTX,
        )
    # Same clean 409 the sequential-duplicate path returns — never a raw 500.
    assert exc.value.details["reason"] == "duplicate_application"
    assert exc.value.http_status == 409
