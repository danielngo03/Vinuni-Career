"""Deterministic interview-readiness signal (WS-6, Task K).

Pure functions (no I/O) that turn a student's real practice history into an
HONEST readiness signal. Non-negotiables:

- Deterministic: the same attempts always yield the same score/band/trend. No
  model call, no randomness, no fabrication.
- Honest low-data state: below ``MIN_ANSWERS_FOR_SIGNAL`` evaluated answers the
  result is ``status="not_enough_data"`` with ``readiness_pct=None`` — we never
  invent a readiness number from too little practice.
- No leakage: inputs are user-facing feedback scores (1-5) only — no
  provider/model/token/confidence internals ever enter this computation.

The readiness percent maps the average coaching score (1-5) onto 0-100; the trend
compares the most-recent answers against the earlier ones so a student can see
whether they are improving across attempts.
"""

from __future__ import annotations

from dataclasses import dataclass

# A readiness score is only emitted once the student has enough evaluated
# answers for the aggregate to mean something. Below this we return an honest
# "not enough attempts yet" state instead of a fabricated number.
MIN_ANSWERS_FOR_SIGNAL = 3
# Number of most-recent answers used to detect an improving/declining trend.
TREND_WINDOW = 5
# Minimum average-score delta (on the 1-5 scale) to call a trend non-flat.
TREND_EPSILON = 0.34

STATUS_READY = "ready_signal"
STATUS_NOT_ENOUGH = "not_enough_data"

BAND_DEVELOPING = "developing"
BAND_EMERGING = "emerging"
BAND_PROGRESSING = "progressing"
BAND_READY = "interview_ready"

TREND_IMPROVING = "improving"
TREND_STEADY = "steady"
TREND_DECLINING = "declining"


@dataclass(frozen=True, slots=True)
class ReadinessSignal:
    """User-facing readiness state (no internals)."""

    status: str
    attempts: int
    answers_evaluated: int
    readiness_pct: int | None
    band: str | None
    trend: str | None
    answers_needed: int

    def to_public(self) -> dict:
        return {
            "status": self.status,
            "attempts": self.attempts,
            "answers_evaluated": self.answers_evaluated,
            "readiness_pct": self.readiness_pct,
            "band": self.band,
            "trend": self.trend,
            "answers_needed": self.answers_needed,
        }


def _pct_from_avg(avg_score: float) -> int:
    """Map an average 1-5 coaching score onto a 0-100 readiness percent."""
    # 1 -> 0, 5 -> 100, linear in between.
    pct = round((avg_score - 1.0) / 4.0 * 100.0)
    return max(0, min(100, pct))


def _band_from_pct(pct: int) -> str:
    if pct >= 80:
        return BAND_READY
    if pct >= 60:
        return BAND_PROGRESSING
    if pct >= 40:
        return BAND_EMERGING
    return BAND_DEVELOPING


def _trend(scores_chrono: list[int]) -> str:
    """Compare the most-recent answers against the earlier ones.

    ``scores_chrono`` is ordered oldest -> newest. Returns steady when there is
    not enough data on either side of the split to compare.
    """
    n = len(scores_chrono)
    if n < 2 * 2:  # need at least 2 recent + 2 earlier to trust a direction
        return TREND_STEADY
    window = min(TREND_WINDOW, n // 2)
    recent = scores_chrono[-window:]
    earlier = scores_chrono[:-window]
    recent_avg = sum(recent) / len(recent)
    earlier_avg = sum(earlier) / len(earlier)
    delta = recent_avg - earlier_avg
    if delta >= TREND_EPSILON:
        return TREND_IMPROVING
    if delta <= -TREND_EPSILON:
        return TREND_DECLINING
    return TREND_STEADY


def compute_readiness(
    *, attempts: int, answer_scores_chrono: list[int]
) -> ReadinessSignal:
    """Compute the readiness signal from evaluated-answer scores.

    Args:
        attempts: number of practice sessions (attempts) the student has made.
        answer_scores_chrono: every evaluated answer's 1-5 score, ordered
            oldest -> newest across all attempts.
    """
    scores = [max(1, min(5, int(s))) for s in answer_scores_chrono]
    evaluated = len(scores)

    if evaluated < MIN_ANSWERS_FOR_SIGNAL:
        return ReadinessSignal(
            status=STATUS_NOT_ENOUGH,
            attempts=attempts,
            answers_evaluated=evaluated,
            readiness_pct=None,
            band=None,
            trend=None,
            answers_needed=MIN_ANSWERS_FOR_SIGNAL - evaluated,
        )

    avg = sum(scores) / evaluated
    pct = _pct_from_avg(avg)
    return ReadinessSignal(
        status=STATUS_READY,
        attempts=attempts,
        answers_evaluated=evaluated,
        readiness_pct=pct,
        band=_band_from_pct(pct),
        trend=_trend(scores),
        answers_needed=0,
    )
