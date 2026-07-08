"""Unit tests for the deterministic competition signal algorithm.

All tests are pure-function, no I/O, no DB, no AI provider calls.
Covers: JD complexity scoring, level mapping, application count clamping,
determinism guarantee, and boundary values.
"""

from __future__ import annotations

import pytest

from app.modules.opportunities.application.competition_service import (
    compute_jd_complexity,
    compute_signal,
    map_raw_to_level,
)


# --------------------------------------------------------------------------- #
# JD complexity: experience tier                                               #
# --------------------------------------------------------------------------- #


def test_experience_none_is_entry() -> None:
    score, exp_tier, _ = compute_jd_complexity(
        experience_min_years=None, required_skills_count=0, employment_type="full_time"
    )
    assert exp_tier == "entry"
    assert score == 0


def test_experience_zero_is_entry() -> None:
    score, exp_tier, _ = compute_jd_complexity(
        experience_min_years=0, required_skills_count=0, employment_type="full_time"
    )
    assert exp_tier == "entry"
    assert score == 0


def test_experience_1_is_junior() -> None:
    _, exp_tier, _ = compute_jd_complexity(
        experience_min_years=1, required_skills_count=0, employment_type="full_time"
    )
    assert exp_tier == "junior"


def test_experience_2_is_junior() -> None:
    _, exp_tier, _ = compute_jd_complexity(
        experience_min_years=2, required_skills_count=0, employment_type="full_time"
    )
    assert exp_tier == "junior"


def test_experience_3_is_mid() -> None:
    _, exp_tier, _ = compute_jd_complexity(
        experience_min_years=3, required_skills_count=0, employment_type="full_time"
    )
    assert exp_tier == "mid"


def test_experience_5_is_mid() -> None:
    """5 falls in the mid tier (3-5 inclusive); 6+ is senior."""
    _, exp_tier, _ = compute_jd_complexity(
        experience_min_years=5, required_skills_count=0, employment_type="full_time"
    )
    assert exp_tier == "mid"


def test_experience_6_is_senior() -> None:
    _, exp_tier, _ = compute_jd_complexity(
        experience_min_years=6, required_skills_count=0, employment_type="full_time"
    )
    assert exp_tier == "senior"


def test_experience_10_is_senior() -> None:
    _, exp_tier, _ = compute_jd_complexity(
        experience_min_years=10, required_skills_count=0, employment_type="full_time"
    )
    assert exp_tier == "senior"


# --------------------------------------------------------------------------- #
# JD complexity: skills tier                                                  #
# --------------------------------------------------------------------------- #


def test_skills_0_is_low() -> None:
    _, _, skills_tier = compute_jd_complexity(
        experience_min_years=None, required_skills_count=0, employment_type="full_time"
    )
    assert skills_tier == "low"


def test_skills_3_is_low() -> None:
    _, _, skills_tier = compute_jd_complexity(
        experience_min_years=None, required_skills_count=3, employment_type="full_time"
    )
    assert skills_tier == "low"


def test_skills_4_is_medium() -> None:
    _, _, skills_tier = compute_jd_complexity(
        experience_min_years=None, required_skills_count=4, employment_type="full_time"
    )
    assert skills_tier == "medium"


def test_skills_6_is_medium() -> None:
    _, _, skills_tier = compute_jd_complexity(
        experience_min_years=None, required_skills_count=6, employment_type="full_time"
    )
    assert skills_tier == "medium"


def test_skills_7_is_high() -> None:
    _, _, skills_tier = compute_jd_complexity(
        experience_min_years=None, required_skills_count=7, employment_type="full_time"
    )
    assert skills_tier == "high"


# --------------------------------------------------------------------------- #
# JD complexity: employment type delta                                         #
# --------------------------------------------------------------------------- #


def test_internship_reduces_score_by_ten() -> None:
    score_ft, _, _ = compute_jd_complexity(
        experience_min_years=None, required_skills_count=0, employment_type="full_time"
    )
    score_int, _, _ = compute_jd_complexity(
        experience_min_years=None, required_skills_count=0, employment_type="internship"
    )
    assert score_int == score_ft - 10


def test_contract_adds_five_to_score() -> None:
    score_ft, _, _ = compute_jd_complexity(
        experience_min_years=None, required_skills_count=0, employment_type="full_time"
    )
    score_ct, _, _ = compute_jd_complexity(
        experience_min_years=None, required_skills_count=0, employment_type="contract"
    )
    assert score_ct == score_ft + 5


def test_full_time_neutral_employment_delta() -> None:
    score, _, _ = compute_jd_complexity(
        experience_min_years=None, required_skills_count=0, employment_type="full_time"
    )
    assert score == 0


# --------------------------------------------------------------------------- #
# Combined scores for representative real-world cases                          #
# --------------------------------------------------------------------------- #


