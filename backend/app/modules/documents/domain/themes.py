"""CV template visual themes (the design payload stored in ``cv_templates.layout_schema``).

A *theme* is the full visual identity of a CV template: layout kind, palette,
typography, photo policy, section styling, region assignment, and default section
order. It is pure data — the frontend ``<CvDocument/>`` renderer and the backend
PDF renderer both consume the identical shape, so there is one source of visual
truth (``docs/superpowers/specs/2026-07-05-cv-studio-rebuild-design.md`` §3).

This module is the single canonical definition of the 8 built-in themes. It is
imported by:

- ``domain.catalog.TEMPLATE_SEEDS`` (student-facing seeded templates),
- ``application.template_seed`` (idempotent seeder used by tests + migration),
- the data migration that upgrades legacy templates to a full theme.

Themes are versioned by ``THEME_VERSION``. Legacy templates whose ``layout_schema``
only held ``{section_order, typography.font, page}`` are upgraded in place by
``upgrade_layout_schema`` so no existing ``cv_profiles.template_id`` is orphaned.

No I/O; pure domain constants and helpers.
"""

from __future__ import annotations

from copy import deepcopy

# Current theme schema version. Bump only on a breaking shape change.
THEME_VERSION = 1

# Allowed vocabulary (kept here so validators and tests share one source).
LAYOUT_KINDS = frozenset(
    {"single", "left-sidebar", "right-sidebar", "header-band", "two-column"}
)
FONT_TOKENS = frozenset({"sans", "serif", "mono"})
PHOTO_SHAPES = frozenset({"circle", "square", "rounded"})
PHOTO_POSITIONS = frozenset({"sidebar", "header", "top-left"})
HEADING_STYLES = frozenset({"rule", "band", "caps", "plain"})

# Every palette theme must define these keys (renderer + AA-contrast checks rely
# on all of them being present).
PALETTE_KEYS = frozenset(
    {
        "primary",
        "accent",
        "sidebarBg",
        "sidebarText",
        "text",
        "muted",
        "rule",
        "pageBg",
    }
)


def _theme(
    *,
    layout: dict,
    palette: dict,
    typography: dict,
    photo: dict,
    section_style: dict,
    regions: dict,
    order: list[str],
    target_roles: list[str] | None = None,
    strengths: list[str] | None = None,
) -> dict:
    """Assemble a full theme dict in the canonical shape."""

    theme: dict = {
        "version": THEME_VERSION,
        "layout": layout,
        "palette": palette,
        "typography": typography,
        "photo": photo,
        "sectionStyle": section_style,
        "regions": regions,
        "order": list(order),
    }
    if target_roles:
        theme["target_roles"] = list(target_roles)
    if strengths:
        theme["strengths"] = list(strengths)
    return theme


# --------------------------------------------------------------------------- #
# The 8 built-in themes (design spec §5). Colourful is intentional here — this  #
# is CV DOCUMENT content, not the app chrome. Palettes are professional and     #
# chosen for WCAG AA text contrast on their backgrounds.                        #
# --------------------------------------------------------------------------- #

_CLASSIC_ATS = _theme(
    layout={"kind": "single", "sidebarWidthPct": 0, "bodyColumns": 1},
    palette={
        "primary": "#111827",
        "accent": "#374151",
        "sidebarBg": "#111827",
        "sidebarText": "#ffffff",
        "text": "#1a1a1a",
        "muted": "#6b7280",
        "rule": "#d1d5db",
        "pageBg": "#ffffff",
    },
    typography={
        "headingFont": "serif",
        "bodyFont": "sans",
        "scale": "regular",
        "headingCase": "normal",
    },
    photo={"show": False, "shape": "square", "position": "top-left"},
    section_style={"heading": "rule", "itemGap": "regular"},
    regions={
        "sidebar": [],
        "main": [
            "header",
            "summary",
            "experience",
            "education",
            "projects",
            "skills",
            "certifications",
            "awards",
        ],
    },
    order=[
        "header",
        "summary",
        "experience",
        "education",
        "projects",
        "skills",
        "certifications",
    ],
)

