"""AI energy vocabulary: cost-weighted credit costs, windows, and allowances.

Every value here is INTERNAL. The credit weights approximate real provider cost
(a vision extraction costs far more than a one-line text edit) so the energy
meter debits proportionally, but the numbers are never surfaced to end users —
only the derived ``energy %`` is.
"""

from __future__ import annotations

from app.ai.observability.billable_usage import (
    FEATURE_CHATBOT,
    FEATURE_COVER_LETTER,
    FEATURE_CV_EDIT_COMMAND,
    FEATURE_CV_EXTRACTION,
    FEATURE_CV_FIT_EXPLANATION,
    FEATURE_CV_SUGGESTION,
    FEATURE_EMBEDDINGS,
    FEATURE_INTERVIEW_SIM,
    FEATURE_JD_EXTRACTION,
    FEATURE_JD_WRITER,
    FEATURE_LEARNING_PLAN,
    FEATURE_RERANK,
    FEATURE_SCORECARD_SUGGESTION,
    FEATURE_SCREENING_BRIEF,
)

# Feature keys that are partner-only vision/text calls not in the base ledger set.
FEATURE_JD_VISION_EXTRACTION = "jd_vision_extraction"
FEATURE_JD_TRANSLATION = "jd_translation"
FEATURE_MARKET_INTELLIGENCE = "market_intelligence"
FEATURE_CANDIDATE_ANALYSIS = "candidate_analysis"
FEATURE_ANALYTICS_ASSISTANT = "analytics_assistant"
# Chat-attachment analysis: the recruiter attaches a file/image to the assistant
# and asks it to read/summarise/extract it. Cost-weighted like the vision tier
# because the priciest path (image / scanned PDF) is a multimodal call.
FEATURE_ATTACHMENT_ANALYSIS = "attachment_analysis"

# --------------------------------------------------------------------------- #
# Cost-weighted credit cost per feature (INTERNAL — never exposed).            #
# Scale: 1 credit ≈ a trivial text call; heavier/vision calls cost more.       #
# --------------------------------------------------------------------------- #
DEFAULT_UNIT_COST = 2

FEATURE_UNIT_COST: dict[str, int] = {
    # Student features
    FEATURE_CHATBOT: 2,
    FEATURE_CV_EXTRACTION: 8,  # vision-tier extraction is the priciest path
    FEATURE_CV_SUGGESTION: 2,
    FEATURE_CV_EDIT_COMMAND: 2,
    FEATURE_CV_FIT_EXPLANATION: 2,
    FEATURE_COVER_LETTER: 3,
    FEATURE_INTERVIEW_SIM: 4,
    FEATURE_LEARNING_PLAN: 3,
    FEATURE_EMBEDDINGS: 1,
    FEATURE_RERANK: 1,
    # Partner features
    FEATURE_JD_EXTRACTION: 4,
    FEATURE_JD_VISION_EXTRACTION: 8,
    FEATURE_JD_WRITER: 4,
    FEATURE_JD_TRANSLATION: 2,
    FEATURE_SCREENING_BRIEF: 3,
    FEATURE_SCORECARD_SUGGESTION: 2,
    FEATURE_MARKET_INTELLIGENCE: 3,
    FEATURE_CANDIDATE_ANALYSIS: 3,
    FEATURE_ANALYTICS_ASSISTANT: 3,
    FEATURE_ATTACHMENT_ANALYSIS: 8,  # vision-tier weight (image/scanned path)
}


def unit_cost(feature_key: str) -> int:
    """Cost-weighted credits a successful call to *feature_key* debits."""

    return FEATURE_UNIT_COST.get(feature_key, DEFAULT_UNIT_COST)


# --------------------------------------------------------------------------- #
# Windows                                                                       #
# --------------------------------------------------------------------------- #
# Weekly = calendar week (Monday 00:00 UTC reset) so the reset copy stays
# truthful ("resets Monday"). 3h = rolling burst window (soft warn only).
SESSION_WINDOW_HOURS = 3
WARNING_THRESHOLD_PCT = 80  # weekly ≥80% used → warn banner

# --------------------------------------------------------------------------- #
# Plan-limit keys + default weekly allowances (in credits).                    #
# A plan's ``limits`` JSON may override via ``ai_weekly_energy_units``. Absent  #
# → the persona/segment default below. Wallet + admin sub-allocation layer on   #
# top (see service.py).                                                         #
# --------------------------------------------------------------------------- #
PLAN_LIMIT_KEY_WEEKLY_UNITS = "ai_weekly_energy_units"

# Student segment defaults (per user / week).
DEFAULT_WEEKLY_UNITS_STUDENT_VINUNI = 300
DEFAULT_WEEKLY_UNITS_STUDENT_EXTERNAL = 120
# Partner ORG pool default (whole org / week) on the free/default plan.
DEFAULT_WEEKLY_UNITS_PARTNER_ORG = 400
# University staff — effectively generous; real gate is admin policy, not billing.
DEFAULT_WEEKLY_UNITS_UNIVERSITY = 2000
# Any other authenticated principal.
DEFAULT_WEEKLY_UNITS_FALLBACK = 120

# A 3h burst soft-cap as a fraction of the weekly allowance (advisory only).
SESSION_SOFT_FRACTION = 0.4

# --------------------------------------------------------------------------- #
# User-safe block/warn reason codes (frontend localizes these).                #
# --------------------------------------------------------------------------- #
REASON_WEEKLY_EXCEEDED = "AI_WEEKLY_ENERGY_EXCEEDED"
REASON_ORG_WEEKLY_EXCEEDED = "AI_ORG_WEEKLY_ENERGY_EXCEEDED"
REASON_MEMBER_ALLOCATION_EXCEEDED = "AI_MEMBER_ALLOCATION_EXCEEDED"
