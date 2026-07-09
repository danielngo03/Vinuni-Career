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
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import job_fit
from app.core.config import get_settings
from app.modules.advertising.application import inventory_facade
from app.modules.discovery.application import frequency_cap
from app.modules.discovery.domain import ranking, taxonomy
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


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


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
    session_categories: list[str]
    session_role_families: list[str]
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


def _coarse_list(tags: dict | None, key: str) -> list[str]:
    if not isinstance(tags, dict):
        return []
    value = tags.get(key)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str)]
    return []


async def _build_ctx(
    session: AsyncSession,
    *,
    principal: Principal,
    cookie_tags: dict | None,
    q: str | None,
    locale: str,
) -> _RankCtx:
    settings = get_settings()
    tags = cookie_tags or {}

    search_terms = _coarse_list(tags, "search_terms")
    query_terms: list[str] = []
    seen: set[str] = set()
    for raw in [*([q] if q else []), *search_terms]:
        norm = taxonomy.normalize(raw)
        if norm and norm not in seen:
            seen.add(norm)
            query_terms.append(raw.strip())
        if len(query_terms) >= _MAX_QUERY_TERMS:
            break

    session_categories = [
        *_coarse_list(tags, "categories"),
        *_coarse_list(tags, "industries"),
    ]
    session_role_families = _coarse_list(tags, "role_families")

    cv_inputs: list[job_fit.CvInput] = []
    prefs: RankingPreferences | None = None
    saved_signals: dict = {}
    if principal.is_authenticated and principal.persona == "student":
        try:
            cv_inputs = await cv_ranking_facade.build_cv_inputs(session, principal=principal)
        except Exception:  # noqa: BLE001 — a CV-read failure must not 500 discovery
            cv_inputs = []
        prefs = await preferences_facade.get_ranking_preferences(
            session,
            user_id=principal.user_id,  # type: ignore[arg-type]
        )
        try:
            saved_signals = await saved_jobs_service.get_saved_job_signals(
                session,
                user_id=principal.user_id,  # type: ignore[arg-type]
            )
        except Exception:  # noqa: BLE001 — saved-read failure must not 500 discovery
            saved_signals = {}

    ctx = _RankCtx(
        now=_now(),
        locale=locale,
        stale_days=settings.cv_stale_after_days,
        query_terms=query_terms,
        session_categories=session_categories,
        session_role_families=session_role_families,
        cv_inputs=cv_inputs,
        prefs=prefs,
        saved_employment_types=saved_signals.get("employment_types", []),
        saved_raw_titles=saved_signals.get("raw_titles", []),
        saved_skills=saved_signals.get("skills", []),
    )
    ctx.has_query = bool(query_terms)
    ctx.has_cv = bool(cv_inputs)
    ctx.has_pref = bool(prefs and prefs.has_signal)
    ctx.has_session = bool(session_categories or session_role_families)
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
    matched = [term for term in ctx.query_terms if taxonomy.term_matches(term, tokens, haystack)]
    frac = len(matched) / len(ctx.query_terms)
    reason = {"code": ranking.REASON_MATCHES_SEARCH, "term": matched[0]} if matched else None
    return frac, reason


def _cv_component(
    cand: RankingCandidate, ctx: _RankCtx
) -> tuple[float | None, dict | None, str | None]:
    if not ctx.cv_inputs:
        return None, None, None
    outcome = job_fit.evaluate(cand.as_fit_job(), ctx.cv_inputs, stale_days=ctx.stale_days)
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
            reasons.append({"code": ranking.REASON_PREFERRED_LOCATION, "value": cand.location_city})
    if prefs.field:
        field_tokens = taxonomy.tokens_of(prefs.field, None)
        hit = bool(field_tokens & tokens) or any(t in haystack for t in field_tokens)
        checks.append(1.0 if hit else 0.0)
        if hit:
            reasons.append({"code": ranking.REASON_PREFERRED_FIELD, "value": prefs.field})
    if not checks:
        return None, []
    return sum(checks) / len(checks), reasons


def _session_component(
    cand: RankingCandidate, ctx: _RankCtx, tokens: set[str]
) -> tuple[float | None, dict | None]:
    if not (ctx.session_categories or ctx.session_role_families):
        return None, None
    matched_value: str | None = None
    matched = 0
    total = max(1, len(ctx.session_categories))
    for cat in ctx.session_categories:
        cat_tokens = taxonomy.tokens_of(cat, None)
        if cat_tokens & tokens:
            matched += 1
            if matched_value is None:
                matched_value = cat
    # Role-family overlap: the candidate's family (or its word parts) appears among
    # the viewed role families the session recorded.
    family = taxonomy.role_family_of(cand.title)
    family_words: set[str] = set()
    for fam in ctx.session_role_families:
        family_words |= taxonomy.tokens_of(fam, None)
        family_words.add(taxonomy.normalize(fam))
    family_hit = bool(
        family and (family in family_words or bool(set(family.split("_")) & family_words))
    )
    frac = matched / total
    if family_hit:
        frac = max(frac, 0.7)
    if matched_value is not None:
        return frac, {"code": ranking.REASON_SIMILAR_INDUSTRY, "value": matched_value}
    if family_hit:
        return frac, {"code": ranking.REASON_SIMILAR_ROLE}
    return (frac if matched else None), None


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
            reasons.append({"code": ranking.REASON_DEADLINE_SOON, "days": max(0, round(remaining))})
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
    item["reason_codes"] = reasons_override if reasons_override is not None else scored.reasons
    item["recommended_cv_id"] = scored.recommended_cv_id
    item["sponsored_disclosure"] = sponsored_disclosure
    item["placement_id"] = str(placement_id) if placement_id is not None else None
    return item


def _fallback_reason(source: str) -> list[dict]:
    code = ranking.REASON_POPULAR if source == ranking.SOURCE_POPULAR else (ranking.REASON_RECENT)
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
) -> dict:
    """Personalized (or honestly-fallback) job recommendations.

    Authenticated student → personalized with ``reason_codes`` / ``score`` /
    ``recommended_cv_id``. Guest with session signal → session-based reasons.
    No signal → honest ``source=recent`` / ``popular`` fallback (never a silent
    "recommended" mislabel). Sponsored items fill defined slots only and never
    reorder organic relevance. Hide-if-empty: ``items == []`` when nothing eligible.
    """

    ctx = await _build_ctx(
        session, principal=principal, cookie_tags=cookie_tags, q=q, locale=locale
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
            discovery_session_id=discovery_session_id,
        )
        # Dedupe: a sponsored job never also appears in the organic stream.
        organic_items = [it for it in organic_items if uuid.UUID(it["id"]) not in sponsored_ids]

    composed = ranking.inject_sponsored(organic_items, sponsored_items)
    return {
        "source": list_source,
        "personalized": list_has_signal,
        "items": composed[:limit],
    }


async def _resolve_sponsored(
    session: AsyncSession,
    *,
    principal: Principal,
    ctx: _RankCtx,
    locale: str,
    discovery_session_id: uuid.UUID | None = None,
) -> tuple[list[dict], set[uuid.UUID]]:
    """Live sponsored job placements, eligibility- and frequency-cap-filtered."""

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

    seed_tokens = taxonomy.tokens_of(seed.title, [*seed.required_skills, *seed.preferred_skills])
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
            reasons.append({"code": ranking.REASON_SKILL_MATCH, "skills": s.overlap_terms[:3]})
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


async def popular_roles(session: AsyncSession, *, limit: int = 8, locale: str = "vi") -> list[dict]:
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
