"""Chat attachment upload + AI analysis — partner-scoped, metered, leakage-safe.

Covers the first backend slice of "recruiter attaches a file/image to the AI
chat and asks the assistant to analyse it":

(a) upload creates an org-scoped ``ChatAttachment`` and returns a SAFE descriptor
    (never the storage key/path).
(b) upload rejects blank / oversized / unsupported files with a user-safe 4xx.
(c) ``analyze_attachment`` on an image returns a structured result, stores it on
    ``analysis_json``, and charges ``FEATURE_ATTACHMENT_ANALYSIS`` exactly once
    (idempotent on re-analyse).
(d) a partner cannot analyse another org's attachment (rejected, no charge).
(e) a student is rejected by dispatch RBAC for the partner-only tool.
(f) the deterministic offline path (no vision) still analyses a CSV/text file.
"""

from __future__ import annotations

import uuid

import pytest
from app.ai.energy.constants import FEATURE_ATTACHMENT_ANALYSIS
from app.ai.energy.service import charge_units
from app.ai.extraction import attachment as attachment_mod
from app.ai.observability.billable_usage import SCOPE_ORG
from app.ai.observability.models import AiBillableUsage
from app.core.config import get_settings
from app.modules.ai_assistant.application import attachment_service, chat_service
from app.modules.ai_assistant.application.tools.dispatch import dispatch_tool
from app.modules.ai_assistant.domain.models import ChatAttachment
from app.shared.exceptions import ValidationFailedError
from sqlalchemy import func, select

from tests.documents_utils import InMemoryStorage, make_student
from tests.org_utils import make_org_with_admin

# Minimal image bytes: sniff_kind reads the PNG magic -> FileKind.IMAGE. The
# analysis vision tier is faked, so real pixels are unnecessary.
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class _FakeVision:
    """A deterministic offline stand-in for the cheap vision-LLM tier."""

    @property
    def available(self) -> bool:
        return True

    def analyze(self, data, kind, *, max_image_px, max_pages, native_text=None):
        return {
            "transcript": "Doanh thu Q1: 100\nDoanh thu Q2: 200",
            "summary": "Bảng doanh thu theo quý.",
            "tables": [
                {"columns": ["Quý", "Doanh thu"], "rows": [["Q1", "100"], ["Q2", "200"]]}
            ],
            "key_values": {"Tổng": "300"},
        }


@pytest.fixture
def _attachment_env():
    """In-memory blob storage + a clean vision-adapter seam per test."""
    from app.modules.documents.infrastructure import storage as doc_storage

    doc_storage.set_storage(InMemoryStorage())
    yield
    doc_storage.set_storage(None)
    attachment_mod.set_attachment_vision_adapter(None)


async def _new_session(db, principal) -> uuid.UUID:
    created = await chat_service.create_session(db, principal=principal)
    return uuid.UUID(created["id"])


async def _upload_png(db, *, partner, session_id, name="chart.png") -> dict:
    return await attachment_service.upload_attachment(
        db,
        principal=partner,
        session_id=session_id,
        filename=name,
        data=_PNG,
        content_type="image/png",
    )


async def _count_charges(db, *, org_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(AiBillableUsage)
                .where(
                    AiBillableUsage.feature_key == FEATURE_ATTACHMENT_ANALYSIS,
                    AiBillableUsage.org_id == org_id,
                )
            )
        ).scalar_one()
    )


# --------------------------------------------------------------------------- #
# (a) upload creates an org-scoped attachment + safe descriptor                #
# --------------------------------------------------------------------------- #


async def test_upload_creates_org_scoped_attachment_safe_descriptor(
    db_session, _attachment_env
) -> None:
    _u, porg, partner = await make_org_with_admin(db_session, display_name="Att Co")
    session_id = await _new_session(db_session, partner)

    desc = await _upload_png(db_session, partner=partner, session_id=session_id)

    # Safe descriptor only — never the storage key/path or any internal field.
    assert set(desc) == {
        "id",
        "session_id",
        "filename",
        "content_type",
        "size",
        "status",
        "created_at",
    }
    assert desc["status"] == "uploaded"
    assert desc["filename"] == "chart.png"
    dumped = str(desc).lower()
    for banned in ("storage_key", "storage_path", "chat-attachments"):
        assert banned not in dumped

    row = (
        await db_session.execute(
            select(ChatAttachment).where(ChatAttachment.id == uuid.UUID(desc["id"]))
        )
    ).scalar_one()
    assert row.org_id == porg.id
    assert row.user_id == partner.user_id
    assert row.storage_key.startswith("chat-attachments/")  # stored internally only


