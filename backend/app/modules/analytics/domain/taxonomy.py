"""The B-548 event-type vocabulary + the properties allowlist gate.

Pure (no I/O). ``record_event`` (application/ingestion_service.py) is the ONLY
writer of ``analytics_events`` and MUST route every inbound ``properties`` dict
through :func:`sanitize_properties` first — default-deny, same discipline as
``discovery.domain.allowlist``. Values are metadata only: ids, counts, short
enum-like strings, booleans, and numbers. Free text, emails, raw CV/prompt
content, and AI provider/model/token internals are never accepted.
"""

from __future__ import annotations

from typing import Any

# One aggregate_type per category named in B-548 ("impressions, clicks, saves,
# apply starts, submissions, CV exports, AI suggestions, workflow executions,
# notifications, ad attribution"). Impressions/clicks/saves for discovery/ad
# surfaces already live in ``discovery_events`` — this taxonomy covers the
# authenticated-domain categories that ledger does not.
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "job.viewed",
        "job.bookmarked",
        "job.applied",
        "application.submitted",
        "application.status_changed",
        "application.withdrawn",
        "cv.export.completed",
        "cv.export.failed",
        "ai.suggestion.generated",
        "ai.tool.called",
        "event.viewed",
        "event.registered",
        "event.checked_in",
        "notification.sent",
        "workflow.executed",
        "ad.impression",
        "ad.click",
        "ad.apply_start",
        "mock_interview.started",
        "mock_interview.completed",
        "mock_interview.flagged",
    }
)

AGGREGATE_TYPES: frozenset[str] = frozenset(
    {
        "job",
        "application",
        "cv_export",
        "event",
        "event_registration",
        "notification",
        "ai_tool",
        "workflow_execution",
        "ad_placement",
        "mock_interview_session",
    }
)

ACTOR_TYPES: frozenset[str] = frozenset({"student", "partner", "university", "system", "guest"})

# Forbidden property keys — belt-and-braces explicit reject list; the allowlist
# below already default-denies anything not named here.
_FORBIDDEN_PROPERTY_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "full_name",
        "email",
        "phone",
        "phone_number",
        "cv_text",
        "raw_cv",
        "resume_text",
        "document_text",
        "prompt",
        "completion",
        "provider",
        "model",
        "token",
        "tokens",
        "confidence",
        "ip",
        "ip_address",
        "raw_ip",
        "gps",
        "latitude",
        "longitude",
    }
)

_MAX_STRING_LEN = 64
_MAX_PROPERTIES = 20


def _looks_safe_scalar(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return len(value) <= _MAX_STRING_LEN and "@" not in value
    return False


def sanitize_properties(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only short, non-PII-shaped scalar/short-list properties.

    Default-deny: an explicitly forbidden key, an unknown-shaped value (nested
    dict, long free text, an ``@``-containing string), or a properties dict
    past the size cap is dropped/truncated rather than raising — a caller that
    accidentally passes something unsafe gets a stripped-down event, never a
    crash and never a leaked field.
    """

    if not isinstance(raw, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in raw.items():
        if len(clean) >= _MAX_PROPERTIES:
            break
        k = str(key).strip().lower()
        if not k or k in _FORBIDDEN_PROPERTY_KEYS:
            continue
        if isinstance(value, (list, tuple)):
            items = [v for v in value if _looks_safe_scalar(v)][:10]
            if items:
                clean[k] = items
            continue
        if _looks_safe_scalar(value):
            clean[k] = value
    return clean
