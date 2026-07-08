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

Taxonomy signal keys (``categories`` / ``industries`` / ``role_families`` /
``search_terms``) are stored as a PII-free per-value **weighted map**
``{value: {"count": int, "last_seen": iso8601}}`` rather than a bare list, so a
value viewed 20× can out-weigh one viewed once and a stale value can time-decay in
the ranker (``ranking.session_signal_weight``). The map holds only the SAME coarse
tokens the list held plus two non-identifying integers/timestamps — no new PII
surface. Legacy presence-only rows (a bare ``list``) are read as ``count=1`` with
an unknown ``last_seen`` (no decay), so old sessions keep working. Opaque-id keys
(``company_ids`` / ``event_ids``) stay bare lists (weighting adds no value to an id
reference).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

# --------------------------------------------------------------------------- #
# Coarse-tag allowlist (the ONLY keys that may live in coarse_tags)            #
# --------------------------------------------------------------------------- #

# Weighted taxonomy signals stored as {value: {count, last_seen}} (freq + decay).
_WEIGHTED_LIST_KEYS: frozenset[str] = frozenset(
    {
        "categories",      # viewed job categories
        "industries",      # viewed industries
        "role_families",   # viewed role families
        "search_terms",    # short search-query terms
    }
)

# Opaque-id list keys whose members must look like UUIDs (anything else dropped).
_UUID_LIST_KEYS: frozenset[str] = frozenset({"company_ids", "event_ids"})

# List-valued coarse signals: weighted taxonomy signals + opaque viewed ids.
_LIST_KEYS: frozenset[str] = _WEIGHTED_LIST_KEYS | _UUID_LIST_KEYS

# Scalar coarse signals: coarse filter selections + layout device class.
_SCALAR_KEYS: frozenset[str] = frozenset(
    {
        "work_mode",   # onsite | remote | hybrid  (a FILTER selection)
        "city",        # a coarse city FILTER selection (NOT GPS / exact location)
        "device_type", # desktop | mobile | tablet (layout + allowed ad targeting)
    }
)

ALLOWED_COARSE_TAG_KEYS: frozenset[str] = _LIST_KEYS | _SCALAR_KEYS

