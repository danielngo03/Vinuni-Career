"""``generate_image`` tool — AI image generation for recruiting content.

Partner/university-staff only, gated on the grantable
``ai_recruiting:generate_image`` capability. The prompt goes through a
DETERMINISTIC content blocklist (real-person likenesses, third-party logos/
trademarks, sexual/violent/political content) and the shared
``input_guard.sanitize_instruction`` pass before any model sees it. Output is
stored as an owner-scoped :class:`ChatExportFile` (PNG, 24 h expiry) and
returned via the FROZEN render artifact::

    {"kind": "image", "download_path": "/ai/chat/exports/{id}",
     "filename": str, "alt": str, "width": int, "height": int}

Offline mode (``AI_REAL_CALLS_ENABLED`` false / no credential) stores a
deterministic placeholder PNG and is NEVER metered; a real provider call is
settled through the billable-usage ledger (idempotent on the export file id).
Provider/model internals never surface — failures collapse to user-safe codes.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.shared.permissions import Principal, permission_checker

logger = logging.getLogger(__name__)

_PNG_MIME = "image/png"
_EXPORT_TTL_HOURS = 24

# --------------------------------------------------------------------------- #
# Deterministic content blocklist (refusal BEFORE any model call)              #
# --------------------------------------------------------------------------- #

# Well-known real people (politicians/celebrities, global + VN) — likeness
# generation is refused outright.
_REAL_PERSON_TERMS = (
    "elon musk",
    "donald trump",
    "joe biden",
    "barack obama",
    "putin",
    "xi jinping",
    "tập cận bình",
    "kim jong",
    "zelensky",
    "taylor swift",
    "beyonce",
    "messi",
    "ronaldo",
    "sơn tùng",
    "hồ chí minh",
    "võ nguyên giáp",
    "nguyễn phú trọng",
    "phạm minh chính",
    "tô lâm",
)
# Generic real-person-likeness phrasing (plain substring terms; word-boundary
# regex is unreliable on Vietnamese diacritics).
_REAL_PERSON_PHRASES = (
    "real person",
    "người thật",
    "celebrity",
    "người nổi tiếng",
    "deepfake",
    "face of",
    "likeness of",
)

# Third-party brands — refused when combined with logo/trademark phrasing.
_BRAND_TERMS = (
    "google",
    "apple",
    "microsoft",
    "amazon",
    "facebook",
    "meta",
    "nike",
    "adidas",
    "coca-cola",
    "coca cola",
    "pepsi",
    "samsung",
    "disney",
    "starbucks",
    "mcdonald",
)
_LOGO_KEYWORDS = ("logo", "trademark", "thương hiệu", "nhãn hiệu", "brand mark")

_SEXUAL_TERMS = (
    "nude",
    "naked",
    "nsfw",
    "sexual",
    "erotic",
    "porn",
    "khỏa thân",
    "khoả thân",
    "khiêu dâm",
)
_VIOLENT_TERMS = (
    "blood",
    "gore",
    "violence",
    "violent",
    "murder",
    "weapon",
    "gun",
    "bạo lực",
    "máu me",
    "giết người",
    "súng",
)
_POLITICAL_TERMS = (
    "political",
    "politician",
    "protest",
    "election",
    "chính trị",
    "biểu tình",
    "bầu cử",
    "đảng phái",
)


def _contains_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def check_prompt_blocklist(prompt: str) -> str | None:
    """Return a refusal category token, or ``None`` when the prompt is allowed.

    Deterministic and offline — runs BEFORE sanitization and any model call.
    """

    text = (prompt or "").lower()
    if _contains_term(text, _REAL_PERSON_TERMS) or _contains_term(text, _REAL_PERSON_PHRASES):
        return "real_person"
    if _contains_term(text, _LOGO_KEYWORDS) and _contains_term(text, _BRAND_TERMS):
        return "trademark"
    if _contains_term(text, _SEXUAL_TERMS):
        return "sexual"
    if _contains_term(text, _VIOLENT_TERMS):
        return "violent"
    if _contains_term(text, _POLITICAL_TERMS):
        return "political"
    return None


_REFUSAL_MESSAGE_VI = (
    "Yêu cầu này nằm ngoài phạm vi tạo ảnh cho nội dung tuyển dụng (không hỗ trợ "
    "hình ảnh người thật, logo/thương hiệu của bên khác, hoặc nội dung nhạy cảm). "
    "Hãy mô tả một hình ảnh minh hoạ chuyên nghiệp khác."
)
_DISABLED_MESSAGE_VI = "Tính năng tạo ảnh hiện chưa được bật trên hệ thống."

_ASPECT_RATIOS = frozenset({"1:1", "16:9", "9:16", "4:3"})


async def _meter_real_generation(
    session: AsyncSession, principal: Principal, *, export_id: _uuid.UUID
) -> None:
    """Settle ONE billable unit for a REAL generation (idempotent, best-effort)."""

    try:
        from app.ai.observability.billable_usage import (
            SCOPE_ORG,
            UsageContext,
            make_idempotency_key,
            record_billable_usage,
        )

        persona = "partner" if (principal.persona or "").startswith("partner") else "university"
        await record_billable_usage(
            session,
            ctx=UsageContext(
                actor_persona=persona,
                feature_key="image_generation",
                task_type="ai_image_generation",
                billing_scope=SCOPE_ORG,
                actor_user_id=principal.user_id,
                org_id=principal.org_id,
                resource_type="chat_export",
                resource_id=export_id,
                idempotency_key=make_idempotency_key("image_generation", export_id),
            ),
            result_status="success",
            base_units=1,
        )
    except Exception:  # noqa: BLE001 - accounting must never break the reply
        logger.warning("image.billable_ledger_write_failed", exc_info=True)


async def generate_image(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Generate one recruiting-content PNG (RBAC + blocklist + metered)."""

    from app.ai.gateway.image import ImageUnavailableError
    from app.ai.gateway.image import generate_image as gateway_generate
    from app.ai.safety.input_guard import sanitize_instruction
    from app.modules.ai_assistant.domain.models import ChatExportFile
    from app.modules.analytics.application import ingestion_service as analytics

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "org_member_only"}
    # Service-layer RBAC (defense in depth beyond the tool-loop gate): the
    # grantable ``ai_recruiting:generate_image`` capability, org-scoped.
    if not permission_checker.can(
        principal, "ai_recruiting", "generate_image", resource_org_id=principal.org_id
    ):
        return {"ok": False, "error": "permission_denied"}

    s = get_settings()
    if not getattr(s, "ai_image_enabled", False):
        return {"ok": False, "error": "image_generation_disabled", "message": _DISABLED_MESSAGE_VI}

    raw_prompt = str(args.get("prompt") or "").strip()
    if not raw_prompt:
        return {"ok": False, "error": "prompt_required"}
    max_chars = int(getattr(s, "ai_image_max_prompt_chars", 600))
    if len(raw_prompt) > max_chars:
        return {"ok": False, "error": "prompt_too_long"}

    refusal = check_prompt_blocklist(raw_prompt)
    if refusal is not None:
        return {
            "ok": False,
            "error": "prompt_refused",
            "refusal_code": refusal,
            "message": _REFUSAL_MESSAGE_VI,
        }

    clean_prompt, _flags = sanitize_instruction(raw_prompt)
    clean_prompt = (clean_prompt or "")[:max_chars]
    if not clean_prompt:
        return {"ok": False, "error": "prompt_required"}

    aspect_ratio = str(args.get("aspect_ratio") or "1:1").strip()
    if aspect_ratio not in _ASPECT_RATIOS:
        aspect_ratio = "1:1"
    style_hint, _ = sanitize_instruction(str(args.get("style_hint") or "") or None)

    try:
        result = await gateway_generate(
            clean_prompt,
            aspect_ratio=aspect_ratio,
            style_hint=style_hint,
            session=session,
            user_id=principal.user_id,
            session_id=None,
        )
    except ImageUnavailableError:
        return {"ok": False, "error": "image_unavailable"}
    except Exception:  # noqa: BLE001 - never leak provider internals
        logger.warning("image.tool_failed", exc_info=True)
        return {"ok": False, "error": "image_unavailable"}

    filename = f"ai-image-{_uuid.uuid4().hex[:8]}.png"
    export = ChatExportFile(
        id=_uuid.uuid4(),
        user_id=principal.user_id,
        org_id=principal.org_id,
        filename=filename,
        mime=_PNG_MIME,
        content=result.png,
        row_count=0,
        expires_at=datetime.now(UTC) + timedelta(hours=_EXPORT_TTL_HOURS),
    )
    session.add(export)

    # Meter ONLY a real provider generation (the offline placeholder is free).
    if result.real_call:
        await _meter_real_generation(session, principal, export_id=export.id)

    # Metadata-only product fact — never the prompt text or image bytes.
    await analytics.record_event_safe(
        session,
        event_type="ai.image.generated",
        aggregate_type="chat_export",
        aggregate_id=export.id,
        actor_id=principal.user_id,
        actor_type="partner" if (principal.persona or "").startswith("partner") else "university",
        properties={
            "aspect_ratio": aspect_ratio,
            "real": bool(result.real_call),
            "width": result.width,
            "height": result.height,
        },
    )

    alt = clean_prompt[:120]
    return {
        "ok": True,
        "filename": filename,
        "alt": alt,
        "width": result.width,
        "height": result.height,
        # FE-only render artifact (stripped before the model sees the result).
        "render": {
            "kind": "image",
            "download_path": f"/ai/chat/exports/{export.id}",
            "filename": filename,
            "alt": alt,
            "width": result.width,
            "height": result.height,
        },
    }
