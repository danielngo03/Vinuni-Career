"""Sponsored-slot inventory vocabulary + seed definitions (pure; no I/O).

Each public SURFACE declares a FIXED number of sponsored slots
(``docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md`` §7.0 "Slot inventory"). Slots are
finite; organic/recommended positions are NEVER converted into paid ones silently.
The allocation engine fills only these declared paid positions, and a surface's
``max_sponsored_share`` is the additional guard the composing discovery read-model
uses so sponsored inventory can never exceed a fraction of the total surface.

The concrete slot rows live in ``ad_slots`` (seeded idempotently in migration
``0098``); this module is the legal vocabulary + the seed source of truth so the
migration and tests agree.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Surfaces                                                                     #
# --------------------------------------------------------------------------- #

SURFACE_DISCOVERY_FEED = "discovery_feed"
SURFACE_PUBLIC_JOB_BOARD = "public_job_board"
SURFACE_COMPANY_DIRECTORY = "company_directory"
SURFACE_HOMEPAGE = "homepage"
SURFACE_EVENTS = "events"

SURFACES: frozenset[str] = frozenset(
    {
        SURFACE_DISCOVERY_FEED,
        SURFACE_PUBLIC_JOB_BOARD,
        SURFACE_COMPANY_DIRECTORY,
        SURFACE_HOMEPAGE,
        SURFACE_EVENTS,
    }
)


def is_valid_surface(code: str) -> bool:
    return code in SURFACES


# --------------------------------------------------------------------------- #
# Seed slot definitions                                                        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SlotSpec:
    code: str
    surface: str
    name_vi: str
    name_en: str
    capacity: int  # number of finite sponsored positions on this surface
    max_sponsored_share: float  # 0..1 max fraction of the surface that may be paid


# One row per (surface) primary sponsored slot. Kept deliberately small +
# finite. ``max_sponsored_share`` is the ratio guard the read-model enforces.
SEED_SLOTS: tuple[SlotSpec, ...] = (
    SlotSpec(
        code="discovery_feed_sponsored",
        surface=SURFACE_DISCOVERY_FEED,
        name_vi="Vị trí tài trợ trong bảng tin khám phá",
        name_en="Discovery feed sponsored slots",
        capacity=2,
        max_sponsored_share=0.20,
    ),
    SlotSpec(
        code="public_job_board_rail",
        surface=SURFACE_PUBLIC_JOB_BOARD,
        name_vi="Banner cột phải bảng việc làm",
        name_en="Public job board right-rail banner",
        capacity=1,
        max_sponsored_share=0.15,
    ),
    SlotSpec(
        code="company_directory_banner",
        surface=SURFACE_COMPANY_DIRECTORY,
        name_vi="Banner danh bạ doanh nghiệp",
        name_en="Company directory banner",
        capacity=1,
        max_sponsored_share=0.15,
    ),
    SlotSpec(
        code="homepage_hero",
        surface=SURFACE_HOMEPAGE,
        name_vi="Banner hero trang chủ",
        name_en="Homepage hero banner",
        capacity=1,
        max_sponsored_share=0.25,
    ),
    SlotSpec(
        code="events_featured",
        surface=SURFACE_EVENTS,
        name_vi="Vị trí sự kiện nổi bật tài trợ",
        name_en="Events featured sponsored slot",
        capacity=1,
        max_sponsored_share=0.20,
    ),
)

SEED_SLOTS_BY_SURFACE: dict[str, SlotSpec] = {s.surface: s for s in SEED_SLOTS}


def slot_name(spec: SlotSpec, *, locale: str = "vi") -> str:
    return spec.name_en if locale == "en" else spec.name_vi
