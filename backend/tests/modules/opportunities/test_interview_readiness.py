"""Deterministic interview-readiness signal — pure function tests (WS-6, Task K).

The readiness signal must be deterministic, honest at low data, and never
fabricate a number. These tests pin the exact math + the low-data gate.

Run:
    cd backend && uv run pytest tests/modules/opportunities/test_interview_readiness.py -q
"""

from __future__ import annotations

from app.modules.opportunities.domain.interview_readiness import (
    BAND_DEVELOPING,
    BAND_PROGRESSING,
    BAND_READY,
    MIN_ANSWERS_FOR_SIGNAL,
    STATUS_NOT_ENOUGH,
    STATUS_READY,
    TREND_DECLINING,
    TREND_IMPROVING,
    TREND_STEADY,
    compute_readiness,
)


def test_low_data_returns_honest_not_enough_state() -> None:
    """Below the minimum evaluated answers → no fabricated score."""
    sig = compute_readiness(attempts=1, answer_scores_chrono=[4, 5])
    assert sig.status == STATUS_NOT_ENOUGH
    assert sig.readiness_pct is None
    assert sig.band is None
    assert sig.trend is None
    assert sig.answers_evaluated == 2
    assert sig.answers_needed == MIN_ANSWERS_FOR_SIGNAL - 2


def test_zero_attempts_is_not_enough() -> None:
    sig = compute_readiness(attempts=0, answer_scores_chrono=[])
    assert sig.status == STATUS_NOT_ENOUGH
    assert sig.readiness_pct is None
    assert sig.answers_needed == MIN_ANSWERS_FOR_SIGNAL


def test_deterministic_pct_mapping() -> None:
    """1-5 average maps linearly onto 0-100 (same input → same output)."""
    # avg 4.0 -> (4-1)/4*100 = 75
    sig = compute_readiness(attempts=3, answer_scores_chrono=[4, 4, 4])
    assert sig.status == STATUS_READY
    assert sig.readiness_pct == 75
    assert sig.band == BAND_PROGRESSING
    # Determinism: recompute is identical.
    again = compute_readiness(attempts=3, answer_scores_chrono=[4, 4, 4])
    assert again.to_public() == sig.to_public()


def test_band_edges() -> None:
    # all 5s -> 100 -> interview_ready
    assert compute_readiness(attempts=3, answer_scores_chrono=[5, 5, 5]).band == BAND_READY
    # all 1s -> 0 -> developing
    assert (
        compute_readiness(attempts=3, answer_scores_chrono=[1, 1, 1]).band
        == BAND_DEVELOPING
    )


def test_trend_improving() -> None:
    """Recent answers stronger than earlier ones → improving."""
    scores = [2, 2, 2, 2, 5, 5, 5, 5]  # earlier weak, recent strong
    sig = compute_readiness(attempts=4, answer_scores_chrono=scores)
    assert sig.trend == TREND_IMPROVING


def test_trend_declining() -> None:
    scores = [5, 5, 5, 5, 2, 2, 2, 2]
    sig = compute_readiness(attempts=4, answer_scores_chrono=scores)
    assert sig.trend == TREND_DECLINING


def test_trend_steady_when_flat() -> None:
    sig = compute_readiness(attempts=4, answer_scores_chrono=[3, 3, 3, 3, 3, 3])
    assert sig.trend == TREND_STEADY


def test_scores_clamped_to_1_5() -> None:
    """Out-of-range scores are clamped (no crash, no fabricated inflation)."""
    sig = compute_readiness(attempts=3, answer_scores_chrono=[0, 9, 3])
    # clamps to [1, 5, 3] -> avg 3.0 -> 50
    assert sig.readiness_pct == 50
