"""The privacy allowlist — the NON-NEGOTIABLE core of guest discovery.

Guest discovery sessions store ONLY privacy-safe coarse signals
(``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §3, ``.claude/rules/backend.md``,
``docs/SECURITY_PRIVACY.md``). This module is pure (no I/O) and is the single point
that decides what may be persisted. The service layer routes every inbound coarse
tag and every event through here BEFORE it touches the database:

- ``sanitize_coarse_tags`` keeps ONLY allowlisted keys and clamps their values;
  every other key (forbidden PII/sensitive/3p-ad-id, or simply unknown) is dropped
  and never stored. There is no path by which a non-allowlisted key reaches the DB.
- ``merge_coarse_tags`` unions sanitized signals into the stored session tags, de-
  duped and capped (most-recent-wins), so a session never grows unbounded.
- The event vocabularies (``EVENT_TYPES`` / ``TARGET_TYPES`` / ``SOURCE_SURFACES``)
  keep organic, recommended, sponsored, and university-curated inventory tracked
  *separately* (``SOURCE_SURFACES`` encodes the inventory class of every event).
- ``placement_id`` is retained ONLY for sponsored surfaces (``SPONSORED_SURFACES``
  or a ``banner`` target); on any organic/recommended/curated surface it is dropped.

``FORBIDDEN_COARSE_TAG_KEYS`` is documentation + a belt-and-braces explicit reject
set used by tests; the allowlist alone is already sufficient (default-deny).
"""

from __future__ import annotations

import uuid
from typing import Any

# --------------------------------------------------------------------------- #
# Coarse-tag allowlist (the ONLY keys that may live in coarse_tags)            #
# --------------------------------------------------------------------------- #

# List-valued coarse signals: viewed taxonomy + short search terms + viewed ids.
_LIST_KEYS: frozenset[str] = frozenset(
    {
        "categories",  # viewed job categories
        "industries",  # viewed industries
        "role_families",  # viewed role families
        "company_ids",  # viewed company ids (opaque uuids)
        "event_ids",  # viewed event ids (opaque uuids)
        "search_terms",  # short search-query terms
    }
)

# Scalar coarse signals: coarse filter selections + layout device class.
_SCALAR_KEYS: frozenset[str] = frozenset(
    {
        "work_mode",  # onsite | remote | hybrid  (a FILTER selection)
        "city",  # a coarse city FILTER selection (NOT GPS / exact location)
        "device_type",  # desktop | mobile | tablet (layout + allowed ad targeting)
    }
)

# Opaque-id list keys whose members must look like UUIDs (anything else dropped).
_UUID_LIST_KEYS: frozenset[str] = frozenset({"company_ids", "event_ids"})

ALLOWED_COARSE_TAG_KEYS: frozenset[str] = _LIST_KEYS | _SCALAR_KEYS

# Explicit forbidden keys — for tests/audit/readability. The default-deny allowlist
# already strips these (and any unknown key); they are NEVER persisted.
FORBIDDEN_COARSE_TAG_KEYS: frozenset[str] = frozenset(
    {
        # direct identifiers
        "name",
        "full_name",
        "first_name",
        "last_name",
        "email",
        "phone",
        "phone_number",
        "username",
        "user_id",
        # location / network
        "ip",
        "ip_address",
        "raw_ip",
        "gps",
        "geo",
        "geolocation",
        "latitude",
        "longitude",
        "lat",
        "lng",
        "lon",
        "coordinates",
        "exact_location",
        "address",
        "postal_code",
        "zip",
        # raw CV / document content
        "cv",
        "cv_text",
        "raw_cv",
        "resume",
        "resume_text",
        "document_text",
        # sensitive categories (docs/SECURITY_PRIVACY.md §Advertising Compliance)
        "health",
        "ethnicity",
        "race",
        "national_origin",
        "gender",
        "sex",
        "sexual_orientation",
        "religion",
        "politics",
        "political",
        "disability",
        "pregnancy",
        "financial_status",
        "income",
        "salary",
        # cross-site / third-party ad identifiers
        "gaid",
        "idfa",
        "fbclid",
        "gclid",
        "ad_id",
        "advertising_id",
        "third_party_id",
        "device_id",
        "fingerprint",
        "tracking_id",
    }
)

# Vocabularies for the scalar filter signals (values outside these are dropped).
_WORK_MODES: frozenset[str] = frozenset({"onsite", "remote", "hybrid"})
_DEVICE_TYPES: frozenset[str] = frozenset({"desktop", "mobile", "tablet"})

# Value clamps — keep signals coarse and the row bounded.
_MAX_LIST_ITEMS = 20
_MAX_TERM_LEN = 64
_MAX_SEARCH_TERM_LEN = 80
_MAX_CITY_LEN = 80
_MAX_SEARCH_TERMS = 10


