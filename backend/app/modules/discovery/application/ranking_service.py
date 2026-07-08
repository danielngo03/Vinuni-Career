"""The recommendation/ranking layer (spec §5): organic relevance, honest source
labels, sponsored-slot separation, diversity, and user-safe reason codes.

This orchestrates the read facades (it imports NO other module's ORM):

- ``opportunities.ranking_read`` — eligibility-filtered candidate data (the SAME
  public-visibility predicate as ``GET /jobs``);
- ``advertising.inventory_facade`` — currently-live sponsored placements + the
  mandatory disclosure (sponsored fills *defined slots only*, never overrides
  organic order);
- ``documents.cv_ranking_facade`` — the caller's active CVs for deterministic
  ``cv_fit`` (reusing ``app.ai.cv.job_fit``; NO AI call, NO provider internals);
- ``student_profiles.preferences_facade`` — confirmed preference signals;
- the guest ``discovery_session`` coarse tags (resolved by the router) for
  "because you searched X" / "similar roles in Finance" reasons.

A list is labelled ``recommended`` ONLY when a real personalization signal exists;
otherwise it honestly falls back to ``recent`` / ``popular`` (never a silent
mislabel). The product ``score`` is a 0-100 product score, never a model
confidence — and no provider/model/token/embedding internal is ever produced.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import job_fit
from app.core.config import get_settings
from app.modules.advertising.application import inventory_facade
from app.modules.advertising.domain import targeting as ad_targeting
from app.modules.discovery.application import frequency_cap, snapshot_service
from app.modules.discovery.domain import allowlist, ranking, taxonomy
from app.modules.discovery.domain.search_log_model import SearchLog
from app.modules.documents.application import cv_ranking_facade
from app.modules.opportunities.application import ranking_read, saved_jobs_service
from app.modules.opportunities.application.ranking_read import RankingCandidate
from app.modules.student_profiles.application import preferences_facade
from app.modules.student_profiles.application.preferences_facade import (
    RankingPreferences,
)
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal

# Candidate pool caps (bounded reads; the ranker re-orders in Python).
_POOL_CAP = 60
_SIMILAR_POOL_CAP = 80
_POPULAR_POOL_CAP = 200
_MAX_QUERY_TERMS = 6
# Recent typed searches (from ``search_logs``) that also personalize job ranking:
# a single indexed read bounded by window + limit (NOT a multi-domain join).
_SEARCH_LOG_LOOKBACK_DAYS = 7
_SEARCH_LOG_QUERY_LIMIT = 10


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _age_days(last_seen_iso: str | None, *, now: datetime) -> float | None:
    """Days since a coarse tag's ``last_seen`` (``None`` for legacy → no decay)."""

    if not last_seen_iso:
        return None
    try:
        dt = datetime.fromisoformat(last_seen_iso)
    except ValueError:
        return None
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return max(0.0, (now - aware).total_seconds() / 86400.0)


def _session_weights(
    tags: dict | None, keys: tuple[str, ...], *, now: datetime
) -> dict[str, float]:
    """Collapse weighted coarse tags across ``keys`` into value → freq×decay weight.

    Reads the PII-free ``{value: {count, last_seen}}`` shape (legacy bare lists read
    as ``count=1`` / no decay) and applies :func:`ranking.session_signal_weight`, so
    the ranker sees a live, frequency- and recency-aware strength per coarse value.
    """

    weights: dict[str, float] = {}
    for key in keys:
        for value, count, last_seen_iso in allowlist.weighted_entries(tags, key):
            weight = ranking.session_signal_weight(
                count, _age_days(last_seen_iso, now=now)
            )
            if weight > weights.get(value, 0.0):
                weights[value] = weight
    return weights


def _days_since(dt: datetime | None, *, now: datetime) -> float | None:
    aware = _aware(dt)
    if aware is None:
        return None
    return max(0.0, (now - aware).total_seconds() / 86400.0)


