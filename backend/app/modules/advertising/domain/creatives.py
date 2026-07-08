"""Campaign creative slot vocabulary, asset requirements, and review states.

(``docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md`` §5,
``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §7.)

A *creative* is the uploaded banner image attached to a sponsored placement for a
particular delivery SLOT. V1 ships the two PRIMARY public slots — the homepage
hero campaign and the right-rail banner — and reserves the inline-card and
event-banner slots (the full five-slot matrix, incl. the later email/newsletter
banner, is a documented follow-up). Each slot has desktop/mobile asset guidance
used to render the "asset requirements / missing-asset" state in the partner
upload UI and the university moderation queue.

Review is a small state machine independent of the placement lifecycle: a
creative is ``pending`` until the university approves/rejects it; only an
``approved`` creative on an ACTIVE placement is ever served publicly.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Slots                                                                         #
# --------------------------------------------------------------------------- #

SLOT_HOMEPAGE_HERO = "homepage_hero"
SLOT_RIGHT_RAIL = "right_rail"
SLOT_INLINE_CARD = "inline_card"
SLOT_EVENT_BANNER = "event_banner"

SLOTS: frozenset[str] = frozenset(
    {SLOT_HOMEPAGE_HERO, SLOT_RIGHT_RAIL, SLOT_INLINE_CARD, SLOT_EVENT_BANNER}
)

# V1 public delivery scope (hero + right rail). The other two slots accept
# uploads (so partners can stage assets) but are not yet wired to a public read.
PRIMARY_SLOTS: frozenset[str] = frozenset({SLOT_HOMEPAGE_HERO, SLOT_RIGHT_RAIL})

# Desktop/mobile asset guidance (spec §5 table) surfaced to the partner uploader
# and the university moderation "missing/incorrect asset" inspector.
SLOT_SPECS: dict[str, dict] = {
    SLOT_HOMEPAGE_HERO: {
        "desktop": "1440x360",
        "desktop_ratio": "4:1",
        "mobile": "720x720",
        "mobile_ratio": "1:1",
        "use": "top campaign carousel",
    },
    SLOT_RIGHT_RAIL: {
        "desktop": "640x800",
        "desktop_ratio": "4:5",
        "mobile": "720x720",
        "mobile_ratio": "1:1",
        "use": "homepage / job detail rail",
    },
    SLOT_INLINE_CARD: {
        "desktop": "1200x630",
        "desktop_ratio": "1.91:1",
        "mobile": "720x900",
        "mobile_ratio": "4:5",
        "use": "between job/event rails",
    },
    SLOT_EVENT_BANNER: {
        "desktop": "1440x480",
        "desktop_ratio": "3:1",
        "mobile": "720x900",
        "mobile_ratio": "4:5",
        "use": "events / career explore",
    },
}

_SLOT_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        SLOT_HOMEPAGE_HERO: "Banner trang chủ (hero)",
        SLOT_RIGHT_RAIL: "Banner cột phải",
        SLOT_INLINE_CARD: "Banner chèn giữa",
        SLOT_EVENT_BANNER: "Banner sự kiện",
    },
    "en": {
        SLOT_HOMEPAGE_HERO: "Homepage hero",
        SLOT_RIGHT_RAIL: "Right-rail banner",
        SLOT_INLINE_CARD: "Inline card banner",
        SLOT_EVENT_BANNER: "Event banner",
    },
}


def is_valid_slot(code: str) -> bool:
    return code in SLOTS


def slot_label(code: str, *, locale: str = "vi") -> str:
    table = _SLOT_LABELS.get(locale, _SLOT_LABELS["vi"])
    return table.get(code, code)


def slot_spec(code: str) -> dict:
    return SLOT_SPECS.get(code, {})


# --------------------------------------------------------------------------- #
# Creative moderation (review) states                                          #
# --------------------------------------------------------------------------- #

CREATIVE_PENDING = "pending"
CREATIVE_APPROVED = "approved"
CREATIVE_REJECTED = "rejected"

CREATIVE_STATUSES: frozenset[str] = frozenset(
    {CREATIVE_PENDING, CREATIVE_APPROVED, CREATIVE_REJECTED}
)

_CREATIVE_STATUS_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        CREATIVE_PENDING: "Chờ duyệt",
        CREATIVE_APPROVED: "Đã duyệt",
        CREATIVE_REJECTED: "Bị từ chối",
    },
    "en": {
        CREATIVE_PENDING: "Pending review",
        CREATIVE_APPROVED: "Approved",
        CREATIVE_REJECTED: "Rejected",
    },
}


def creative_status_label(code: str, *, locale: str = "vi") -> str:
    table = _CREATIVE_STATUS_LABELS.get(locale, _CREATIVE_STATUS_LABELS["vi"])
    return table.get(code, code)
