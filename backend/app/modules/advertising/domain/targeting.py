"""Coarse ad-targeting allowlist, forbidden-dimension guard, viewer segment, and
targeting-match logic (pure; no I/O).

The allocation engine may only ever target and segment on COARSE, privacy-safe
dimensions (``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §7.0 "Targeting
dimensions (coarse only)", ``docs/SECURITY_PRIVACY.md`` "Advertising Compliance"):

- partner LOCATION (coarse city / region / campus + work-mode);
- student MAJOR / faculty;
- declared CAREER-interest / role-family;
- coarse year/cohort and device class.

NEVER exact GPS, exact address, raw IP, or ANY sensitive category (health,
ethnicity, gender, religion, politics, disability, pregnancy, financial). Two
entry points enforce this at different trust levels:

- :func:`validate_campaign_targeting` — STRICT. A partner authors this explicitly,
  so a forbidden or unknown dimension is REJECTED (the builder blocks it), never
  silently accepted. Values are normalized to coarse tokens.
- :func:`sanitize_viewer_segment` — LENIENT default-deny. Derived from a guest
  discovery session or a student's confirmed coarse profile; forbidden/unknown
  keys are DROPPED (never raise, never persist) so a viewer signal can never leak
  a sensitive attribute into the engine.

A campaign with NO targeting dimensions is BROAD (matches everyone). Otherwise a
campaign matches a viewer when ANY targeted dimension overlaps the viewer's coarse
attributes (OR semantics — wider reach; the match *reason* records only coarse,
non-PII values for audit).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# Targeting dimensions                                                        #
# --------------------------------------------------------------------------- #

DIM_LOCATIONS = "locations"
DIM_MAJORS = "majors"
DIM_CAREERS = "careers"
DIM_WORK_MODES = "work_modes"
DIM_YEAR_COHORTS = "year_cohorts"
DIM_DEVICE_CLASSES = "device_classes"

# The ONLY targeting/segment keys that may ever be stored or matched on.
ALLOWED_TARGETING_KEYS: frozenset[str] = frozenset(
    {
        DIM_LOCATIONS,
        DIM_MAJORS,
        DIM_CAREERS,
        DIM_WORK_MODES,
        DIM_YEAR_COHORTS,
        DIM_DEVICE_CLASSES,
    }
)

# Explicit forbidden keys — a clear reject for the strict partner path (and a
# belt-and-braces drop for the viewer path). Mirrors the discovery allowlist
# forbidden set (GPS / exact location / raw IP / sensitive categories / 3p ad ids).
FORBIDDEN_TARGETING_KEYS: frozenset[str] = frozenset(
    {
        # exact location / network
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
        "street",
        "postal_code",
        "zip",
        "ip",
        "ip_address",
        "raw_ip",
        # direct identifiers
        "name",
        "email",
        "phone",
        "user_id",
        "username",
        # sensitive categories (docs/SECURITY_PRIVACY.md "Advertising Compliance")
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

# --------------------------------------------------------------------------- #
# Coarse value vocabularies (values outside these are dropped)                #
# --------------------------------------------------------------------------- #

# Coarse Vietnam locations + VinUni campus + remote. NOT exact addresses/GPS.
COARSE_LOCATIONS: frozenset[str] = frozenset(
    {
        "hanoi",
        "ho_chi_minh",
        "da_nang",
        "hai_phong",
        "can_tho",
        "binh_duong",
        "dong_nai",
        "north",
        "central",
        "south",
        "vinuni_campus",
        "remote",
        "overseas",
        "other",
    }
)

# Coarse student major / faculty buckets (VinUni college structure + catch-alls).
COARSE_MAJORS: frozenset[str] = frozenset(
    {
        "computer_science",
        "engineering",
        "business",
        "economics",
        "health_sciences",
        "medicine",
        "nursing",
        "arts_sciences",
        "humanities",
        "design",
        "law",
        "hospitality",
        "undecided",
        "other",
    }
)

# Coarse career-interest / role-family buckets.
COARSE_CAREERS: frozenset[str] = frozenset(
    {
        "software_engineering",
        "data",
        "ai_ml",
        "product",
        "design",
        "finance",
        "banking",
        "accounting",
        "marketing",
        "sales",
        "operations",
        "consulting",
        "research",
        "healthcare",
        "hospitality",
        "education",
        "legal",
        "human_resources",
        "supply_chain",
        "other",
    }
)

WORK_MODES: frozenset[str] = frozenset({"onsite", "remote", "hybrid"})
YEAR_COHORTS: frozenset[str] = frozenset(
    {"freshman", "sophomore", "junior", "senior", "graduate", "alumni"}
)
DEVICE_CLASSES: frozenset[str] = frozenset({"desktop", "mobile", "tablet"})

_DIM_VOCAB: dict[str, frozenset[str]] = {
    DIM_LOCATIONS: COARSE_LOCATIONS,
    DIM_MAJORS: COARSE_MAJORS,
    DIM_CAREERS: COARSE_CAREERS,
    DIM_WORK_MODES: WORK_MODES,
    DIM_YEAR_COHORTS: YEAR_COHORTS,
    DIM_DEVICE_CLASSES: DEVICE_CLASSES,
}

_MAX_ITEMS_PER_DIM = 12


class ForbiddenTargetingDimension(ValueError):
    """A campaign targeting payload used a forbidden (GPS/sensitive) dimension."""

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension
        super().__init__(dimension)


class UnknownTargetingDimension(ValueError):
    """A campaign targeting payload used an unrecognized dimension key."""

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension
        super().__init__(dimension)


def _norm_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = re.sub(r"[\s\-]+", "_", value.strip().lower())
    token = re.sub(r"[^a-z0-9_]+", "", token)
    return token or None


def _clean_dim_values(dim: str, value: Any) -> list[str]:
    """Normalize + allowlist-filter the values for one dimension (order-stable)."""

    vocab = _DIM_VOCAB[dim]
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        token = _norm_token(item)
        if token and token in vocab and token not in seen:
            seen.add(token)
            out.append(token)
        if len(out) >= _MAX_ITEMS_PER_DIM:
            break
    return out


def validate_campaign_targeting(raw: dict[str, Any] | None) -> dict[str, list[str]]:
    """STRICT: normalize + allowlist a partner-authored targeting payload.

    Raises :class:`ForbiddenTargetingDimension` for any GPS/sensitive key and
    :class:`UnknownTargetingDimension` for any non-coarse key, so the builder can
    surface a clear "forbidden dimension" error. Returns a dict of dimension ->
    coarse-token list (dimensions that clean to empty are omitted). An empty result
    means the campaign is BROAD (untargeted).
    """

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise UnknownTargetingDimension("targeting")
    clean: dict[str, list[str]] = {}
    for key, value in raw.items():
        k = str(key).strip().lower()
        if k in FORBIDDEN_TARGETING_KEYS:
            raise ForbiddenTargetingDimension(k)
        if k not in ALLOWED_TARGETING_KEYS:
            raise UnknownTargetingDimension(k)
        values = _clean_dim_values(k, value)
        if values:
            clean[k] = values
    return clean


# --------------------------------------------------------------------------- #
# Viewer segment (coarse, privacy-safe)                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ViewerSegment:
    """A coarse, privacy-safe descriptor of who is viewing a surface.

    Guests contribute ONLY coarse signals (from a discovery session's allowlisted
    ``coarse_tags``); authenticated students may add coarse confirmed-profile
    signals. There is no field for name/email/exact location/IP/sensitive data.
    """

    locations: frozenset[str] = field(default_factory=frozenset)
    majors: frozenset[str] = field(default_factory=frozenset)
    careers: frozenset[str] = field(default_factory=frozenset)
    work_modes: frozenset[str] = field(default_factory=frozenset)
    year_cohorts: frozenset[str] = field(default_factory=frozenset)
    device_classes: frozenset[str] = field(default_factory=frozenset)

    def dim(self, key: str) -> frozenset[str]:
        return {
            DIM_LOCATIONS: self.locations,
            DIM_MAJORS: self.majors,
            DIM_CAREERS: self.careers,
            DIM_WORK_MODES: self.work_modes,
            DIM_YEAR_COHORTS: self.year_cohorts,
            DIM_DEVICE_CLASSES: self.device_classes,
        }.get(key, frozenset())

    @property
    def is_empty(self) -> bool:
        return not (
            self.locations
            or self.majors
            or self.careers
            or self.work_modes
            or self.year_cohorts
            or self.device_classes
        )


def sanitize_viewer_segment(raw: dict[str, Any] | None) -> ViewerSegment:
    """LENIENT default-deny: build a :class:`ViewerSegment` from arbitrary input.

    Forbidden and unknown keys are DROPPED (never raise, never persist); values are
    normalized and allowlist-filtered. Also accepts the discovery ``coarse_tags``
    shape (``city`` -> location, ``role_families`` -> careers, ``industries`` /
    ``categories`` -> careers, ``work_mode`` scalar, ``device_type`` scalar) so a
    guest session can feed the engine without any PII.
    """

    if not isinstance(raw, dict):
        return ViewerSegment()

    buckets: dict[str, set[str]] = {k: set() for k in ALLOWED_TARGETING_KEYS}

    def _add(dim: str, value: Any) -> None:
        for token in _clean_dim_values(dim, value):
            buckets[dim].add(token)

    for key, value in raw.items():
        k = str(key).strip().lower()
        if k in FORBIDDEN_TARGETING_KEYS:
            continue  # default-deny
        if k in ALLOWED_TARGETING_KEYS:
            _add(k, value)
            continue
        # Discovery coarse_tags compatibility shims (privacy-safe only).
        if k == "city":
            _add(DIM_LOCATIONS, value)
        elif k in ("role_families", "categories", "industries"):
            _add(DIM_CAREERS, value)
        elif k == "work_mode":
            _add(DIM_WORK_MODES, value)
        elif k == "device_type":
            _add(DIM_DEVICE_CLASSES, value)
        # anything else silently dropped

    return ViewerSegment(
        locations=frozenset(buckets[DIM_LOCATIONS]),
        majors=frozenset(buckets[DIM_MAJORS]),
        careers=frozenset(buckets[DIM_CAREERS]),
        work_modes=frozenset(buckets[DIM_WORK_MODES]),
        year_cohorts=frozenset(buckets[DIM_YEAR_COHORTS]),
        device_classes=frozenset(buckets[DIM_DEVICE_CLASSES]),
    )


# --------------------------------------------------------------------------- #
# Matching + segment key                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TargetMatch:
    """The result of matching a campaign's targeting against a viewer."""

    matched: bool
    score: int  # number of overlapping targeted dimensions (0 for broad match)
    reason: dict  # coarse, non-PII match explanation for audit