# --------------------------------------------------------------------------- #
# Request context (resolved signals shared across the candidate loop)         #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _RankCtx:
    now: datetime
    locale: str
    stale_days: int
    query_terms: list[str]
    # Value → frequency×decay weight (freshly recomputed per request from the
    # coarse ``{count, last_seen}`` tags), consumed by ``_session_component``.
    session_category_weights: dict[str, float]
    session_role_family_weights: dict[str, float]
    cv_inputs: list[job_fit.CvInput]
    prefs: RankingPreferences | None
    saved_employment_types: list[str] = field(default_factory=list)
    saved_raw_titles: list[str] = field(default_factory=list)
    saved_skills: list[str] = field(default_factory=list)
    # Request-level signal availability (drives the honest list source label).
    has_query: bool = field(default=False)
    has_cv: bool = field(default=False)
    has_pref: bool = field(default=False)
    has_session: bool = field(default=False)
    has_saved: bool = field(default=False)

    @property
    def list_has_signal(self) -> bool:
        return ranking.has_signal(
            query=1.0 if self.has_query else None,
            cv=1.0 if self.has_cv else None,
            preference=1.0 if self.has_pref else None,
            session=1.0 if self.has_session else None,
            saved=1.0 if self.has_saved else None,
        )


async def _recent_search_terms(
    session: AsyncSession, discovery_session_id: uuid.UUID, *, now: datetime
) -> list[str]:
    """Recent typed searches for this session from ``search_logs`` (newest first).

    Unifies the previously-disconnected keyword store with the ranker: a bounded,
    session-scoped, indexed read (``ix_search_logs_session_created``) — never a
    heavy join. A failure here must never 500 discovery (caller guards).
    """

    cutoff = now - timedelta(days=_SEARCH_LOG_LOOKBACK_DAYS)
    rows = await session.execute(
        select(SearchLog.query)
        .where(
            SearchLog.session_id == discovery_session_id,
            SearchLog.created_at >= cutoff,
        )
        .order_by(SearchLog.created_at.desc())
        .limit(_SEARCH_LOG_QUERY_LIMIT)
    )
    return [q for (q,) in rows.all()]


async def _build_ctx(
    session: AsyncSession,
    *,
    principal: Principal,
    cookie_tags: dict | None,
    q: str | None,
    locale: str,
    discovery_session_id: uuid.UUID | None = None,
) -> _RankCtx:
    settings = get_settings()
    now = _now()
    tags = cookie_tags or {}

    # Query terms: explicit ``q`` → recorded coarse ``search_terms`` → recent typed
    # searches from ``search_logs``. De-duped by normalized form so a term recorded
    # in BOTH stores is never double-counted.
    query_terms: list[str] = []
    seen: set[str] = set()

    def _add_term(raw: str | None) -> None:
        if not raw or len(query_terms) >= _MAX_QUERY_TERMS:
            return
        norm = taxonomy.normalize(raw)
        if norm and norm not in seen:
            seen.add(norm)
            query_terms.append(raw.strip())

    if q:
        _add_term(q)
    for term in allowlist.coarse_values(tags, "search_terms"):
        _add_term(term)
    if discovery_session_id is not None and len(query_terms) < _MAX_QUERY_TERMS:
        try:
            recent = await _recent_search_terms(
                session, discovery_session_id, now=now
            )
        except Exception:  # noqa: BLE001 — a search-log read must not 500 discovery
            recent = []
        for term in recent:
            _add_term(term)

    session_category_weights = _session_weights(
        tags, ("categories", "industries"), now=now
    )
    session_role_family_weights = _session_weights(tags, ("role_families",), now=now)

    cv_inputs: list[job_fit.CvInput] = []
    prefs: RankingPreferences | None = None
    saved_signals: dict = {}
    if principal.is_authenticated and principal.persona == "student":
        try:
            cv_inputs = await cv_ranking_facade.build_cv_inputs(
                session, principal=principal
            )
        except Exception:  # noqa: BLE001 — a CV-read failure must not 500 discovery
            cv_inputs = []
        prefs = await preferences_facade.get_ranking_preferences(
            session, user_id=principal.user_id  # type: ignore[arg-type]
        )
        try:
            saved_signals = await saved_jobs_service.get_saved_job_signals(
                session, user_id=principal.user_id  # type: ignore[arg-type]
            )
        except Exception:  # noqa: BLE001 — saved-read failure must not 500 discovery
            saved_signals = {}

    ctx = _RankCtx(
        now=now,
        locale=locale,
        stale_days=settings.cv_stale_after_days,
        query_terms=query_terms,
        session_category_weights=session_category_weights,
        session_role_family_weights=session_role_family_weights,
        cv_inputs=cv_inputs,
        prefs=prefs,
        saved_employment_types=saved_signals.get("employment_types", []),
        saved_raw_titles=saved_signals.get("raw_titles", []),
        saved_skills=saved_signals.get("skills", []),
    )
    ctx.has_query = bool(query_terms)
    ctx.has_cv = bool(cv_inputs)
    ctx.has_pref = bool(prefs and prefs.has_signal)
    ctx.has_session = bool(
        session_category_weights or session_role_family_weights
    )
    ctx.has_saved = bool(
        saved_signals.get("employment_types")
        or saved_signals.get("raw_titles")
        or saved_signals.get("skills")
    )
    return ctx


