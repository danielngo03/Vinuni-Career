"""Inventory-class taxonomy + polished bilingual disclosure labels.

(``docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md`` §4,
``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §7.)

Two related concepts live here:

- INVENTORY CLASSES describe how a piece of marketplace inventory was selected:
  ``organic`` (normal jobs/events/companies), ``recommended`` (personalized by
  search/session/profile/CV signals), and the four CAMPAIGN classes a placement
  can carry — ``university_curated``, ``strategic_partner``, ``paid_sponsored``,
  ``featured``.
- DISCLOSURE_CLASS is the subset of inventory classes a *placement* stores and
  the public sees. Only ``paid_sponsored`` is PAID inventory, so its disclosure
  is NON-REMOVABLE; ``university_curated`` / ``strategic_partner`` / ``featured``
  are truthful editorial/partnership labels and must NEVER be presented as paid.

Public labels are polished + bilingual so the marketplace reads as an institution,
not a pay-to-win billboard. Raw enum codes never reach end users.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Inventory classes (§4)                                                       #
# --------------------------------------------------------------------------- #

ORGANIC = "organic"
RECOMMENDED = "recommended"
UNIVERSITY_CURATED = "university_curated"
STRATEGIC_PARTNER = "strategic_partner"
PAID_SPONSORED = "paid_sponsored"
FEATURED = "featured"

INVENTORY_CLASSES: frozenset[str] = frozenset(
    {
        ORGANIC,
        RECOMMENDED,
        UNIVERSITY_CURATED,
        STRATEGIC_PARTNER,
        PAID_SPONSORED,
        FEATURED,
    }
)

# The classes a placement may carry as its public ``disclosure_class``.
DISCLOSURE_CLASSES: frozenset[str] = frozenset(
    {PAID_SPONSORED, UNIVERSITY_CURATED, STRATEGIC_PARTNER, FEATURED}
)

# Partner placements default to paid; only the university may relabel to a
# non-paid editorial/partnership class within compliance rules.
DEFAULT_DISCLOSURE_CLASS = PAID_SPONSORED

# The only PAID class — its disclosure is mandatory and non-removable.
PAID_DISCLOSURE_CLASSES: frozenset[str] = frozenset({PAID_SPONSORED})


# --------------------------------------------------------------------------- #
# Polished bilingual labels                                                    #
# --------------------------------------------------------------------------- #

_DISCLOSURE_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        PAID_SPONSORED: "Đối tác tài trợ",
        UNIVERSITY_CURATED: "VinUni tuyển chọn",
        STRATEGIC_PARTNER: "Đối tác chiến lược",
        FEATURED: "Nổi bật",
    },
    "en": {
        PAID_SPONSORED: "Partner-sponsored",
        UNIVERSITY_CURATED: "Curated by VinUni",
        STRATEGIC_PARTNER: "Strategic partner",
        FEATURED: "Featured",
    },
}


def is_valid_disclosure_class(code: str) -> bool:
    """True if ``code`` is a class a placement may carry publicly."""

    return code in DISCLOSURE_CLASSES


def is_paid(code: str) -> bool:
    """True only for PAID inventory (``paid_sponsored``)."""

    return code in PAID_DISCLOSURE_CLASSES


def disclosure_class_label(code: str, *, locale: str = "vi") -> str:
    """The polished public label for a disclosure class (never a raw code)."""

    table = _DISCLOSURE_LABELS.get(locale, _DISCLOSURE_LABELS["vi"])
    return table.get(code, table.get(PAID_SPONSORED, code))


def disclosure_payload(code: str, *, locale: str = "vi") -> dict:
    """Public disclosure descriptor for a placement's class.

    ``is_removable`` is ``False`` for paid inventory (the disclosure must always
    show) and ``True`` for editorial/partnership classes (still shown, but they
    are truthfully not paid). ``is_sponsored`` is kept for backward compatibility
    with existing sponsored-banner/discovery consumers and is ``True`` only when
    the class is paid.
    """

    paid = is_paid(code)
    return {
        "class": code,
        "label": disclosure_class_label(code, locale=locale),
        "is_paid": paid,
        "is_removable": not paid,
        "is_sponsored": paid,
    }
