"""Budget/pacing math for the ad allocation engine (pure; no I/O).

A campaign's ``budget_amount`` buys a notional impression goal via a frozen CPM
(``cost per 1000 impressions``). Delivery spends against the budget one impression
at a time; the engine must NOT blow the whole budget instantly
(``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §7.0 "Pacing spreads a campaign's
budget across its run window", "Fairness/anti-starvation"):

- ``even`` pacing computes a per-day impression cap = ``impression_goal / run_days``
  and throttles a campaign once today's delivery reaches that cap;
- ``asap`` pacing has no daily cap (deliver until the budget is exhausted).

A campaign is INELIGIBLE for a slot when its budget is exhausted or it is paced-out
for the day. All math is deterministic and integer/`Decimal`-safe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

# The two pacing codes live in :mod:`campaign`; re-imported here for eligibility.
from app.modules.advertising.domain.campaign import PACING_EVEN

_MILLE = Decimal(1000)


def impression_goal(*, budget: Decimal, cpm: Decimal) -> int:
    """Notional impressions a budget buys at ``cpm`` cost-per-1000. 0 if cpm<=0."""

    if cpm is None or cpm <= 0:
        return 0
    return int((budget / cpm) * _MILLE)


def cost_per_impression(*, cpm: Decimal) -> Decimal:
    """Money spent per delivered impression (``cpm / 1000``)."""

    if cpm is None or cpm <= 0:
        return Decimal("0")
    return (cpm / _MILLE).quantize(Decimal("0.0001"))


def run_days(*, start_at: datetime, end_at: datetime) -> int:
    """Whole days in the run window (min 1); used to spread ``even`` pacing."""

    delta = end_at - start_at
    days = math.ceil(delta.total_seconds() / 86400.0)
    return max(1, days)


def daily_impression_cap(
    *, budget: Decimal, cpm: Decimal, pacing: str, start_at: datetime, end_at: datetime
) -> int | None:
    """Per-day impression cap for ``even`` pacing; ``None`` for ``asap`` (no cap)."""

    if pacing != PACING_EVEN:
        return None
    goal = impression_goal(budget=budget, cpm=cpm)
    if goal <= 0:
        return None
    return max(1, math.ceil(goal / run_days(start_at=start_at, end_at=end_at)))


def budget_exhausted(*, spent: Decimal, budget: Decimal) -> bool:
    """True once cumulative spend has reached the campaign budget."""

    return spent >= budget


def is_paced_out(*, impressions_today: int, daily_cap: int | None) -> bool:
    """True when ``even`` pacing has delivered its daily share already."""

    return daily_cap is not None and impressions_today >= daily_cap


@dataclass(frozen=True, slots=True)
class PacingState:
    """The pacing snapshot recorded on each allocation decision (audit + reporting)."""

    pacing: str
    budget: Decimal
    spent: Decimal
    cpm: Decimal
    impression_goal: int
    daily_cap: int | None
    impressions_today: int
    budget_exhausted: bool
    paced_out: bool

    @property
    def eligible(self) -> bool:
        """Serving-eligible only when in-budget AND not paced-out for the day."""

        return not self.budget_exhausted and not self.paced_out

    def as_dict(self) -> dict:
        return {
            "pacing": self.pacing,
            "budget": f"{self.budget:.2f}",
            "spent": f"{self.spent:.2f}",
            "impression_goal": self.impression_goal,
            "daily_cap": self.daily_cap,
            "impressions_today": self.impressions_today,
            "budget_exhausted": self.budget_exhausted,
            "paced_out": self.paced_out,
        }


def compute_pacing_state(
    *,
    pacing: str,
    budget: Decimal,
    spent: Decimal,
    cpm: Decimal,
    start_at: datetime,
    end_at: datetime,
    impressions_today: int,
) -> PacingState:
    """Assemble the full :class:`PacingState` for a campaign at ``now``."""

    goal = impression_goal(budget=budget, cpm=cpm)
    cap = daily_impression_cap(
        budget=budget, cpm=cpm, pacing=pacing, start_at=start_at, end_at=end_at
    )
    exhausted = budget_exhausted(spent=spent, budget=budget)
    paced = is_paced_out(impressions_today=impressions_today, daily_cap=cap)
    return PacingState(
        pacing=pacing,
        budget=budget,
        spent=spent,
        cpm=cpm,
        impression_goal=goal,
        daily_cap=cap,
        impressions_today=impressions_today,
        budget_exhausted=exhausted,
        paced_out=paced,
    )


def pacing_pressure(state: PacingState) -> float:
    """A 0..1 "under-delivery" urgency used to rank even-paced campaigns fairly.

    Higher = the campaign has more of today's daily cap still unspent, so it should
    win an open slot ahead of a campaign that has already delivered its share
    (anti-starvation). ``asap`` / uncapped campaigns get a neutral mid pressure.
    """

    if state.daily_cap is None or state.daily_cap <= 0:
        return 0.5
    remaining = max(0, state.daily_cap - state.impressions_today)
    return remaining / state.daily_cap
