"""Student-profile vocabulary + localized labels.

Every raw enum code is paired with a vi/en label so the API never ships a raw
code alone (``.claude/rules/backend.md``: "No raw enum codes in end-user
responses"). Canonical field set follows ``docs/DATA_MODEL.md`` §6; the single
``profile_visibility`` overall gate is introduced by this slice (see the module
docstring in ``models.py`` for the documented reconciliation with the per-field
``privacy_settings`` of the data model).
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
# Enumerations                                                                 #
# --------------------------------------------------------------------------- #

OPEN_TO_WORK_TYPES = frozenset({"full_time", "internship", "part_time", "contract"})
DEGREE_LEVELS = frozenset({"undergraduate", "graduate", "phd"})
EMPLOYMENT_TYPES = frozenset({"full_time", "part_time", "internship", "contract"})
SKILL_CATEGORIES = frozenset({"technical", "language", "soft"})

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

_OPEN_TO_WORK_LABELS: dict[str, tuple[str, str]] = {
    "full_time": ("Toàn thời gian", "Full-time"),
    "internship": ("Thực tập", "Internship"),
    "part_time": ("Bán thời gian", "Part-time"),
    "contract": ("Hợp đồng", "Contract"),
}

_DEGREE_LABELS: dict[str, tuple[str, str]] = {
    "undergraduate": ("Đại học", "Undergraduate"),
    "graduate": ("Sau đại học", "Graduate"),
    "phd": ("Tiến sĩ", "PhD"),
}

_EMPLOYMENT_LABELS: dict[str, tuple[str, str]] = {
    "full_time": ("Toàn thời gian", "Full-time"),
    "part_time": ("Bán thời gian", "Part-time"),
    "internship": ("Thực tập", "Internship"),
    "contract": ("Hợp đồng", "Contract"),
}

_SKILL_CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "technical": ("Kỹ thuật", "Technical"),
    "language": ("Ngôn ngữ", "Language"),
    "soft": ("Kỹ năng mềm", "Soft skill"),
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


def open_to_work_label(code: str, *, locale: str = "vi") -> str | None:
    return _label(_OPEN_TO_WORK_LABELS, code, locale=locale)


def degree_label(code: str | None, *, locale: str = "vi") -> str | None:
    return _label(_DEGREE_LABELS, code, locale=locale)


def employment_label(code: str | None, *, locale: str = "vi") -> str | None:
    return _label(_EMPLOYMENT_LABELS, code, locale=locale)


def skill_category_label(code: str | None, *, locale: str = "vi") -> str | None:
    return _label(_SKILL_CATEGORY_LABELS, code, locale=locale)
