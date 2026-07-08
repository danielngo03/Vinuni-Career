"""Sponsored-placement audience targeting descriptor + viewer matcher (pure).

A *targeting descriptor* is a small, validated, allowlist-safe audience spec that a
partner (or the university) attaches to a placement so a paid slot is delivered to
RELEVANT viewers instead of "newest campaign wins". It is persisted inside the
existing ``sponsored_placements.settings`` JSON under the ``"targeting"`` key — no
schema migration, no new PII surface.

Privacy is the non-negotiable core (``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md``
§4/§7, ``docs/SECURITY_PRIVACY.md``): targeting may ONLY use the same coarse,
privacy-safe signals the discovery layer already stores. This module REUSES the
discovery forbidden-signal allowlist (:data:`allowlist.FORBIDDEN_COARSE_TAG_KEYS`)
so a placement can NEVER target on a PII / sensitive category (name, email, exact
location, health, ethnicity, gender, religion, politics, disability, income,
salary, …) or a third-party ad id — such a dimension is rejected outright.

Descriptor shape (stored)::

    {"mode": "manual",
     "dimensions": {"industry": ["finance"], "region": ["hanoi"], ...}}

Modes:
    automatic              broad reach; no audience restriction (default).
    manual                 partner-declared audience values per dimension.
    university_restricted  university-set audience values; the partner may not
                           edit them (only the university relabels/clears them).

Filtering semantics (per dimension, viewer-side):
    - A dimension the descriptor does not list is not evaluated.
    - If the viewer has NO signal for a listed dimension it is INDETERMINATE — it
      neither excludes nor boosts (we never over-suppress on missing data).
    - If the viewer HAS a signal that INTERSECTS the allowed set → positive match
      (adds relevance so better-matched placements rank ahead of broad ones).
    - If the viewer HAS a signal that does NOT intersect → the placement is
      EXCLUDED for this viewer (the paid slot is simply left unfilled, never
      backfilled with organic content, and organic order is never touched).

Only the six dimensions with a real, privacy-safe viewer signal actively FILTER
(region, industry, role_family, work_mode, student_segment, language). The
academic dimensions (degree / major / year) are validated + stored so a partner
can declare intent and the university can restrict them, but they do not filter
today because the identity-only student profile (owner decision 2026-07-06) no
longer carries a viewer major/graduation-year signal; they are documented as
declared-only until a privacy-safe cohort signal exists.

No I/O lives here — same inputs always yield the same eligibility + relevance, so
paid-slot selection is reproducible and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.discovery.domain import allowlist

# --------------------------------------------------------------------------- #
# Modes                                                                        #
# --------------------------------------------------------------------------- #

MODE_AUTOMATIC = "automatic"
MODE_MANUAL = "manual"
MODE_UNIVERSITY_RESTRICTED = "university_restricted"

MODES: frozenset[str] = frozenset(
    {MODE_AUTOMATIC, MODE_MANUAL, MODE_UNIVERSITY_RESTRICTED}
)
# Modes a PARTNER may set on their own placement (never self-restrict).
PARTNER_MODES: frozenset[str] = frozenset({MODE_AUTOMATIC, MODE_MANUAL})

DEFAULT_MODE = MODE_AUTOMATIC

# --------------------------------------------------------------------------- #
# Dimensions                                                                   #
# --------------------------------------------------------------------------- #

DIM_REGION = "region"
DIM_INDUSTRY = "industry"
DIM_ROLE_FAMILY = "role_family"
DIM_WORK_MODE = "work_mode"
DIM_STUDENT_SEGMENT = "student_segment"
DIM_LANGUAGE = "language"
DIM_DEGREE = "degree"
DIM_MAJOR = "major"
DIM_YEAR = "year"

# Dimensions that have a privacy-safe viewer signal and therefore actively filter.
FILTERING_DIMENSIONS: frozenset[str] = frozenset(
    {
        DIM_REGION,
        DIM_INDUSTRY,
        DIM_ROLE_FAMILY,
        DIM_WORK_MODE,
        DIM_STUDENT_SEGMENT,
        DIM_LANGUAGE,
    }
)
# Validated + stored, but no viewer signal today (declared-only, university-gated).
DECLARED_ONLY_DIMENSIONS: frozenset[str] = frozenset(
    {DIM_DEGREE, DIM_MAJOR, DIM_YEAR}
)

TARGETING_DIMENSIONS: frozenset[str] = FILTERING_DIMENSIONS | DECLARED_ONLY_DIMENSIONS

# Closed vocabularies for the scalar-style dimensions (values outside are dropped).
_WORK_MODES: frozenset[str] = frozenset({"onsite", "remote", "hybrid"})
_STUDENT_SEGMENTS: frozenset[str] = frozenset({"student", "alumni", "guest"})
_LANGUAGES: frozenset[str] = frozenset({"vi", "en"})

_MAX_VALUES_PER_DIM = 20
_MAX_TOKEN_LEN = 64


class InvalidTargetingError(ValueError):
    """A targeting dimension is forbidden (PII/sensitive) or a mode is illegal.

    Raised by :func:`validate_and_normalize`; the service layer maps it to a
    user-safe ``422`` via :class:`InvalidTargetingFieldError`.
    """

    def __init__(self, *, reason: str, dimension: str | None = None) -> None:
        self.reason = reason
        self.dimension = dimension
        super().__init__(reason)


def _norm(value: Any) -> str | None:
    """Lowercase + trim a token (matching how coarse tags are stored). No accents
    are stripped so an accented city/industry token still matches the viewer's."""

    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if not token:
        return None
    return token[:_MAX_TOKEN_LEN]