def _clean_token(value: Any, *, max_len: int) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token:
        return None
    return token[:max_len].lower()


def _clean_uuid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError):
        return None


def _clean_list(key: str, value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    is_uuid = key in _UUID_LIST_KEYS
    max_len = _MAX_SEARCH_TERM_LEN if key == "search_terms" else _MAX_TERM_LEN
    cap = _MAX_SEARCH_TERMS if key == "search_terms" else _MAX_LIST_ITEMS
    for item in value:
        cleaned = _clean_uuid(item) if is_uuid else _clean_token(item, max_len=max_len)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
        if len(out) >= cap:
            break
    return out


def _clean_scalar(key: str, value: Any) -> str | None:
    if key == "work_mode":
        token = _clean_token(value, max_len=16)
        return token if token in _WORK_MODES else None
    if key == "device_type":
        token = _clean_token(value, max_len=16)
        return token if token in _DEVICE_TYPES else None
    if key == "city":
        return _clean_token(value, max_len=_MAX_CITY_LEN)
    return None


def sanitize_coarse_tags(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return a coarse-tag dict containing ONLY allowlisted, clamped signals.

    Every non-allowlisted key (forbidden PII/sensitive/3p-ad-id or unknown) is
    dropped. Empty results after cleaning are omitted. This is the gate: nothing
    that is not allowlisted can be persisted.
    """

    if not isinstance(raw, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in raw.items():
        k = str(key).strip().lower()
        if k not in ALLOWED_COARSE_TAG_KEYS:
            continue  # default-deny: forbidden + unknown keys are stripped
        if k in _LIST_KEYS:
            items = _clean_list(k, value)
            if items:
                clean[k] = items
        else:
            scalar = _clean_scalar(k, value)
            if scalar:
                clean[k] = scalar
    return clean


def merge_coarse_tags(
    existing: dict[str, Any] | None, incoming: dict[str, Any] | None
) -> dict[str, Any]:
    """Union sanitized ``incoming`` into ``existing`` (most-recent-wins, capped).

    Both inputs are passed through :func:`sanitize_coarse_tags` so the result is
    guaranteed allowlisted regardless of what is stored. Lists de-dupe and keep the
    most recent items; scalars overwrite.
    """

    base = sanitize_coarse_tags(existing)
    add = sanitize_coarse_tags(incoming)
    merged: dict[str, Any] = dict(base)
    for key, value in add.items():
        if key in _LIST_KEYS:
            cap = _MAX_SEARCH_TERMS if key == "search_terms" else _MAX_LIST_ITEMS
            combined = list(dict.fromkeys([*base.get(key, []), *value]))
            merged[key] = combined[-cap:]
        else:
            merged[key] = value
    return merged


# --------------------------------------------------------------------------- #
# Event vocabularies (organic / recommended / sponsored / curated kept apart)  #
# --------------------------------------------------------------------------- #

EVENT_TYPES: frozenset[str] = frozenset(
    {
        "impression",
        "click",
        "view",
        "apply_start",
        "save_intent",
        "event_register_intent",
    }
)

TARGET_TYPES: frozenset[str] = frozenset({"job", "event", "company", "banner"})

# Every surface is classified by its inventory class so analytics never conflate
# organic, recommended, sponsored, and university-curated inventory.
SOURCE_SURFACES: frozenset[str] = frozenset(
    {
        # organic
        "homepage_recent",
        "homepage_popular",
        "search",
        "job_detail",
        "job_detail_similar",
        "event_detail",
        "company_profile",
        "mega_companies",
        "mega_events",
        # recommended (deterministic/session/profile/CV signals)
        "homepage_recommended",
        "search_recommended",
        "job_detail_recommended_cv",
        "mega_jobs_recommended",
        # sponsored (paid inventory; disclosure required)
        "homepage_sponsored",
        "search_sponsored",
        "right_rail_banner",
        "email_sponsored",
        "mega_sponsored",
        # university-curated
        "employer_spotlight",
        "career_explore",
        "university_curated",
    }
)

# Surfaces on which a ``placement_id`` (sponsored inventory) is meaningful. On any
# other surface a supplied ``placement_id`` is dropped (organic ≠ sponsored).
SPONSORED_SURFACES: frozenset[str] = frozenset(
    {
        "homepage_sponsored",
        "search_sponsored",
        "right_rail_banner",
        "email_sponsored",
        "mega_sponsored",
    }
)


def is_sponsored_surface(source_surface: str, target_type: str) -> bool:
    """Whether this surface/target legitimately carries a sponsored placement."""

    return source_surface in SPONSORED_SURFACES or target_type == "banner"