# --------------------------------------------------------------------------- #
# (b) upload rejects blank / oversized / unsupported                           #
# --------------------------------------------------------------------------- #


async def test_upload_rejects_blank_unsupported_and_oversize(
    db_session, _attachment_env
) -> None:
    _u, _porg, partner = await make_org_with_admin(db_session, display_name="Reject Co")
    session_id = await _new_session(db_session, partner)

    with pytest.raises(ValidationFailedError):
        await attachment_service.upload_attachment(
            db_session,
            principal=partner,
            session_id=session_id,
            filename="empty.png",
            data=b"",
            content_type="image/png",
        )

    with pytest.raises(ValidationFailedError):
        await attachment_service.upload_attachment(
            db_session,
            principal=partner,
            session_id=session_id,
            filename="notes.bin",
            data=b"\x00\x01\x02junk-binary",
            content_type="application/octet-stream",
        )

    big = b"x" * (get_settings().max_upload_bytes + 1)
    with pytest.raises(ValidationFailedError):
        await attachment_service.upload_attachment(
            db_session,
            principal=partner,
            session_id=session_id,
            filename="huge.pdf",
            data=big,
            content_type="application/pdf",
        )


async def test_upload_rejects_non_owned_session(db_session, _attachment_env) -> None:
    """A partner cannot attach to a session they do not own (404)."""
    from app.shared.exceptions import ResourceNotFoundError

    _ua, _porgA, partnerA = await make_org_with_admin(db_session, display_name="Own A")
    _ub, _porgB, partnerB = await make_org_with_admin(db_session, display_name="Own B")
    session_a = await _new_session(db_session, partnerA)

    with pytest.raises(ResourceNotFoundError):
        await _upload_png(db_session, partner=partnerB, session_id=session_a)


# --------------------------------------------------------------------------- #
# (c) analyze image: structured result + stored + charged once (idempotent)    #
# --------------------------------------------------------------------------- #


async def test_analyze_image_returns_structured_result_and_charges_once(
    db_session, _attachment_env
) -> None:
    attachment_mod.set_attachment_vision_adapter(_FakeVision())
    _u, porg, partner = await make_org_with_admin(db_session, display_name="Vision Co")
    session_id = await _new_session(db_session, partner)
    desc = await _upload_png(db_session, partner=partner, session_id=session_id)
    attachment_id = desc["id"]

    r1 = await dispatch_tool(
        "analyze_attachment",
        {"attachment_id": attachment_id},
        session=db_session,
        principal=partner,
    )
    assert r1["ok"] is True
    assert r1["analyzed"] is True
    assert r1["status"] == "analyzed"
    assert r1["cached"] is False
    assert r1["kind"] == "image"
    assert r1["summary"]
    assert r1["table"]["columns"] == ["Quý", "Doanh thu"]
    assert ["Q1", "100"] in r1["table"]["rows"]
    assert r1["key_values"]["Tổng"] == "300"

    # No leakage of storage keys / provider / model / token internals.
    dumped = str(r1).lower()
    for banned in ("storage_key", "chat-attachments", "provider", "token", "prompt"):
        assert banned not in dumped

    assert await _count_charges(db_session, org_id=porg.id) == 1
    row = (
        await db_session.execute(
            select(ChatAttachment).where(ChatAttachment.id == uuid.UUID(attachment_id))
        )
    ).scalar_one()
    assert row.status == "analyzed"
    assert isinstance(row.analysis_json, dict)

    # Re-analyse the same attachment → cached, no second charge.
    r2 = await dispatch_tool(
        "analyze_attachment",
        {"attachment_id": attachment_id},
        session=db_session,
        principal=partner,
    )
    assert r2["ok"] is True
    assert r2["cached"] is True
    assert await _count_charges(db_session, org_id=porg.id) == 1

    # The single charge is org-scoped and cost-weighted.
    charge = (
        await db_session.execute(
            select(AiBillableUsage).where(
                AiBillableUsage.feature_key == FEATURE_ATTACHMENT_ANALYSIS,
                AiBillableUsage.org_id == porg.id,
            )
        )
    ).scalar_one()
    assert charge.billing_scope == SCOPE_ORG
    assert charge.units_charged == charge_units(FEATURE_ATTACHMENT_ANALYSIS) > 0
    assert charge.resource_type == "attachment"


