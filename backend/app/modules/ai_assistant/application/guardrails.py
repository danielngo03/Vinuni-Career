"""Chat-turn guardrail wiring (deterministic, multi-layer — AI_PRODUCT_SPEC §9).

Layers applied to every assistant turn, in order:

1. **Pre-LLM policy preflight** (:func:`preflight_policy`) — runs the central
   :func:`app.ai.safety.policy_orchestrator.check_policy` pipeline (intent
   classification → PII redaction / injection strip → policy action) BEFORE the
   fast-path, the deterministic planner, and the native tool loop. A refusal
   never reaches a model and never consumes quota/energy.

   Student/university external-source asks are *deferred* instead of refused
   outright: the deterministic planner already produces a richer, deterministic
   "platform data only" reply for those (no LLM either). If the planner does not
   catch the phrasing, the caller falls back to the policy refusal so the turn
   is still guaranteed to never reach a model.

2. **Post-LLM partner scope guard** (:func:`partner_scope_guard`) — when a
   partner turn produced NO tool call (pure text), the model's own final answer
   must reference the recruiting domain; otherwise it is replaced with a polite
   scoped refusal. Mirrors the student ``enforce_keyword_scope`` fallback with a
   partner vocabulary; deliberately generous with smalltalk/meta allowances to
   avoid false positives. A tool-grounded answer is trusted by construction.

3. ``guard_completion`` (gateway output guard) stays on every completion —
   applied inside ``llm_complete_native`` / ``llm_complete`` / summarize/title
   helpers, not here.

All user-facing copy in this module is vi/en localized; prompts/guard text stay
English per ai.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ai.safety.output_guard import enforce_keyword_scope
from app.ai.safety.policy_orchestrator import (
    ACTION_REFUSE,
    INTENT_BOUNDARY_PROBE,
    INTENT_EXTERNAL_SOURCE,
    check_policy,
)

_PARTNER_PERSONA_PREFIX = "partner"


# --------------------------------------------------------------------------- #
# Localized guardrail copy (user-facing; kept local because this module owns   #
# the partner-flavoured wording — the shared catalog keys stay untouched).     #
# --------------------------------------------------------------------------- #

_COPY: dict[str, dict[str, str]] = {
    # Partner-facing refusal for external/web/boundary asks: friendly, explains
    # the in-system + own-permissions boundary, offers a next step.
    "refuse.partner_scope": {
        "vi": (
            "Mình chỉ làm việc với dữ liệu tuyển dụng bên trong VinUni Career Platform "
            "và trong phạm vi quyền của chính bạn — mình không truy cập internet, website "
            "hay nguồn dữ liệu bên ngoài. Bạn có thể nhờ mình xem tin tuyển dụng, ứng viên "
            "theo vòng, soạn JD, tóm tắt sàng lọc, thống kê tuyển dụng hoặc sự kiện của "
            "tổ chức bạn."
        ),
        "en": (
            "I only work with recruiting data inside the VinUni Career Platform, scoped to "
            "your own permissions — I can't access the internet, external websites, or "
            "outside data sources. You can ask me to review your job postings, look up "
            "candidates by stage, draft a JD, summarise screening, check recruiting "
            "analytics, or list your organisation's events."
        ),
    },
    # Post-LLM partner topical-scope refusal (answer drifted off recruiting).
    "refuse.partner_off_topic": {
        "vi": (
            "Mình là trợ lý tuyển dụng cho tổ chức của bạn nên chỉ hỗ trợ các chủ đề "
            "về tuyển dụng: tin tuyển dụng, ứng viên, pipeline, phỏng vấn, offer, sự kiện, "
            "thương hiệu tuyển dụng và số liệu tuyển dụng. Bạn muốn mình giúp một việc "
            "cụ thể trong các mảng đó không?"
        ),
        "en": (
            "I'm your organisation's recruiting assistant, so I can only help with hiring "
            "topics: job postings, candidates, pipeline, interviews, offers, events, "
            "employer branding, and recruiting analytics. Would you like help with "
            "something in those areas?"
        ),
    },
    # Persona-appropriate allowance-exhausted messages (never billing upsell for
    # university staff; partner routes to admin limit/top-up).
    "limit.partner": {
        "vi": (
            "Tổ chức của bạn đã dùng hết hạn mức AI hiện tại nên mình tạm dừng xử lý "
            "yêu cầu này. Quản trị viên của tổ chức có thể điều chỉnh hạn mức hoặc nạp "
            "thêm trong phần quản trị; hạn mức cũng tự đặt lại theo chu kỳ."
        ),
        "en": (
            "Your organisation has used up its current AI allowance, so I paused this "
            "request. Your organisation admin can adjust the limit or top it up in the "
            "admin area; the allowance also resets on its regular cycle."
        ),
    },
    "limit.university": {
        "vi": (
            "Hạn mức AI của đơn vị bạn đã được dùng hết nên mình tạm dừng xử lý yêu cầu "
            "này. Bạn có thể đề nghị quản trị viên của trường tăng hạn mức cho đơn vị; "
            "hạn mức cũng tự đặt lại theo chu kỳ."
        ),
        "en": (
            "Your unit's AI allowance has been used up, so I paused this request. "
            "You can ask your university administrator to raise the unit's limit; "
            "the allowance also resets on its regular cycle."
        ),
    },
    "limit.student": {
        "vi": (
            "Bạn đã dùng hết hạn mức AI hiện tại nên mình tạm dừng xử lý yêu cầu này. "
            "Hạn mức sẽ tự đặt lại theo chu kỳ, hoặc bạn có thể xem các lựa chọn nâng "
            "hạn mức trong phần cài đặt tài khoản."
        ),
        "en": (
            "You've used up your current AI allowance, so I paused this request. "
            "The allowance resets on its regular cycle, or you can review upgrade "
            "options in your account settings."
        ),
    },
    # Cancelled pending tool action acknowledgement.
    "confirm.cancelled": {
        "vi": "Đã hủy thao tác. Mình chưa thực hiện thay đổi nào.",
        "en": "The action has been cancelled. No changes were made.",
    },
}


def _copy(key: str, locale: str) -> str:
    entry = _COPY[key]
    base = (locale or "vi").split("-")[0].lower()
    return entry.get(base) or entry["vi"]


def cancelled_ack(locale: str = "vi") -> str:
    """User-facing acknowledgement after cancelling a pending tool action."""
    return _copy("confirm.cancelled", locale)


def limit_reached_reply(persona: str | None, locale: str = "vi") -> str:
    """Persona-appropriate allowance-exhausted copy (no internals, no upsell for staff)."""
    p = persona or ""
    if p.startswith(_PARTNER_PERSONA_PREFIX):
        return _copy("limit.partner", locale)
    if p.startswith("university"):
        return _copy("limit.university", locale)
    return _copy("limit.student", locale)


# --------------------------------------------------------------------------- #
# 1. Pre-LLM policy preflight                                                  #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PolicyPreflight:
    """Outcome of the pre-LLM policy check for one user turn.

    - ``refusal_text`` set → refuse NOW (persist + return; no model call).
    - ``deferred_refusal_text`` set → let the deterministic planner answer; if
      it produces no plan the caller must fall back to this refusal (still no
      model call for the flagged intent).
    - otherwise proceed with ``clean_text`` (PII-redacted / injection-stripped).
    """

    clean_text: str | None
    refusal_text: str | None = None
    deferred_refusal_text: str | None = None
    intent: str = "benign"
    flags: tuple[str, ...] = ()

    @property
    def refused(self) -> bool:
        return self.refusal_text is not None


def preflight_policy(text: str, *, persona: str | None, locale: str = "vi") -> PolicyPreflight:
    """Run the central safety policy on a raw user turn (ALL personas).

    Harmful content and boundary probes are refused for everyone. External
    source/web-access asks are refused immediately for partner personas (their
    planner-free native loop would otherwise reach the model) and deferred to
    the deterministic planner for student/university personas, which already
    produce a friendlier deterministic reply for those asks.
    """
    decision = check_policy(text, locale=locale)
    flags = tuple(decision.flags)

    if decision.action != ACTION_REFUSE:
        return PolicyPreflight(clean_text=decision.clean_text, intent=decision.intent, flags=flags)

    refusal = decision.refusal_message or ""
    is_partner = bool(persona) and str(persona).startswith(_PARTNER_PERSONA_PREFIX)

    if decision.intent == INTENT_EXTERNAL_SOURCE:
        if is_partner:
            return PolicyPreflight(
                clean_text=None,
                refusal_text=_copy("refuse.partner_scope", locale),
                intent=decision.intent,
                flags=flags,
            )
        # Student/university: the planner owns the richer deterministic reply;
        # fall back to the policy refusal if it produces no plan.
        from app.ai.safety.input_guard import sanitize_instruction

        clean, _ = sanitize_instruction(text)
        return PolicyPreflight(
            clean_text=clean,
            deferred_refusal_text=refusal,
            intent=decision.intent,
            flags=flags,
        )

    if is_partner and decision.intent == INTENT_BOUNDARY_PROBE:
        # Same refusal class, partner-flavoured wording (in-system data + own
        # permissions) instead of the student-flavoured catalog copy.
        refusal = _copy("refuse.partner_scope", locale)

    return PolicyPreflight(
        clean_text=None,
        refusal_text=refusal,
        intent=decision.intent,
        flags=flags,
    )


# --------------------------------------------------------------------------- #
# 2. Post-LLM partner topical scope guard                                      #
# --------------------------------------------------------------------------- #

# Recruiting-domain vocabulary (vi + en, lowercase substrings). The guard only
# refuses when the model's own final answer references NONE of these — so the
# list is intentionally broad, plus explicit smalltalk/meta allowances.
PARTNER_DOMAIN_KEYWORDS: tuple[str, ...] = (
    # hiring operations
    "tuyển",
    "recruit",
    "hiring",
    "hire",
    "ứng viên",
    "candidate",
    "applicant",
    "pipeline",
    "sàng lọc",
    "screening",
    "scorecard",
    "phỏng vấn",
    "interview",
    "offer",
    "đề nghị",
    "jd",
    "job",
    "việc",
    "công việc",
    "vị trí",
    "position",
    "role",
    "mô tả",
    "description",
    "cv",
    "hồ sơ",
    "đơn",
    "application",
    "stage",
    "vòng",
    "talent",
    "onboard",
    # events / branding / analytics
    "sự kiện",
    "event",
    "thương hiệu",
    "brand",
    "employer",
    "analytics",
    "phân tích",
    "báo cáo",
    "report",
    "thống kê",
    "biểu đồ",
    "chart",
    "funnel",
    "phễu",
    "chuyển đổi",
    "conversion",
    "số liệu",
    "metric",
    "lương",
    "salary",
    "benchmark",
    # org / platform context
    "công ty",
    "company",
    "tổ chức",
    "organisation",
    "organization",
    "team",
    "thành viên",
    "quyền",
    "permission",
    "vinuni",
    "hệ thống",
    "platform",
    "nền tảng",
    "dữ liệu",
    "data",
    "xuất",
    "export",
    "bản nháp",
    "draft",
    # smalltalk / meta allowances (conservative false-positive protection)
    "xin chào",
    "chào",
    "hello",
    "cảm ơn",
    "thank",
    "giúp",
    "help",
    "hỗ trợ",
    "assist",
    "trợ lý",
)


def partner_scope_guard(text: str, *, used_tool: bool, locale: str = "vi") -> str:
    """Deterministic recruiting-domain scope check on a partner turn's final text.

    Skipped when a tool was dispatched this turn (tool-grounded answers are
    trusted by construction). Off-scope text is replaced by a polite scoped
    refusal; on-scope/smalltalk text passes through unchanged.
    """
    return enforce_keyword_scope(
        text,
        domain_keywords=PARTNER_DOMAIN_KEYWORDS,
        refusal_text=_copy("refuse.partner_off_topic", locale),
        skip=used_tool,
    )
