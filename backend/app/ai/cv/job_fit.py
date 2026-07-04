"""Deterministic CV-to-job fit scoring (``recommend_cv_for_job`` base layer).

The user-facing 0-100 ``score`` is a **product score**, computed PURELY from the
structured job requirements and the CV's own content — never a model confidence,
embedding similarity, or hiring decision (``docs/BUSINESS_LOGIC.md`` §4B.3B;
``docs/CV_STUDIO_SPEC.md`` §recommend; ``.claude/rules/ai.md``). The same inputs
always produce the same score (reproducible), so it can be ranked, cached, and
explained without spending a model call.

Score composition (weights are the single source of truth — keep in sync with the
docstring and ``docs/API_CONTRACTS.md``):

    score = round(
        0.50 * skills      # JD required/preferred skill coverage in the CV
      + 0.25 * experience  # evidence of relevant experience/project sections
      + 0.10 * logistics   # work-mode / location fit where job data exists
      + 0.15 * quality     # CV completeness + recency (staleness)
    )

Each band is itself a 0-100 integer so it can be shown to the student as an
explainable category. ``matched_skills`` / ``gaps`` are human-readable (the
original JD skill strings), and missing skills are framed as evidence to add
"if true" by the caller — the scorer never fabricates a skill the CV lacks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.cv import grounding

# --------------------------------------------------------------------------- #
# Weights (must sum to 1.0)                                                    #
# --------------------------------------------------------------------------- #

W_SKILLS = 0.50
W_EXPERIENCE = 0.25
W_LOGISTICS = 0.10
W_QUALITY = 0.15

# Section types treated as "experience evidence".
_EXPERIENCE_TYPES = frozenset(
    {"experience", "work", "work_experience", "projects", "project", "internship"}
)
# Core sections used for the completeness signal.
_CORE_TYPES = ("summary", "objective", "education", "experience", "skills", "projects")
_CORE_TARGET = 4  # having 4 of the core sections filled counts as "complete"

# When the job exposes no structured skills, fall back to the top JD keywords so a
# vague posting can still be scored (signal is flagged ``low_signal`` upstream).
_JD_FALLBACK_KEYWORDS = 12

# How fast the recency signal decays once a CV is past the stale threshold.
_RECENCY_DECAY_DAYS = 120


@dataclass(slots=True)
class CvInput:
    """One active CV to score (already loaded + owner-checked by the service)."""

    cv_id: str
    title: str
    language: str
    sections: list[dict]  # [{section_type, title, content}], see _section_dict
    last_updated_days: int


@dataclass(slots=True)
class BandScores:
    skills: int
    experience: int
    logistics: int
    quality: int

    def as_dict(self) -> dict[str, int]:
        return {
            "skills": self.skills,
            "experience": self.experience,
            "logistics": self.logistics,
            "quality": self.quality,
        }


@dataclass(slots=True)
class CvFit:
    cv_id: str
    title: str
    score: int
    bands: BandScores
    matched_skills: list[str]
    gaps: list[str]
    stale: bool
    last_updated_days: int


@dataclass(slots=True)
class JobFitOutcome:
    results: list[CvFit]
    recommended_cv_id: str | None
    signal: str  # "ok" | "low_signal"
    requirement_count: int = 0


@dataclass(slots=True)
class _Requirements:
    required: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    used_fallback: bool = False

    @property
    def all_terms(self) -> list[str]:
        return [*self.required, *self.preferred]

    @property
    def count(self) -> int:
        return len(self.required) + len(self.preferred)


# --------------------------------------------------------------------------- #
# Matching helpers                                                             #
# --------------------------------------------------------------------------- #


def _clean_terms(values: object) -> list[str]:
    """Normalise a JD skills list to de-duplicated, non-empty original strings."""

    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if not isinstance(v, str):
            continue
        term = v.strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            out.append(term)
    return out


def resolve_requirements(job: dict) -> _Requirements:
    """Resolve the skill terms used for scoring (with a JD-keyword fallback)."""

    required = _clean_terms(job.get("required_skills"))
    preferred = _clean_terms(job.get("preferred_skills"))
    if required or preferred:
        return _Requirements(required=required, preferred=preferred)
    # No structured skills — derive keywords from the JD text so we still score.
    kws = grounding.extract_keywords(job.get("jd_text") or "", limit=_JD_FALLBACK_KEYWORDS)
    return _Requirements(required=kws, preferred=[], used_fallback=True)


def _split_present(terms: list[str], text_norm_expanded: str) -> tuple[list[str], list[str]]:
    """Return ``(present, missing)`` using expansion-aware matching.

    ``text_norm_expanded`` must be pre-built with :func:`grounding.normalize_expanded`
    so that "k8s" in the CV also generates "kubernetes" in the searchable text,
    and "kubernetes" in the JD therefore matches the CV.
    """

    present: list[str] = []
    missing: list[str] = []
    for term in terms:
        if grounding.term_present(term, text_norm_expanded):
            present.append(term)
        else:
            missing.append(term)
    return present, missing


def _section_text(sections: list[dict], types: frozenset[str]) -> str:
    parts = [
        grounding.content_to_text(s.get("content"))
        for s in sections
        if (s.get("section_type") or "") in types
    ]
    return " ".join(p for p in parts if p)


# --------------------------------------------------------------------------- #
# Band scorers (each returns a 0-100 int)                                      #
# --------------------------------------------------------------------------- #


def _skills_band(
    req: _Requirements, cv_text_norm: str
) -> tuple[int, list[str], list[str]]:
    pres_req, miss_req = _split_present(req.required, cv_text_norm)
    pres_pref, miss_pref = _split_present(req.preferred, cv_text_norm)

    req_cov = (len(pres_req) / len(req.required)) if req.required else None
    pref_cov = (len(pres_pref) / len(req.preferred)) if req.preferred else None

    if req_cov is not None and pref_cov is not None:
        ratio = 0.8 * req_cov + 0.2 * pref_cov
    elif req_cov is not None:
        ratio = req_cov
    elif pref_cov is not None:
        ratio = pref_cov
    else:
        ratio = 0.0

    matched = [*pres_req, *pres_pref]
    gaps = [*miss_req, *miss_pref]
    return round(ratio * 100), matched, gaps


def _experience_band(req: _Requirements, sections: list[dict]) -> int:
    evidence = grounding.normalize_expanded(_section_text(sections, _EXPERIENCE_TYPES))
    if not evidence:
        return 0
    terms = req.all_terms
    if terms:
        present, _ = _split_present(terms, evidence)
        rel = len(present) / len(terms)
    else:
        rel = 1.0
    # Base credit for having real experience evidence, scaled up by relevance.
    return round(100 * (0.4 + 0.6 * rel))


def _logistics_band(job: dict, cv_text_norm: str) -> int:
    """Work-mode / location fit where the job exposes data; neutral otherwise.

    Language fit is intentionally not scored: jobs carry no structured language
    requirement, so inventing one would be unfounded. Documented for honesty.
    """

    location_type = (job.get("location_type") or "").lower()
    if location_type == "remote":
        return 100
    city = grounding.normalize(job.get("location_city") or "")
    country = grounding.normalize(job.get("location_country") or "")
    if city and city in cv_text_norm:
        return 100
    if country and country in cv_text_norm:
        return 85
    if city or country:
        return 50  # location data exists but the CV gives no matching signal
    return 70  # no location data on the job — neutral, do not penalise


def _quality_band(sections: list[dict], last_updated_days: int, stale_days: int) -> int:
    filled_core = 0
    for stype in _CORE_TYPES:
        text = _section_text(sections, frozenset({stype}))
        if text.strip():
            filled_core += 1
    completeness = min(filled_core, _CORE_TARGET) / _CORE_TARGET

    if last_updated_days <= stale_days:
        recency = 1.0
    else:
        over = last_updated_days - stale_days
        recency = max(0.0, 1.0 - over / _RECENCY_DECAY_DAYS)

    return round(100 * (0.6 * completeness + 0.4 * recency))


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def score_cv(job: dict, req: _Requirements, cv: CvInput, *, stale_days: int) -> CvFit:
    # Use expansion-aware normalization so "k8s" in the CV matches "kubernetes"
    # in the JD and vice-versa. normalize_expanded() appends all alias tokens,
    # growing the text for matching purposes only (no content is fabricated).
    cv_text_norm = grounding.normalize_expanded(grounding.sections_to_text(cv.sections))

    skills, matched, gaps = _skills_band(req, cv_text_norm)
    experience = _experience_band(req, cv.sections)
    logistics = _logistics_band(job, cv_text_norm)
    quality = _quality_band(cv.sections, cv.last_updated_days, stale_days)

    score = round(
        W_SKILLS * skills
        + W_EXPERIENCE * experience
        + W_LOGISTICS * logistics
        + W_QUALITY * quality
    )
    score = max(0, min(100, score))

    return CvFit(
        cv_id=cv.cv_id,
        title=cv.title,
        score=score,
        bands=BandScores(
            skills=skills, experience=experience, logistics=logistics, quality=quality
        ),
        matched_skills=matched,
        gaps=gaps,
        stale=cv.last_updated_days > stale_days,
        last_updated_days=cv.last_updated_days,
    )


def evaluate(job: dict, cvs: list[CvInput], *, stale_days: int) -> JobFitOutcome:
    """Score + rank every CV for the job. Pure and deterministic."""

    req = resolve_requirements(job)
    results = [score_cv(job, req, cv, stale_days=stale_days) for cv in cvs]

    # Highest score wins; tie-break on the freshest CV, then cv_id for a total,
    # reproducible order.
    results.sort(key=lambda r: (-r.score, r.last_updated_days, r.cv_id))

    recommended_cv_id = results[0].cv_id if results else None
    # "low_signal" when the JD yields too few parseable requirements to score on.
    signal = "low_signal" if req.count < 2 else "ok"
    return JobFitOutcome(
        results=results,
        recommended_cv_id=recommended_cv_id,
        signal=signal,
        requirement_count=req.count,
    )
