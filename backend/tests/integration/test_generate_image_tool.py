"""Tests for the ``generate_image`` tool + image gateway tier (Lane B).

Everything here runs OFFLINE (``AI_REAL_CALLS_ENABLED=false`` is pinned by
conftest): the gateway returns its deterministic placeholder PNG, which must be
stored/rendered exactly like a real image but NEVER metered. The real-call
metering path is exercised through a faked gateway result (``real_call=True``).
Blocklist refusals, the disabled-flag path, RBAC/persona visibility, and
leak-safety are all covered.
"""

from __future__ import annotations

import uuid

from app.ai.gateway.image import service as image_service
from app.ai.observability.models import AiBillableUsage
from app.core.config import get_settings
from app.modules.ai_assistant.application.native_loop import available_specs
from app.modules.ai_assistant.application.tools.dispatch import (
    SUPPORTED_TOOL_NAMES,
    dispatch_tool,
)
from app.modules.ai_assistant.application.tools.image import check_prompt_blocklist
from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS
from app.modules.ai_assistant.domain.models import ChatExportFile
from app.shared.permissions import GUEST, Principal
from sqlalchemy import select

from tests.auth_utils import register_verified
from tests.messaging_utils import make_partner, make_university
from tests.org_utils import add_member

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _enable_images(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_image_enabled", True)


async def _billable_rows(db) -> list[AiBillableUsage]:
    return list(
        (
            await db.execute(
                select(AiBillableUsage).where(
                    AiBillableUsage.task_type == "ai_image_generation"
                )
            )
        )
        .scalars()
        .all()
    )


# --------------------------------------------------------------------------- #
# Registry / visibility                                                        #
# --------------------------------------------------------------------------- #


def test_generate_image_registered() -> None:
    assert "generate_image" in TOOL_SPECS
    assert "generate_image" in SUPPORTED_TOOL_NAMES
    spec = TOOL_SPECS["generate_image"]
    assert spec.permission_class == "read_only"
    assert set(spec.persona) == {"partner_user", "university_staff"}
    assert "ai_recruiting:generate_image" in spec.required_permissions
    assert spec.audit_event_type == "TOOL_GENERATE_IMAGE"
    assert spec.fallback


async def test_generate_image_visibility(db_session) -> None:
    _u, org, partner_admin = await make_partner(db_session)
    _uu, _uorg, uni_admin = await make_university(db_session)
    _mu, _m, ungranted = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    student_user = await register_verified(
        db_session, email=f"s_{uuid.uuid4().hex[:8]}@vinuni.edu.vn"
    )
    student = Principal(user_id=student_user.id, persona="student", permissions=frozenset())

    assert "generate_image" in {s.name for s in available_specs(partner_admin)}
    assert "generate_image" in {s.name for s in available_specs(uni_admin)}
    assert "generate_image" not in {s.name for s in available_specs(ungranted)}
    assert "generate_image" not in {s.name for s in available_specs(student)}


async def test_generate_image_rbac_denied_without_grant(db_session, monkeypatch) -> None:
    _enable_images(monkeypatch)
    _u, org, _admin = await make_partner(db_session)
    _mu, _m, member = await add_member(
        db_session, org=org, permissions=[("applications", "read")]
    )
    res = await dispatch_tool(
        "generate_image", {"prompt": "a friendly office"}, session=db_session, principal=member
    )
    assert res == {"ok": False, "error": "permission_denied"}


async def test_generate_image_guest_denied(db_session, monkeypatch) -> None:
    _enable_images(monkeypatch)
    res = await dispatch_tool(
        "generate_image", {"prompt": "an office"}, session=db_session, principal=GUEST
    )
    assert res["ok"] is False


# --------------------------------------------------------------------------- #
# Offline placeholder path (never metered)                                     #
# --------------------------------------------------------------------------- #


async def test_generate_image_offline_placeholder_stored(db_session, monkeypatch) -> None:
    _enable_images(monkeypatch)
    _u, _org, admin = await make_partner(db_session)

    res = await dispatch_tool(
        "generate_image",
        {"prompt": "modern office teamwork illustration", "aspect_ratio": "16:9"},
        session=db_session,
        principal=admin,
    )
    assert res["ok"] is True

    # FROZEN artifact contract.
    render = res["render"]
    assert set(render.keys()) == {
        "kind",
        "download_path",
        "filename",
        "alt",
        "width",
        "height",
    }
    assert render["kind"] == "image"
    assert render["filename"].startswith("ai-image-") and render["filename"].endswith(".png")
    assert render["download_path"].startswith("/ai/chat/exports/")
    assert render["alt"]
    # 16:9 framing (offline placeholder long side = 64).
    assert render["width"] == 64 and render["height"] == 36

    export_id = uuid.UUID(render["download_path"].rsplit("/", 1)[-1])
    row = await db_session.get(ChatExportFile, export_id)
    assert row is not None
    assert row.mime == "image/png"
    assert row.row_count == 0
    assert row.content.startswith(_PNG_MAGIC)
    assert row.expires_at is not None

    # Offline placeholder is FREE — nothing lands in the billable ledger.
    assert await _billable_rows(db_session) == []

    # Metadata-only analytics fact (never the prompt text).
    from app.modules.analytics.domain.models import AnalyticsEvent

    facts = (
        (
            await db_session.execute(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.event_type == "ai.image.generated"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(facts) == 1
    assert facts[0].properties["real"] is False
    assert "teamwork" not in str(facts[0].properties)

    # Leak-safety: no provider/model internals in the result.
    blob = str(res).lower()
    for term in ("gemini", "google", "vertex", "provider", "model"):
        assert term not in blob


async def test_generate_image_disabled_flag(db_session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_image_enabled", False)
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "generate_image", {"prompt": "an office"}, session=db_session, principal=admin
    )
    assert res["ok"] is False
    assert res["error"] == "image_generation_disabled"
    assert res["message"]  # user-safe copy, no internals
    assert await _billable_rows(db_session) == []


async def test_generate_image_prompt_limits(db_session, monkeypatch) -> None:
    _enable_images(monkeypatch)
    _u, _org, admin = await make_partner(db_session)

    res = await dispatch_tool(
        "generate_image", {"prompt": "   "}, session=db_session, principal=admin
    )
    assert res["ok"] is False  # blank → missing/required

    max_chars = int(get_settings().ai_image_max_prompt_chars)
    res = await dispatch_tool(
        "generate_image", {"prompt": "x" * (max_chars + 1)}, session=db_session, principal=admin
    )
    assert res == {"ok": False, "error": "prompt_too_long"}


# --------------------------------------------------------------------------- #
# Deterministic blocklist                                                      #
# --------------------------------------------------------------------------- #


def test_blocklist_categories() -> None:
    assert check_prompt_blocklist("chân dung Elon Musk trong văn phòng") == "real_person"
    assert check_prompt_blocklist("vẽ ảnh người nổi tiếng") == "real_person"
    assert check_prompt_blocklist("draw the Nike logo on a banner") == "trademark"
    assert check_prompt_blocklist("thiết kế thương hiệu giống Coca-Cola") == "trademark"
    assert check_prompt_blocklist("ảnh khỏa thân nghệ thuật") == "sexual"
    assert check_prompt_blocklist("a violent battle scene with blood") == "violent"
    assert check_prompt_blocklist("poster biểu tình chính trị") == "political"
    # Normal recruiting content passes.
    assert check_prompt_blocklist("banner hội chợ việc làm với sinh viên vui vẻ") is None
    # A brand mention WITHOUT logo/trademark phrasing is allowed (e.g. tech-stack art).
    assert check_prompt_blocklist("developers working on Google Cloud dashboards") is None


async def test_generate_image_refusal_is_user_safe_and_unmetered(
    db_session, monkeypatch
) -> None:
    _enable_images(monkeypatch)
    _u, _org, admin = await make_partner(db_session)
    res = await dispatch_tool(
        "generate_image",
        {"prompt": "logo of Nike on our job banner"},
        session=db_session,
        principal=admin,
    )
    assert res["ok"] is False
    assert res["error"] == "prompt_refused"
    assert res["refusal_code"] == "trademark"
    assert res["message"]
    assert "render" not in res
    assert await _billable_rows(db_session) == []
    # Nothing was stored either.
    stored = (await db_session.execute(select(ChatExportFile))).scalars().all()
    assert stored == []


# --------------------------------------------------------------------------- #
# Real-call metering (faked gateway result)                                    #
# --------------------------------------------------------------------------- #


async def test_generate_image_real_call_is_metered_once(db_session, monkeypatch) -> None:
    import app.ai.gateway.image as image_pkg

    _enable_images(monkeypatch)
    _u, org, admin = await make_partner(db_session)

    png, w, h = image_service.placeholder_png("1:1")

    async def fake_generate(prompt, **kwargs):
        return image_service.ImageResult(png=png, width=w, height=h, real_call=True)

    monkeypatch.setattr(image_pkg, "generate_image", fake_generate)

    res = await dispatch_tool(
        "generate_image",
        {"prompt": "a bright modern campus career fair"},
        session=db_session,
        principal=admin,
    )
    assert res["ok"] is True
    rows = await _billable_rows(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.units_charged == 1
    assert row.feature_key == "image_generation"
    assert row.actor_persona == "partner"
    assert row.org_id == org.id
    assert row.billing_scope == "org"
    export_id = res["render"]["download_path"].rsplit("/", 1)[-1]
    assert row.idempotency_key == f"image_generation:{export_id}"


# --------------------------------------------------------------------------- #
# Gateway unit behaviour                                                       #
# --------------------------------------------------------------------------- #


def test_placeholder_png_dims_follow_aspect_ratio() -> None:
    for ratio, (ew, eh) in {
        "1:1": (64, 64),
        "16:9": (64, 36),
        "9:16": (36, 64),
        "4:3": (64, 48),
    }.items():
        png, width, height = image_service.placeholder_png(ratio)
        assert png.startswith(_PNG_MAGIC)
        assert (width, height) == (ew, eh)
    # Deterministic bytes (idempotent tests / snapshots).
    a, _, _ = image_service.placeholder_png("1:1")
    b, _, _ = image_service.placeholder_png("1:1")
    assert a == b


async def test_gateway_disabled_raises_leak_safe_error(monkeypatch) -> None:
    import pytest

    monkeypatch.setattr(get_settings(), "ai_image_enabled", False)
    with pytest.raises(image_service.ImageUnavailableError) as exc:
        await image_service.generate_image("an office")
    assert exc.value.reason == "disabled"


async def test_gateway_offline_returns_placeholder(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_image_enabled", True)
    result = await image_service.generate_image("an office", aspect_ratio="9:16")
    assert result.real_call is False
    assert result.png.startswith(_PNG_MAGIC)
    assert (result.width, result.height) == (36, 64)