# --------------------------------------------------------------------------- #
# Per-candidate scoring + reason derivation                                   #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _Scored:
    candidate: RankingCandidate
    score: int
    reasons: list[dict]
    recommended_cv_id: str | None
    published: datetime | None


def _query_component(
    cand: RankingCandidate, ctx: _RankCtx, tokens: set[str], haystack: str
) -> tuple[float | None, dict | None]:
    if not ctx.query_terms:
        return None, None
    matched = [
        term
        for term in ctx.query_terms
        if taxonomy.term_matches(term, tokens, haystack)
    ]
    frac = len(matched) / len(ctx.query_terms)
    reason = (
        {"code": ranking.REASON_MATCHES_SEARCH, "term": matched[0]} if matched else None
    )
    return frac, reason


def _cv_component(
    cand: RankingCandidate, ctx: _RankCtx
) -> tuple[float | None, dict | None, str | None]:
    if not ctx.cv_inputs:
        return None, None, None
    outcome = job_fit.evaluate(
        cand.as_fit_job(), ctx.cv_inputs, stale_days=ctx.stale_days
    )
    if not outcome.results:
        return None, None, None
    best = outcome.results[0]
    reason = None
    if best.score >= ranking.CV_FIT_REASON_MIN:
        reason = {
            "code": ranking.REASON_CV_FIT,
            "score": best.score,
            "cv_id": best.cv_id,
            "cv_title": best.title,
        }
    return best.score / 100.0, reason, outcome.recommended_cv_id


def _preference_component(
    cand: RankingCandidate, ctx: _RankCtx, tokens: set[str], haystack: str
) -> tuple[float | None, list[dict]]:
    prefs = ctx.prefs
    if prefs is None or not prefs.has_signal:
        return None, []
    checks: list[float] = []
    reasons: list[dict] = []

    if prefs.job_types:
        hit = cand.employment_type in prefs.job_types
        checks.append(1.0 if hit else 0.0)
        if hit:
            reasons.append(
                {
                    "code": ranking.REASON_PREFERRED_JOB_TYPE,
                    "value": cand.employment_type,
                }
            )
    if prefs.location_city:
        pref_city = taxonomy.normalize(prefs.location_city)
        cand_city = taxonomy.normalize(cand.location_city)
        hit = bool(pref_city) and pref_city == cand_city
        checks.append(1.0 if hit else 0.0)
        if hit:
            reasons.append(
                {"code": ranking.REASON_PREFERRED_LOCATION, "value": cand.location_city}
            )
    if prefs.field:
        field_tokens = taxonomy.tokens_of(prefs.field, None)
        hit = bool(field_tokens & tokens) or any(
            t in haystack for t in field_tokens
        )
        checks.append(1.0 if hit else 0.0)
        if hit:
            reasons.append(
                {"code": ranking.REASON_PREFERRED_FIELD, "value": prefs.field}
            )
    if not checks:
        return None, []
    return sum(checks) / len(checks), reasons


def _session_component(
    cand: RankingCandidate, ctx: _RankCtx, tokens: set[str]
) -> tuple[float | None, dict | None]:
    """Frequency- and recency-weighted guest-session affinity for a candidate.

    Each matched coarse value contributes its ``session_signal_weight`` (already
    freq×decay-scaled into [0,1]); the candidate takes the STRONGEST match. So a
    Finance job matches a "Finance viewed 20×" signal far more strongly than a
    once-viewed one, and a month-old signal has decayed toward zero — while a
    no-overlap candidate returns ``None`` (the component is simply absent, never a
    diluting zero).
    """

    if not (ctx.session_category_weights or ctx.session_role_family_weights):
        return None, None

    best_category: str | None = None
    best_category_weight = 0.0
    for cat, weight in ctx.session_category_weights.items():
        if taxonomy.tokens_of(cat, None) & tokens and weight > best_category_weight:
            best_category_weight = weight
            best_category = cat

    # Role-family overlap: the candidate's family (or its word parts) appears among
    # the weighted viewed role families the session recorded.
    family = taxonomy.role_family_of(cand.title)
    best_family_weight = 0.0
    if family:
        for fam, weight in ctx.session_role_family_weights.items():
            fam_words = taxonomy.tokens_of(fam, None) | {taxonomy.normalize(fam)}
            if (
                family in fam_words or bool(set(family.split("_")) & fam_words)
            ) and weight > best_family_weight:
                best_family_weight = weight

    frac = max(best_category_weight, best_family_weight)
    if frac <= 0.0:
        return None, None
    if best_category is not None and best_category_weight >= best_family_weight:
        return frac, {"code": ranking.REASON_SIMILAR_INDUSTRY, "value": best_category}
    return frac, {"code": ranking.REASON_SIMILAR_ROLE}