_MODERN_NAVY = _theme(
    layout={"kind": "left-sidebar", "sidebarWidthPct": 34, "bodyColumns": 1},
    palette={
        "primary": "#1e3a5f",
        "accent": "#2563eb",
        "sidebarBg": "#1e3a5f",
        "sidebarText": "#f8fafc",
        "text": "#1a1a1a",
        "muted": "#6b7280",
        "rule": "#e5e7eb",
        "pageBg": "#ffffff",
    },
    typography={
        "headingFont": "sans",
        "bodyFont": "sans",
        "scale": "regular",
        "headingCase": "upper",
    },
    photo={"show": True, "shape": "circle", "position": "sidebar"},
    section_style={"heading": "caps", "itemGap": "regular"},
    regions={
        "sidebar": ["header", "skills", "languages", "interests"],
        "main": ["summary", "experience", "education", "projects", "certifications"],
    },
    order=[
        "header",
        "summary",
        "experience",
        "education",
        "projects",
        "skills",
        "languages",
    ],
)

_MODERN_TEAL = _theme(
    layout={"kind": "right-sidebar", "sidebarWidthPct": 34, "bodyColumns": 1},
    palette={
        "primary": "#0f766e",
        "accent": "#0f766e",
        "sidebarBg": "#0f766e",
        "sidebarText": "#f0fdfa",
        "text": "#1a1a1a",
        "muted": "#6b7280",
        "rule": "#d1fae5",
        "pageBg": "#ffffff",
    },
    typography={
        "headingFont": "sans",
        "bodyFont": "sans",
        "scale": "regular",
        "headingCase": "normal",
    },
    photo={"show": True, "shape": "rounded", "position": "sidebar"},
    section_style={"heading": "rule", "itemGap": "regular"},
    regions={
        "sidebar": ["header", "skills", "languages", "certifications"],
        "main": ["summary", "experience", "projects", "education"],
    },
    order=[
        "header",
        "summary",
        "experience",
        "projects",
        "skills",
        "education",
        "certifications",
    ],
    target_roles=["Software Engineer", "Product Intern", "Data Engineer"],
    strengths=["projects", "technical_skills"],
)

_MINIMAL_MONO = _theme(
    layout={"kind": "single", "sidebarWidthPct": 0, "bodyColumns": 1},
    palette={
        "primary": "#1f2937",
        "accent": "#4b5563",
        "sidebarBg": "#1f2937",
        "sidebarText": "#ffffff",
        "text": "#1a1a1a",
        "muted": "#9ca3af",
        "rule": "#e5e7eb",
        "pageBg": "#ffffff",
    },
    typography={
        "headingFont": "sans",
        "bodyFont": "sans",
        "scale": "regular",
        "headingCase": "normal",
    },
    photo={"show": False, "shape": "circle", "position": "top-left"},
    section_style={"heading": "plain", "itemGap": "regular"},
    regions={
        "sidebar": [],
        "main": [
            "header",
            "summary",
            "experience",
            "education",
            "projects",
            "skills",
            "certifications",
        ],
    },
    order=[
        "header",
        "summary",
        "experience",
        "education",
        "projects",
        "skills",
    ],
)

_BOLD_HEADER = _theme(
    layout={"kind": "header-band", "sidebarWidthPct": 0, "bodyColumns": 2},
    palette={
        "primary": "#111827",
        "accent": "#1f2937",
        "sidebarBg": "#111827",
        "sidebarText": "#ffffff",
        "text": "#1a1a1a",
        "muted": "#6b7280",
        "rule": "#e5e7eb",
        "pageBg": "#ffffff",
    },
    typography={
        "headingFont": "sans",
        "bodyFont": "sans",
        "scale": "compact",
        "headingCase": "upper",
    },
    photo={"show": True, "shape": "square", "position": "header"},
    section_style={"heading": "band", "itemGap": "tight"},
    regions={
        "sidebar": [],
        "main": [
            "header",
            "summary",
            "experience",
            "projects",
            "education",
            "skills",
            "certifications",
        ],
    },
    order=[
        "header",
        "summary",
        "experience",
        "projects",
        "education",
        "skills",
        "certifications",
    ],
    strengths=["impact", "leadership"],
)