def _clean_values(dimension: str, raw: Any) -> list[str]:
    """Normalize + vocab-clamp the value list for one dimension (de-duped, capped)."""

    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        token = _norm(item)
        if token is None:
            continue
        if dimension == DIM_WORK_MODE and token not in _WORK_MODES:
            continue
        if dimension == DIM_STUDENT_SEGMENT and token not in _STUDENT_SEGMENTS:
            continue
        if dimension == DIM_LANGUAGE and token not in _LANGUAGES:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
        if len(out) >= _MAX_VALUES_PER_DIM:
            break
    return out


def validate_and_normalize(
    raw: dict[str, Any] | None, *, allow_restricted: bool = False
) -> dict[str, Any]:
    """Validate + normalize an inbound targeting descriptor for persistence.

    Returns ``{"mode": <mode>, "dimensions": {<dim>: [<value>, ...], ...}}``.

    - ``mode`` must be a known mode. ``university_restricted`` is only accepted
      when ``allow_restricted`` (the university path); a partner attempting it is
      rejected.
    - Every dimension KEY is checked against the discovery forbidden-signal
      allowlist FIRST — a PII / sensitive / third-party-ad-id key raises
      :class:`InvalidTargetingError` (targeting can never use those). Unknown
      non-forbidden keys are dropped (default-deny). Known dimensions are
      value-cleaned + vocab-clamped.
    - ``automatic`` mode always stores empty dimensions (broad reach).
    """

    if raw is None:
        return {"mode": DEFAULT_MODE, "dimensions": {}}
    if not isinstance(raw, dict):
        raise InvalidTargetingError(reason="invalid_targeting")

    mode = _norm(raw.get("mode")) or DEFAULT_MODE
    if mode not in MODES:
        raise InvalidTargetingError(reason="invalid_mode", dimension="mode")
    if mode == MODE_UNIVERSITY_RESTRICTED and not allow_restricted:
        raise InvalidTargetingError(reason="restricted_mode_forbidden", dimension="mode")

    dims_raw = raw.get("dimensions")
    if dims_raw is None:
        # Tolerate a flat descriptor (dimensions provided at the top level).
        dims_raw = {k: v for k, v in raw.items() if k != "mode"}
    if not isinstance(dims_raw, dict):
        raise InvalidTargetingError(reason="invalid_dimensions", dimension="dimensions")

    cleaned: dict[str, list[str]] = {}
    if mode != MODE_AUTOMATIC:
        for key, value in dims_raw.items():
            kname = _norm(key)
            if kname is None:
                continue
            # Non-negotiable: never target on a forbidden PII/sensitive signal.
            if kname in allowlist.FORBIDDEN_COARSE_TAG_KEYS:
                raise InvalidTargetingError(
                    reason="forbidden_targeting_dimension", dimension=kname
                )
            if kname not in TARGETING_DIMENSIONS:
                continue  # default-deny unknown (non-forbidden) keys
            values = _clean_values(kname, value)
            if values:
                cleaned[kname] = values

    return {"mode": mode, "dimensions": cleaned}


