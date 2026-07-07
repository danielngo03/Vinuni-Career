"""Campaign / banner CREATIVE ASSET + inventory-class disclosure taxonomy tests.

(``docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md`` §4/§5/§6,
``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §7.)

Covers: creative upload sets the asset + the public serve returns bytes/media_type
only for an APPROVED creative on an ACTIVE placement; non-image / oversize
rejected with a user-safe reason; the disclosure_class -> polished bilingual label
mapping (paid vs curated vs strategic vs featured); the marketplace hero/banner
returns the creative image_url + disclosure when an active placement has one, else
the curated fallback (labelled curated, NOT paid); cross-org upload -> 404;
university moderation sees the creative preview + disclosure_class + missing-asset
state; PAID disclosure is non-removable while curated/strategic are never labelled
paid; and no raw storage path leaks anywhere.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import get_settings
from app.modules.advertising.application import (
    creative_service,
    moderation_service,
    placement_service,
)
from app.modules.advertising.domain import disclosure as disclosure_vocab
from app.modules.advertising.domain.models import SponsoredPlacement
from app.modules.documents.infrastructure import storage
from app.modules.marketplace.application import overview_service
from app.modules.opportunities.application import job_service
from app.modules.opportunities.application import (
    moderation_service as jobs_moderation,
)
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin

# Smallest byte payloads that pass / fail the magic-byte sniff.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
NOT_AN_IMAGE = b"this is plainly not an image, just ASCII text content"


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
    backend = _MemoryStorage()
    storage.set_storage(backend)
    yield backend
    storage.set_storage(None)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _job_payload(title: str = "Backend Intern", **over) -> dict:
    base = {
        "title": title,
        "description": "We are hiring a backend intern to build APIs.",
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


async def _published_job(db, partner, uni, *, title="Live Job") -> uuid.UUID:
    created = await job_service.create_job(
        db, principal=partner, payload=_job_payload(title), ctx=CTX
    )
    await job_service.submit_job(
        db, principal=partner, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    await jobs_moderation.approve_job(
        db, principal=uni, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    return uuid.UUID(created["id"])


async def _seed_placement(
    db,
    partner,
    *,
    target_id: uuid.UUID,
    status: str = "active",
    disclosure_class: str = "paid_sponsored",
    paid: bool = True,
) -> SponsoredPlacement:
    """Seed a placement directly (FK to ad_packages not enforced on SQLite)."""

    now = _now()
    placement = SponsoredPlacement(
        org_id=partner.org_id,
        created_by=partner.user_id,
        target_type="job",
        target_id=target_id,
        placement_type="sponsored",
        package_id=uuid.uuid4(),
        price_amount="3000000.00",
        currency="VND",
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=13),
        status=status,
        disclosure_class=disclosure_class,
        disclosure_confirmed=True,
        paid_at=now if paid else None,
        activated_at=now if status == "active" else None,
    )
    db.add(placement)
    await db.commit()
    await db.refresh(placement)
    return placement


async def _upload(db, principal, placement_id, *, slot="homepage_hero", data=PNG_BYTES):
    return await creative_service.upload_creative(
        db, principal=principal, placement_id=placement_id, slot=slot,
        data=data, content_type="image/png", alt_vi="Banner VN", alt_en="Banner EN",
        focal_x=0.4, focal_y=0.6, click_target="/companies/acme", ctx=CTX,
    )


async def _approve_creative(db, uni, creative_id):
    return await moderation_service.review_creative(
        db, principal=uni, creative_id=uuid.UUID(creative_id), decision="approve",
        ctx=CTX,
    )


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# Upload + serve                                                             #
# --------------------------------------------------------------------------- #


async def test_upload_sets_asset_and_serve_returns_bytes(db_session, _memory_storage):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(db_session, partner, target_id=job_id)

    before = await _audit_count(db_session, "advertising.creative_uploaded")
    created = await _upload(db_session, partner, placement.id)

    # No raw storage key in the projection — only the safe public serve URL.
    assert "image_path" not in created
    assert created["image_url"].endswith(
        f"/advertising/creatives/{created['id']}/image?v={created['version']}"
    )
    assert created["slot"] == "homepage_hero"
    assert created["moderation_status"] == "pending"
    assert created["focal_point"] == {"x": 0.4, "y": 0.6}
    assert await _audit_count(db_session, "advertising.creative_uploaded") == before + 1

    # Pending creative is NOT publicly servable.
    with pytest.raises(ResourceNotFoundError):
        await creative_service.serve_creative(
            db_session, creative_id=uuid.UUID(created["id"])
        )

    # Approve -> servable.
    await _approve_creative(db_session, uni, created["id"])
    served = await creative_service.serve_creative(
        db_session, creative_id=uuid.UUID(created["id"])
    )
    assert served.content == PNG_BYTES
    assert served.media_type == "image/png"


async def test_serve_404_when_placement_not_active(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    # Placement is only approved (not active) -> creative never serves.
    placement = await _seed_placement(
        db_session, partner, target_id=job_id, status="approved", paid=False
    )
    created = await _upload(db_session, partner, placement.id)
    await _approve_creative(db_session, uni, created["id"])
    with pytest.raises(ResourceNotFoundError):
        await creative_service.serve_creative(
            db_session, creative_id=uuid.UUID(created["id"])
        )


# --------------------------------------------------------------------------- #
# Validation: non-image / oversize                                          #
# --------------------------------------------------------------------------- #


async def test_non_image_rejected_user_safe(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(db_session, partner, target_id=job_id)
    with pytest.raises(ValidationFailedError) as exc:
        await _upload(db_session, partner, placement.id, data=NOT_AN_IMAGE)
    assert exc.value.details["reason"] == "unsupported_image_type"


async def test_oversize_rejected(db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "campaign_creative_max_mb", 0, raising=False)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(db_session, partner, target_id=job_id)
    with pytest.raises(ValidationFailedError) as exc:
        await _upload(db_session, partner, placement.id)
    assert exc.value.details["reason"] == "file_too_large"


async def test_invalid_slot_and_focal_rejected(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(db_session, partner, target_id=job_id)
    with pytest.raises(ValidationFailedError):
        await _upload(db_session, partner, placement.id, slot="not_a_slot")
    with pytest.raises(ValidationFailedError):
        await creative_service.upload_creative(
            db_session, principal=partner, placement_id=placement.id,
            slot="right_rail", data=PNG_BYTES, content_type="image/png",
            focal_x=1.5, focal_y=0.5, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# RBAC + tenant isolation                                                    #
# --------------------------------------------------------------------------- #


async def test_cross_org_creative_upload_is_404(db_session):
    _ua, _oa, partner_a = await make_org_with_admin(db_session, display_name="Org A")
    _ub, _ob, partner_b = await make_org_with_admin(db_session, display_name="Org B")
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_b = await _published_job(db_session, partner_b, uni)
    placement_b = await _seed_placement(db_session, partner_b, target_id=job_b)
    # Partner A targets Org B's placement -> hidden as 404, never 403.
    with pytest.raises(ResourceNotFoundError):
        await _upload(db_session, partner_a, placement_b.id)


async def test_member_without_permission_denied(db_session):
    _u, org, _admin = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    _mu, _m, member = await add_member(
        db_session, org=org, permissions=[("members", "read")]
    )
    job_id = await _published_job(db_session, _admin, uni)
    placement = await _seed_placement(db_session, _admin, target_id=job_id)
    with pytest.raises(PermissionDeniedError):
        await _upload(db_session, member, placement.id)


# --------------------------------------------------------------------------- #
# Disclosure-class -> polished bilingual labels                              #
# --------------------------------------------------------------------------- #


def test_disclosure_class_polished_label_mapping():
    paid_vi = disclosure_vocab.disclosure_payload("paid_sponsored", locale="vi")
    paid_en = disclosure_vocab.disclosure_payload("paid_sponsored", locale="en")
    assert paid_vi["label"] == "Đối tác tài trợ"
    assert paid_en["label"] == "Partner-sponsored"
    assert paid_vi["is_paid"] is True and paid_vi["is_removable"] is False

    curated = disclosure_vocab.disclosure_payload("university_curated", locale="en")
    assert curated["label"] == "Curated by VinUni"
    assert curated["is_paid"] is False and curated["is_removable"] is True

    strategic = disclosure_vocab.disclosure_payload("strategic_partner", locale="vi")
    assert strategic["label"] == "Đối tác chiến lược" and strategic["is_paid"] is False

    featured = disclosure_vocab.disclosure_payload("featured", locale="en")
    assert featured["label"] == "Featured" and featured["is_paid"] is False


# --------------------------------------------------------------------------- #
# Marketplace banner read: creative vs curated fallback                       #
# --------------------------------------------------------------------------- #


async def test_marketplace_hero_returns_creative_image(db_session):
    _u, partner, p_admin = await make_org_with_admin(db_session, display_name="Acme Co")
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, p_admin, uni, title="Hero Role")
    placement = await _seed_placement(db_session, p_admin, target_id=job_id)
    created = await _upload(db_session, p_admin, placement.id, slot="homepage_hero")
    await _approve_creative(db_session, uni, created["id"])

    data = await overview_service.get_overview(db_session)
    hero = data["hero_campaign"]
    assert hero is not None
    assert hero["source"] == "partner"
    assert hero["placement_id"] == str(placement.id)
    # Approval bumps the creative version, so the cache key is >= the upload's.
    assert f"/advertising/creatives/{created['id']}/image?v=" in (
        hero["creative"]["image_url"]
    )
    assert hero["creative"]["focal_point"] == {"x": 0.4, "y": 0.6}
    # Paid placement -> non-removable paid disclosure.
    assert hero["disclosure"]["class"] == "paid_sponsored"
    assert hero["disclosure"]["is_paid"] is True
    assert hero["disclosure"]["is_removable"] is False
    # No storage key leak anywhere in the banner.
    assert "image_path" not in str(hero)


async def test_marketplace_curated_fallback_when_no_partner_creative(
    db_session, monkeypatch
):
    monkeypatch.setattr(
        get_settings(), "marketplace_hero_fallback_image",
        "/images/career-day-2026.jpg", raising=False,
    )
    monkeypatch.setattr(
        get_settings(), "marketplace_rail_fallback_image",
        "/images/vinuni-campus.png", raising=False,
    )
    # Completely empty marketplace -> curated fallback, NEVER paid.
    data = await overview_service.get_overview(db_session)
    hero = data["hero_campaign"]
    assert hero is not None
    assert hero["source"] == "vinuni_curated"
    assert hero["placement_id"] is None
    assert hero["creative"]["image_url"] == "/images/career-day-2026.jpg"
    assert hero["disclosure"]["class"] == "university_curated"
    assert hero["disclosure"]["is_paid"] is False
    assert hero["disclosure"]["label"] in {"VinUni tuyển chọn", "Curated by VinUni"}

    rail = data["sponsored_banner"]
    assert rail is not None and rail["source"] == "vinuni_curated"
    assert rail["disclosure"]["is_paid"] is False


async def test_marketplace_fallback_hidden_when_unconfigured(db_session):
    # Default config has no fallback asset -> no fabricated banner (hide-if-empty).
    data = await overview_service.get_overview(db_session)
    assert data["hero_campaign"] is None
    assert data["sponsored_banner"] is None


# --------------------------------------------------------------------------- #
# University moderation sees the creative                                     #
# --------------------------------------------------------------------------- #


async def test_university_moderation_sees_creative_preview(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(db_session, partner, target_id=job_id)
    created = await _upload(db_session, partner, placement.id, slot="homepage_hero")

    items, total, _spend = await moderation_service.list_all(db_session, principal=uni)
    assert total == 1
    row = items[0]
    assert row["disclosure_class"] == "paid_sponsored"
    assert len(row["creatives"]) == 1
    assert row["creatives"][0]["image_url"].endswith(
        f"/advertising/creatives/{created['id']}/image?v={created['version']}"
    )
    # Missing-asset state: hero present (but pending, not approved) -> still
    # flagged missing until approved; right_rail also missing.
    assert "right_rail" in row["missing_primary_slots"]
    assert row["has_approved_creative"] is False


async def test_creative_review_reject_requires_note_and_blocks_serve(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(db_session, partner, target_id=job_id)
    created = await _upload(db_session, partner, placement.id)

    with pytest.raises(ValidationFailedError):
        await moderation_service.review_creative(
            db_session, principal=uni, creative_id=uuid.UUID(created["id"]),
            decision="reject", ctx=CTX,
        )
    rejected = await moderation_service.review_creative(
        db_session, principal=uni, creative_id=uuid.UUID(created["id"]),
        decision="reject", note="Logo safe-area violated", ctx=CTX,
    )
    assert rejected["moderation_status"] == "rejected"
    with pytest.raises(ResourceNotFoundError):
        await creative_service.serve_creative(
            db_session, creative_id=uuid.UUID(created["id"])
        )


# --------------------------------------------------------------------------- #
# Disclosure non-removable for paid; curated/strategic not paid               #
# --------------------------------------------------------------------------- #


async def test_paid_disclosure_is_non_removable(db_session):
    from app.modules.advertising.application.errors import PaidDisclosureImmutableError

    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(
        db_session, partner, target_id=job_id, paid=True
    )
    # A PAID placement can never be relabelled to a non-paid editorial class.
    with pytest.raises(PaidDisclosureImmutableError):
        await moderation_service.set_disclosure_class(
            db_session, principal=uni, placement_id=placement.id,
            disclosure_class="university_curated", ctx=CTX,
        )


async def test_unpaid_placement_can_be_curated_not_labelled_paid(db_session):
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(
        db_session, partner, target_id=job_id, status="pending_approval", paid=False
    )
    updated = await moderation_service.set_disclosure_class(
        db_session, principal=uni, placement_id=placement.id,
        disclosure_class="strategic_partner", ctx=CTX,
    )
    assert updated["disclosure_class"] == "strategic_partner"
    assert updated["disclosure"]["is_paid"] is False
    assert updated["disclosure"]["label"] in {"Đối tác chiến lược", "Strategic partner"}


async def test_partner_admin_cannot_moderate_creative(db_session):
    from app.shared.exceptions import PermissionDeniedError as _PD

    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    placement = await _seed_placement(db_session, partner, target_id=job_id)
    created = await _upload(db_session, partner, placement.id)
    # A partner admin's *:* cannot self-approve its own creative (university only).
    with pytest.raises(_PD):
        await moderation_service.review_creative(
            db_session, principal=partner, creative_id=uuid.UUID(created["id"]),
            decision="approve", ctx=CTX,
        )
