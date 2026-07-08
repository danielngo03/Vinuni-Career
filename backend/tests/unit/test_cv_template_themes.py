"""Unit tests for CV template visual themes (design payload) + legacy upgrade.

The theme is the renderer's single source of truth; every built-in theme must be
structurally complete (valid layout kind, full palette, header-first order) and
the 8 shipped themes must be visually distinct. The legacy-upgrade helper must
turn an old ``{section_order, typography.font}`` schema into a full theme without
losing the section order (so existing CVs are not orphaned).
"""

from __future__ import annotations

from app.modules.documents.domain import themes
from app.modules.documents.domain.catalog import DEFAULT_SECTIONS, SECTION_TYPES


def test_eight_builtin_themes() -> None:
    assert len(themes.BUILTIN_THEMES) == 8
    assert set(themes.BUILTIN_THEMES) == {
        "classic_ats",
        "modern_navy",
        "modern_teal",
        "minimal_mono",
        "bold_header",
        "elegant_serif",
        "creative_twotone",
        "tech_chips",
    }


def test_every_theme_is_structurally_complete() -> None:
    for key, theme in themes.BUILTIN_THEMES.items():
        assert theme["version"] == themes.THEME_VERSION, key
        assert theme["layout"]["kind"] in themes.LAYOUT_KINDS, key
        assert themes.PALETTE_KEYS <= set(theme["palette"].keys()), key
        assert theme["typography"]["headingFont"] in themes.FONT_TOKENS, key
        assert theme["typography"]["bodyFont"] in themes.FONT_TOKENS, key
        assert theme["photo"]["shape"] in themes.PHOTO_SHAPES, key
        assert theme["sectionStyle"]["heading"] in themes.HEADING_STYLES, key
        assert isinstance(theme["regions"]["sidebar"], list), key
        assert isinstance(theme["regions"]["main"], list), key
        # The header (name + contact) always leads the order.
        assert theme["order"][0] == "header", key
        # is_full_theme agrees.
        assert themes.is_full_theme(theme), key
        # All ordered/region section types are real section types.
        for st in theme["order"]:
            assert st in SECTION_TYPES, (key, st)


def test_themes_are_visually_distinct() -> None:
    # No two themes share the same (layout kind, sidebar background, accent).
    signatures = {
        (t["layout"]["kind"], t["palette"]["sidebarBg"], t["palette"]["accent"])
        for t in themes.BUILTIN_THEMES.values()
    }
    assert len(signatures) == len(themes.BUILTIN_THEMES)


def test_theme_for_returns_independent_copy() -> None:
    a = themes.theme_for("classic_ats")
    a["palette"]["accent"] = "#ffffff"
    b = themes.theme_for("classic_ats")
    assert b["palette"]["accent"] != "#ffffff"  # not mutated by the caller


def test_header_is_first_default_section() -> None:
    assert DEFAULT_SECTIONS[0]["section_type"] == "header"
    assert "header" in SECTION_TYPES


def test_legacy_upgrade_mapped_key_uses_builtin_theme() -> None:
    upgraded = themes.upgrade_layout_schema(
        "classic_one_page",
        {"section_order": ["summary", "education"], "typography": {"font": "serif"}},
    )
    assert themes.is_full_theme(upgraded)
    assert upgraded == themes.theme_for("classic_ats")


def test_legacy_upgrade_unknown_key_preserves_order_and_font() -> None:
    upgraded = themes.upgrade_layout_schema(
        "policy_research",
        {
            "section_order": ["summary", "education", "projects"],
            "typography": {"font": "serif"},
            "target_roles": ["Policy Intern"],
        },
    )
    assert themes.is_full_theme(upgraded)
    # Header is prepended; the legacy order is preserved after it.
    assert upgraded["order"] == ["header", "summary", "education", "projects"]
    assert upgraded["regions"]["main"] == ["header", "summary", "education", "projects"]
    assert upgraded["typography"]["bodyFont"] == "serif"
    assert upgraded["target_roles"] == ["Policy Intern"]


def test_is_full_theme_rejects_legacy_schema() -> None:
    assert not themes.is_full_theme({"section_order": ["summary"]})
    assert not themes.is_full_theme({"layout": {"kind": "nope"}, "palette": {}})
    assert not themes.is_full_theme(None)