def _saved_component(
    cand: RankingCandidate, ctx: _RankCtx, tokens: set[str]
) -> tuple[float | None, dict | None]:
    """Score a candidate by affinity to the student's saved jobs.

    Checks employment-type match, title-token overlap, and skill overlap.
    Returns None when no saved signals are present.
    """
    if not ctx.has_saved:
        return None, None

    checks: list[float] = []

    if ctx.saved_employment_types:
        checks.append(1.0 if cand.employment_type in ctx.saved_employment_types else 0.0)

    # Title-token overlap across all saved job titles.
    if ctx.saved_raw_titles:
        saved_tokens: set[str] = set()
        for raw_title in ctx.saved_raw_titles:
            saved_tokens |= taxonomy.tokens_of(raw_title, None)
        overlap = len(tokens & saved_tokens)
        checks.append(min(1.0, overlap / max(1, len(saved_tokens))))

    # Skill overlap.
    if ctx.saved_skills:
        cand_skills = {
            taxonomy.normalize(s) for s in [*cand.required_skills, *cand.preferred_skills]
        }
        saved_skill_tokens = {taxonomy.normalize(s) for s in ctx.saved_skills}
        overlap = len(cand_skills & saved_skill_tokens)
        checks.append(min(1.0, overlap / max(1, len(saved_skill_tokens))))

    if not checks:
        return None, None

    score = sum(checks) / len(checks)
    reason = {"code": ranking.REASON_SAVED_AFFINITY} if score >= 0.4 else None
    return score, reason


def _secondary_reasons(cand: RankingCandidate, ctx: _RankCtx) -> list[dict]:
    reasons: list[dict] = []
    # Deadline within N days (deadline is in the FUTURE for visible jobs).
    deadline = _aware(cand.application_deadline)
    if deadline is not None:
        remaining = (deadline - ctx.now).total_seconds() / 86400.0
        if 0 <= remaining <= ranking.DEADLINE_SOON_DAYS:
            reasons.append(
                {"code": ranking.REASON_DEADLINE_SOON, "days": max(0, round(remaining))}
            )
    if cand.application_count >= ranking.POPULAR_REASON_MIN:
        reasons.append({"code": ranking.REASON_POPULAR})
    if cand.is_verified_employer:
        reasons.append({"code": ranking.REASON_VERIFIED_EMPLOYER})
    return reasons


def _score_candidate(cand: RankingCandidate, ctx: _RankCtx) -> _Scored:
    skills = [*cand.required_skills, *cand.preferred_skills]
    tokens = taxonomy.tokens_of(cand.title, skills)
    haystack = taxonomy.normalize(f"{cand.title} {cand.jd_text}")

    s_query, r_query = _query_component(cand, ctx, tokens, haystack)
    s_cv, r_cv, recommended_cv_id = _cv_component(cand, ctx)
    s_pref, r_prefs = _preference_component(cand, ctx, tokens, haystack)
    s_session, r_session = _session_component(cand, ctx, tokens)
    s_saved, r_saved = _saved_component(cand, ctx, tokens)

    components = ranking.Components(
        recency=ranking.recency_score(_days_since(cand.published_at, now=ctx.now)),
        employer=ranking.employer_score(cand.is_verified_employer),
        popularity=ranking.popularity_score(cand.application_count),
        query=s_query,
        cv=s_cv,
        preference=s_pref,
        session=s_session,
        saved=s_saved,
    )
    score = ranking.product_score(components)

    # Primary reasons (most meaningful first), then secondary, capped.
    reasons: list[dict] = []
    for r in (r_cv, r_query, r_session, r_saved):
        if r is not None:
            reasons.append(r)
    reasons.extend(r_prefs)
    reasons.extend(_secondary_reasons(cand, ctx))
    reasons = reasons[: ranking.MAX_REASONS]

    return _Scored(
        candidate=cand,
        score=score,
        reasons=reasons,
        recommended_cv_id=recommended_cv_id,
        published=_aware(cand.published_at),
    )


