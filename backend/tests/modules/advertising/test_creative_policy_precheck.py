"""Deterministic creative-policy PRE-checks (WS-13, Task P).

A creative upload runs deterministic pre-checks (dimensions vs SLOT_SPECS, banned
claims, off-platform contact) that AUTO-FLAG the placement into the EXISTING human
review queue. The check is advisory — the creative stays ``pending`` and a human
still approves; this just pre-flags. A clean creative produces no flag.
"""

from __future__ import annotations

import struct
import uuid
from datetime import UTC, datetime

import pytest
from app.modules.advertising.application import creative_service, placement_service
from app.modules.advertising.domain.creatives import CREATIVE_PENDING
from app.modules.advertising.domain.models import AdPackage, CampaignCreative
from app.modules.documents.infrastructure import storage
from app.modules.moderation.domain.models import SOURCE_CONTENT, HumanReviewItem
from app.shared.exceptions import PermissionDeniedError
from sqlalchemy import func, select
from tests.auth_utils import CTX
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import publish_job


class _MemoryStorage:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> None:
        self._data[key] = data

    def load(self, key: str) -> bytes:
        try:
            return self._data[key]
        except KeyError as exc:
            raise storage.StorageError("object not found") from exc

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


@pytest.fixture(autouse=True)
def _memory_storage():
    storage.set_storage(_MemoryStorage())
    yield
    storage.set_storage(None)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _png(width: int, height: int) -> bytes:
    """A minimal valid PNG (signature + IHDR) with real dimensions in the header."""

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
    return sig + ihdr


async def _seed_package(db) -> AdPackage:
    pkg = AdPackage(
        code="sponsored_14d", name="Tài trợ 14 ngày", placement_type="sponsored",
        price_amount="3000000.00", currency="VND", duration_days=14,
        grants_sponsored=True, grants_featured=False, is_active=True,
    )
    db.add(pkg)
    await db.commit()
    await db.refresh(pkg)
    return pkg


async def _draft_placement(db, partner, uni) -> uuid.UUID:
    pkg = await _seed_package(db)
    job_id = await publish_job(
        db, partner_principal=partner, uni_principal=uni, title="Role"
    )
    created = await placement_service.create_placement(
        db, principal=partner, ctx=CTX,
        payload={
            "target_type": "job", "target_id": job_id,
            "placement_type": "sponsored", "package_id": pkg.id,
            "start_at": _now(), "disclosure_confirmed": True,
        },
    )
    return uuid.UUID(created["id"])


async def _partner(db, name: str):
    _u, _org, partner = await make_org_with_admin(db, display_name=name)
    return partner


async def _university(db):
    _u, _org, uni = await make_org_with_admin(db, org_type="university")
    return uni


async def _queue_count(db, placement_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(HumanReviewItem).where(
                HumanReviewItem.source == SOURCE_CONTENT,
                HumanReviewItem.resource_type == "advertising_placement",
                HumanReviewItem.resource_id == placement_id,
            )
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Bad creative -> pre-flag into the escalation queue                           #
# --------------------------------------------------------------------------- #


async def test_bad_dimension_and_banned_claim_flags_into_queue(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    pid = await _draft_placement(db_session, partner, uni)

    # 600x600 into the 4:1 homepage hero slot + a banned claim + an off-platform
    # phone number: three deterministic findings.
    result = await creative_service.upload_creative(
        db_session, principal=partner, placement_id=pid, slot="homepage_hero",
        data=_png(600, 600), content_type="image/png",
        alt_vi="Cam kết việc làm! Liên hệ zalo 0901234567",
        alt_en="Guaranteed job — contact us",
        ctx=CTX,
    )
    codes = {f["code"] for f in result["policy_flags"]}
    assert "creative_dimension_mismatch" in codes
    assert "banned_claim" in codes
    assert "off_platform_contact" in codes

    # The placement is auto-flagged into the SAME queue escalate_placement feeds,
    # at high severity, and the creative is still PENDING (human still decides).
    assert await _queue_count(db_session, pid) == 1
    item = (
        await db_session.execute(
            select(HumanReviewItem).where(HumanReviewItem.resource_id == pid)
        )
    ).scalar_one()
    assert item.severity == "high"
    assert item.findings_json["kind"] == "creative_policy_precheck"
    creative = (
        await db_session.execute(
            select(CampaignCreative).where(CampaignCreative.placement_id == pid)
        )
    ).scalar_one()
    assert creative.moderation_status == CREATIVE_PENDING


async def test_clean_creative_produces_no_flag(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    pid = await _draft_placement(db_session, partner, uni)

    # Correct 4:1 hero dimensions + clean alt text -> no findings, no queue item.
    result = await creative_service.upload_creative(
        db_session, principal=partner, placement_id=pid, slot="homepage_hero",
        data=_png(1440, 360), content_type="image/png",
        alt_vi="Tuyển thực tập sinh backend", alt_en="Backend internship",
        click_target="/companies/acme", ctx=CTX,
    )
    assert result["policy_flags"] == []
    assert await _queue_count(db_session, pid) == 0


async def test_precheck_flag_is_idempotent_on_reupload(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    uni = await _university(db_session)
    pid = await _draft_placement(db_session, partner, uni)

    for _ in range(2):
        await creative_service.upload_creative(
            db_session, principal=partner, placement_id=pid, slot="homepage_hero",
            data=_png(600, 600), content_type="image/png",
            alt_en="Guaranteed job", ctx=CTX,
        )
    # The review queue dedupes per (source, resource_type, resource_id): one item.
    assert await _queue_count(db_session, pid) == 1


async def test_upload_still_rbac_gated(db_session) -> None:
    partner = await _partner(db_session, "Acme")
    other = await _partner(db_session, "Other")
    uni = await _university(db_session)
    pid = await _draft_placement(db_session, partner, uni)
    # A different org uploading to this placement is a 404 (never enumerable),
    # and the pre-check never runs for a non-owner.
    from app.shared.exceptions import ResourceNotFoundError

    with pytest.raises((ResourceNotFoundError, PermissionDeniedError)):
        await creative_service.upload_creative(
            db_session, principal=other, placement_id=pid, slot="homepage_hero",
            data=_png(1440, 360), content_type="image/png", ctx=CTX,
        )