_ELEGANT_SERIF = _theme(
    layout={"kind": "two-column", "sidebarWidthPct": 32, "bodyColumns": 1},
    palette={
        "primary": "#7c2d12",
        "accent": "#92400e",
        "sidebarBg": "#fef3c7",
        "sidebarText": "#7c2d12",
        "text": "#1a1a1a",
        "muted": "#78716c",
        "rule": "#e7e5e4",
        "pageBg": "#ffffff",
    },
    typography={
        "headingFont": "serif",
        "bodyFont": "serif",
        "scale": "regular",
        "headingCase": "upper",
    },
    photo={"show": True, "shape": "circle", "position": "top-left"},
    section_style={"heading": "caps", "itemGap": "regular"},
    regions={
        "sidebar": ["header", "skills", "languages", "certifications"],
        "main": ["summary", "experience", "education", "awards"],
    },
    order=[
        "header",
        "summary",
        "experience",
        "education",
        "skills",
        "awards",
        "languages",
    ],
    target_roles=["Investment Analyst", "Consulting Intern", "Business Analyst"],
    strengths=["impact", "leadership", "case_projects"],
)

_CREATIVE_TWOTONE = _theme(
    layout={"kind": "left-sidebar", "sidebarWidthPct": 36, "bodyColumns": 1},
    palette={
        "primary": "#7c3aed",
        "accent": "#7c3aed",
        "sidebarBg": "#7c3aed",
        "sidebarText": "#f5f3ff",
        "text": "#1a1a1a",
        "muted": "#6b7280",
        "rule": "#ede9fe",
        "pageBg": "#ffffff",
    },
    typography={
        "headingFont": "sans",
        "bodyFont": "sans",
        "scale": "regular",
        "headingCase": "upper",
    },
    photo={"show": True, "shape": "circle", "position": "sidebar"},
    section_style={"heading": "band", "itemGap": "regular"},
    regions={
        "sidebar": ["header", "skills", "interests", "languages"],
        "main": ["summary", "projects", "experience", "education", "awards"],
    },
    order=[
        "header",
        "summary",
        "projects",
        "experience",
        "skills",
        "education",
        "awards",
    ],
    target_roles=["Marketing Intern", "Growth Intern", "Content Strategist"],
    strengths=["portfolio", "campaign_metrics", "communication"],
)

_TECH_CHIPS = _theme(
    layout={"kind": "single", "sidebarWidthPct": 0, "bodyColumns": 1},
    palette={
        "primary": "#1e293b",
        "accent": "#2563eb",
        "sidebarBg": "#1e293b",
        "sidebarText": "#ffffff",
        "text": "#1a1a1a",
        "muted": "#64748b",
        "rule": "#e2e8f0",
        "pageBg": "#ffffff",
    },
    typography={
        "headingFont": "mono",
        "bodyFont": "sans",
        "scale": "compact",
        "headingCase": "normal",
    },
    photo={"show": False, "shape": "rounded", "position": "top-left"},
    section_style={"heading": "rule", "itemGap": "tight"},
    regions={
        "sidebar": [],
        "main": [
            "header",
            "summary",
            "skills",
            "experience",
            "projects",
            "education",
            "certifications",
        ],
    },
    order=[
        "header",
        "summary",
        "skills",
        "experience",
        "projects",
        "education",
        "certifications",
    ],
    target_roles=["Software Engineer", "Backend Intern", "DevOps Intern"],
    strengths=["technical_skills", "projects"],
)


