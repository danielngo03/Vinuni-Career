"""Unit tests for the shared per-queue SLA policy + traffic-light helpers.

Covers the BUSINESS_LOGIC.md §11 SLA windows and the amber/red thresholds the
University Operations read model and its frontend share.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.shared.moderation import (
    HEALTH_BREACHED,
    HEALTH_DUE_SOON,
    HEALTH_ON_TRACK,
    QUEUE_ADS,
    QUEUE_AI_REVIEW,
    QUEUE_EVENTS,
    QUEUE_JOBS,
    QUEUE_KEYS,
    QUEUE_PARTNER_REGISTRATIONS,
    queue_health,
    queue_sla_hours,
    sla_health,
    summarize_queue,
)

_NOW = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)


class TestQueueSlaHours:
    def test_documented_windows(self) -> None:
        assert queue_sla_hours(QUEUE_JOBS) == 24
        assert queue_sla_hours(QUEUE_EVENTS) == 24
        assert queue_sla_hours(QUEUE_ADS) == 24
        assert queue_sla_hours(QUEUE_PARTNER_REGISTRATIONS) == 48
        assert queue_sla_hours(QUEUE_AI_REVIEW) == 4

    def test_unknown_queue_defaults_to_24(self) -> None:
        assert queue_sla_hours("nonexistent") == 24

    def test_every_canonical_key_has_a_window(self) -> None:
        for key in QUEUE_KEYS:
            assert queue_sla_hours(key) > 0


class TestSlaHealth:
    def test_no_deadline_is_on_track(self) -> None:
        assert sla_health(None, _NOW, sla_hours=24) == HEALTH_ON_TRACK

    def test_past_deadline_is_breached(self) -> None:
        due = _NOW - timedelta(minutes=1)
        assert sla_health(due, _NOW, sla_hours=24) == HEALTH_BREACHED

    def test_exactly_at_deadline_is_breached(self) -> None:
        assert sla_health(_NOW, _NOW, sla_hours=24) == HEALTH_BREACHED

    def test_far_from_deadline_is_on_track(self) -> None:
        due = _NOW + timedelta(hours=20)  # 24h SLA -> amber window is 6h
        assert sla_health(due, _NOW, sla_hours=24) == HEALTH_ON_TRACK

    def test_within_amber_window_is_due_soon(self) -> None:
        due = _NOW + timedelta(hours=5)  # inside 6h amber window of a 24h SLA
        assert sla_health(due, _NOW, sla_hours=24) == HEALTH_DUE_SOON

    def test_short_sla_uses_two_hour_floor(self) -> None:
        # 4h SLA -> 25% == 1h, but the floor keeps the amber window at 2h.
        due = _NOW + timedelta(hours=1.5)
        assert sla_health(due, _NOW, sla_hours=4) == HEALTH_DUE_SOON

    def test_naive_datetime_is_coerced(self) -> None:
        naive_due = datetime(2026, 7, 8, 11, 0)  # noqa: DTZ001 - deliberately naive
        assert sla_health(naive_due, _NOW, sla_hours=24) == HEALTH_BREACHED


class TestQueueHealth:
    def test_empty_queue_is_on_track(self) -> None:
        assert queue_health(pending=0, overdue=0, due_soon=0) == HEALTH_ON_TRACK

    def test_any_overdue_makes_queue_breached(self) -> None:
        assert queue_health(pending=5, overdue=1, due_soon=3) == HEALTH_BREACHED

    def test_due_soon_without_overdue_is_amber(self) -> None:
        assert queue_health(pending=5, overdue=0, due_soon=2) == HEALTH_DUE_SOON

    def test_pending_only_is_on_track(self) -> None:
        assert queue_health(pending=5, overdue=0, due_soon=0) == HEALTH_ON_TRACK


class TestSummarizeQueue:
    def test_empty_queue(self) -> None:
        stats = summarize_queue([], now=_NOW, sla_hours=24)
        assert stats["pending"] == 0
        assert stats["overdue"] == 0
        assert stats["due_soon"] == 0
        assert stats["oldest_age_hours"] is None
        assert stats["next_due_at"] is None
        assert stats["health"] == HEALTH_ON_TRACK
        assert stats["sla_hours"] == 24

    def test_counts_overdue_due_soon_and_on_track(self) -> None:
        rows = [
            (_NOW - timedelta(hours=30), _NOW - timedelta(hours=6)),  # breached
            (_NOW - timedelta(hours=20), _NOW + timedelta(hours=4)),  # due_soon (<6h)
            (_NOW - timedelta(hours=2), _NOW + timedelta(hours=22)),  # on_track
        ]
        stats = summarize_queue(rows, now=_NOW, sla_hours=24)
        assert stats["pending"] == 3
        assert stats["overdue"] == 1
        assert stats["due_soon"] == 1
        assert stats["health"] == HEALTH_BREACHED  # any breach reddens the card

    def test_derives_due_by_from_submitted_when_absent(self) -> None:
        # No stored deadline: submitted 5h ago on a 4h SLA -> already breached.
        rows = [(_NOW - timedelta(hours=5), None)]
        stats = summarize_queue(rows, now=_NOW, sla_hours=4)
        assert stats["overdue"] == 1
        assert stats["health"] == HEALTH_BREACHED

    def test_oldest_age_and_next_due(self) -> None:
        rows = [
            (_NOW - timedelta(hours=10), _NOW + timedelta(hours=14)),
            (_NOW - timedelta(hours=3), _NOW + timedelta(hours=21)),
        ]
        stats = summarize_queue(rows, now=_NOW, sla_hours=24)
        assert stats["oldest_age_hours"] == 10.0
        # next_due is the earliest deadline across the two items
        assert stats["next_due_at"] == (_NOW + timedelta(hours=14)).isoformat()


class TestCsvSafe:
    """CSV formula-injection escaping for attendee exports."""

    def test_leading_formula_chars_are_neutralised(self) -> None:
        from app.modules.opportunities.api.events_router import _csv_safe

        for danger in ("=SUM(A1)", "+1", "-1", "@cmd", "\tx", "\rx"):
            assert _csv_safe(danger).startswith("'")

    def test_plain_values_pass_through(self) -> None:
        from app.modules.opportunities.api.events_router import _csv_safe

        assert _csv_safe("Nguyễn Văn A") == "Nguyễn Văn A"
        assert _csv_safe("a@b.com") == "a@b.com"  # @ only dangerous when leading
        assert _csv_safe(None) == ""
