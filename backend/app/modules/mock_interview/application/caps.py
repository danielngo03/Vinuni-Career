"""Mock-interview cost & safety caps.

Central, unit-testable limits. These are the FLOOR of the layered cost-control
model (docs plan §7): even if a client misbehaves, the sum of these caps plus the
provider-enforced ephemeral-token TTL (Tier V2) bounds spend per user.

Governance MAY override the per-day / per-week session caps per university; the
resolver reads config and falls back to these defaults.
"""

from __future__ import annotations

# --- realtime / session shape --------------------------------------------- #
MAX_SESSION_SECONDS = 600  # 10 min hard cap on a single session
DEFAULT_TARGET_QUESTIONS = 6  # how many questions a normal session aims for
MAX_QUESTIONS = 12  # interviewer stops after this many questions
IDLE_TIMEOUT_SECONDS = 45  # auto-end after this much candidate silence
EPHEMERAL_TOKEN_TTL_SECONDS = 660  # Tier V2 token / socket ceiling (> session cap)

# --- concurrency & rate ---------------------------------------------------- #
MAX_CONCURRENT_PER_USER = 1  # one live session at a time
DAILY_SESSION_CAP = 3  # completed+active sessions started per rolling 24h
WEEKLY_SESSION_CAP = 10  # per rolling 7 days

# --- per-turn text bounds (defense-in-depth around the gateway) ------------ #
MAX_ANSWER_CHARS = 4000  # a single candidate answer
MAX_TURNS_PERSISTED = 60  # transcript hard ceiling (2 * MAX_QUESTIONS + slack)

# --- LLM token budgets (keep cheap) ---------------------------------------- #
QUESTION_MAX_TOKENS = 320  # one interviewer turn (a question + short follow-up)
REPORT_MAX_TOKENS = 1400  # the whole coaching report


def clamp_questions(n: int) -> int:
    """Clamp a requested question count into ``[3, MAX_QUESTIONS]``."""

    return max(3, min(MAX_QUESTIONS, int(n)))


def clamp_duration(seconds: int) -> int:
    """Clamp a reported session duration into ``[0, MAX_SESSION_SECONDS]``."""

    return max(0, min(MAX_SESSION_SECONDS, int(seconds)))