# --------------------------------------------------------------------------- #
# (d) cross-org isolation                                                      #
# --------------------------------------------------------------------------- #


async def test_partner_cannot_analyze_other_orgs_attachment(
    db_session, _attachment_env
) -> None:
    attachment_mod.set_attachment_vision_adapter(_FakeVision())
    _ua, _porgA, partnerA = await make_org_with_admin(db_session, display_name="Org A")
    session_a = await _new_session(db_session, partnerA)
    desc = await _upload_png(db_session, partner=partnerA, session_id=session_a)

    _ub, porgB, partnerB = await make_org_with_admin(db_session, display_name="Org B")

    res = await dispatch_tool(
        "analyze_attachment",
        {"attachment_id": desc["id"]},
        session=db_session,
        principal=partnerB,
    )
    assert res == {"ok": False, "error": "not_found"}
    assert await _count_charges(db_session, org_id=porgB.id) == 0


# --------------------------------------------------------------------------- #
# (e) dispatch RBAC — student rejected for the partner-only tool               #
# --------------------------------------------------------------------------- #


async def test_dispatch_rejects_student_for_analyze_attachment(
    db_session, _attachment_env
) -> None:
    _su, student = await make_student(db_session)

    res = await dispatch_tool(
        "analyze_attachment",
        {"attachment_id": str(uuid.uuid4())},
        session=db_session,
        principal=student,
    )
    assert res == {"ok": False, "error": "tool_not_permitted"}


# --------------------------------------------------------------------------- #
# (f) deterministic offline path (no vision) still analyses a CSV/text file    #
# --------------------------------------------------------------------------- #


async def test_analyze_image_degrades_when_vision_unavailable(
    db_session, _attachment_env
) -> None:
    """AI-off: an image with no OCR/vision returns a clean, uncharged result."""
    # Default gateway adapter reports available=False offline → no real call, no
    # crash, no fabrication.
    _u, porg, partner = await make_org_with_admin(db_session, display_name="Degrade Co")
    session_id = await _new_session(db_session, partner)
    desc = await _upload_png(db_session, partner=partner, session_id=session_id)

    res = await dispatch_tool(
        "analyze_attachment",
        {"attachment_id": desc["id"]},
        session=db_session,
        principal=partner,
    )
    assert res["ok"] is True
    assert res["analyzed"] is False
    assert res["status"] == "not_analyzable"
    # Never charged for a non-result.
    assert await _count_charges(db_session, org_id=porg.id) == 0


async def test_analyze_csv_offline_without_vision(db_session, _attachment_env) -> None:
    # No vision adapter set → disabled default; the text tier handles the CSV.
    _u, porg, partner = await make_org_with_admin(db_session, display_name="CSV Co")
    session_id = await _new_session(db_session, partner)
    csv = b"Name,Score\nAn,90\nBinh,85\n"
    desc = await attachment_service.upload_attachment(
        db_session,
        principal=partner,
        session_id=session_id,
        filename="scores.csv",
        data=csv,
        content_type="text/csv",
    )

    res = await dispatch_tool(
        "analyze_attachment",
        {"attachment_id": desc["id"]},
        session=db_session,
        principal=partner,
    )
    assert res["ok"] is True
    assert res["analyzed"] is True
    assert res["kind"] == "text"
    assert res["table"]["columns"] == ["Name", "Score"]
    assert ["An", "90"] in res["table"]["rows"]
    assert await _count_charges(db_session, org_id=porg.id) == 1