# --------------------------------------------------------------------------- #
# Presentation                                                                #
# --------------------------------------------------------------------------- #


def _present(
    scored: _Scored,
    *,
    source: str,
    sponsored_disclosure: dict | None = None,
    placement_id: uuid.UUID | None = None,
    reasons_override: list[dict] | None = None,
) -> dict:
    item = dict(scored.candidate.summary)
    item["score"] = scored.score
    item["source"] = source
    item["reason_codes"] = (
        reasons_override if reasons_override is not None else scored.reasons
    )
    item["recommended_cv_id"] = scored.recommended_cv_id
    item["sponsored_disclosure"] = sponsored_disclosure
    item["placement_id"] = str(placement_id) if placement_id is not None else None
    return item


def _fallback_reason(source: str) -> list[dict]:
    code = ranking.REASON_POPULAR if source == ranking.SOURCE_POPULAR else (
        ranking.REASON_RECENT
    )
    return [{"code": code}]


# --------------------------------------------------------------------------- #
# Public: job recommendations                                                 #
# --------------------------------------------------------------------------- #


async def recommend_jobs(
    session: AsyncSession,
    *,
    principal: Principal,
    cookie_tags: dict | None = None,
    q: str | None = None,
    limit: int = 12,
    locale: str = "vi",
    fallback: str = ranking.SOURCE_RECENT,
    with_sponsored: bool = True,
    discovery_session_id: uuid.UUID | None = None,
    snapshot_surface: str | None = None,
) -> dict:
    """Personalized (or honestly-fallback) job recommendations.

    Authenticated student → personalized with ``reason_codes`` / ``score`` /
    ``recommended_cv_id``. Guest with session signal → session-based reasons.
    No signal → honest ``source=recent`` / ``popular`` fallback (never a silent
    "recommended" mislabel). Sponsored items fill defined slots only and never
    reorder organic relevance. Hide-if-empty: ``items == []`` when nothing eligible.

    When ``snapshot_surface`` is set (only at the real serving points —
    ``marketplace_overview`` / ``jobs_recommendations``), a privacy-safe
    ``recommendation_snapshot`` of exactly what was returned (job ids + honest
    source + reason codes, no PII) is persisted best-effort for audit/repro/eval.
    """

    ctx = await _build_ctx(
        session,
        principal=principal,
        cookie_tags=cookie_tags,
        q=q,
        locale=locale,
        discovery_session_id=discovery_session_id,
    )
    pool = await ranking_read.list_candidates(
        session,
        persona=principal.persona,
        is_authenticated=principal.is_authenticated,
        limit=_POOL_CAP,
        locale=locale,
    )

    list_has_signal = ctx.list_has_signal
    list_source = ranking.SOURCE_RECOMMENDED if list_has_signal else fallback

    scored = [_score_candidate(c, ctx) for c in pool]
    if list_has_signal:
        scored.sort(
            key=lambda s: (
                -s.score,
                -(s.published.timestamp() if s.published else 0.0),
                str(s.candidate.job_id),
            )
        )
    # else: keep the recency order already returned by the candidate facade.

    diversified = ranking.diversify(scored, group_of=lambda s: s.candidate.org_id)

    organic_items = [
        _present(
            s,
            source=list_source,
            reasons_override=None if list_has_signal else _fallback_reason(list_source),
        )
        for s in diversified
    ]

    sponsored_items: list[dict] = []
    sponsored_ids: set[uuid.UUID] = set()
    if with_sponsored:
        sponsored_items, sponsored_ids = await _resolve_sponsored(
            session,
            principal=principal,
            ctx=ctx,
            locale=locale,
            cookie_tags=cookie_tags,
            discovery_session_id=discovery_session_id,
        )
        # Dedupe: a sponsored job never also appears in the organic stream.
        organic_items = [
            it for it in organic_items if uuid.UUID(it["id"]) not in sponsored_ids
        ]

    composed = ranking.inject_sponsored(organic_items, sponsored_items)
    items = composed[:limit]

    if snapshot_surface is not None and items:
        await snapshot_service.record_serving_snapshot(
            session,
            surface=snapshot_surface,
            principal=principal,
            discovery_session_id=discovery_session_id,
            list_source=list_source,
            personalized=list_has_signal,
            items=items,
        )

    return {
        "source": list_source,
        "personalized": list_has_signal,
        "items": items,
    }