def match_targeting(
    targeting: dict[str, Any] | None, viewer: ViewerSegment
) -> TargetMatch:
    """Does ``targeting`` match ``viewer``? (broad if untargeted; else OR overlap).

    ``score`` is the count of targeted dimensions that overlap the viewer (used to
    rank a more precisely-targeted campaign above a broad one). ``reason`` records
    only coarse token values — never PII.
    """

    dims = {k: v for k, v in (targeting or {}).items() if k in ALLOWED_TARGETING_KEYS and v}
    if not dims:
        return TargetMatch(matched=True, score=0, reason={"untargeted": True})

    overlaps: dict[str, list[str]] = {}
    for key, wanted in dims.items():
        viewer_values = viewer.dim(key)
        hit = sorted(set(wanted) & viewer_values)
        if hit:
            overlaps[key] = hit

    if not overlaps:
        return TargetMatch(matched=False, score=0, reason={"matched_dimensions": {}})
    return TargetMatch(
        matched=True,
        score=len(overlaps),
        reason={"matched_dimensions": overlaps},
    )


def segment_key(viewer: ViewerSegment) -> str:
    """A deterministic, bounded, privacy-safe key for a coarse viewer segment.

    Canonicalizes the coarse dimensions into a stable string; long segments are
    hashed so the stored ``ad_allocations.segment_key`` stays within its column
    bound. ``"anon"`` for an empty (no-signal) segment.
    """

    parts: list[str] = []
    for prefix, values in (
        ("loc", viewer.locations),
        ("maj", viewer.majors),
        ("car", viewer.careers),
        ("wm", viewer.work_modes),
        ("yr", viewer.year_cohorts),
        ("dev", viewer.device_classes),
    ):
        if values:
            parts.append(f"{prefix}:{','.join(sorted(values))}")
    if not parts:
        return "anon"
    canonical = "|".join(parts)
    if len(canonical) <= 110:
        return canonical
    return "h:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:100]
