"""Notification category catalogue and mandatory-category rules.

``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §3/§5: some categories are
mandatory (security/compliance/lifecycle/billing) and cannot be disabled — they
are surfaced to clients as ``locked`` with an ``email`` setting of ``mandatory``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Email setting values accepted on PATCH for non-locked categories.
EMAIL_SETTINGS: frozenset[str] = frozenset({"off", "immediate", "daily", "weekly"})

# Categories that may never be disabled (security alerts, legal, lifecycle, billing).
MANDATORY_CATEGORIES: frozenset[str] = frozenset(
    {
        "security_alert",
        "legal_compliance",
        "application_lifecycle",
        "billing_receipt",
    }
)


@dataclass(frozen=True, slots=True)
class CategoryDefault:
    category: str
    in_app: bool = True
    email: str = "immediate"
    push: bool = False


# Default catalogue presented when a user has no stored preference for a category.
DEFAULT_CATEGORIES: tuple[CategoryDefault, ...] = (
    CategoryDefault("security_alert", email="mandatory"),
    CategoryDefault("legal_compliance", email="mandatory"),
    CategoryDefault("application_lifecycle", email="mandatory"),
    CategoryDefault("billing_receipt", email="mandatory"),
    CategoryDefault("application_status", email="immediate"),
    CategoryDefault("interview", email="immediate"),
    CategoryDefault("offer", email="immediate"),
    CategoryDefault("job_digest", email="weekly"),
    # Saved-job application-deadline nudges (spec §3). Opt-outable per channel.
    CategoryDefault("job_deadline", in_app=True, email="immediate", push=False),
    CategoryDefault("event", email="immediate"),
    CategoryDefault("cv", email="immediate"),
    # Messaging (ADR-0012 §4): optional, default-on, NOT mandatory.
    CategoryDefault("message", email="immediate"),
    # Job alert matches (linked to student job alert subscriptions).
    CategoryDefault("job_alert", in_app=True, email="immediate", push=False),
)


def is_mandatory(category: str) -> bool:
    return category in MANDATORY_CATEGORIES