def test_entry_internship_minimal_skills_lowest_score() -> None:
    """No experience + 0 skills + internship = 0 + 0 − 10 = −10."""
    score, exp_tier, _ = compute_jd_complexity(
        experience_min_years=None, required_skills_count=0, employment_type="internship"
    )
    assert score == -10
    assert exp_tier == "entry"


def test_senior_contract_high_skills_max_jd_score() -> None:
    """6+ years (+30) + 7 skills (+20) + contract (+5) = 55."""
    score, _, _ = compute_jd_complexity(
        experience_min_years=6, required_skills_count=7, employment_type="contract"
    )
    assert score == 55


def test_mid_fulltime_medium_skills_score() -> None:
    """3 years (+20) + 4 skills (+10) + full_time (+0) = 30."""
    score, _, _ = compute_jd_complexity(
        experience_min_years=3, required_skills_count=4, employment_type="full_time"
    )
    assert score == 30


# --------------------------------------------------------------------------- #
# Level mapping                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("raw,expected", [
    (-10, "low"),
    (0, "low"),
    (19, "low"),
    (20, "medium"),
    (30, "medium"),
    (44, "medium"),
    (45, "high"),
    (55, "high"),
    (64, "high"),
    (65, "very_high"),
    (100, "very_high"),
])
def test_level_mapping_boundaries(raw: int, expected: str) -> None:
    assert map_raw_to_level(raw) == expected


# --------------------------------------------------------------------------- #
# compute_signal: application count contribution and clamping                 #
# --------------------------------------------------------------------------- #


def test_zero_applications_no_contribution() -> None:
    _raw, level = compute_signal(jd_complexity=0, application_count=0)
    assert level == "low"  # raw = 0 < 20


def test_application_count_adds_three_per_app() -> None:
    """5 applications contribute 15 to the raw score (5 × 3 = 15)."""
    # jd_complexity=20 + 5*3=15 → raw=35 → medium
    raw, level = compute_signal(jd_complexity=20, application_count=5)
    assert raw == 35
    assert level == "medium"


def test_application_count_clamped_at_40() -> None:
    """14 apps: 14 × 3 = 42 → clamped to 40; 20 apps also clamped to 40."""
    raw_14, level_14 = compute_signal(jd_complexity=0, application_count=14)
    raw_20, level_20 = compute_signal(jd_complexity=0, application_count=20)
    # Both: app contribution = 40, raw = 40, level = medium
    assert raw_14 == 40
    assert raw_20 == 40
    assert level_14 == "medium"
    assert level_20 == "medium"


def test_clamp_at_exactly_thirteen_apps() -> None:
    """13 apps: 13 × 3 = 39 (below clamp); 14 apps: 14 × 3 = 42 → 40 (clamped)."""
    raw_13, _ = compute_signal(jd_complexity=0, application_count=13)
    raw_14, _ = compute_signal(jd_complexity=0, application_count=14)
    assert raw_13 == 39
    assert raw_14 == 40  # clamped


def test_many_applications_drives_level_to_very_high() -> None:
    """Mid JD complexity (30) + max app contribution (40) = 70 → very_high."""
    raw, level = compute_signal(jd_complexity=30, application_count=14)
    assert raw == 70
    assert level == "very_high"


# --------------------------------------------------------------------------- #
# Determinism guarantee                                                        #
# --------------------------------------------------------------------------- #


def test_same_inputs_always_same_output() -> None:
    """Determinism: identical inputs must produce identical results every time."""
    kwargs = dict(
        experience_min_years=3,
        required_skills_count=5,
        employment_type="full_time",
    )
    assert compute_jd_complexity(**kwargs) == compute_jd_complexity(**kwargs)

    jd_score, _, _ = compute_jd_complexity(**kwargs)
    sig_kwargs = dict(jd_complexity=jd_score, application_count=7)
    assert compute_signal(**sig_kwargs) == compute_signal(**sig_kwargs)


# --------------------------------------------------------------------------- #
# End-to-end algorithm flow (pure)                                             #
# --------------------------------------------------------------------------- #


def test_e2e_low_competition_internship() -> None:
    """An entry-level internship with few skills and no applications is 'low'."""
    jd_score, _, _ = compute_jd_complexity(
        experience_min_years=None, required_skills_count=2, employment_type="internship"
    )
    # 0 + 0 - 10 = -10
    assert jd_score == -10
    raw, level = compute_signal(jd_complexity=jd_score, application_count=0)
    assert raw == -10
    assert level == "low"


def test_e2e_high_competition_senior_fulltime_many_applicants() -> None:
    """Senior full-time + 8 skills + 10 active applications is 'very_high'."""
    jd_score, _, _ = compute_jd_complexity(
        experience_min_years=7, required_skills_count=8, employment_type="full_time"
    )
    # 30 + 20 + 0 = 50
    assert jd_score == 50
    raw, level = compute_signal(jd_complexity=jd_score, application_count=10)
    # 50 + min(30, 40) = 80
    assert raw == 80
    assert level == "very_high"
