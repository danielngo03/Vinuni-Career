"""Unit tests for the ad allocation-engine pure domain (spec §7.0).

Covers the coarse targeting allowlist + forbidden-dimension guard, viewer-segment
sanitization, targeting match, segment key, and the budget/pacing math — all pure,
no DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.modules.advertising.domain import campaign as lifecycle
from app.modules.advertising.domain import pacing as pacing_math
from app.modules.advertising.domain import targeting as t


# --------------------------------------------------------------------------- #
# Targeting allowlist + forbidden guard                                       #
# --------------------------------------------------------------------------- #


def test_validate_campaign_targeting_keeps_coarse_and_normalizes():
    out = t.validate_campaign_targeting(
        {"locations": ["Hanoi", "Ho Chi Minh"], "careers": ["Software Engineering"]}
    )
    assert out["locations"] == ["hanoi", "ho_chi_minh"]
    assert out["careers"] == ["software_engineering"]


def test_validate_campaign_targeting_drops_unknown_values_but_keeps_dim():
    # "atlantis" is not an allowlisted coarse location -> dropped; dim omitted.
    out = t.validate_campaign_targeting({"locations": ["atlantis"]})
    assert out == {}


@pytest.mark.parametrize(
    "forbidden",
    ["gps", "latitude", "exact_location", "health", "gender", "religion", "income", "gclid"],
)
def test_validate_campaign_targeting_rejects_forbidden_dimension(forbidden):
    with pytest.raises(t.ForbiddenTargetingDimension):
        t.validate_campaign_targeting({forbidden: ["x"]})


def test_validate_campaign_targeting_rejects_unknown_key():
    with pytest.raises(t.UnknownTargetingDimension):
        t.validate_campaign_targeting({"favorite_color": ["blue"]})


def test_empty_targeting_is_broad():
    assert t.validate_campaign_targeting(None) == {}
    assert t.validate_campaign_targeting({}) == {}


# --------------------------------------------------------------------------- #
# Viewer segment sanitization (default-deny, never raises)                    #
# --------------------------------------------------------------------------- #


def test_sanitize_viewer_segment_drops_forbidden_and_keeps_coarse():
    seg = t.sanitize_viewer_segment(
        {
            "locations": ["hanoi"],
            "majors": ["computer_science"],
            "gps": "21.02,105.83",  # forbidden -> dropped
            "email": "a@b.com",  # forbidden -> dropped
            "latitude": 21.0,  # forbidden -> dropped
        }
    )
    assert seg.locations == frozenset({"hanoi"})
    assert seg.majors == frozenset({"computer_science"})
    # No forbidden signal survived anywhere.
    assert not seg.careers and not seg.work_modes


def test_sanitize_viewer_segment_maps_discovery_coarse_tags_shape():
    seg = t.sanitize_viewer_segment(
        {
            "city": "hanoi",
            "role_families": ["data", "finance"],
            "work_mode": "remote",
            "device_type": "mobile",
        }
    )
    assert seg.locations == frozenset({"hanoi"})
    assert seg.careers == frozenset({"data", "finance"})
    assert seg.work_modes == frozenset({"remote"})
    assert seg.device_classes == frozenset({"mobile"})


# --------------------------------------------------------------------------- #
# Match + segment key                                                         #
# --------------------------------------------------------------------------- #


def test_untargeted_campaign_matches_everyone():
    m = t.match_targeting({}, t.ViewerSegment(locations=frozenset({"hcmc"})))
    assert m.matched and m.score == 0 and m.reason == {"untargeted": True}


def test_targeted_campaign_matches_on_overlap():
    m = t.match_targeting(
        {"locations": ["hanoi"], "careers": ["data"]},
        t.ViewerSegment(locations=frozenset({"hanoi"})),
    )
    assert m.matched and m.score == 1
    assert m.reason["matched_dimensions"]["locations"] == ["hanoi"]


def test_targeted_campaign_no_overlap_does_not_match():
    m = t.match_targeting(
        {"locations": ["hanoi"]},
        t.ViewerSegment(locations=frozenset({"ho_chi_minh"})),
    )
    assert not m.matched


def test_segment_key_stable_and_anon_for_empty():
    assert t.segment_key(t.ViewerSegment()) == "anon"
    a = t.segment_key(t.ViewerSegment(locations=frozenset({"hanoi", "ho_chi_minh"})))
    b = t.segment_key(t.ViewerSegment(locations=frozenset({"ho_chi_minh", "hanoi"})))
    assert a == b == "loc:hanoi,ho_chi_minh"


# --------------------------------------------------------------------------- #
# Pacing math                                                                 #
# --------------------------------------------------------------------------- #


def _window(days: int) -> tuple[datetime, datetime]:
    start = datetime(2026, 7, 10, tzinfo=UTC)
    return start, start + timedelta(days=days)


def test_impression_goal_and_cost_per_impression():
    assert pacing_math.impression_goal(budget=Decimal("100"), cpm=Decimal("50000")) == 2
    assert pacing_math.cost_per_impression(cpm=Decimal("50000")) == Decimal("50.0000")
    assert pacing_math.impression_goal(budget=Decimal("100"), cpm=Decimal("0")) == 0


def test_even_pacing_daily_cap_and_asap_uncapped():
    start, end = _window(10)
    cap = pacing_math.daily_impression_cap(
        budget=Decimal("500000"), cpm=Decimal("50000"), pacing="even", start_at=start, end_at=end
    )
    # goal = 10_000 impressions over 10 days -> 1000/day.
    assert cap == 1000
    assert (
        pacing_math.daily_impression_cap(
            budget=Decimal("500000"), cpm=Decimal("50000"), pacing="asap",
            start_at=start, end_at=end,
        )
        is None
    )


def test_budget_exhausted_and_paced_out():
    assert pacing_math.budget_exhausted(spent=Decimal("100"), budget=Decimal("100"))
    assert not pacing_math.budget_exhausted(spent=Decimal("99"), budget=Decimal("100"))
    assert pacing_math.is_paced_out(impressions_today=10, daily_cap=10)
    assert not pacing_math.is_paced_out(impressions_today=9, daily_cap=10)
    assert not pacing_math.is_paced_out(impressions_today=99, daily_cap=None)


def test_compute_pacing_state_eligibility():
    start, end = _window(10)
    state = pacing_math.compute_pacing_state(
        pacing="even",
        budget=Decimal("500000"),
        spent=Decimal("0"),
        cpm=Decimal("50000"),
        start_at=start,
        end_at=end,
        impressions_today=0,
    )
    assert state.eligible
    paced = pacing_math.compute_pacing_state(
        pacing="even",
        budget=Decimal("500000"),
        spent=Decimal("0"),
        cpm=Decimal("50000"),
        start_at=start,
        end_at=end,
        impressions_today=state.daily_cap or 0,
    )
    assert not paced.eligible and paced.paced_out
    broke = pacing_math.compute_pacing_state(
        pacing="asap",
        budget=Decimal("100"),
        spent=Decimal("100"),
        cpm=Decimal("50000"),
        start_at=start,
        end_at=end,
        impressions_today=0,
    )
    assert not broke.eligible and broke.budget_exhausted


# --------------------------------------------------------------------------- #
# Campaign lifecycle                                                          #
# --------------------------------------------------------------------------- #


def test_campaign_transitions():
    assert lifecycle.can_transition("submit", lifecycle.DRAFT)
    assert lifecycle.can_transition("approve", lifecycle.PENDING_REVIEW)
    assert lifecycle.target_state("approve") == lifecycle.APPROVED
    assert not lifecycle.can_transition("approve", lifecycle.DRAFT)
    assert lifecycle.can_transition("pause", lifecycle.ACTIVE)
    assert lifecycle.can_transition("resume", lifecycle.PAUSED)
