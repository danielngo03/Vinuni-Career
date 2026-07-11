"""Talent Pool AI semantic search (owner-locked flagship).

A partner pastes/uploads a JD (posted OR not-yet-posted) or types skill/experience
filters -> we find the best-matching candidates in the consented CV pool -> an LLM
rerank returns human-readable match reasons (NEVER a raw score) -> a deterministic
keyword+filter fallback keeps working when AI is off/over-budget.

Design (mirrors ``recruitment.cv_evaluation_service``):

- **No pgvector.** Candidate vectors live in ``cv_embeddings.vector`` (portable
  JSONB) and are ranked in Python via ``top_k_by_cosine``. Local scale = hundreds
  of CVs, so a full in-process scan is fine.
- **RBAC.** Requires the candidate-access capability (``candidate_identity:view_cv``
  — grep the catalog, never a hardcoded role). Superadmin bypasses. Every search is
  audited (actor / filters / result count / fallback) with NO candidate PII.
- **Consent + visibility.** Only discoverable students are indexed
  (``is_open_to_work`` + ``profile_visibility != private``); at search time an
  external partner sees only ``public`` profiles, VinUni personas + superadmin also
  see ``vinuni_only``. (Owner follow-up: a first-class ``talent_pool_opt_in``
  consent flag should replace this proxy — no new column added this wave.)
- **Metered.** The rerank is one governed gateway call with a partner
  ``UsageContext`` (budget pre-check + durable idempotent ledger).
- **Guardrails.** Candidate CV text is treated as untrusted data (instruction
  strip via the gateway input guard + anonymized cards that omit name/contact so
  the model can't bias on identity); reasons are output-guarded (provider/brand/
  key scrub) and score-stripped; a bias-flagged reason set is dropped for the
  deterministic reasons. No provider/model/token/embedding-dim/cosine leakage.
- **Never 500.** AI down / over budget / offline -> deterministic keyword+skill
  overlap ranking with rules-based tier + reasons.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import runtime_config
from app.ai.gateway.base import AIMessage
from app.ai.gateway.factory import real_provider_active
from app.ai.gateway.task_runner import AiTaskRunner
from app.ai.observability import billable_usage
from app.ai.prompts.talent_match import v1 as talent_prompt
from app.ai.retrieval.embeddings import embed_single, top_k_by_cosine
from app.ai.safety.bias_detection import check_bias
from app.ai.safety.output_guard import guard_completion
from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.student_profiles.application import talent_facade
from app.modules.talent_pool.domain.models import CvEmbedding
from app.shared.audit import AuditContext, write_audit
from app.shared.exceptions import (
    AIUnavailableError,
    PaymentRequiredError,
    ValidationFailedError,
)
from app.shared.permissions import Principal, permission_checker

# The candidate-access capability (grepped from
# ``organization.domain.catalog.PERMISSION_CATALOG``) — never a hardcoded role.
_RESOURCE = "candidate_identity"
_ACTION = "view_cv"

_TASK_TYPE = "talent_match"
_FEATURE = billable_usage.FEATURE_RERANK
_MAX_TOKENS = 900
_RERANK_POOL = 30  # candidates sent to the LLM rerank (page-bounded)
_MAX_PAGE = 20
_DEFAULT_PAGE = 12

_VINUNI_PERSONAS = frozenset({"student", "alumni", "university_staff"})

_TIERS = talent_prompt.VALID_TIERS  # excellent > strong > moderate > exploratory
_TIER_RANK = {t: i for i, t in enumerate(reversed(_TIERS))}  # exploratory=0 … excellent=3

# ------------------------------------------------------------------ #
# Tokenization + deterministic scoring (pure — exercised by the eval  #
# harness and unit tests without a DB).                               #
# ------------------------------------------------------------------ #

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#-]{1,}", re.I)
# Strip anything that looks like a leaked numeric score / similarity / percent.
_SCORE_RE = re.compile(
    r"\b(?:score|similarity|confidence|match|cosine|rank)\b\s*[:=]?\s*\d+(?:\.\d+)?%?",
    re.I,
)
_BARE_PERCENT_RE = re.compile(r"\b\d{1,3}\s?%")
_BARE_FLOAT_RE = re.compile(r"\b0?\.\d{2,}\b")
# Defence-in-depth PII strip on any reason the model returns (the gateway input
# guard already redacts the CV text it sees; this guards the OUTPUT too).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_DIGITS_RE = re.compile(r"\d{7,}")

_STOPWORDS = frozenset(
    {
        "and",
        "the",
        "for",
        "with",
        "you",
        "your",
        "our",
        "will",
        "are",
        "who",
        "job",
        "role",
        "work",
        "team",
        "have",
        "has",
        "from",
        "this",
        "that",
        "must",
        "should",
        "years",
        "year",
        "experience",
    }
)


def tokenize(text: str) -> set[str]:
    """Lowercase job-relevant term set (drops stopwords + 1-char tokens)."""

    if not text:
        return set()
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) > 1 and t.lower() not in _STOPWORDS
    }


def tier_from_fraction(fraction: float) -> str:
    """Map a deterministic overlap fraction (0..1) to a categorical tier."""

    if fraction >= 0.6:
        return "excellent"
    if fraction >= 0.4:
        return "strong"
    if fraction >= 0.15:
        return "moderate"
    return "exploratory"


def deterministic_match(
    *,
    query_terms: set[str],
    required_skills: list[str],
    candidate_skills: list[str],
    candidate_text: str,
) -> tuple[float, list[str], list[str]]:
    """Return ``(overlap_fraction, matched_skills, missing_required_skills)``.

    Skill hits are weighted 2x term hits. ``matched_skills`` are the candidate
    skills that appear in the query; ``missing`` are required skills with no
    candidate evidence — the deterministic "gap" signal.
    """

    cand_skill_set = {s.lower().strip() for s in candidate_skills if s}
    cand_tokens = tokenize(candidate_text) | cand_skill_set
    req = [s.lower().strip() for s in required_skills if s and s.strip()]

    matched_skills = sorted(
        {s for s in cand_skill_set if s in query_terms}
        | {r for r in req if r in cand_skill_set or _skill_in_tokens(r, cand_tokens)}
    )
    missing = [r for r in req if r not in cand_skill_set and not _skill_in_tokens(r, cand_tokens)]

    term_hits = len(query_terms & cand_tokens)
    skill_hits = len(matched_skills)
    denom = max(len(query_terms) + len(req), 1)
    fraction = min(1.0, (term_hits + 2 * skill_hits) / (denom + len(req)))
    return fraction, matched_skills[:8], missing[:6]


def _skill_in_tokens(skill: str, tokens: set[str]) -> bool:
    """True when a (possibly multi-word) skill is evidenced by the token set."""

    parts = list(tokenize(skill))
    return bool(parts) and all(p in tokens for p in parts)


def deterministic_reasons(
    *, matched_skills: list[str], missing: list[str], years: int | None, locale: str
) -> list[str]:
    """Rules-based, human-readable reasons (no score) for the fallback path."""

    vi = locale != "en"
    reasons: list[str] = []
    if matched_skills:
        top = ", ".join(matched_skills[:4])
        reasons.append(
            f"Khớp kỹ năng: {top}" if vi else f"Matches on {top}"
        )
    if isinstance(years, int) and years > 0:
        reasons.append(
            f"Khoảng {years} năm kinh nghiệm liên quan"
            if vi
            else f"~{years} yrs of relevant experience"
        )
    if missing:
        gap = ", ".join(missing[:3])
        reasons.append(
            f"Chưa thấy bằng chứng: {gap}" if vi else f"{gap} not evidenced"
        )
    if not reasons:
        reasons.append(
            "Khớp một phần với yêu cầu" if vi else "Partial match on the requirements"
        )
    return reasons[:3]


def scrub_reason(text: str) -> str:
    """Output-guard one reason string: provider/brand/key scrub + score strip."""

    cleaned = guard_completion(text)
    cleaned = _EMAIL_RE.sub("", cleaned)
    cleaned = _SCORE_RE.sub("", cleaned)
    cleaned = _BARE_PERCENT_RE.sub("", cleaned)
    cleaned = _BARE_FLOAT_RE.sub("", cleaned)
    cleaned = _LONG_DIGITS_RE.sub("", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip(" .,:;-")[:200]


def normalize_rerank(raw_json: dict, *, valid_refs: set[int]) -> dict[int, dict]:
    """Validate + clamp an LLM rerank payload into ``{ref: {tier, reasons}}``.

    Pure function. Unknown refs are dropped, unknown tiers neutralized to
    ``moderate``, reasons scrubbed + capped (max 3, max 200 chars each). A reason
    set that trips the bias guard is discarded (caller falls back to deterministic
    reasons for that ref).
    """

    out: dict[int, dict] = {}
    candidates = raw_json.get("candidates")
    if not isinstance(candidates, list):
        return out
    for item in candidates:
        if not isinstance(item, dict):
            continue
        ref = item.get("ref")
        if not isinstance(ref, int) or ref not in valid_refs or ref in out:
            continue
        tier = item.get("tier")
        if tier not in _TIERS:
            tier = "moderate"
        reasons_raw = item.get("reasons")
        reasons: list[str] = []
        if isinstance(reasons_raw, list):
            for r in reasons_raw:
                if isinstance(r, str):
                    s = scrub_reason(r)
                    if s:
                        reasons.append(s)
                if len(reasons) >= 3:
                    break
        # Fairness guard: drop the model reasons if any protected-attribute phrasing
        # slipped through; the caller substitutes deterministic reasons.
        if reasons and check_bias(" ".join(reasons)).requires_human_review:
            reasons = []
        out[ref] = {"tier": tier, "reasons": reasons}
    return out


# ------------------------------------------------------------------ #
# Public entry point                                                 #
# ------------------------------------------------------------------ #


async def search_talent(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    query_text: str | None = None,
    jd_text: str | None = None,
    skills: list[str] | None = None,
    min_experience: int | None = None,
    limit: int = _DEFAULT_PAGE,
    offset: int = 0,
    locale: str = "vi",
) -> dict:
    """Rank consented candidates for a hiring need. Never raises for AI failure."""

    # RBAC: the candidate-access capability (global talent pool, not org-scoped).
    permission_checker.require(principal, _RESOURCE, _ACTION)

    skills = [s.strip() for s in (skills or []) if s and s.strip()][:25]
    query_text = (query_text or "").strip()[:1000] or None
    jd_text = (jd_text or "").strip()[:8000] or None
    if not query_text and not jd_text and not skills:
        raise ValidationFailedError(
            "Provide a JD, search text, or at least one skill.",
            details={"reason": "empty_query"},
        )

    limit = max(1, min(limit, _MAX_PAGE))
    offset = max(0, offset)

    need_text = jd_text or query_text or ""
    query_terms = tokenize(f"{need_text} {' '.join(skills)} {query_text or ''}")

    # 1) Load the consented, visibility-scoped candidate pool.
    pool = await _load_pool(session, principal=principal)

    # 2) Filter (skills AND + min_experience).
    filtered = [row for row in pool if _passes_filters(row, skills, min_experience)]

    # 3) Rank (semantic when a real provider is live, else deterministic keyword).
    ranked = await _rank(
        filtered, query_terms=query_terms, required_skills=skills, need_text=need_text
    )

    # 4) Dedup to the best CV per candidate, then paginate.
    deduped = _dedup_by_user(ranked)
    total = len(deduped)
    page = deduped[offset : offset + limit]

    # 5) Reasons: LLM rerank for the page (metered) with deterministic fallback.
    reasons_by_index, used_ai = await _reasons_for_page(
        session,
        principal=principal,
        page=page,
        need_text=need_text,
        required_skills=skills,
        locale=locale,
    )

    items = await _shape_items(session, page=page, reasons_by_index=reasons_by_index, locale=locale)

    await _audit_search(
        session,
        principal=principal,
        ctx=ctx,
        filters={"has_jd": bool(jd_text), "skills": skills, "min_experience": min_experience},
        result_count=len(items),
        total=total,
        used_ai=used_ai,
    )
    await session.commit()

    return {
        "items": items,
        "source": "ai_semantic" if used_ai else "keyword_fallback",
        "page": {"total": total, "limit": limit, "offset": offset},
    }


# ------------------------------------------------------------------ #
# Pool loading + filtering                                            #
# ------------------------------------------------------------------ #


def _sees_vinuni_only(principal: Principal) -> bool:
    return principal.is_superadmin or principal.persona in _VINUNI_PERSONAS


async def _load_pool(session: AsyncSession, *, principal: Principal) -> list[CvEmbedding]:
    """Consented, visibility-scoped, discoverable embeddings for the caller's alias.

    Consent/visibility is resolved through ``talent_facade`` (student_profiles owns
    the ``StudentProfile`` ORM); this service only filters its OWN ``CvEmbedding``
    rows to that visible set — no cross-module ORM join.
    """

    alias = get_settings().ai_embedding_model_alias
    visible_user_ids = set(
        await talent_facade.list_discoverable_user_ids(
            session, include_vinuni_only=_sees_vinuni_only(principal)
        )
    )
    if not visible_user_ids:
        return []
    rows = (
        (
            await session.execute(
                select(CvEmbedding).where(CvEmbedding.model_alias == alias)
            )
        )
        .scalars()
        .all()
    )
    return [row for row in rows if row.user_id in visible_user_ids]


def _passes_filters(
    row: CvEmbedding, skills: list[str], min_experience: int | None
) -> bool:
    if min_experience:
        if not isinstance(row.experience_years, int) or row.experience_years < min_experience:
            return False
    if skills:
        cand = {s.lower().strip() for s in (row.skills or [])}
        cand_tokens = tokenize(row.content_text or "") | cand
        for want in skills:
            w = want.lower().strip()
            if w in cand or _skill_in_tokens(w, cand_tokens):
                continue
            return False
    return True


# ------------------------------------------------------------------ #
# Ranking                                                             #
# ------------------------------------------------------------------ #


class _Ranked:
    __slots__ = ("row", "matched_skills", "missing", "fraction")

    def __init__(
        self, row: CvEmbedding, matched_skills: list[str], missing: list[str], fraction: float
    ) -> None:
        self.row = row
        self.matched_skills = matched_skills
        self.missing = missing
        self.fraction = fraction


async def _rank(
    pool: list[CvEmbedding],
    *,
    query_terms: set[str],
    required_skills: list[str],
    need_text: str,
) -> list[_Ranked]:
    """Rank the pool. Semantic (cosine) order when a real provider is live, else
    deterministic keyword-overlap order. Evidence (matched/missing) is always
    computed deterministically so reasons never depend on the model."""

    scored: list[tuple[float, _Ranked]] = []

    evidence: dict[uuid.UUID, _Ranked] = {}
    for row in pool:
        fraction, matched, missing = deterministic_match(
            query_terms=query_terms,
            required_skills=required_skills,
            candidate_skills=list(row.skills or []),
            candidate_text=row.content_text or "",
        )
        evidence[row.id] = _Ranked(row, matched, missing, fraction)

    if real_provider_active() and pool:
        try:
            query_vec = await embed_single(need_text or " ".join(query_terms))
        except Exception:  # noqa: BLE001 — degrade to deterministic order
            query_vec = []
        if query_vec:
            candidates: list[tuple[str, Sequence[float]]] = [
                (str(row.id), list(row.vector or []))
                for row in pool
                if row.vector
            ]
            ordered = top_k_by_cosine(query_vec, candidates, k=len(candidates), min_score=-1.0)
            for cid, cos in ordered:
                rid = uuid.UUID(cid)
                ranked = evidence.get(rid)
                if ranked is not None:
                    # Cosine drives ORDER only; it is never surfaced. Blend a small
                    # deterministic term for stable tie-breaks.
                    scored.append((cos + 0.05 * ranked.fraction, ranked))
            scored.sort(key=lambda t: -t[0])
            return [r for _, r in scored]

    # Deterministic path: order by keyword/skill overlap.
    ordered_det = sorted(evidence.values(), key=lambda r: -r.fraction)
    return ordered_det


def _dedup_by_user(ranked: list[_Ranked]) -> list[_Ranked]:
    """Keep the best-ranked CV per candidate (one card per person)."""

    seen: set[uuid.UUID] = set()
    out: list[_Ranked] = []
    for r in ranked:
        if r.row.user_id in seen:
            continue
        seen.add(r.row.user_id)
        out.append(r)
    return out


# ------------------------------------------------------------------ #
# Reasons: LLM rerank (metered) with deterministic fallback          #
# ------------------------------------------------------------------ #


async def _reasons_for_page(
    session: AsyncSession,
    *,
    principal: Principal,
    page: list[_Ranked],
    need_text: str,
    required_skills: list[str],
    locale: str,
) -> tuple[dict[int, dict], bool]:
    """Return ``({page_index: {tier, reasons}}, used_ai)`` for the current page."""

    if not page:
        return {}, False

    # Deterministic baseline for every card (also the fallback for missing refs).
    baseline: dict[int, dict] = {}
    for idx, r in enumerate(page):
        baseline[idx] = {
            "tier": tier_from_fraction(r.fraction),
            "reasons": deterministic_reasons(
                matched_skills=r.matched_skills,
                missing=r.missing,
                years=r.row.experience_years,
                locale=locale,
            ),
        }

    if not real_provider_active():
        return baseline, False

    cards = [
        {
            "ref": idx,
            "skills": list(r.row.skills or [])[:20],
            "experience": _experience_lines(r.row.content_text or ""),
            "education": _education_line(r.row.content_text or ""),
            "experience_years": r.row.experience_years,
        }
        for idx, r in enumerate(page[:_RERANK_POOL])
    ]

    usage_ctx = billable_usage.UsageContext(
        actor_persona=billable_usage.PERSONA_PARTNER,
        feature_key=_FEATURE,
        task_type=_TASK_TYPE,
        billing_scope=billable_usage.SCOPE_ORG,
        actor_user_id=principal.user_id,
        org_id=principal.org_id,
        resource_type="talent_pool",
    )

    try:
        raw_text = await _run_rerank(
            session,
            need_text=need_text,
            required_skills=required_skills,
            cards=cards,
            usage_ctx=usage_ctx,
            user_id=principal.user_id,
            org_id=principal.org_id,
        )
    except (AIUnavailableError, PaymentRequiredError):
        return baseline, False

    parsed = _parse_json(raw_text)
    if parsed is None:
        return baseline, False

    reranked = normalize_rerank(parsed, valid_refs=set(range(len(cards))))
    if not reranked:
        return baseline, False

    # Merge: model tier + reasons where present/valid; deterministic elsewhere.
    merged: dict[int, dict] = dict(baseline)
    for idx, val in reranked.items():
        reasons = val.get("reasons") or baseline[idx]["reasons"]
        merged[idx] = {"tier": val.get("tier") or baseline[idx]["tier"], "reasons": reasons}

    # Best-effort durable, idempotent charge row for the successful rerank.
    try:
        await billable_usage.record_billable_usage(
            session, ctx=usage_ctx, result_status=billable_usage.RESULT_SUCCESS, base_units=1
        )
    except Exception:  # noqa: BLE001 — accounting must never break the response
        pass

    return merged, True


async def _run_rerank(
    session: AsyncSession,
    *,
    need_text: str,
    required_skills: list[str],
    cards: list[dict],
    usage_ctx: billable_usage.UsageContext,
    user_id: uuid.UUID | None,
    org_id: uuid.UUID | None,
) -> str:
    """Single governed, metered gateway completion. Returns SCRUBBED model text.

    Isolated at module level so tests can monkeypatch the model call without the
    RBAC / pool / audit orchestration around it.
    """

    runner = AiTaskRunner(
        session,
        alias=runtime_config.current().chat_model_alias,
        task_type=_TASK_TYPE,
        user_id=user_id,
        org_id=org_id,
        usage_context=usage_ctx,
        tool_class="read_only",
    )
    completion = await runner.complete(
        [
            AIMessage(role="system", content=talent_prompt.STATIC_SYSTEM_PROMPT),
            AIMessage(
                role="user",
                content=talent_prompt.build_user_message(
                    need_summary=need_text,
                    required_skills=required_skills,
                    candidate_cards=cards,
                ),
            ),
        ],
        temperature=0.2,
        max_tokens=_MAX_TOKENS,
    )
    return completion.text


# ------------------------------------------------------------------ #
# Response shaping                                                    #
# ------------------------------------------------------------------ #


async def _shape_items(
    session: AsyncSession,
    *,
    page: list[_Ranked],
    reasons_by_index: dict[int, dict],
    locale: str,
) -> list[dict]:
    if not page:
        return []
    # Safe identity cards (display name + avatar_url + location) come from the
    # student_profiles seam — this service never touches the StudentProfile ORM.
    cards = await talent_facade.talent_cards(session, user_ids=[r.row.user_id for r in page])

    items: list[dict] = []
    for idx, r in enumerate(page):
        rr = reasons_by_index.get(idx, {})
        card = cards.get(r.row.user_id)
        items.append(
            {
                # Identity summary — RBAC-gated (candidate_access) + audited above.
                "profile_id": str(card.profile_id) if card else None,
                "display_name": (card.display_name if card else None) or "Student",
                "avatar_url": card.avatar_url if card else None,
                "location_city": card.location_city if card else None,
                "location_country": card.location_country if card else None,
                # Match summary — categorical tier + human-readable reasons ONLY.
                # NEVER a raw cosine/confidence number, provider/model, or token.
                "match_tier": rr.get("tier") or tier_from_fraction(r.fraction),
                "match_reasons": rr.get("reasons") or [],
                "matched_skills": r.matched_skills,
            }
        )
    return items


# ------------------------------------------------------------------ #
# Small helpers                                                       #
# ------------------------------------------------------------------ #


def _experience_lines(content_text: str) -> list[str]:
    """Best-effort experience lines from the stored matching text (for the cards)."""

    lines = [ln.strip() for ln in (content_text or "").splitlines() if " · " in ln]
    return lines[:6]


def _education_line(content_text: str) -> str:
    for ln in (content_text or "").splitlines():
        low = ln.lower()
        if any(h in low for h in ("bsc", "msc", "university", "bachelor", "master", "degree")):
            return ln.strip()[:160]
    return ""


def _parse_json(raw: str) -> dict | None:
    import json

    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def _audit_search(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: RequestContext,
    filters: dict,
    result_count: int,
    total: int,
    used_ai: bool,
) -> None:
    await write_audit(
        session,
        action="talent_pool.searched",
        resource_type="talent_pool",
        resource_id=None,
        context=AuditContext(
            actor_id=principal.user_id,
            actor_org_id=principal.org_id,
            ip=ctx.ip,
            user_agent=ctx.user_agent,
        ),
        after={
            "filters": filters,
            "result_count": result_count,
            "total": total,
            "used_ai": used_ai,
        },
    )
