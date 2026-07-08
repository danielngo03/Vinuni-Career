"""Student-profile vocabulary + localized labels (identity-only profile).

Every raw enum code is paired with a vi/en label so the API never ships a raw
code alone (``.claude/rules/backend.md``: "No raw enum codes in end-user
responses"). Since the profile is now identity-only (owner decision 2026-07-06),
the only vocabulary it owns is the overall visibility gate and the per-field
contact gates. Career vocabulary (degrees, employment types, skill categories,
open-to-work types) moved out with the career fields.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Overall profile discoverability / visibility                                #
# --------------------------------------------------------------------------- #

VISIBILITY_PUBLIC = "public"          # any authenticated user may see the public projection
VISIBILITY_VINUNI_ONLY = "vinuni_only"  # only the VinUni community (student/alumni/staff)
VISIBILITY_PRIVATE = "private"        # owner only (+ staff governance); not discoverable

PROFILE_VISIBILITY = frozenset(
    {VISIBILITY_PUBLIC, VISIBILITY_VINUNI_ONLY, VISIBILITY_PRIVATE}
)

# --------------------------------------------------------------------------- #
# Per-field contact visibility (subset of docs/DATA_MODEL.md privacy_settings) #
# --------------------------------------------------------------------------- #

CONTACT_PUBLIC = "public"     # visible in any allowed view
CONTACT_INVITED = "invited"   # visible only in an accepted-reveal / application context
CONTACT_HIDDEN = "hidden"     # never exposed to anyone but the owner

CONTACT_VISIBILITY = frozenset({CONTACT_PUBLIC, CONTACT_INVITED, CONTACT_HIDDEN})

# --------------------------------------------------------------------------- #
# Labels                                                                       #
# --------------------------------------------------------------------------- #

_VISIBILITY_LABELS: dict[str, tuple[str, str]] = {
    VISIBILITY_PUBLIC: ("Công khai", "Public"),
    VISIBILITY_VINUNI_ONLY: ("Chỉ trong VinUni", "VinUni only"),
    VISIBILITY_PRIVATE: ("Riêng tư", "Private"),
}

_CONTACT_LABELS: dict[str, tuple[str, str]] = {
    CONTACT_PUBLIC: ("Hiển thị", "Visible"),
    CONTACT_INVITED: ("Khi được mời", "When invited"),
    CONTACT_HIDDEN: ("Ẩn", "Hidden"),
}


def _label(table: dict[str, tuple[str, str]], code: str | None, *, locale: str) -> str | None:
    if code is None:
        return None
    vi, en = table.get(code, (code, code))
    return vi if locale == "vi" else en


def visibility_label(code: str, *, locale: str = "vi") -> str:
    return _label(_VISIBILITY_LABELS, code, locale=locale) or code


def contact_label(code: str, *, locale: str = "vi") -> str:
    return _label(_CONTACT_LABELS, code, locale=locale) or code
