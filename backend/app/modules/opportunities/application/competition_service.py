"""Competition level signal for a job posting (opportunities module).

Provides a lightweight, on-the-fly estimation of how competitive a given
visible/active job is likely to be for applicants.

Algorithm (``docs/BUSINESS_LOGIC.md``):
  1. Load the job (same visibility predicate as public discovery; ``None`` → 404).
  2. Count active (non-rejected, non-withdrawn) applications via a cross-module
     read query — no recruitment module implementation imports.
  3. Compute a deterministic JD complexity score from job fields.
  4. Combine into a raw signal and map to a labelled level.
  5. Optionally enrich with a one-sentence AI explanation (degrades gracefully).

JD complexity scoring:
  - ``experience_min_years``:
      None/0 → entry   (+0)
      1–2    → junior  (+10)
      3–5    → mid     (+20)
      6+     → senior  (+30)
  - ``required_skills`` count:
      0–3 → low    (+0)
      4–6 → medium (+10)
      7+  → high   (+20)
  - ``employment_type``:
      internship → −10 | full_time → +0 | contract → +5

Level mapping (``raw = jd_complexity + clamp(application_count × 3, 0, 40)``):
  raw < 20  → low
  20–44     → medium
  45–64     → high
  65+       → very_high

Privacy:
  - Raw application count is used in the computation only. It is returned in the
    response only when the partner has opted in via
    ``job.settings["show_application_count"] == True``.
  - AI enrichment follows the same gateway / output-guard pattern as
    ``documents.job_fit_service`` — provider/model/token internals never reach
    the caller.

RBAC:
  - Public endpoint; no auth required for visible/active jobs.
  - Authenticated callers may see visibility tiers beyond ``public``.
  - No audit write — this is a read-only advisory signal.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import Uuid, bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv.llm import generate_note
from app.ai.energy import service as energy_service
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import real_provider_active
from app.ai.observability.billable_usage import (
    FEATURE_COMPETITION_EXPLANATION,
    record_billable_usage,
)
from app.ai.prompts.competition import v1 as competition_prompt
from app.modules.opportunities.application import competition_projection_service
from app.modules.opportunities.application.visibility import apply_visible_filter
from app.modules.opportunities.domain import competition_scoring as scoring
from app.modules.opportunities.domain import lifecycle
from app.modules.opportunities.domain.models import Job
from app.shared.exceptions import (
    AIUnavailableError,
    PermissionDeniedError,
    QuotaExceededError,
    ResourceNotFoundError,
)
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Internal constants                                                           #
# --------------------------------------------------------------------------- #

TASK_TYPE = "competition_signal_explanation"

# Active application statuses from the recruitment module lifecycle (not
# imported — copied here to avoid cross-module implementation coupling).
# Keep in sync with ``recruitment.domain.lifecycle.ACTIVE_STATUSES``.
_ACTIVE_APPLICATION_STATUSES = ("submitted", "under_review")

_LEVEL_LABELS: dict[str, str] = {
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "very_high": "Rất cao",
}

_EXPERIENCE_TIER_LABELS: dict[str, str] = {
    "entry": "Không yêu cầu kinh nghiệm",
    "junior": "Sơ cấp (1-2 năm)",
    "mid": "Trung cấp (3-5 năm)",
    "senior": "Cao cấp (6+ năm)",
}

_SKILLS_TIER_LABELS: dict[str, str] = {
    "low": "Ít kỹ năng yêu cầu (0-3)",
    "medium": "Vừa phải (4-6 kỹ năng)",
    "high": "Nhiều kỹ năng yêu cầu (7+)",
}


# --------------------------------------------------------------------------- #
# Job loader (within-module; reuses the public visibility predicate)           #
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _load_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    principal: Principal,
) -> Job | None:
    """Load a visible job row, applying the same predicate as public discovery.

    Returns ``None`` when the job does not exist or is not visible to the
    caller's persona/auth level — the caller maps this to a non-enumerable 404.
    """

    levels = lifecycle.visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    stmt = apply_visible_filter(
        select(Job).where(Job.id == job_id),
        levels=levels,
        now=_now(),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Cross-module read: active application count                                  #
# --------------------------------------------------------------------------- #


async def _count_active_applications(
    session: AsyncSession, *, job_id: uuid.UUID
) -> int:
    """Count active (non-rejected, non-withdrawn) applications for the job.

    Cross-module read contract: queries the ``applications`` table directly via
    a text query to avoid importing the ``recruitment`` module's ORM models
    (backend rule: no cross-module implementation imports). Active statuses
    (``submitted``, ``under_review``) are copied from the recruitment lifecycle
    vocabulary and must be kept in sync.
    """

    # Use a typed bindparam so SQLAlchemy encodes the UUID in the dialect-
    # correct format: hex-without-dashes on SQLite, native UUID on PostgreSQL.
    result = await session.execute(
        text(
            "SELECT COUNT(*) FROM applications"
            " WHERE job_id = :job_id"
            " AND status IN ('submitted', 'under_review')"
            " AND deleted_at IS NULL"
        ).bindparams(bindparam("job_id", type_=Uuid(as_uuid=True))),
        {"job_id": job_id},
    )
    count = result.scalar_one()
    return int(count) if count is not None else 0


# --------------------------------------------------------------------------- #
# Deterministic algorithm (pure functions)                                     #
# --------------------------------------------------------------------------- #


def _experience_tier(experience_min_years: int | None) -> tuple[str, int]:
    """Return ``(tier_key, score_delta)`` for the experience requirement.

    Boundary resolution for ambiguous spec overlap at year 5: the published
    range is ``3-5 → mid (+20)`` and ``5+ → senior (+30)``; we resolve by
    treating the ``5+`` threshold as **≥ 6** so 5 falls in mid and ranges are
    non-overlapping. This is the most natural HR convention.
    """

    y = experience_min_years or 0
    if y <= 0:
        return "entry", 0
    if y <= 2:
        return "junior", 10
    if y <= 5:
        return "mid", 20
    return "senior", 30


def _skills_tier(required_skills_count: int) -> tuple[str, int]:
    """Return ``(tier_key, score_delta)`` for the required skills count."""

    n = required_skills_count
    if n <= 3:
        return "low", 0
    if n <= 6:
        return "medium", 10
    return "high", 20


def _employment_type_delta(employment_type: str) -> int:
    """Score delta for employment type."""

    if employment_type == "internship":
        return -10
    if employment_type == "contract":
        return 5
    return 0  # full_time, part_time, unknown → neutral


def compute_jd_complexity(
    *,
    experience_min_years: int | None,
    required_skills_count: int,
    employment_type: str,
) -> tuple[int, str, str]:
    """Return ``(jd_complexity_score, experience_tier_key, skills_tier_key)``.

    Pure function — deterministic, testable, no I/O.
    """

    exp_tier, exp_delta = _experience_tier(experience_min_years)
    skills_tier, skills_delta = _skills_tier(required_skills_count)
    emp_delta = _employment_type_delta(employment_type)
    score = exp_delta + skills_delta + emp_delta
    return score, exp_tier, skills_tier


def map_raw_to_level(raw: int) -> str:
    """Map the combined raw score to a competition level key.

    Thin re-export of the shared pure mapping in
    :mod:`opportunities.domain.competition_scoring` so the public signal, the
    student-aware signal, and the projection all agree on the level boundaries.
    """

    return scoring.map_raw_to_level(raw)


def compute_signal(
    *,
    jd_complexity: int,
    application_count: int,
) -> tuple[int, str]:
    """Return ``(raw_score, level_key)`` for the PUBLIC (non-personalized) signal.

    ``raw = jd_complexity + clamp(application_count × 3, 0, 40)``. This
    volume-based mapping is used by the public ``competition_signal`` endpoint
    only; the authenticated-student signal is QUALITY-adjusted (reads on the
    caliber of real applicants, not raw volume) via
    ``scoring.quality_adjusted_level``.
    """

    raw = scoring.volume_raw(jd_complexity, application_count)
    return raw, scoring.map_raw_to_level(raw)


# --------------------------------------------------------------------------- #
# Optional AI enrichment                                                       #
# --------------------------------------------------------------------------- #


async def _maybe_explain(
    *,
    job_title: str,
    level: str,
    experience_tier: str,
    skills_tier: str,
    employment_type: str,
) -> tuple[str | None, bool]:
    """Return ``(explanation, available)`` for the competition level.

    Two AND-guards (same pattern as ``job_fit_service._maybe_explain``):
      - real-provider gate (env + key + db toggle, ADR-0011 §2)
      - admin feature flag ``job_fit_ai_explanation_enabled``

    Either off → ``(None, False)``; the deterministic signal is still returned.
    On AI failure → ``(None, False)``; no exception propagates.
    """

    if (
        not real_provider_active()
        or not runtime_config.current().job_fit_ai_explanation_enabled
    ):
        return None, False

    try:
        text_out = await generate_note(
            task_type=TASK_TYPE,
            system_prompt=competition_prompt.SYSTEM_PROMPT,
            user_content=competition_prompt.build_user_content(
                job_title=job_title,
                level=_LEVEL_LABELS.get(level, level),
                experience_tier=_EXPERIENCE_TIER_LABELS.get(experience_tier, experience_tier),
                skills_tier=_SKILLS_TIER_LABELS.get(skills_tier, skills_tier),
                employment_type=employment_type,
            ),
            temperature=0.2,
            max_tokens=120,
        )
    except AIUnavailableError:
        return None, False

    text_out = (text_out or "").strip()
    return (text_out or None), bool(text_out)


# --------------------------------------------------------------------------- #
# Public service function                                                      #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Student-aware bucketed competition intelligence (E35 / B-536, B-537)         #
# --------------------------------------------------------------------------- #
#
# Distinct from ``competition_signal`` above (which is public and NOT fit-aware):
# this variant is only ever called for an authenticated student (the caller
# checks ``principal.persona``) and additionally buckets seats, application
# volume, deadline freshness, applicant-quality, the student's own CV fit, and
# organic/recommended/sponsored discovery source mix — all privacy-safe
# aggregates, never another applicant's identity, raw score, or exact rank.

_LOW_SIGNAL_APPLICATION_THRESHOLD = 3
_LOW_SIGNAL_SOURCE_EVENT_THRESHOLD = 5

# English machine-readable label (distinct from the Vietnamese display label
# used by the public, non-personalized ``competition_signal`` above).
_STUDENT_LABELS: dict[str, str] = {
    "low": "low",
    "medium": "moderate",
    "high": "high",
    "very_high": "very_high",
}

# Fit-score -> competitiveness bucket. Derived purely from the student's own
# deterministic CV fit score — never a claim about other candidates.
_FIT_BUCKET_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (85, "highly_competitive"),
    (70, "competitive"),
    (50, "developing"),
    (0, "needs_improvement"),
)


def _seats_bucket(headcount: int) -> str:
    if headcount <= 1:
        return "single_seat"
    if headcount <= 5:
        return "small_batch"
    if headcount <= 15:
        return "batch"
    return "mass_hiring"


def _application_volume_bucket(count: int) -> str:
    if count <= 4:
        return "low"
    if count <= 14:
        return "medium"
    if count <= 39:
        return "high"
    return "very_high"


def _deadline_freshness(deadline: datetime | None, *, now: datetime) -> str:
    if deadline is None:
        return "no_deadline"
    # SQLite round-trips DateTime columns as tz-naive; PostgreSQL keeps tz-aware.
    # Normalise to UTC-aware so the subtraction below works on both backends
    # (same fix as ``job_fit_service._as_utc``).
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    delta_days = (deadline - now).total_seconds() / 86400
    if delta_days < 0:
        return "closed"
    if delta_days < 3:
        return "final_days"
    if delta_days <= 14:
        return "closing_soon"
    return "long_runway"


def _student_fit_bucket(fit_score: int | None) -> str:
    if fit_score is None:
        return "unknown"
    for threshold, bucket in _FIT_BUCKET_THRESHOLDS:
        if fit_score >= threshold:
            return bucket
    return "needs_improvement"


async def _source_mix(
    session: AsyncSession, *, job_id: uuid.UUID
) -> dict[str, float] | None:
    """Organic/recommended/sponsored view-event ratio for this job (real data).

    Built from ``discovery_events`` (privacy-safe by construction; no PII).
    Returns ``None`` when too few events exist to form a meaningful ratio
    (low-signal — never fabricate a plausible-looking split).
    """

    result = await session.execute(
        text(
            "SELECT source_surface, COUNT(*) FROM discovery_events"
            " WHERE target_type = 'job' AND target_id = :job_id"
            " GROUP BY source_surface"
        ).bindparams(bindparam("job_id", type_=Uuid(as_uuid=True))),
        {"job_id": job_id},
    )
    rows = result.all()
    total = sum(int(n) for _surface, n in rows)
    if total < _LOW_SIGNAL_SOURCE_EVENT_THRESHOLD:
        return None

    buckets = {"organic": 0, "recommendation": 0, "sponsored": 0, "curated": 0}
    for surface, n in rows:
        n = int(n)
        if surface in {
            "homepage_sponsored", "search_sponsored", "right_rail_banner",
            "email_sponsored", "mega_sponsored",
        }:
            buckets["sponsored"] += n
        elif surface in {
            "homepage_recommended", "search_recommended",
            "job_detail_recommended_cv", "mega_jobs_recommended",
        }:
            buckets["recommendation"] += n
        elif surface in {"employer_spotlight", "career_explore", "university_curated"}:
            buckets["curated"] += n
        else:
            buckets["organic"] += n

    return {k: round(v / total, 2) for k, v in buckets.items() if v > 0}


async def _applied_by_student(
    session: AsyncSession, *, job_id: uuid.UUID, student_user_id: uuid.UUID
) -> bool:
    """Whether this student has an ACTIVE (re-apply-blocking) application.

    This is the canonical "already applied → cannot re-apply" predicate that
    drives the apply-readiness flag / apply-button disable. It MUST match the
    server-side apply guard (``apply_service._active_duplicate`` blocks exactly
    the ACTIVE statuses), so that a state which the backend would actually accept
    a re-application for never shows a disabled apply button. A ``withdrawn``,
    ``rejected``, or ``hired`` application frees the slot (``lifecycle`` docstring)
    and therefore does NOT count as already-applied here — re-apply is allowed.
    """

    result = await session.execute(
        text(
            "SELECT 1 FROM applications"
            " WHERE job_id = :job_id AND applicant_id = :user_id"
            " AND status IN ('submitted', 'under_review')"
            " AND deleted_at IS NULL"
            " LIMIT 1"
        ).bindparams(
            bindparam("job_id", type_=Uuid(as_uuid=True)),
            bindparam("user_id", type_=Uuid(as_uuid=True)),
        ),
        {"job_id": job_id, "user_id": student_user_id},
    )
    return result.first() is not None


# --------------------------------------------------------------------------- #
# Localized guidance strings (vi-first; frontend renders these raw).           #
# --------------------------------------------------------------------------- #

_DEFAULT_LOCALE = "vi"

_GUIDANCE_STRINGS: dict[str, dict[str, str]] = {
    "vi": {
        "already_applied": "Bạn đã ứng tuyển công việc này.",
        "low_signal": (
            "Chưa đủ hoạt động để đánh giá chính xác mức độ cạnh tranh — ứng tuyển "
            "sớm vẫn có lợi."
        ),
        "strengthen_cv": (
            "Củng cố bằng chứng trong CV cho vai trò này trước khi ứng tuyển."
        ),
        "strong_fit_high_comp": (
            "Mức độ cạnh tranh có vẻ cao, nhưng CV của bạn rất phù hợp — hãy ứng "
            "tuyển kèm thư xin việc được điều chỉnh riêng."
        ),
        "deadline_final_days": (
            "Hạn nộp hồ sơ sẽ đóng trong vài ngày tới."
        ),
        "deadline_closing_soon": (
            "Hạn nộp hồ sơ đang đến gần — hãy ứng tuyển sớm."
        ),
        "apply_when_ready": (
            "Hãy ứng tuyển khi CV của bạn phản ánh tốt nhất yêu cầu của vai trò này."
        ),
    },
    "en": {
        "already_applied": "You have already applied to this job.",
        "low_signal": (
            "Not enough activity yet to gauge competition precisely — "
            "applying early still helps."
        ),
        "strengthen_cv": (
            "Strengthen your CV evidence for this role before applying."
        ),
        "strong_fit_high_comp": (
            "Competition looks high, but your CV fit is strong — apply with a "
            "tailored cover letter."
        ),
        "deadline_final_days": (
            "The application deadline is closing in the next few days."
        ),
        "deadline_closing_soon": (
            "The application deadline is approaching — apply soon."
        ),
        "apply_when_ready": (
            "Apply when your CV best reflects this role's requirements."
        ),
    },
}


def _g(locale: str, key: str) -> str:
    """Return a localized guidance string; fall back to ``vi``."""

    table = _GUIDANCE_STRINGS.get(locale, _GUIDANCE_STRINGS[_DEFAULT_LOCALE])
    return table.get(key) or _GUIDANCE_STRINGS[_DEFAULT_LOCALE][key]


def _deadline_guidance(locale: str, deadline_freshness: str) -> str | None:
    if deadline_freshness == "final_days":
        return _g(locale, "deadline_final_days")
    if deadline_freshness == "closing_soon":
        return _g(locale, "deadline_closing_soon")
    return None


def _guidance(
    *,
    signal: str,
    level: str,
    fit_bucket: str,
    deadline_freshness: str,
    already_applied: bool,
    locale: str = _DEFAULT_LOCALE,
) -> list[str]:
    """Deterministic, truthful guidance sentences (no AI narrative dependency).

    Templated from real buckets only — never a hiring-probability claim.

    An already-applied student still receives deadline-freshness guidance and a
    weak-CV nudge where relevant, so the "already applied" line does not swallow
    other useful signals near the deadline (audit #6).
    """

    lines: list[str] = []
    weak_cv = fit_bucket in ("needs_improvement", "developing")
    deadline_line = _deadline_guidance(locale, deadline_freshness)

    if already_applied:
        lines.append(_g(locale, "already_applied"))
        if deadline_line is not None:
            lines.append(deadline_line)
        if weak_cv:
            lines.append(_g(locale, "strengthen_cv"))
        return lines

    if signal == "low_signal":
        lines.append(_g(locale, "low_signal"))
    if weak_cv:
        lines.append(_g(locale, "strengthen_cv"))
    elif fit_bucket in ("competitive", "highly_competitive") and level in (
        "high", "very_high",
    ):
        lines.append(_g(locale, "strong_fit_high_comp"))
    if deadline_line is not None:
        lines.append(deadline_line)

    if not lines:
        lines.append(_g(locale, "apply_when_ready"))
    return lines


async def student_competition_intelligence(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    student_fit_score: int | None,
    locale: str = _DEFAULT_LOCALE,
) -> dict:
    """Bucketed, privacy-safe competition intelligence for one logged-in student.

    Caller (``student_intelligence_service``) has already verified
    ``principal.persona == "student"``. Returns the public ``competition``
    contract sub-object plus two caller-only keys (``_deadline_passed``,
    ``_already_applied``) that must be popped before the object reaches the
    HTTP response — they exist so the composing service can derive apply
    readiness without a second job/application query.
    """

    job = await _load_job(session, job_id=job_id, principal=principal)
    if job is None:
        raise ResourceNotFoundError()

    now = _now()
    required_skills_count = len(job.required_skills or [])
    jd_complexity, _exp_tier, _skills_tier = compute_jd_complexity(
        experience_min_years=job.experience_min_years,
        required_skills_count=required_skills_count,
        employment_type=job.employment_type,
    )

    # Hot path: read the materialized competition inputs from the
    # ``job_competition_daily`` projection (ONE indexed lookup; on a miss a single
    # bounded live compute for this job). The applicant-quality pool is the set of
    # REAL active applicants joined to their immutable snapshot fit — NOT fit-score
    # viewers/browsers. NULL-fit applicants are unknown quality, excluded from the
    # caliber math (never fit 0).
    stats = await competition_projection_service.stats_for_read(
        session, job_id=job_id, org_id=job.org_id, seats=job.headcount
    )
    app_count = stats.active_applications

    # QUALITY-adjusted headline: reads on strong-competitor density (real caliber),
    # so 1000 weak applicants + a handful of strong ones for one seat reads on the
    # handful, not the 1000. Falls back to a capped volume estimate only when the
    # scored pool is too thin to judge caliber (honest cold start). AI never moves
    # this number.
    raw, level, basis = scoring.quality_adjusted_level(stats, jd_complexity)

    deadline_freshness = _deadline_freshness(job.application_deadline, now=now)
    already_applied = False
    if principal.user_id is not None:
        already_applied = await _applied_by_student(
            session, job_id=job_id, student_user_id=principal.user_id
        )

    fit_bucket = _student_fit_bucket(student_fit_score)

    # Coarse, privacy-safe bands over the REAL-applicant distribution. Every
    # caliber band is guarded by a minimum scored pool (never a raw count, an
    # individual score, an exact rank, or an identity).
    applicant_quality_bucket = scoring.applicant_quality_bucket(stats)
    student_standing_bucket = scoring.student_standing_bucket(student_fit_score, stats)
    applicants_per_seat_band = scoring.applicants_per_seat_band(stats)
    strong_competitor_density = scoring.strong_competitor_density(stats)
    standing_vs_strong = scoring.standing_vs_strong(student_fit_score, stats)

    signal = "low_signal" if app_count < _LOW_SIGNAL_APPLICATION_THRESHOLD else "ok"
    source_mix = await _source_mix(session, job_id=job_id)

    guidance = _guidance(
        signal=signal,
        level=level,
        fit_bucket=fit_bucket,
        deadline_freshness=deadline_freshness,
        already_applied=already_applied,
        locale=locale,
    )

    return {
        "score": None if signal == "low_signal" else max(0, min(100, raw)),
        "label": None if signal == "low_signal" else _STUDENT_LABELS[level],
        "signal": signal,
        "basis": None if signal == "low_signal" else basis,
        "seats_bucket": _seats_bucket(job.headcount),
        "application_volume_bucket": _application_volume_bucket(app_count),
        "applicants_per_seat_band": applicants_per_seat_band,
        "strong_competitor_density": strong_competitor_density,
        "applicant_quality_bucket": applicant_quality_bucket,
        "student_fit_bucket": fit_bucket,
        "student_standing_bucket": student_standing_bucket,
        "standing_vs_strong": standing_vs_strong,
        "deadline_freshness": deadline_freshness,
        "source_mix": source_mix,
        "guidance": guidance,
        "_deadline_passed": deadline_freshness == "closed",
        "_already_applied": already_applied,
    }


# --------------------------------------------------------------------------- #
# On-demand AI competition narrative (metered; user-triggered drawer only)      #
# --------------------------------------------------------------------------- #
#
# The deterministic bands above OWN the signal and are FREE. This narrative is a
# single short, grounded paragraph that explains the pre-computed level in plain
# language — produced ONLY when the student opens the Competition drawer, cached,
# and metered on success. It NEVER moves the numbers.

TASK_TYPE_EXPLANATION = "student_competition_explanation"
_COMPETITION_NARRATIVE_TTL_SECONDS = 6 * 3600


async def _charge_competition_energy(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID, level: str
) -> None:
    """Debit the student's AI energy for one freshly-generated narrative.

    Idempotent on the ``(job, level)`` pair so re-opening the drawer while the
    signal is unchanged never double-charges. Best-effort; never breaks the read.
    Stores no provider/model/token internals.
    """

    try:
        ctx = energy_service.build_usage_context(
            principal,
            feature_key=FEATURE_COMPETITION_EXPLANATION,
            task_type=TASK_TYPE_EXPLANATION,
            resource_type="job",
            resource_id=job_id,
            idempotency_parts=(job_id, level),
        )
        await record_billable_usage(
            session,
            ctx=ctx,
            result_status="success",
            base_units=energy_service.charge_units(FEATURE_COMPETITION_EXPLANATION),
        )
    except Exception:  # noqa: BLE001 — accounting must never break the read
        logger.warning("competition_energy_charge_failed", exc_info=True)


async def competition_explanation(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    locale: str = _DEFAULT_LOCALE,
    redis: object | None = None,
) -> dict:
    """On-demand, metered AI narrative for the student Competition drawer.

    Returns ``{level, label, explanation, ai_explanation_available}``. The
    deterministic ``level``/``label`` are always present (they are the product);
    ``explanation`` is the advisory narrative, ``None`` when the AI gate is off,
    the provider fails, weekly energy is exhausted, or the signal is still
    ``low_signal`` (nothing to explain yet). A cache hit returns the stored
    narrative WITHOUT charging (``cached`` → 0 credits); a fresh generation
    charges once (idempotent per ``(job, level)``). Never raises for AI-off /
    failure; provider/model/token/prompt/cost internals are never exposed.
    """

    if principal.persona != "student":
        raise PermissionDeniedError()

    job = await _load_job(session, job_id=job_id, principal=principal)
    if job is None:
        raise ResourceNotFoundError()

    required_skills_count = len(job.required_skills or [])
    jd_complexity, exp_tier, skills_tier = compute_jd_complexity(
        experience_min_years=job.experience_min_years,
        required_skills_count=required_skills_count,
        employment_type=job.employment_type,
    )
    stats = await competition_projection_service.stats_for_read(
        session, job_id=job_id, org_id=job.org_id, seats=job.headcount
    )
    _raw, level, _basis = scoring.quality_adjusted_level(stats, jd_complexity)

    # Not enough activity to explain competition honestly yet.
    if stats.active_applications < _LOW_SIGNAL_APPLICATION_THRESHOLD:
        return {
            "level": None,
            "label": None,
            "explanation": None,
            "ai_explanation_available": False,
        }

    label = _STUDENT_LABELS[level]

    # AI gate OFF -> deterministic level only, no charge.
    if not (
        real_provider_active()
        and runtime_config.current().job_fit_ai_explanation_enabled
    ):
        return {
            "level": level,
            "label": label,
            "explanation": None,
            "ai_explanation_available": False,
        }

    cache_key = f"competition_expl:{job_id}:{level}:{locale}"
    cached = await _cache_get(redis, cache_key)
    if cached is not None:
        # Cache hit: reuse the narrative, charge 0 (already billed on generation).
        return {
            "level": level,
            "label": label,
            "explanation": cached,
            "ai_explanation_available": True,
        }

    # Preflight the weekly energy gate; the narrative is advisory enrichment, so
    # degrade to no-narrative on exhaustion rather than surfacing a 409 here.
    try:
        await energy_service.enforce_energy(session, principal=principal)
    except QuotaExceededError:
        return {
            "level": level,
            "label": label,
            "explanation": None,
            "ai_explanation_available": False,
        }

    explanation, available = await _maybe_explain(
        job_title=job.title,
        level=level,
        experience_tier=exp_tier,
        skills_tier=skills_tier,
        employment_type=job.employment_type,
    )
    if available and explanation is not None:
        await _cache_set(redis, cache_key, explanation)
        await _charge_competition_energy(
            session, principal=principal, job_id=job_id, level=level
        )
        await session.commit()

    return {
        "level": level,
        "label": label,
        "explanation": explanation,
        "ai_explanation_available": available,
    }


async def _cache_get(redis: object | None, key: str) -> str | None:
    if redis is None:
        return None
    try:
        value = await redis.get(key)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — cache is best-effort
        return None
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


async def _cache_set(redis: object | None, key: str, value: str) -> None:
    if redis is None:
        return
    try:
        await redis.set(  # type: ignore[attr-defined]
            key, value, ex=_COMPETITION_NARRATIVE_TTL_SECONDS
        )
    except Exception:  # noqa: BLE001 — cache is best-effort
        logger.debug("competition_narrative_cache_set_failed", exc_info=True)


async def competition_signal(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
) -> dict:
    """Compute and return the competition level signal for a visible job.

    Public (no auth required). Returns a non-enumerable 404 for hidden/closed/
    missing jobs (same semantics as ``job_service.get_job``).

    Privacy: raw ``application_count`` is included in the response only when the
    partner has explicitly opted in via ``job.settings["show_application_count"]``.
    The count is always used in computation regardless.
    """

    job = await _load_job(session, job_id=job_id, principal=principal)
    if job is None:
        raise ResourceNotFoundError()

    # --- Application count (cross-module read; privacy-gated on return) ---
    app_count = await _count_active_applications(session, job_id=job_id)

    # --- Deterministic JD complexity + combined signal ---
    required_skills_count = len(job.required_skills or [])
    jd_complexity, exp_tier, skills_tier = compute_jd_complexity(
        experience_min_years=job.experience_min_years,
        required_skills_count=required_skills_count,
        employment_type=job.employment_type,
    )
    _raw, level = compute_signal(
        jd_complexity=jd_complexity,
        application_count=app_count,
    )

    # --- Optional AI enrichment ---
    explanation, ai_available = await _maybe_explain(
        job_title=job.title,
        level=level,
        experience_tier=exp_tier,
        skills_tier=skills_tier,
        employment_type=job.employment_type,
    )

    # --- Privacy gate: only return raw count when partner opted in ---
    show_count: bool = bool((job.settings or {}).get("show_application_count", False))

    return {
        "level": level,
        "label": _LEVEL_LABELS[level],
        "explanation": explanation,
        "ai_explanation_available": ai_available,
        "basis": "estimated",
        "jd_complexity_score": jd_complexity,
        "application_count": app_count if show_count else None,
        "updated_at": _now().isoformat(),
    }