# Explicit forbidden keys — for tests/audit/readability. The default-deny allowlist
# already strips these (and any unknown key); they are NEVER persisted.
FORBIDDEN_COARSE_TAG_KEYS: frozenset[str] = frozenset(
    {
        # direct identifiers
        "name", "full_name", "first_name", "last_name", "email", "phone",
        "phone_number", "username", "user_id",
        # location / network
        "ip", "ip_address", "raw_ip", "gps", "geo", "geolocation",
        "latitude", "longitude", "lat", "lng", "lon", "coordinates",
        "exact_location", "address", "postal_code", "zip",
        # raw CV / document content
        "cv", "cv_text", "raw_cv", "resume", "resume_text", "document_text",
        # sensitive categories (docs/SECURITY_PRIVACY.md §Advertising Compliance)
        "health", "ethnicity", "race", "national_origin", "gender", "sex",
        "sexual_orientation", "religion", "politics", "political", "disability",
        "pregnancy", "financial_status", "income", "salary",
        # cross-site / third-party ad identifiers
        "gaid", "idfa", "fbclid", "gclid", "ad_id", "advertising_id",
        "third_party_id", "device_id", "fingerprint", "tracking_id",
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
# Per-value view count is clamped so a single burst can never dominate unbounded.
_MAX_COUNT = 1000


def _now() -> datetime:
    return datetime.now(tz=UTC)


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


def _coerce_dt(value: Any, *, now: datetime) -> datetime:
    """Parse a stored ISO ``last_seen`` back to an aware datetime (default ``now``)."""

    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return now
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return now


def _clamp_count(value: Any) -> int:
    if isinstance(value, bool):  # bool is an int subclass — reject it explicitly
        return 1
    if isinstance(value, (int, float)) and value >= 1:
        return min(int(value), _MAX_COUNT)
    return 1


def _uuid_list(value: Any) -> list[str]:
    """Opaque-id list keys (company_ids/event_ids) stay bare, de-duped, capped."""

    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = _clean_uuid(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
        if len(out) >= _MAX_LIST_ITEMS:
            break
    return out


def _weighted_map(key: str, value: Any, *, now: datetime) -> dict[str, dict[str, Any]]:
    """Clean a weighted taxonomy key into ``{token: {count, last_seen}}``.

    Accepts the new dict shape ``{value: {count, last_seen}}`` AND the legacy /
    inbound bare-list shape ``[value, ...]`` (each defaulting to ``count=1`` at
    ``now``). Duplicate tokens within one input sum their counts (bounded) and keep
    the newest ``last_seen``; the map is capped to the most-recently-seen tokens.
    """

    max_len = _MAX_SEARCH_TERM_LEN if key == "search_terms" else _MAX_TERM_LEN
    cap = _MAX_SEARCH_TERMS if key == "search_terms" else _MAX_LIST_ITEMS

    pairs: list[tuple[str, int, datetime]] = []
    if isinstance(value, dict):
        for raw_k, raw_v in value.items():
            token = _clean_token(raw_k, max_len=max_len)
            if token is None:
                continue
            if isinstance(raw_v, dict):
                count = _clamp_count(raw_v.get("count"))
                last_seen = _coerce_dt(raw_v.get("last_seen"), now=now)
            elif isinstance(raw_v, (int, float)) and not isinstance(raw_v, bool):
                count = _clamp_count(raw_v)
                last_seen = now
            else:
                count, last_seen = 1, now
            pairs.append((token, count, last_seen))
    else:
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, (list, tuple)):
            return {}
        for item in items:
            token = _clean_token(item, max_len=max_len)
            if token is not None:
                pairs.append((token, 1, now))

    out: dict[str, dict[str, Any]] = {}
    for token, count, last_seen in pairs:
        if token in out:
            merged_count = min(out[token]["count"] + count, _MAX_COUNT)
            prev = _coerce_dt(out[token]["last_seen"], now=now)
            newest = max(prev, last_seen)
            out[token] = {"count": merged_count, "last_seen": newest.isoformat()}
        else:
            out[token] = {"count": count, "last_seen": last_seen.isoformat()}

    if len(out) > cap:
        ordered = sorted(
            out.items(),
            key=lambda kv: _coerce_dt(kv[1]["last_seen"], now=now),
            reverse=True,
        )
        out = dict(ordered[:cap])
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


def sanitize_coarse_tags(
    raw: dict[str, Any] | None, *, now: datetime | None = None
) -> dict[str, Any]:
    """Return a coarse-tag dict containing ONLY allowlisted, clamped signals.

    Every non-allowlisted key (forbidden PII/sensitive/3p-ad-id or unknown) is
    dropped. Empty results after cleaning are omitted. This is the gate: nothing
    that is not allowlisted can be persisted. Weighted taxonomy keys are normalized
    to ``{token: {count, last_seen}}`` (accepting both the dict and legacy list
    shapes); opaque-id keys stay bare lists; scalars are vocab-clamped.
    """

    if not isinstance(raw, dict):
        return {}
    now = now or _now()
    clean: dict[str, Any] = {}
    for key, value in raw.items():
        k = str(key).strip().lower()
        if k not in ALLOWED_COARSE_TAG_KEYS:
            continue  # default-deny: forbidden + unknown keys are stripped
        if k in _WEIGHTED_LIST_KEYS:
            weighted = _weighted_map(k, value, now=now)
            if weighted:
                clean[k] = weighted
        elif k in _LIST_KEYS:  # opaque-id list keys (company_ids/event_ids)
            ids = _uuid_list(value)
            if ids:
                clean[k] = ids
        else:
            scalar = _clean_scalar(k, value)
            if scalar:
                clean[k] = scalar
    return clean


def merge_coarse_tags(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Union sanitized ``incoming`` into ``existing`` (frequency + recency aware).

    Both inputs are passed through :func:`sanitize_coarse_tags` so the result is
    guaranteed allowlisted regardless of what is stored. Weighted taxonomy tokens
    ACCUMULATE (``count`` sums, bounded; ``last_seen`` advances) so a repeatedly
    viewed value out-weighs a one-off; opaque-id lists de-dupe most-recent-wins;
    scalars overwrite. The result stays capped so a session never grows unbounded.
    """

    now = now or _now()
    base = sanitize_coarse_tags(existing, now=now)
    add = sanitize_coarse_tags(incoming, now=now)
    merged: dict[str, Any] = dict(base)
    for key, value in add.items():
        if key in _WEIGHTED_LIST_KEYS:
            cap = _MAX_SEARCH_TERMS if key == "search_terms" else _MAX_LIST_ITEMS
            combined: dict[str, dict[str, Any]] = {
                tok: dict(entry) for tok, entry in base.get(key, {}).items()
            }
            for token, entry in value.items():
                if token in combined:
                    prev = combined[token]
                    newest = max(
                        _coerce_dt(prev["last_seen"], now=now),
                        _coerce_dt(entry["last_seen"], now=now),
                    )
                    combined[token] = {
                        "count": min(prev["count"] + entry["count"], _MAX_COUNT),
                        "last_seen": newest.isoformat(),
                    }
                else:
                    combined[token] = dict(entry)
            if len(combined) > cap:
                ordered = sorted(
                    combined.items(),
                    key=lambda kv: _coerce_dt(kv[1]["last_seen"], now=now),
                    reverse=True,
                )
                combined = dict(ordered[:cap])
            merged[key] = combined
        elif key in _LIST_KEYS:  # opaque-id list keys — de-dupe, most-recent-wins
            combined_ids = list(dict.fromkeys([*base.get(key, []), *value]))
            merged[key] = combined_ids[-_MAX_LIST_ITEMS:]
        else:
            merged[key] = value
    return merged


# --------------------------------------------------------------------------- #
# Read helpers — shape-tolerant access for the ranker + delivery surfaces       #
# --------------------------------------------------------------------------- #


def coarse_values(tags: dict[str, Any] | None, key: str) -> list[str]:
    """The plain list of values for ``key``, tolerant of list OR weighted shape.

    Used by consumers that only need the set of viewed tokens (query matching,
    company/industry recommendation seeds). Weighted maps yield their keys; legacy
    bare lists pass through; a scalar yields a one-item list.
    """

    if not isinstance(tags, dict):
        return []
    value = tags.get(key)
    if isinstance(value, dict):
        return [str(k) for k in value if isinstance(k, str) and k]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if isinstance(v, str) and v]
    if isinstance(value, str) and value:
        return [value]
    return []


def weighted_entries(
    tags: dict[str, Any] | None, key: str
) -> list[tuple[str, int, str | None]]:
    """Return ``(value, count, last_seen_iso)`` triples for a weighted key.

    Legacy bare-list rows read as ``count=1`` with ``last_seen=None`` (unknown →
    the ranker applies no decay, so old sessions keep their prior behaviour). Never
    returns PII (the keys are allowlisted coarse tokens by construction).
    """

    if not isinstance(tags, dict):
        return []
    value = tags.get(key)
    out: list[tuple[str, int, str | None]] = []
    if isinstance(value, dict):
        for tok, entry in value.items():
            if not isinstance(tok, str) or not tok:
                continue
            if isinstance(entry, dict):
                count = _clamp_count(entry.get("count"))
                last_seen = entry.get("last_seen")
                out.append((tok, count, last_seen if isinstance(last_seen, str) else None))
            elif isinstance(entry, (int, float)) and not isinstance(entry, bool):
                out.append((tok, _clamp_count(entry), None))
            else:
                out.append((tok, 1, None))
    elif isinstance(value, (list, tuple)):
        for v in value:
            if isinstance(v, str) and v:
                out.append((v, 1, None))
    elif isinstance(value, str) and value:
        out.append((value, 1, None))
    return out


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