def _norm_token(value: str | None) -> str | None:
    if not value:
        return None
    token = value.strip().lower()
    return token or None


def _build_viewer_signals(
    *,
    cookie_tags: dict | None,
    principal: Principal,
    locale: str,
    prefs: RankingPreferences | None,
) -> ad_targeting.ViewerSignals:
    """Assemble the PII-free coarse signals a paid slot may be targeted against.

    Reuses ONLY allowlisted coarse tags (city / work_mode / industries /
    role_families) plus the student's confirmed preference field/location and the
    coarse persona + locale — never any PII/sensitive signal (the targeting domain
    also re-checks the descriptor against the forbidden-signal allowlist).
    """

    tags = cookie_tags or {}
    cities = {t for t in allowlist.coarse_values(tags, "city") if t}
    work_modes = {t for t in allowlist.coarse_values(tags, "work_mode") if t}
    industries = {t for t in allowlist.coarse_values(tags, "industries") if t}
    role_families = {t for t in allowlist.coarse_values(tags, "role_families") if t}

    if prefs is not None:
        pref_city = _norm_token(prefs.location_city)
        if pref_city:
            cities.add(pref_city)
        pref_field = _norm_token(prefs.field)
        if pref_field:
            industries.add(pref_field)

    return ad_targeting.ViewerSignals(
        persona=principal.persona,
        locale=locale,
        cities=frozenset(cities),
        work_modes=frozenset(work_modes),
        industries=frozenset(industries),
        role_families=frozenset(role_families),
    )


async def _resolve_sponsored(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: _RankCtx,
    locale: str,
    cookie_tags: dict | None = None,
    discovery_session_id: uuid.UUID | None = None,
) -> tuple[list[dict], set[uuid.UUID]]:
    """Live sponsored job placements, targeting-, eligibility- and cap-filtered.

    Paid slots are relevance-filtered to the viewer's coarse signals BEFORE the
    organic dedupe/injection — targeting only ever selects/orders the PAID slots;
    it never reorders or bleeds into the organic stream (that separation is
    preserved by ``ranking.inject_sponsored`` in the caller).
    """

    viewer = _build_viewer_signals(
        cookie_tags=cookie_tags, principal=principal, locale=locale, prefs=ctx.prefs
    )
    capped = await frequency_cap.over_capped_placements(
        session,
        session_id=discovery_session_id,
        user_id=principal.user_id if principal.is_authenticated else None,
    )
    active = await inventory_facade.list_active_sponsored(
        session,
        target_type="job",
        limit=len(ranking.SPONSORED_SLOTS),
        exclude_placement_ids=capped,
        viewer=viewer,
    )
    if not active:
        return [], set()
    cand_map = await ranking_read.load_candidates_by_ids(
        session,
        job_ids=[a.target_id for a in active],
        persona=principal.persona,
        is_authenticated=principal.is_authenticated,
        locale=locale,
    )
    disclosure = inventory_facade.disclosure(locale=locale)
    items: list[dict] = []
    ids: set[uuid.UUID] = set()
    for a in active:
        cand = cand_map.get(a.target_id)
        if cand is None or cand.job_id in ids:  # hidden/expired target dropped
            continue
        scored = _score_candidate(cand, ctx)
        items.append(
            _present(
                scored,
                source=ranking.SOURCE_SPONSORED,
                sponsored_disclosure=disclosure,
                placement_id=a.placement_id,
            )
        )
        ids.add(cand.job_id)
    return items, ids


# --------------------------------------------------------------------------- #
# Public: similar jobs                                                        #
# --------------------------------------------------------------------------- #


