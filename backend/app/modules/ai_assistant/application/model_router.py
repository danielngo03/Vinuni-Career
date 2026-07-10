"""Deterministic multi-tier model routing + tool-subset selection for chat turns.

No LLM is ever called here (a routing LLM would add cost/latency and create a
guard-bypass surface). A rule-based classifier looks at the user's turn and
returns a :class:`RouteDecision`:

- ``model_alias`` — which *alias* (never a provider/model id) should serve the
  turn. Tiers: ``chat_cheap`` for greetings/smalltalk/meta questions that will
  not need tools; the configured chat default for standard operational asks;
  the reasoning alias ONLY for explicit deep-analysis intents.
- ``tool_groups`` — which intent groups of tools to advertise to the model.
  Today ~26 tool JSON schemas ship with every partner turn; passing only the
  matched groups plus a small always-on core set is a large token saving.
- ``escalate_alias`` — the single one-step-up retry alias the turn driver may
  use when the chosen tier returns an empty/failed completion (at most ONE
  escalation per turn; enforced by the caller).

Fail-open contract: when classification is NOT confident (no group matched, or
mixed signals) the caller must pass the FULL tool set — a wrong subset must
never silently remove a capability. :func:`select_specs` implements that rule
and also tolerates group members that do not exist (yet) in the registry.

Aliases are internal-only vocabulary (AI_PRODUCT_SPEC §5.1); they are never
surfaced to any user-facing response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.ai_assistant.application.tools.specs import ToolSpec

# --------------------------------------------------------------------------- #
# Tiers                                                                        #
# --------------------------------------------------------------------------- #

TIER_CHEAP = "cheap"
TIER_DEFAULT = "default"
TIER_REASONING = "reasoning"

# The cheap tier is a fixed builtin alias; default/reasoning come from the
# runtime snapshot so superadmin re-binding keeps working.
_CHEAP_ALIAS = "chat_cheap"


# --------------------------------------------------------------------------- #
# Tool intent groups (names only — resolved against the live registry later)   #
# --------------------------------------------------------------------------- #

CORE_GROUP = "core"

TOOL_GROUPS: dict[str, frozenset[str]] = {
    "jobs": frozenset({"get_partner_jobs", "get_job_detail", "export_jobs"}),
    "pipeline": frozenset(
        {
            "get_partner_pipeline_summary",
            "search_partner_candidates",
            "get_candidate_detail",
            "move_candidate_stage",
            "job_stats",
            "pipeline_summary",
            "search_candidates",
            "generate_screening_brief",
            "suggest_scorecard",
            "export_applications",
            "export_interviews",
            "export_offers",
        }
    ),
    "analytics": frozenset(
        {
            "get_recruitment_analytics_chart",
            "get_hiring_funnel_diagram",
            "recruiting_analytics",
        }
    ),
    "jd": frozenset(
        {
            "draft_job_description",
            "rewrite_job_description",
            "check_jd_bias",
            "draft_job_from_attachment",
            "draft_job_from_text",
            "validate_job_draft",
            "create_job",
        }
    ),
    "media": frozenset({"generate_image"}),
    "events": frozenset(
        {
            "get_upcoming_partner_events",
            "search_events",
            "get_upcoming_events",
            "export_events",
        }
    ),
    "knowledge": frozenset(
        {
            "knowledge_base_query",
            "get_career_advice",
            "get_salary_benchmark",
            "get_company_detail",
            "search_companies",
            "get_company_reviews",
        }
    ),
    CORE_GROUP: frozenset({"analyze_attachment"}),
}

# Keyword → group signals (lowercase substring match on the user turn; vi + en).
# Broad on purpose: several groups may match one turn and their union is passed.
_GROUP_SIGNALS: dict[str, tuple[str, ...]] = {
    "jobs": (
        "tin tuyển dụng",
        "job posting",
        "bài đăng",
        "đăng tuyển",
        "job của tôi",
        "danh sách job",
        "các job",
        "vị trí đang mở",
        "posting",
        "job",
        "việc làm",
    ),
    "pipeline": (
        "ứng viên",
        "candidate",
        "pipeline",
        "vòng",
        "stage",
        "sàng lọc",
        "screening",
        "scorecard",
        "phiếu đánh giá",
        "phỏng vấn",
        "interview",
        "offer",
        "đề nghị",
        "applicant",
        "application",
        "đơn ứng tuyển",
        "hồ sơ",
        "cv",
        "talent",
        "shortlist",
        "xuất danh sách",
        "export",
    ),
    "analytics": (
        "biểu đồ",
        "chart",
        "funnel",
        "phễu",
        "thống kê",
        "báo cáo",
        "report",
        "analytics",
        "chuyển đổi",
        "conversion",
        "tỉ lệ",
        "tỷ lệ",
        "hiệu quả tuyển",
        "số liệu",
        "metric",
    ),
    "jd": (
        "jd",
        "mô tả công việc",
        "job description",
        "viết tin",
        "soạn tin",
        "viết jd",
        "soạn jd",
        "draft",
        "bản nháp",
        "viết lại",
        "rewrite",
        "bias",
        "thiên vị",
        "tạo job",
        "tạo tin",
        "đăng tin",
        "create job",
        "yêu cầu tuyển dụng",
    ),
    "media": (
        "ảnh",
        "hình",
        "image",
        "banner",
        "poster",
        "logo",
        "visual",
        "thiết kế",
    ),
    "events": (
        "sự kiện",
        "event",
        "career fair",
        "hội chợ",
        "webinar",
        "workshop",
        "ngày hội",
    ),
    "knowledge": (
        "chính sách",
        "policy",
        "hướng dẫn",
        "quy định",
        "kiến thức",
        "knowledge",
        "lương",
        "salary",
        "benchmark",
        "công ty",
        "company",
        "review",
        "thị trường",
        "market",
        "tư vấn",
        "advice",
    ),
}

# Explicit deep-analysis intents → reasoning tier. Deliberately narrow: the
# reasoning model is slower and pricier, so only unmistakable asks route there.
_REASONING_SIGNALS: tuple[str, ...] = (
    "phân tích sâu",
    "phân tích chuyên sâu",
    "phân tích kỹ",
    "so sánh",
    "chiến lược",
    "đánh giá toàn diện",
    "đánh giá tổng thể",
    "toàn diện",
    "nguyên nhân gốc",
    "deep analysis",
    "in-depth",
    "in depth",
    "compare",
    "comparison",
    "strategy",
    "strategic",
    "comprehensive",
    "root cause",
    "trade-off",
    "tradeoff",
)

# Long analytical asks also earn the reasoning tier (length + analytic verb).
_ANALYTIC_HINTS: tuple[str, ...] = (
    "phân tích",
    "đánh giá",
    "analy",
    "assess",
    "vì sao",
    "tại sao",
    "why",
    "giải thích",
    "explain",
)
_REASONING_MIN_CHARS = 350

# Smalltalk / meta turns that need no tools and no big model. Conservative:
# these must clearly be conversational filler or capability questions.
_SMALLTALK_RE = re.compile(
    r"^\s*("
    r"(xin\s+)?ch[àa]o(\s+b[ạa]n)?|hello|hi|hey|alo"
    r"|c[ảa]m\s*[ơo]n(\s+b[ạa]n)?(\s+nhi[ềe]u)?|thanks?(\s+you)?|thank\s+you"
    r"|ok(ay)?|đ[ưu][ợo]c\s+r[ồo]i|tuy[ệe]t(\s+v[ờo]i)?|great|nice|good\s+job"
    r"|t[ạa]m\s+bi[ệe]t|bye|goodbye"
    r")[\s!.,?~]*$",
    re.IGNORECASE,
)
_META_SIGNALS: tuple[str, ...] = (
    "bạn có thể làm gì",
    "bạn làm được gì",
    "bạn giúp được gì",
    "khả năng của bạn",
    "what can you do",
    "what can you help",
    "how can you help",
    "bạn là ai",
    "who are you",
)
_CHEAP_MAX_CHARS = 40


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Deterministic routing outcome for one user turn (internal-only)."""

    tier: str
    model_alias: str
    tool_groups: tuple[str, ...]
    confident: bool
    escalate_alias: str | None

    @property
    def escalate_allowed(self) -> bool:
        return self.escalate_alias is not None


