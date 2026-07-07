"""``AiUsageContext`` — the standard attribution + accounting carrier for a
single governed AI call (``docs/AI_PRODUCT_SPEC.md`` §5.4, §11; the AI usage
accounting rule in ``CLAUDE.md``).

It is threaded from the request/service layer into the AI gateway so that every
real provider call can be:

- **attributed** to a user / chat session / organization,
- **charged** against the correct budget scope (``billing_scope``), and
- **de-duplicated on retry** via an ``idempotency_key`` so a re-run of the same
  logical operation never double-charges the ledger.

It carries an optional DB session handle so the durable ``ai_usage_log`` ledger
and ops telemetry can be written on the caller's own transaction. When ``db`` is
``None`` (anonymous / background / sync context) the governed path degrades to a
metadata-only log line — the same behaviour the call-sites had before, so wiring
a context in is always safe and never a breaking change.

SECRECY: a context never carries prompt/response content, provider/model
identity, API keys, or raw token/cost internals.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# --------------------------------------------------------------------------- #
# billing_scope — WHICH budget an AI call is charged against and HOW an        #
# exhausted quota is surfaced. Per CLAUDE.md: student/partner exhaustion may   #
# route to a plan/credit upgrade; university-staff exhaustion routes to an     #
# admin limit/request workflow (never a billing upsell); platform/system are   #
# internal/background scopes charged to the platform budget.                    #
# --------------------------------------------------------------------------- #
BILLING_SCOPE_STUDENT: Final[str] = "student"
BILLING_SCOPE_PARTNER_ORG: Final[str] = "partner_org"
BILLING_SCOPE_UNIVERSITY_BUDGET: Final[str] = "university_budget"
BILLING_SCOPE_PLATFORM: Final[str] = "platform"
BILLING_SCOPE_SYSTEM: Final[str] = "system"

VALID_BILLING_SCOPES: Final[frozenset[str]] = frozenset(
    {
        BILLING_SCOPE_STUDENT,
        BILLING_SCOPE_PARTNER_ORG,
        BILLING_SCOPE_UNIVERSITY_BUDGET,
        BILLING_SCOPE_PLATFORM,
        BILLING_SCOPE_SYSTEM,
    }
)


def billing_scope_for_persona(persona: str | None) -> str:
    """Map an auth persona to the default billing scope for its AI usage.

    Unknown/absent personas default to ``system`` (charged to the platform
    budget, never surfaced as a user upsell).
    """

    mapping = {
        "student": BILLING_SCOPE_STUDENT,
        "alumni": BILLING_SCOPE_STUDENT,
        "partner": BILLING_SCOPE_PARTNER_ORG,
        "recruiter": BILLING_SCOPE_PARTNER_ORG,
        "employer": BILLING_SCOPE_PARTNER_ORG,
        "university": BILLING_SCOPE_UNIVERSITY_BUDGET,
        "staff": BILLING_SCOPE_UNIVERSITY_BUDGET,
        "superadmin": BILLING_SCOPE_PLATFORM,
    }
    return mapping.get((persona or "").strip().lower(), BILLING_SCOPE_SYSTEM)


@dataclass(frozen=True, slots=True)
class AiUsageContext:
    """Attribution + accounting for one governed AI call.

    All fields are optional so a context can be built incrementally. The gateway
    treats ``db is None`` as "no durable accounting available" and falls back to
    a metadata-only log line.
    """

    db: AsyncSession | None = None
    user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    org_id: uuid.UUID | None = None
    tool_class: str = "read_only"
    billing_scope: str = BILLING_SCOPE_STUDENT
    idempotency_key: str | None = None

    def __post_init__(self) -> None:  # pragma: no cover - trivial guard
        if self.billing_scope not in VALID_BILLING_SCOPES:
            raise ValueError(f"invalid billing_scope: {self.billing_scope!r}")

    def with_idempotency_key(self, key: str | None) -> AiUsageContext:
        """Return a copy scoped to a specific idempotency key.

        Callers derive a stable key from the logical operation (e.g.
        ``f"cv_rewrite:{cv_version_id}:{section_id}"``) so a retry of the same
        operation reuses the existing ledger row instead of double-charging.
        """

        return replace(self, idempotency_key=key)


def system_context(db: AsyncSession | None = None) -> AiUsageContext:
    """Context for internal/background AI work with no end-user attribution."""

    return AiUsageContext(db=db, billing_scope=BILLING_SCOPE_SYSTEM)
