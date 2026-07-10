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

# Groups are persona-agnostic supersets. ``select_specs`` intersects the matched
# groups with the CALLER's already grant-filtered spec list, so a group may list
# both partner and student tools safely — a caller only ever sees the subset they
# are authorized for, and an empty intersection fails open to their full set. The
# student read/analysis tools were added here so a routed student turn advertises
# a complete, relevant subset (never a partial one that silently drops a needed
# capability).
TOOL_GROUPS: dict[str, frozenset[str]] = {
    "jobs": frozenset(
        {
            # partner
            "get_partner_jobs",
            "export_jobs",
            # shared / student
            "get_job_detail",
            "search_jobs",
            "recommend_jobs",
            "get_saved_jobs",
            "match_cv_to_jobs",
            "compare_jobs",
        }
    ),
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
    # Student CV↔job intelligence: viewing/comparing CVs, matching, fit breakdown,
    # skill gaps. No partner tools here (partner never has these), so a student
    # "cv/fit" turn gets exactly this set.
    "cv": frozenset(
        {
            "get_my_cvs",
            "show_cv",
            "compare_cvs",
            "match_cv_to_jobs",
            "explain_job_fit",
            "get_skill_gap",
            "recommend_jobs",
        }
    ),
    # Student application/interview status.
    "applications": frozenset(
        {
            "get_my_applications",
            "get_upcoming_interviews",
            "get_job_alerts",
            "set_job_alert",
        }
    ),
    "interview": frozenset({"start_interview_sim"}),
    "profile": frozenset({"get_profile_status", "get_job_alerts"}),
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
            "get_my_registered_events",
            "register_for_event",
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
        # student job discovery / recommendation
        "tìm việc",
        "thực tập",
        "internship",
        "intern",
        "gợi ý việc",
        "recommend",
        "việc phù hợp",
        "vị trí phù hợp",
        "so sánh job",
        "so sánh việc",
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
    # Student CV↔job intelligence (view/compare CVs, matching, fit, skill gap).
    "cv": (
        "cv",
        "resume",
        "hồ sơ",
        "kỹ năng",
        "skill",
        "phù hợp",
        "fit",
        "độ phù hợp",
        "so sánh cv",
        "cv nào",
        "match cv",
        "job fit",
        "khoảng cách kỹ năng",
        "skill gap",
        "cải thiện cv",
        "review cv",
        "đánh giá cv",
    ),
    # Student application + interview status.
    "applications": (
        "ứng tuyển",
        "đơn ứng tuyển",
        "đơn của tôi",
        "application",
        "đã nộp",
        "trạng thái đơn",
        "lịch phỏng vấn",
        "job alert",
        "thông báo việc",
    ),
    "interview": (
        "phỏng vấn",
        "interview",
        "mock interview",
        "luyện phỏng vấn",
        "phỏng vấn thử",
        "chuẩn bị phỏng vấn",
    ),
    "profile": (
        "profile",
        "hồ sơ cá nhân",
        "open to work",
        "trạng thái hồ sơ",
        "mức độ hoàn thiện",
    ),
    "events": (
        "sự kiện",
        "event",
        "career fair",
        "hội chợ",
        "webinar",
        "workshop",
        "ngày hội",
        "đăng ký sự kiện",
        "sự kiện của tôi",
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


# --------------------------------------------------------------------------- #
# Leak-safe status phases (FROZEN vocabulary — never a tool/provider/model name)#
# --------------------------------------------------------------------------- #
#
# The native loop streams a ``{"type": "status", "code": <phase>}`` event to the
# client to describe *what kind of work* is happening. The phase MUST be one of
# the codes below — it describes the KIND of work (retrieving / analyzing / …)
# and never reveals WHICH tool ran, so a status event can never leak a tool
# name, provider, or model id (AI_PRODUCT_SPEC §15 / ai.md privacy rules). The
# frontend renders these directly and maps any unknown code to a generic label.

PHASE_UNDERSTANDING = "understanding"
PHASE_RETRIEVING = "retrieving"
PHASE_ANALYZING = "analyzing"
PHASE_DRAFTING = "drafting"
PHASE_VISUALIZING = "visualizing"
PHASE_EXPORTING = "exporting"
PHASE_GENERATING_IMAGE = "generating_image"
PHASE_COMPOSING = "composing"

LEAK_SAFE_PHASES: frozenset[str] = frozenset(
    {
        PHASE_UNDERSTANDING,
        PHASE_RETRIEVING,
        PHASE_ANALYZING,
        PHASE_DRAFTING,
        PHASE_VISUALIZING,
        PHASE_EXPORTING,
        PHASE_GENERATING_IMAGE,
        PHASE_COMPOSING,
    }
)

# Per-tool phase overrides, evaluated before the group fallback. Each set groups
# tools by the *kind* of work they do so the FE label stays meaningful without
# ever exposing the tool identity.
_PHASE_VISUALIZING_TOOLS: frozenset[str] = frozenset(
    {
        "get_recruitment_analytics_chart",
        "get_hiring_funnel_diagram",
        "recruiting_analytics",
        "pipeline_summary",
    }
)
_PHASE_DRAFTING_TOOLS: frozenset[str] = frozenset(
    {
        "draft_job_description",
        "draft_job_from_text",
        "draft_job_from_attachment",
        "rewrite_job_description",
        "check_jd_bias",
        "validate_job_draft",
    }
)
_PHASE_ANALYZING_TOOLS: frozenset[str] = frozenset(
    {
        "create_job",
        "move_candidate_stage",
        # Student CV↔job intelligence — matching / fit / comparison is "analysis"
        # work, not a plain retrieval (still leak-safe: never the tool name).
        "match_cv_to_jobs",
        "explain_job_fit",
        "compare_jobs",
        "compare_cvs",
        "get_skill_gap",
    }
)


def phase_for_tool(name: str) -> str:
    """Map a tool NAME to a leak-safe status phase (pure; no I/O, no LLM).

    Precedence: image → ``export_*`` prefix → explicit visualizing / drafting /
    analyzing overrides → default ``retrieving`` (jobs / pipeline / events /
    knowledge read tools, ``analyze_attachment``, ``knowledge_base_query``, and
    anything unrecognised — a safe generic phase that never leaks a capability).
    The return value is ALWAYS a member of :data:`LEAK_SAFE_PHASES`.
    """
    n = name or ""
    if n == "generate_image":
        return PHASE_GENERATING_IMAGE
    if n.startswith("export_"):
        return PHASE_EXPORTING
    if n in _PHASE_VISUALIZING_TOOLS:
        return PHASE_VISUALIZING
    if n in _PHASE_DRAFTING_TOOLS:
        return PHASE_DRAFTING
    if n in _PHASE_ANALYZING_TOOLS:
        return PHASE_ANALYZING
    return PHASE_RETRIEVING