async def similar_jobs(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    limit: int = 6,
    locale: str = "vi",
) -> dict:
    """Deterministic similar public jobs by skill/role-family overlap.

    Eligibility-filtered (same predicate as ``GET /jobs``); a hidden/closed seed
    is a non-enumerable ``404``. ``items == []`` when nothing genuinely similar
    (hide-if-empty — never pad with unrelated jobs labelled "recommended").
    """

    seed = await ranking_read.load_candidate(
        session,
        job_id=job_id,
        persona=principal.persona,
        is_authenticated=principal.is_authenticated,
        locale=locale,
    )
    if seed is None:
        raise ResourceNotFoundError()

    seed_tokens = taxonomy.tokens_of(
        seed.title, [*seed.required_skills, *seed.preferred_skills]
    )
    seed_family = taxonomy.role_family_of(seed.title)

    pool = await ranking_read.list_candidates(
        session,
        persona=principal.persona,
        is_authenticated=principal.is_authenticated,
        limit=_SIMILAR_POOL_CAP,
        exclude_ids={job_id},
        locale=locale,
    )
    now = _now()

    @dataclass(slots=True)
    class _Sim:
        candidate: RankingCandidate
        overlap: int
        family_hit: bool
        overlap_terms: list[str]
        published: datetime | None

    sims: list[_Sim] = []
    for cand in pool:
        cand_tokens = taxonomy.tokens_of(
            cand.title, [*cand.required_skills, *cand.preferred_skills]
        )
        shared = seed_tokens & cand_tokens
        family_hit = bool(seed_family and taxonomy.role_family_of(cand.title) == seed_family)
        if not shared and not family_hit:
            continue
        sims.append(
            _Sim(
                candidate=cand,
                overlap=len(shared),
                family_hit=family_hit,
                overlap_terms=sorted(shared),
                published=_aware(cand.published_at),
            )
        )

    sims.sort(
        key=lambda s: (
            -(s.overlap + (1 if s.family_hit else 0)),
            -(s.published.timestamp() if s.published else 0.0),
            str(s.candidate.job_id),
        )
    )
    sims = ranking.diversify(sims, group_of=lambda s: s.candidate.org_id)

    items: list[dict] = []
    for s in sims[:limit]:
        reasons: list[dict] = []
        if s.overlap_terms:
            reasons.append(
                {"code": ranking.REASON_SKILL_MATCH, "skills": s.overlap_terms[:3]}
            )
        if s.family_hit:
            reasons.append({"code": ranking.REASON_SIMILAR_ROLE})
        if s.candidate.is_verified_employer:
            reasons.append({"code": ranking.REASON_VERIFIED_EMPLOYER})
        components = ranking.Components(
            recency=ranking.recency_score(_days_since(s.candidate.published_at, now=now)),
            employer=ranking.employer_score(s.candidate.is_verified_employer),
            popularity=ranking.popularity_score(s.candidate.application_count),
            query=(s.overlap / max(1, len(seed_tokens))),
            session=(1.0 if s.family_hit else None),
        )
        item = dict(s.candidate.summary)
        item["score"] = ranking.product_score(components)
        item["source"] = ranking.SOURCE_RECOMMENDED
        item["reason_codes"] = reasons[: ranking.MAX_REASONS]
        item["recommended_cv_id"] = None
        item["sponsored_disclosure"] = None
        item["placement_id"] = None
        items.append(item)

    return {"job_id": str(job_id), "items": items}


# --------------------------------------------------------------------------- #
# Public: popular role families (real aggregate, hide-if-empty)               #
# --------------------------------------------------------------------------- #


async def popular_roles(
    session: AsyncSession, *, limit: int = 8, locale: str = "vi"
) -> list[dict]:
    """Most-common role families across eligible jobs (real counts; hide-if-empty).

    Aggregated from real visible jobs by deterministic role family; titles that
    match no known family are excluded (never bucketed into a fabricated total).
    Returns ``[]`` when there is no data — the rail then hides. No invented metrics.
    """

    pool = await ranking_read.list_candidates(
        session,
        persona="guest",
        is_authenticated=False,
        limit=_POPULAR_POOL_CAP,
        locale=locale,
    )
    agg: dict[str, dict[str, int]] = {}
    for cand in pool:
        family = taxonomy.role_family_of(cand.title)
        if family is None:
            continue
        bucket = agg.setdefault(family, {"job_count": 0, "application_count": 0})
        bucket["job_count"] += 1
        bucket["application_count"] += cand.application_count

    ordered = sorted(
        agg.items(),
        key=lambda kv: (-kv[1]["job_count"], -kv[1]["application_count"], kv[0]),
    )
    return [
        {
            "role_family": family,
            "job_count": data["job_count"],
            "application_count": data["application_count"],
        }
        for family, data in ordered[:limit]
    ]
