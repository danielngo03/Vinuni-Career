"""Deterministic, rule-based fraud-risk assessment over structured signals.

AI_PRODUCT_SPEC.md §3 lists ``fraud_detection`` (permission_class:
``human_review``) over profile/docs/activity signals. This v1 is a pure
function over a structured signal dict — zero LLM, zero DB, zero network —
so it is trivially testable, reusable from any module that already has the
signals, and free to run on every evaluation.

ADVISORY ONLY (§1, §9.3): the returned ``risk_score`` (0.0-1.0, internal —
NEVER shown to end users) drives escalation to ``human_review_queue`` when
``risk_score >= ESCALATION_THRESHOLD`` (0.85, per §9.3). A human University
moderator makes every final decision; nothing is auto-blocked.

Signals are additive weighted rules with a hard cap at 1.0. Unknown/missing
signals contribute nothing (partial input degrades gracefully — a caller that
only knows 2 signals still gets a meaningful, conservative score).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# §9.3: "The fraud detection tool returns risk_score >= 0.85" escalates.
ESCALATION_THRESHOLD = 0.85

RISK_HIGH = "high"
RISK_MEDIUM = "medium"
RISK_LOW = "low"


@dataclass(slots=True)
class FraudSignal:
    code: str
    weight: float
    reason: str


@dataclass(slots=True)
class FraudAssessment:
    risk_score: float = 0.0
    signals: list[FraudSignal] = field(default_factory=list)

    @property
    def requires_human_review(self) -> bool:
        return self.risk_score >= ESCALATION_THRESHOLD

    @property
    def risk_level(self) -> str:
        if self.risk_score >= ESCALATION_THRESHOLD:
            return RISK_HIGH
        if self.risk_score >= 0.5:
            return RISK_MEDIUM
        return RISK_LOW

    def as_dict(self) -> dict:
        """Internal representation for the review queue and audit metadata.

        ``risk_score`` is internal-only. User-facing surfaces (if any) must
        present ``risk_level`` wording, never the raw score.
        """
        return {
            "risk_score": round(self.risk_score, 4),
            "risk_level": self.risk_level,
            "requires_human_review": self.requires_human_review,
            "signals": [
                {"code": s.code, "reason": s.reason} for s in self.signals
            ],
        }


def _as_bool(value: object) -> bool:
    return value is True


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


# (signal_key, evaluator) — each evaluator returns a FraudSignal or None.
def _rule_org_created_recently(signals: dict) -> FraudSignal | None:
    days = _as_number(signals.get("org_age_days"))
    if days is not None and days < 7:
        return FraudSignal(
            code="new_org_burst_risk",
            weight=0.25,
            reason="Organization account is less than 7 days old.",
        )
    return None


def _rule_unverified_email_domain(signals: dict) -> FraudSignal | None:
    if signals.get("has_verified_email_domain") is False:
        return FraudSignal(
            code="unverified_email_domain",
            weight=0.20,
            reason="Recruiter email domain does not match a verified "
            "company domain.",
        )
    return None


def _rule_posting_burst(signals: dict) -> FraudSignal | None:
    n = _as_number(signals.get("jobs_posted_last_7d"))
    if n is not None and n >= 10:
        return FraudSignal(
            code="posting_burst",
            weight=0.20,
            reason="Unusually high posting volume in the last 7 days.",
        )
    return None


def _rule_off_platform_contact(signals: dict) -> FraudSignal | None:
    if _as_bool(signals.get("external_contact_in_content")):
        return FraudSignal(
            code="off_platform_contact",
            weight=0.20,
            reason="Content pushes candidates to unmonitored external "
            "channels before applying.",
        )
    return None


def _rule_fee_collection(signals: dict) -> FraudSignal | None:
    if _as_bool(signals.get("fee_collection_flagged")):
        return FraudSignal(
            code="fee_collection_flagged",
            weight=0.45,
            reason="Content moderation flagged candidate fee collection.",
        )
    return None


def _rule_duplicate_content(signals: dict) -> FraudSignal | None:
    ratio = _as_number(signals.get("duplicate_content_ratio"))
    if ratio is not None and ratio >= 0.9:
        return FraudSignal(
            code="duplicated_content",
            weight=0.15,
            reason="Content is a near-duplicate of other postings "
            "(copy-paste farm pattern).",
        )
    return None


def _rule_salary_outlier(signals: dict) -> FraudSignal | None:
    ratio = _as_number(signals.get("salary_to_market_ratio"))
    if ratio is not None and ratio >= 3.0:
        return FraudSignal(
            code="salary_outlier",
            weight=0.20,
            reason="Advertised salary is an extreme outlier versus market "
            "range for the role.",
        )
    return None


def _rule_report_volume(signals: dict) -> FraudSignal | None:
    n = _as_number(signals.get("user_reports_last_30d"))
    if n is not None and n >= 3:
        return FraudSignal(
            code="user_report_volume",
            weight=0.30,
            reason="Multiple users reported this account/content recently.",
        )
    return None


_RULES = (
    _rule_org_created_recently,
    _rule_unverified_email_domain,
    _rule_posting_burst,
    _rule_off_platform_contact,
    _rule_fee_collection,
    _rule_duplicate_content,
    _rule_salary_outlier,
    _rule_report_volume,
)


def assess_fraud_signals(signals: dict | None) -> FraudAssessment:
    """Score structured fraud signals into a capped additive risk score.

    Deterministic, pure, and tolerant of missing/garbage input: unknown keys
    are ignored, wrong-typed values contribute nothing, and ``None``/empty
    input yields a zero-risk assessment (never raises).
    """
    if not isinstance(signals, dict):
        return FraudAssessment()

    matched: list[FraudSignal] = []
    for rule in _RULES:
        found = rule(signals)
        if found is not None:
            matched.append(found)

    score = min(1.0, sum(s.weight for s in matched))
    return FraudAssessment(risk_score=score, signals=matched)