def descriptor_from_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Read the stored targeting descriptor out of a placement's ``settings`` JSON.

    Tolerant of a missing/legacy row (returns the broad-reach ``automatic``
    default) and re-normalizes what is stored so a hand-edited row can never
    smuggle a forbidden dimension into the matcher.
    """

    if not isinstance(settings, dict):
        return {"mode": DEFAULT_MODE, "dimensions": {}}
    stored = settings.get("targeting")
    if not isinstance(stored, dict):
        return {"mode": DEFAULT_MODE, "dimensions": {}}
    try:
        # allow_restricted=True: a stored university_restricted descriptor is valid
        # to READ back (the write path is what gates who may SET it).
        return validate_and_normalize(stored, allow_restricted=True)
    except InvalidTargetingError:
        # A corrupt/hostile stored descriptor never widens delivery — fall back to
        # broad reach rather than trusting an unvalidatable spec.
        return {"mode": DEFAULT_MODE, "dimensions": {}}


def is_restricted(settings: dict[str, Any] | None) -> bool:
    """Whether the stored descriptor is university-restricted (partner-immutable)."""

    return descriptor_from_settings(settings).get("mode") == MODE_UNIVERSITY_RESTRICTED


# --------------------------------------------------------------------------- #
# Viewer signals + matcher                                                     #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ViewerSignals:
    """The privacy-safe, coarse signals a paid slot may be targeted against.

    All fields are coarse allowlisted tokens (never PII): ``persona`` is the
    coarse student segment, ``locale`` the language, and the sets are the same
    coarse city / work-mode / industry / role-family signals the discovery
    session already stores. Tokens are lowercased to match descriptor values.
    """

    persona: str = "guest"
    locale: str = "vi"
    cities: frozenset[str] = field(default_factory=frozenset)
    work_modes: frozenset[str] = field(default_factory=frozenset)
    industries: frozenset[str] = field(default_factory=frozenset)
    role_families: frozenset[str] = field(default_factory=frozenset)

    def values_for(self, dimension: str) -> frozenset[str]:
        if dimension == DIM_REGION:
            return self.cities
        if dimension == DIM_INDUSTRY:
            return self.industries
        if dimension == DIM_ROLE_FAMILY:
            return self.role_families
        if dimension == DIM_WORK_MODE:
            return self.work_modes
        if dimension == DIM_STUDENT_SEGMENT:
            seg = (self.persona or "guest").strip().lower()
            return frozenset({seg}) if seg else frozenset()
        if dimension == DIM_LANGUAGE:
            lang = (self.locale or "vi").strip().lower()
            return frozenset({lang}) if lang else frozenset()
        return frozenset()


@dataclass(frozen=True, slots=True)
class TargetingMatch:
    """Result of matching a descriptor against a viewer."""

    eligible: bool
    relevance: int
    matched_dimensions: tuple[str, ...] = ()


def match(descriptor: dict[str, Any], viewer: ViewerSignals) -> TargetingMatch:
    """Decide whether a paid slot is eligible for ``viewer`` and how relevant.

    Broad-reach (``automatic`` / no dimensions) placements are always eligible at
    relevance ``0`` (they show to everyone but rank behind positively-matched
    placements). A single contradicting determinable signal excludes the slot.
    """

    dims = descriptor.get("dimensions") if isinstance(descriptor, dict) else None
    if not isinstance(dims, dict) or not dims:
        return TargetingMatch(eligible=True, relevance=0)

    relevance = 0
    matched: list[str] = []
    for dimension, allowed in dims.items():
        if dimension not in FILTERING_DIMENSIONS:
            continue  # declared-only (degree/major/year) never filters yet
        allowed_set = {v for v in allowed if isinstance(v, str)}
        if not allowed_set:
            continue
        viewer_values = viewer.values_for(dimension)
        if not viewer_values:
            continue  # indeterminate — never exclude on missing data
        if allowed_set & viewer_values:
            relevance += 1
            matched.append(dimension)
        else:
            # A determinable signal that contradicts the target audience excludes.
            return TargetingMatch(eligible=False, relevance=0)

    return TargetingMatch(
        eligible=True, relevance=relevance, matched_dimensions=tuple(matched)
    )
