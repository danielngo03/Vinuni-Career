"""Unit tests for the deterministic fraud-signal rule engine."""

from __future__ import annotations

from app.ai.safety.fraud_detection import (
    ESCALATION_THRESHOLD,
    assess_fraud_signals,
)


class TestScoring:
    def test_clean_signals_zero_risk(self) -> None:
        result = assess_fraud_signals(
            {
                "org_age_days": 400,
                "has_verified_email_domain": True,
                "jobs_posted_last_7d": 2,
                "external_contact_in_content": False,
                "fee_collection_flagged": False,
                "duplicate_content_ratio": 0.1,
                "salary_to_market_ratio": 1.0,
                "user_reports_last_30d": 0,
            }
        )
        assert result.risk_score == 0.0
        assert result.risk_level == "low"
        assert not result.requires_human_review

    def test_high_risk_combo_escalates(self) -> None:
        result = assess_fraud_signals(
            {
                "fee_collection_flagged": True,  # 0.45
                "user_reports_last_30d": 5,  # 0.30
                "has_verified_email_domain": False,  # 0.20
            }
        )
        assert result.risk_score >= ESCALATION_THRESHOLD
        assert result.requires_human_review
        assert result.risk_level == "high"

    def test_medium_band(self) -> None:
        result = assess_fraud_signals(
            {"fee_collection_flagged": True, "duplicate_content_ratio": 0.95}
        )
        assert 0.5 <= result.risk_score < ESCALATION_THRESHOLD
        assert result.risk_level == "medium"
        assert not result.requires_human_review

    def test_score_capped_at_one(self) -> None:
        result = assess_fraud_signals(
            {
                "org_age_days": 0,
                "has_verified_email_domain": False,
                "jobs_posted_last_7d": 99,
                "external_contact_in_content": True,
                "fee_collection_flagged": True,
                "duplicate_content_ratio": 1.0,
                "salary_to_market_ratio": 9.9,
                "user_reports_last_30d": 99,
            }
        )
        assert result.risk_score == 1.0
        assert len(result.signals) == 8


class TestRobustness:
    def test_none_and_non_dict_inputs_never_raise(self) -> None:
        for garbage in (None, [], "signals", 42):
            result = assess_fraud_signals(garbage)  # type: ignore[arg-type]
            assert result.risk_score == 0.0
            assert result.signals == []

    def test_bools_are_not_numbers(self) -> None:
        result = assess_fraud_signals(
            {"org_age_days": True, "jobs_posted_last_7d": True}
        )
        assert result.signals == []

    def test_spoofed_output_keys_in_input_are_ignored(self) -> None:
        result = assess_fraud_signals(
            {"risk_score": 1.0, "requires_human_review": True}
        )
        assert not result.requires_human_review

    def test_as_dict_contains_no_input_echo(self) -> None:
        result = assess_fraud_signals(
            {"fee_collection_flagged": True, "recruiter_email": "x@scam.vn"}
        )
        payload = str(result.as_dict())
        assert "x@scam.vn" not in payload