# Ordered mapping of stable template key -> full theme. The seeder and the
# data-migration both iterate this, so the 8 shipped templates and their themes
# stay in lock-step.
BUILTIN_THEMES: dict[str, dict] = {
    "classic_ats": _CLASSIC_ATS,
    "modern_navy": _MODERN_NAVY,
    "modern_teal": _MODERN_TEAL,
    "minimal_mono": _MINIMAL_MONO,
    "bold_header": _BOLD_HEADER,
    "elegant_serif": _ELEGANT_SERIF,
    "creative_twotone": _CREATIVE_TWOTONE,
    "tech_chips": _TECH_CHIPS,
}


def theme_for(key: str) -> dict:
    """Return a deep copy of the built-in theme for ``key`` (KeyError if unknown)."""

    return deepcopy(BUILTIN_THEMES[key])


# --------------------------------------------------------------------------- #
# Legacy upgrade: {section_order, typography.font, page} -> a full theme.       #
# Used by the data migration so no existing template row is left theme-less.    #
# --------------------------------------------------------------------------- #

# Old keys that map cleanly onto a new built-in theme (upgrade-in-place preserves
# the row + its id, so any cv_profiles.template_id still resolves).
LEGACY_KEY_TO_THEME: dict[str, str] = {
    "classic_one_page": "classic_ats",
    "technical_modern": "tech_chips",
    "data_analytics_research": "modern_teal",
    "finance_consulting": "elegant_serif",
    "marketing_growth": "creative_twotone",
    "healthcare_impact": "modern_navy",
    "business_premium": "bold_header",
}


def _default_theme_from_legacy(legacy: dict) -> dict:
    """Build a full theme from an old ``{section_order, typography, page}`` schema.

    Preserves the legacy section order (as ``order`` + ``regions.main``), maps the
    old font hint onto ``typography.bodyFont``/``headingFont``, and keeps any
    ``target_roles``/``strengths`` the old schema carried. Produces a conservative,
    accessible single-column ink theme (a safe default for any un-mapped key).
    """

    base = deepcopy(_CLASSIC_ATS)
    font = "sans"
    typo = legacy.get("typography")
    if isinstance(typo, dict) and typo.get("font") in FONT_TOKENS:
        font = str(typo["font"])
    base["typography"]["headingFont"] = font
    base["typography"]["bodyFont"] = font

    order = legacy.get("section_order")
    if isinstance(order, list) and all(isinstance(s, str) and s.strip() for s in order):
        section_order = ["header"] + [s for s in order if s != "header"]
        base["order"] = section_order
        base["regions"] = {"sidebar": [], "main": list(section_order)}

    for extra in ("target_roles", "strengths"):
        value = legacy.get(extra)
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            base[extra] = list(value)
    return base


def upgrade_layout_schema(key: str, legacy: dict | None) -> dict:
    """Return the full theme a template row should carry.

    - A canonical built-in key always resolves to its real built-in theme (so a row
      that was previously seeded with a stale/generic theme self-heals).
    - A known legacy key upgrades to its mapped built-in theme (visual refresh).
    - An already-full custom theme is preserved verbatim (idempotent — never clobber
      an admin-authored design).
    - Any other key is upgraded in place from its own ``section_order``/font hint,
      so custom university templates keep their identity but gain a full theme.
    """

    if key in BUILTIN_THEMES:
        return theme_for(key)
    mapped = LEGACY_KEY_TO_THEME.get(key)
    if mapped is not None:
        return theme_for(mapped)
    if is_full_theme(legacy):
        return deepcopy(legacy)  # type: ignore[arg-type]
    return _default_theme_from_legacy(legacy or {})


def is_full_theme(schema: object) -> bool:
    """Cheap structural check: does ``schema`` already carry a full theme?

    True when it has a ``layout.kind`` and a palette with every required key.
    """

    if not isinstance(schema, dict):
        return False
    layout = schema.get("layout")
    palette = schema.get("palette")
    if not isinstance(layout, dict) or not isinstance(palette, dict):
        return False
    if layout.get("kind") not in LAYOUT_KINDS:
        return False
    return PALETTE_KEYS.issubset(palette.keys())