def _resolve_aliases() -> tuple[str, str]:
    """(default_alias, reasoning_alias) from the runtime snapshot (never exposed)."""
    from app.ai.gateway import runtime_config

    cfg = runtime_config.current()
    return cfg.chat_model_alias, cfg.reasoning_model_alias


def _matched_groups(lowered: str) -> tuple[str, ...]:
    groups: list[str] = []
    for group, signals in _GROUP_SIGNALS.items():
        if any(signal in lowered for signal in signals):
            groups.append(group)
    return tuple(groups)


def _is_smalltalk(text: str, lowered: str) -> bool:
    if _SMALLTALK_RE.match(text):
        return True
    return any(signal in lowered for signal in _META_SIGNALS)


def _wants_reasoning(lowered: str) -> bool:
    if any(signal in lowered for signal in _REASONING_SIGNALS):
        return True
    if len(lowered) >= _REASONING_MIN_CHARS and any(h in lowered for h in _ANALYTIC_HINTS):
        return True
    return False


def route_turn(text: str) -> RouteDecision:
    """Classify one user turn into (tier, tool groups) — deterministic, no LLM.

    Fail-open: any ambiguity resolves to the default tier with an empty,
    non-confident group set (→ the caller passes the full tool set).
    """
    default_alias, reasoning_alias = _resolve_aliases()
    lowered = (text or "").strip().lower()
    groups = _matched_groups(lowered)

    if _wants_reasoning(lowered):
        return RouteDecision(
            tier=TIER_REASONING,
            model_alias=reasoning_alias,
            tool_groups=groups,
            confident=bool(groups),
            escalate_alias=None,  # already the top tier — no further escalation
        )

    if _is_smalltalk(text or "", lowered) and not groups:
        return RouteDecision(
            tier=TIER_CHEAP,
            model_alias=_CHEAP_ALIAS,
            tool_groups=(CORE_GROUP,),
            confident=True,
            escalate_alias=default_alias,
        )

    if not groups and len(lowered) <= _CHEAP_MAX_CHARS and not any(c.isdigit() for c in lowered):
        # Very short factual/conversational ask with no tool intent detected.
        return RouteDecision(
            tier=TIER_CHEAP,
            model_alias=_CHEAP_ALIAS,
            tool_groups=(),
            confident=False,  # fail-open: full tool set, just a cheaper model
            escalate_alias=default_alias,
        )

    return RouteDecision(
        tier=TIER_DEFAULT,
        model_alias=default_alias,
        tool_groups=groups,
        confident=bool(groups),
        escalate_alias=reasoning_alias,
    )


def select_specs(specs: list[ToolSpec], decision: RouteDecision) -> list[ToolSpec]:
    """Return the tool subset for this turn, failing open to the full set.

    Rules:
    - not confident OR no groups matched → full set (never silently drop a
      capability on a guess);
    - otherwise: union of the matched groups plus the always-on core group;
    - group members missing from the live registry are tolerated (other lanes
      add tools in parallel);
    - an empty subset (all matched names unavailable to this caller) → full set.
    """
    if not decision.confident or not decision.tool_groups:
        return specs
    allowed: set[str] = set(TOOL_GROUPS[CORE_GROUP])
    for group in decision.tool_groups:
        allowed |= TOOL_GROUPS.get(group, frozenset())
    subset = [s for s in specs if s.name in allowed]
    return subset or specs
