"""Pure, deterministic competition-band scoring (opportunities domain).

The single source of truth for turning a job's REAL-APPLICANT distribution into
privacy-safe, coarse competition bands. No I/O, no DB, no AI — every function
here is a pure mapping from :class:`CompetitionStats` (+ the student's own fit)
to a band label, so the LIVE compute path and the ``job_competition_daily``
projection read path derive IDENTICAL bands from the SAME materialized inputs
(the projection stores exactly the fields :class:`CompetitionStats` carries).

Design rules (``docs/PRODUCT_REALITY_REBUILD_SPEC.md`` WS-5, ``.claude/rules``):

- Competition is grounded in the CALIBER of real applicants, never raw volume
  and never browsers/viewers. The applicant-quality distribution is built from
  ACTUAL active applicants joined to their immutable snapshot ``fit_score``
  (WS-5). Applicants whose snapshot has no deterministic fit (uploaded-document
  applies, pre-migration history) are UNKNOWN quality — counted in the total
  ``active_applications`` but EXCLUDED from every caliber bucket. They are never
  treated as fit 0.
- Bands are coarse and privacy-safe: never a raw count, an individual score, an
  exact rank/percentile, or an identity. Caliber-dependent bands stay
  ``low_signal`` / ``unknown`` below :data:`MIN_QUALITY_POOL` so a coarse band
  over a handful of rows can never hint at one individual.
- The headline level is QUALITY-ADJUSTED: it reads on the strong-competitor
  density (strong applicants per seat), so a job with 1000 weak applicants and a
  handful of strong ones for one seat reads on the handful, not the 1000. Only
  when the scored pool is too thin to judge caliber does it fall back to a
  capped application-volume estimate (honest cold start).
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Thresholds (INTERNAL — never surfaced; only the derived bands are)           #
# --------------------------------------------------------------------------- #

# A "strong competitor" is an active applicant whose deterministic apply-time CV
# fit is >= this (matches the good_fit / competitive product boundary).
STRONG_THRESHOLD = 70
# The top ("highly competitive") tier.
TOP_THRESHOLD = 85
# A mid applicant sits in [MIXED_THRESHOLD, STRONG_THRESHOLD).
MIXED_THRESHOLD = 50

# Minimum SCORED (fit-known) active applicants before any caliber band may be
# emitted — statistical + privacy floor.
MIN_QUALITY_POOL = 5
# Minimum total active applicants before the applicants-per-seat band is emitted.
MIN_ACTIVE_POOL = 5

# Quality-adjusted headline: strong-per-seat -> pressure. Scaled + capped so a
# handful of strong applicants for one seat reads "high", while thousands of weak
# ones contribute nothing to the headline.
_STRONG_PRESSURE_SCALE = 15
_STRONG_PRESSURE_CAP = 55

# Cold-start volume fallback (used ONLY when the scored pool is below
# MIN_QUALITY_POOL): the legacy capped application-volume contribution.
_VOLUME_PER_APP = 3
_VOLUME_CAP = 40


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


@dataclass(frozen=True, slots=True)
class CompetitionStats:
    """Materialized, student-agnostic competition inputs for one job.

    Exactly the fields the ``job_competition_daily`` projection persists, so a
    projection read reconstructs this object verbatim and every band below is
    identical to a live compute. The four ``dist_*`` buckets partition the SCORED
    active applicants (those with a snapshot ``fit_score``) by caliber; NULL-fit
    applicants are excluded from them but still count in ``active_applications``.
    """

    seats: int
    active_applications: int
    dist_developing: int  # scored fit < MIXED_THRESHOLD
    dist_mixed: int  # [MIXED_THRESHOLD, STRONG_THRESHOLD)
    dist_strong: int  # [STRONG_THRESHOLD, TOP_THRESHOLD)
    dist_top: int  # >= TOP_THRESHOLD

    @property
    def scored_applicants(self) -> int:
        return (
            self.dist_developing + self.dist_mixed + self.dist_strong + self.dist_top
        )

    @property
    def strong_applicants(self) -> int:
        """Active applicants at or above the strong bar (caliber, not volume)."""

        return self.dist_strong + self.dist_top


def histogram(scored_fits: list[int]) -> tuple[int, int, int, int]:
    """Partition scored fit values into ``(developing, mixed, strong, top)``."""

    developing = mixed = strong = top = 0
    for fit in scored_fits:
        if fit >= TOP_THRESHOLD:
            top += 1
        elif fit >= STRONG_THRESHOLD:
            strong += 1
        elif fit >= MIXED_THRESHOLD:
            mixed += 1
        else:
            developing += 1
    return developing, mixed, strong, top


def stats_from_pool(
    *, seats: int, active_applications: int, scored_fits: list[int]
) -> CompetitionStats:
    """Build :class:`CompetitionStats` from the real active-applicant pool.

    ``scored_fits`` are the non-NULL apply-time fit scores of active applicants;
    ``active_applications`` is the TOTAL active count (NULL-fit applicants
    included in the total, excluded from ``scored_fits``).
    """

    developing, mixed, strong, top = histogram(scored_fits)
    return CompetitionStats(
        seats=max(seats, 0),
        active_applications=active_applications,
        dist_developing=developing,
        dist_mixed=mixed,
        dist_strong=strong,
        dist_top=top,
    )


# --------------------------------------------------------------------------- #
# Level mapping                                                                 #
# --------------------------------------------------------------------------- #


def map_raw_to_level(raw: int) -> str:
    """Map a combined raw score to a competition level key."""

    if raw < 20:
        return "low"
    if raw < 45:
        return "medium"
    if raw < 65:
        return "high"
    return "very_high"


def volume_raw(jd_complexity: int, active_applications: int) -> int:
    """Legacy capped application-volume raw (kept for the public signal + the
    cold-start fallback). ``raw = jd + clamp(apps * 3, 0, 40)``."""

    contribution = _clamp(active_applications * _VOLUME_PER_APP, 0, _VOLUME_CAP)
    return jd_complexity + contribution


def quality_adjusted_level(
    stats: CompetitionStats, jd_complexity: int
) -> tuple[int, str, str]:
    """Return ``(raw_score, level_key, basis)`` for the student headline.

    ``basis`` is ``"applicant_caliber"`` when the scored pool is deep enough to
    judge caliber (headline reads on strong-per-seat), else
    ``"application_volume"`` (honest cold-start fallback on capped volume). AI
    never touches this — it is a pure function of real applicant data + the JD.
    """

    if stats.scored_applicants >= MIN_QUALITY_POOL:
        per_seat = stats.strong_applicants / max(stats.seats, 1)
        pressure = _clamp(
            round(per_seat * _STRONG_PRESSURE_SCALE), 0, _STRONG_PRESSURE_CAP
        )
        raw = jd_complexity + pressure
        return _clamp(raw, 0, 100), map_raw_to_level(raw), "applicant_caliber"

    raw = volume_raw(jd_complexity, stats.active_applications)
    return _clamp(raw, 0, 100), map_raw_to_level(raw), "application_volume"


# --------------------------------------------------------------------------- #
# Coarse bands                                                                  #
# --------------------------------------------------------------------------- #


def applicants_per_seat_band(stats: CompetitionStats) -> str:
    """Total applicants relative to seats: ``low``/``moderate``/``high``/
    ``very_high`` — or ``low_signal`` below :data:`MIN_ACTIVE_POOL`."""

    if stats.active_applications < MIN_ACTIVE_POOL:
        return "low_signal"
    per_seat = stats.active_applications / max(stats.seats, 1)
    if per_seat < 5:
        return "low"
    if per_seat < 15:
        return "moderate"
    if per_seat < 40:
        return "high"
    return "very_high"


def strong_competitor_density(stats: CompetitionStats) -> str:
    """Strong applicants per seat: ``few``/``some``/``many`` — or ``low_signal``
    below :data:`MIN_QUALITY_POOL` scored applicants (caliber unknown)."""

    if stats.scored_applicants < MIN_QUALITY_POOL:
        return "low_signal"
    per_seat = stats.strong_applicants / max(stats.seats, 1)
    if per_seat < 1:
        return "few"
    if per_seat < 3:
        return "some"
    return "many"


def applicant_quality_bucket(stats: CompetitionStats) -> str:
    """Coarse caliber of the SCORED pool from its median band.

    ``strong`` / ``mixed`` / ``developing`` — or ``unknown`` below
    :data:`MIN_QUALITY_POOL`. Derived from the histogram median band only (never
    an individual value): the lower-median element decides the bucket, which is
    exactly the side of the 50/70 boundaries the median falls on.
    """

    n = stats.scored_applicants
    if n < MIN_QUALITY_POOL:
        return "unknown"
    median_index = (n - 1) // 2  # lower median, 0-based
    if median_index < stats.dist_developing:
        return "developing"
    if median_index < stats.dist_developing + stats.dist_mixed:
        return "mixed"
    return "strong"  # median lands in the strong or top band


def _student_band_index(fit: int) -> int:
    if fit >= TOP_THRESHOLD:
        return 3
    if fit >= STRONG_THRESHOLD:
        return 2
    if fit >= MIXED_THRESHOLD:
        return 1
    return 0


def student_standing_bucket(student_fit: int | None, stats: CompetitionStats) -> str:
    """Coarse position of the student within the SCORED pool (three thirds).

    ``ahead_of_most`` / ``middle_of_pack`` / ``behind_most`` — or ``unknown``
    below :data:`MIN_QUALITY_POOL`. Computed from the caliber histogram (the
    fraction of the pool in the student's band or lower), so it can never be
    reversed into another candidate's score or an exact ordering.
    """

    n = stats.scored_applicants
    if student_fit is None or n < MIN_QUALITY_POOL:
        return "unknown"
    counts = (
        stats.dist_developing,
        stats.dist_mixed,
        stats.dist_strong,
        stats.dist_top,
    )
    band = _student_band_index(student_fit)
    at_or_below = sum(counts[: band + 1])
    fraction = at_or_below / n
    if fraction >= 0.66:
        return "ahead_of_most"
    if fraction >= 0.33:
        return "middle_of_pack"
    return "behind_most"


def standing_vs_strong(student_fit: int | None, stats: CompetitionStats) -> str:
    """Where the student stands relative to the STRONG competitor pool.

    ``ahead`` (top tier) / ``among`` (a strong competitor) / ``behind`` (below
    the strong bar) — or ``low_signal`` when there is no student fit, the scored
    pool is below :data:`MIN_QUALITY_POOL`, or no strong pool exists to compare
    against. Derived purely from the student's OWN fit against fixed thresholds
    (contextualized by the existence of a real strong contingent), so it exposes
    nothing about any individual competitor.
    """

    if (
        student_fit is None
        or stats.scored_applicants < MIN_QUALITY_POOL
        or stats.strong_applicants < 1
    ):
        return "low_signal"
    if student_fit >= TOP_THRESHOLD:
        return "ahead"
    if student_fit >= STRONG_THRESHOLD:
        return "among"
    return "behind"
