"""``cv_profiles.matching_json`` is populated on commit and consumed by job-fit
as a determinism-preserving fast path (B-596).

The stored matching snapshot is a version-stamped, LOSSLESS projection of the
sections the deterministic scorer consumes. ``job_fit_service._build_cv_input``
reuses it while fresh, so these tests prove:

- finalize + upload-import both populate a version-stamped snapshot;
- the fast-path ``CvInput`` is byte-identical to a live section load, so the
  deterministic score/bands are unchanged (the paramount contract);
- a STALE snapshot (version bumped by an edit) is never used — the fast path
  falls back to a live section load.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from app.ai.cv import job_fit
from app.core.config import get_settings
from app.modules.documents.application import (
    cv_lifecycle_service,
    cv_service,
    ingestion_service,
    job_fit_service,
    template_seed,
)
from app.modules.documents.domain.models import CvProfile
from app.modules.documents.infrastructure import storage
from sqlalchemy import select

from tests.auth_utils import CTX
from tests.documents_utils import InMemoryStorage, make_student, new_key
from tests.fixtures import cv as F

# A representative JD so the parity assertion exercises several scoring bands.
_JOB = {
    "id": str(uuid.uuid4()),
    "title": "Backend Engineer Intern",
    "description": "Build REST APIs with Python and PostgreSQL.",
    "requirements": "Python, FastAPI, SQL, REST APIs.",
    "required_skills": ["Python", "FastAPI", "SQL"],
    "preferred_skills": ["PostgreSQL", "Docker"],
    "experience_mode": "fresher",
    "version": 1,
}


async def _load_cv(db, cv_id: uuid.UUID) -> CvProfile:
    return (
        await db.execute(select(CvProfile).where(CvProfile.id == cv_id))
    ).scalar_one()


async def _rich_ready_cv(db, student) -> uuid.UUID:
    """Create + finalize a CV with header, leveled skills, and an experience entry."""

    cv = await cv_service.create_cv(
        db, principal=student,
        payload={"title": "Backend CV", "creation_mode": "blank_template"}, ctx=CTX,
    )
    cv_id = uuid.UUID(cv["id"])
    by_type = {s["section_type"]: s for s in cv["sections"]}
    version = cv["version"]

    async def _seed(section_type: str, content: dict) -> None:
        nonlocal version
        await cv_service.upsert_section(
            db, principal=student, cv_id=cv_id,
            section_id=uuid.UUID(by_type[section_type]["id"]),
            payload={"content": content, "expected_version": version}, ctx=CTX,
        )
        version += 1

    await _seed("header", {"name": "Le Van B", "email": "b@example.com"})
    await _seed("skills", {"items": [{"name": "Python", "level": 90},
                                     {"name": "FastAPI", "level": 70},
                                     {"name": "SQL", "level": 60}]})
    await _seed("experience", {"entries": [
        {"heading": "Backend Intern", "subheading": "Example Tech",
         "timeframe": "2024 - 2025",
         "highlights": ["Built REST APIs with FastAPI and PostgreSQL"]},
    ]})
    await cv_lifecycle_service.finalize_cv(db, principal=student, cv_id=cv_id, ctx=CTX)
    return cv_id


# --------------------------------------------------------------------------- #
# Finalize populates the snapshot; the fast path matches a live load exactly   #
# --------------------------------------------------------------------------- #


async def test_fast_path_cv_input_matches_live_load(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _rich_ready_cv(db_session, student)
    cv = await _load_cv(db_session, cv_id)
    now = datetime.now(tz=UTC)

    # A committed CV has a fresh snapshot -> fast path.
    assert isinstance(cv.matching_json, dict)
    assert cv.matching_json["content_version"] == cv.version
    fast = await job_fit_service._build_cv_input(db_session, cv=cv, now=now)

    # Drop the snapshot -> forces the live section-load path.
    cv.matching_json = None
    await db_session.flush()
    live = await job_fit_service._build_cv_input(db_session, cv=cv, now=now)

    # The two inputs are byte-identical, so the scorer cannot tell them apart.
    assert fast.cv_id == live.cv_id
    assert fast.title == live.title
    assert fast.language == live.language
    assert fast.sections == live.sections
    assert fast.last_updated_days == live.last_updated_days

    # ...and therefore the deterministic score + bands are identical.
    fast_fit = job_fit.evaluate(_JOB, [fast], stale_days=30).results[0]
    live_fit = job_fit.evaluate(_JOB, [live], stale_days=30).results[0]
    assert fast_fit.score == live_fit.score
    assert fast_fit.bands.as_dict() == live_fit.bands.as_dict()
    assert fast_fit.matched_skills == live_fit.matched_skills
    assert fast_fit.gaps == live_fit.gaps


# --------------------------------------------------------------------------- #
# A STALE snapshot (version bumped by an edit) is never used                    #
# --------------------------------------------------------------------------- #


async def test_stale_snapshot_falls_back_to_live_sections(db_session) -> None:
    _u, student = await make_student(db_session)
    cv_id = await _rich_ready_cv(db_session, student)
    cv = await _load_cv(db_session, cv_id)
    now = datetime.now(tz=UTC)

    # Poison the snapshot with a marker section but keep content_version fresh:
    # the fast path SHOULD trust it (proving the fast path is actually taken).
    marker = [{"section_type": "summary", "title": "M", "content": {"items": [{"text": "MARKER"}]}}]
    cv.matching_json = {
        "schema_version": cv_lifecycle_service.MATCHING_SCHEMA_VERSION,
        "content_version": cv.version,
        "sections": marker,
        "last_activity_at": now.isoformat(),
    }
    await db_session.flush()
    used_fast = await job_fit_service._build_cv_input(db_session, cv=cv, now=now)
    assert used_fast.sections == marker  # fast path was taken

    # Now simulate an edit: bump the version so the snapshot is STALE. The fast path
    # must be skipped and the LIVE sections used (never the poisoned marker).
    cv.version += 1
    await db_session.flush()
    used_live = await job_fit_service._build_cv_input(db_session, cv=cv, now=now)
    assert used_live.sections != marker
    section_types = {s["section_type"] for s in used_live.sections}
    assert "experience" in section_types and "skills" in section_types


# --------------------------------------------------------------------------- #
# Upload-import also lands matching-ready                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def _sync_storage():
    storage.set_storage(InMemoryStorage())
    os.environ["CV_INGESTION_ASYNC"] = "false"
    get_settings.cache_clear()
    yield
    storage.set_storage(None)
    os.environ.pop("CV_INGESTION_ASYNC", None)
    get_settings.cache_clear()


async def test_upload_import_populates_matching_snapshot(db_session, _sync_storage) -> None:
    await template_seed.ensure_default_templates(db_session)
    await db_session.commit()
    _u, student = await make_student(db_session)

    up = await ingestion_service.create_upload(
        db_session, principal=student, filename="cv.pdf", data=F.text_pdf_en(),
        content_type="application/pdf", idempotency_key=new_key(), ctx=CTX,
    )
    ing = await ingestion_service.start_ingestion(
        db_session, principal=student, document_id=uuid.UUID(up["document_id"]), ctx=CTX,
    )
    detail = await ingestion_service.import_ingestion(
        db_session, principal=student, ingestion_id=uuid.UUID(ing["ingestion_id"]),
        payload={"title": "Uploaded CV"}, ctx=CTX,
    )
    cv = await _load_cv(db_session, uuid.UUID(detail["id"]))
    assert isinstance(cv.matching_json, dict)
    assert cv.matching_json["content_version"] == cv.version
    assert isinstance(cv.matching_json["sections"], list) and cv.matching_json["sections"]
    assert cv.matching_json["last_activity_at"]

    # And the fast path still matches a live load for the imported CV.
    now = datetime.now(tz=UTC)
    fast = await job_fit_service._build_cv_input(db_session, cv=cv, now=now)
    cv.matching_json = None
    await db_session.flush()
    live = await job_fit_service._build_cv_input(db_session, cv=cv, now=now)
    assert fast.sections == live.sections
    assert fast.last_updated_days == live.last_updated_days
