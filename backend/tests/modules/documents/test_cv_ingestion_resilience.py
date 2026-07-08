"""End-to-end CV ingestion resilience + metering (offline; no real model calls).

Drives the real ``ingestion_service.start_ingestion`` path (async inline worker)
and asserts the WS-9 contract holds through the whole stack:

- native-text CVs extract OFFLINE and are FREE (no energy charged);
- a scan with AI absent degrades to a user-safe status without fabricating a CV
  and without charging;
- blank / not-CV / corrupt reject cleanly, never fabricated, never charged;
- a student who is OUT of AI energy can still upload: native text still extracts
  (free); a scan returns a retryable ``ai_unavailable`` state, no charge, no leak.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from app.ai.energy.models import SCOPE_USER, AiEnergyAccount
from app.ai.observability.billable_usage import (
    FEATURE_CV_EXTRACTION,
    AiBillableUsage,
)
from app.modules.documents.application import ingestion_service
from app.modules.documents.domain.models import CvIngestion
from app.modules.documents.infrastructure import storage
from sqlalchemy import func, select
from tests.auth_utils import CTX
from tests.documents_utils import InMemoryStorage, make_student, new_key
from tests.fixtures import cv as F


@pytest.fixture(autouse=True)
def _isolated_storage():
    storage.set_storage(InMemoryStorage())
    yield
    storage.set_storage(None)


async def _upload(db, student, *, filename, data, content_type="application/pdf"):
    return await ingestion_service.create_upload(
        db, principal=student, filename=filename, data=data,
        content_type=content_type, idempotency_key=new_key(), ctx=CTX,
    )


async def _ingest(db, student, document_id):
    return await ingestion_service.start_ingestion(
        db, principal=student, document_id=uuid.UUID(document_id), ctx=CTX,
    )


async def _cv_charges(db, user_id) -> int:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id,
                AiBillableUsage.feature_key == FEATURE_CV_EXTRACTION,
            )
        )
    ).scalar_one()
    return int(total or 0)


async def _cv_rows(db, user_id) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(AiBillableUsage).where(
                    AiBillableUsage.actor_user_id == user_id,
                    AiBillableUsage.feature_key == FEATURE_CV_EXTRACTION,
                )
            )
        ).scalar_one()
    )


async def _ingestion_row(db, ingestion_id) -> CvIngestion:
    return (
        await db.execute(
            select(CvIngestion).where(CvIngestion.id == uuid.UUID(ingestion_id))
        )
    ).scalar_one()


async def _exhaust_energy(db, user_id) -> None:
    """Seed the student's user scope so the weekly hard gate is exhausted."""
    db.add(
        AiEnergyAccount(
            scope_type=SCOPE_USER, scope_id=user_id,
            weekly_allowance_units=1, wallet_units=0,
        )
    )
    db.add(
        AiBillableUsage(
            actor_user_id=user_id, actor_persona="student", billing_scope=SCOPE_USER,
            feature_key="chatbot", task_type="chatbot", units_charged=5,
            result_status="success", created_at=datetime.now(UTC),
        )
    )
    await db.commit()


# --------------------------------------------------------------------------- #
# Offline (AI absent): native text works free; scans/rejects never charge       #
# --------------------------------------------------------------------------- #


async def test_native_text_extracts_offline_and_is_free(db_session) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(db_session, student, filename="cv.pdf", data=F.text_pdf_en())
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["status"] in ("needs_review", "ready")
    assert ing["quality_code"] == "REVIEW_REQUIRED"
    # Deterministic native-text tier is free — no CV-extraction credits charged.
    assert await _cv_rows(db_session, student.user_id) == 0


async def test_scan_without_ai_degrades_safely_and_free(db_session) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(
        db_session, student, filename="scan.png", data=F.scanned_image_cv(),
        content_type="image/png",
    )
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["status"] == "failed"
    assert ing["quality_code"] == "LOW_QUALITY_SCAN"
    assert ing["quality_message"]  # user-safe copy present
    # No fabricated CV; no charge.
    row = await _ingestion_row(db_session, ing["ingestion_id"])
    assert row.extracted_data is None
    assert await _cv_rows(db_session, student.user_id) == 0


@pytest.mark.parametrize(
    ("filename", "builder", "expected"),
    [
        ("blank.pdf", F.blank_pdf, "BLANK_DOCUMENT"),
        ("notes.pdf", F.not_cv_pdf, "NOT_A_CV"),
        ("broken.pdf", F.corrupt_pdf, "CORRUPT_FILE"),
    ],
)
async def test_hard_rejects_never_charge_or_fabricate(
    db_session, filename, builder, expected
) -> None:
    _u, student = await make_student(db_session)
    up = await _upload(db_session, student, filename=filename, data=builder())
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["status"] == "failed"
    assert ing["quality_code"] == expected
    row = await _ingestion_row(db_session, ing["ingestion_id"])
    assert row.extracted_data is None
    assert await _cv_rows(db_session, student.user_id) == 0


# --------------------------------------------------------------------------- #
# Out of AI energy: upload still succeeds, native text still free, scan pending  #
# --------------------------------------------------------------------------- #


async def test_energy_exhausted_native_text_still_extracts_free(db_session) -> None:
    _u, student = await make_student(db_session)
    await _exhaust_energy(db_session, student.user_id)
    up = await _upload(db_session, student, filename="cv.pdf", data=F.text_pdf_en())
    ing = await _ingest(db_session, student, up["document_id"])
    # A free native-text extraction is NOT blocked by energy exhaustion.
    assert ing["status"] in ("needs_review", "ready")
    assert ing["quality_code"] == "REVIEW_REQUIRED"
    assert await _cv_charges(db_session, student.user_id) == 0


async def test_energy_exhausted_scan_is_ai_unavailable_no_charge(db_session) -> None:
    _u, student = await make_student(db_session)
    await _exhaust_energy(db_session, student.user_id)
    up = await _upload(
        db_session, student, filename="scan.png", data=F.scanned_image_cv(),
        content_type="image/png",
    )
    ing = await _ingest(db_session, student, up["document_id"])
    # Paid tier withheld → retryable "extraction pending", not a hard failure.
    assert ing["status"] == "ai_unavailable"
    assert ing["quality_code"] == "EXTRACTION_PENDING_AI"
    assert ing["quality_message"]
    assert "retry_extraction" in ing["next_actions"]
    # No fabrication; nothing charged for a withheld extraction.
    row = await _ingestion_row(db_session, ing["ingestion_id"])
    assert row.extracted_data is None
    assert await _cv_rows(db_session, student.user_id) == 0
    # No provider/model/internal leak in the user-facing payload.
    blob = json.dumps(ing).lower()
    for needle in ("openrouter", "gemini", "provider", "token", "httpx", "vision_llm"):
        assert needle not in blob, needle


async def test_energy_exhausted_upload_never_hard_500s(db_session) -> None:
    # The whole point: metering degradation returns a status, never raises.
    _u, student = await make_student(db_session)
    await _exhaust_energy(db_session, student.user_id)
    up = await _upload(db_session, student, filename="cv.pdf", data=F.text_pdf_en())
    ing = await _ingest(db_session, student, up["document_id"])
    assert ing["status"] in ("needs_review", "ready", "ai_unavailable", "failed")
