"""DEV-ONLY demo marketplace seed (synthetic, idempotent).

⚠ LOCAL/DEV ONLY. This script inserts **synthetic, clearly-fictional** partner
companies, job postings, and **events** so the public career gateway
(``/marketplace`` + ``/companies`` + ``/events``) can be honestly visually
reviewed instead of showing a near-empty directory. It is never meant to run
against staging/production and refuses to do so (see
:func:`_assert_dev_environment`).

Honesty / safety guarantees (``docs/DESIGN.md`` "seeded dev data only when
explicitly marked", ``docs/ENVIRONMENT.md`` secret policy):

- Every seeded row is tagged with the ``demo-`` slug prefix and the poster user
  uses a fixed ``@demo.local`` email, so ``--wipe`` removes **only** demo rows
  and never touches real/test accounts or real seed data.
- Company names are obviously fictional ("… (Demo)", "Demo …", "VinUni Partner
  Labs") and never impersonate a real company. Logos are obviously-synthetic
  placeholder marks (a solid brand-color square with the org initials + a "DEMO"
  tag), not real brand art.
- No network calls and no secrets. Logo bytes are generated locally and stored
  through the same storage backend + key helper the real logo pipeline uses
  (``organization.infrastructure.logo_media`` + ``documents.infrastructure.
  storage``), so the public ``GET /companies/{slug}/logo`` route serves them.
- Jobs reach ``active`` through the documented lifecycle fields (draft -> submit
  -> approve) using :mod:`opportunities.domain.lifecycle`, not a raw status hack.
- Events reach ``published`` the same way via
  :mod:`opportunities.domain.event_lifecycle` (partner submit -> university
  approve), setting exactly the fields the real services set. One event has
  ``capacity=2`` filled by two synthetic demo students so a 3rd UI registration
  exercises the waitlist path; a couple are ``is_sponsored``/``is_featured`` so
  the marketplace sponsored/featured event strips populate.

Run from ``backend/``::

    uv run python -m scripts.seed_demo_marketplace          # upsert demo data
    uv run python -m scripts.seed_demo_marketplace --wipe    # remove demo data

Idempotent: safe to run repeatedly (upsert by stable ``slug`` / email natural
key — never duplicates).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.metadata import import_all_models
from app.modules.auth.application.context import RequestContext
from app.modules.auth.infrastructure.passwords import hash_password
from app.modules.documents.infrastructure import storage as storage_backend
from app.modules.messaging.application import message_service, thread_service
from app.modules.messaging.domain import rules as messaging_rules
from app.modules.messaging.domain.models import (
    Message,
    MessageThread,
    MessageThreadParticipant,
)
from app.modules.opportunities.domain import event_lifecycle, lifecycle
from app.modules.opportunities.domain.event_models import Event, EventRegistration
from app.modules.opportunities.domain.models import Job
from app.modules.organization.domain.models import Membership, Organization
from app.modules.organization.infrastructure import logo_media
from app.modules.recruitment.application import (
    decision_service,
    interview_service,
    offer_service,
    scorecard_service,
    stage_service,
)
from app.modules.recruitment.domain import lifecycle as rec_lifecycle
from app.modules.recruitment.domain import offer as offer_domain
from app.modules.recruitment.domain import pipeline as rec_pipeline
from app.modules.recruitment.domain import scorecard as scorecard_domain
from app.modules.recruitment.domain.models import (
    Application,
    CandidateStage,
    Interview,
    InterviewAssignee,
    Offer,
    PipelineStage,
    PipelineTemplate,
    Scorecard,
    ScorecardScore,
)
from app.modules.users.domain.models import Identity, User
from app.shared.permissions import Principal
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

# --------------------------------------------------------------------------- #
# Demo markers (the ONLY rows --wipe ever touches)                            #
# --------------------------------------------------------------------------- #

DEMO_SLUG_PREFIX = "demo-"
DEMO_POSTER_EMAIL = "demo-marketplace-seed@demo.local"
DEMO_POSTER_NAME = "Demo Marketplace Seed (synthetic)"

# All demo users share the ``demo-…@demo.local`` shape so ``--wipe`` removes only
# synthetic accounts (the poster + the demo students used to fill an event's
# capacity for the waitlist demo) and never touches real/test users.
DEMO_USER_EMAIL_LIKE = "demo-%@demo.local"
# Synthetic students whose confirmed registrations make the capacity-2 event full
# so a real student's 3rd registration in the UI exercises the waitlist path.
_DEMO_STUDENTS: list[dict] = [
    {"email": "demo-student-1@demo.local", "name": "Demo Student One (synthetic)"},
    {"email": "demo-student-2@demo.local", "name": "Demo Student Two (synthetic)"},
]

# Environments where seeding synthetic data is allowed.
_DEV_ENVIRONMENTS = frozenset({"local", "dev", "development", "test", "testing"})

# --------------------------------------------------------------------------- #
# Recruitment pipeline progression markers (dev browser-verify fixture)        #
# --------------------------------------------------------------------------- #
#
# Progresses ONE synthetic candidate through the SHIPPED recruitment services so
# the partner scorecard/interview/offer panels + the student offer card render
# real data for a local browser review (instead of empty panels). Everything is
# driven through the REAL service entry points (review -> advance -> scorecard ->
# interview -> offer send), never a raw status hack — mirroring how the job/event
# seed reaches its states via the documented lifecycle.
#
# Target: the existing partner job "Backend Engineer Intern" (slug
# ``backend-engineer-intern``) so the panels surface under the real partner login
# that owns it. The job/org/partner are DISCOVERED at runtime (they are created by
# the recruitment E2E flows, not this seed); when absent the progression is
# SKIPPED and the marketplace seed still succeeds.
#
# Real-data safety: this never mutates the partner org, the job content, or any
# real application. It creates a DEDICATED demo student + a demo application
# (tagged by a stable ``idempotency_key``) and progresses THAT. The only shared-
# config touch is flipping the candidate's CURRENT pipeline stage to
# ``required_action='scorecard'`` so the scorecard advance-gate is visible/met;
# ``--wipe`` restores it to ``manual`` and removes the demo application + its
# scorecards/interviews/offers/candidate_stages.
DEMO_TARGET_JOB_SLUG = "backend-engineer-intern"
DEMO_CANDIDATE_EMAIL = "demo-recruit-candidate@demo.local"
DEMO_CANDIDATE_NAME = "Demo Recruit Candidate (synthetic)"
# DEV-ONLY known login so the offer card can be browser-verified as this student.
DEMO_CANDIDATE_PASSWORD = "DemoCandidate#2026"  # noqa: S105 - dev seed, local only
DEMO_APPLICATION_IDEMPOTENCY = "demo-progression:backend-engineer-intern"
# Anchor the scorecard + interview + offer on the Interview stage (sort_order 2 of
# the default ladder). Chosen so the shared ``required_action`` flip does NOT alter
# the advance gate of a real candidate sitting at stage 1 (Screening).
DEMO_PROGRESSION_STAGE_ORDER = 2

# --------------------------------------------------------------------------- #
# Messaging demo markers (dev browser-verify fixture)                          #
# --------------------------------------------------------------------------- #
#
# Seeds a few institutional MESSAGING threads through the SHIPPED messaging
# services (``thread_service.create_thread`` + ``message_service.send_message``)
# so the inbox/thread UI can be browser-verified per persona instead of an empty
# inbox. Everything is driven through the REAL service entry points so the
# permission matrix, anonymity masking, the one-thread-per-application dedupe, and
# the per-message ``client_dedupe_key`` idempotency are all honored — never a raw
# insert.
#
# Real-data safety / wipe contract: every seeded thread carries a stable subject
# starting with ``DEMO_THREAD_SUBJECT_PREFIX``; ``--wipe`` removes ONLY threads
# (and their messages + participants) matching that prefix — never a real thread.
# Recipients may be real test accounts (e.g. ``browser_smoke_001``); only the
# synthetic DEMO thread we attach to them is removable, the accounts are untouched.
DEMO_THREAD_SUBJECT_PREFIX = "[DEMO] "
_MSG_SUBJECT_PARTNER_CANDIDATE = (
    f"{DEMO_THREAD_SUBJECT_PREFIX}Trao đổi ứng tuyển Backend Engineer Intern"
)
_MSG_SUBJECT_UNI_STUDENT = (
    f"{DEMO_THREAD_SUBJECT_PREFIX}Hỗ trợ hướng nghiệp từ VinUni"
)
_MSG_SUBJECT_UNI_PARTNER = (
    f"{DEMO_THREAD_SUBJECT_PREFIX}Trao đổi hợp tác tuyển dụng"
)
# A real test student (NOT a demo-…@demo.local account) so the browser_smoke login
# has a university thread in its inbox. Discovered by email; skipped if absent.
DEMO_MSG_STUDENT_EMAIL = "browser_smoke_001@vinuni.edu.vn"

# Canonical industry strings the public companies filter / mega-menu deep-links
# use (frontend ``company-mega-menu.tsx`` INDUSTRIES.query). Demo industries MUST
# match these exactly (note the en-dash in "Tài chính – Ngân hàng") so the
# ``?industry=`` filter returns the seeded companies.
IND_IT = "Công nghệ thông tin"
IND_FINANCE = "Tài chính – Ngân hàng"
IND_CONSULTING = "Tư vấn & Kiểm toán"
IND_MANUFACTURING = "Sản xuất & Kỹ thuật"
IND_HEALTHCARE = "Y tế & Dược phẩm"
IND_EDUCATION = "Giáo dục & Nghiên cứu"

# Canonical company-size buckets (frontend ``validation/organization.ts``).
SIZE_S = "11-50"
SIZE_M = "50-200"
SIZE_L = "200-1000"
SIZE_XL = "1000+"


# --------------------------------------------------------------------------- #
# Synthetic organizations (clearly fictional — never real companies)          #
# --------------------------------------------------------------------------- #

_ORG_SEED: list[dict] = [
    {
        "key": "demotech",
        "display_name": "Demo Tech Vietnam",
        "industry": IND_IT,
        "company_size": SIZE_L,
        "city": "Hà Nội",
        "founded_year": 2014,
        "is_verified": True,
        "trust_level": "strategic",
        "color": (37, 99, 235),  # blue
        "with_logo": True,
        "description": "Demo synthetic employer for local UI review. Builds web "
        "and mobile products. Not a real company.",
    },
    {
        "key": "hanoifin",
        "display_name": "Hanoi FinServe (Demo)",
        "industry": IND_FINANCE,
        "company_size": SIZE_XL,
        "city": "Hà Nội",
        "founded_year": 2009,
        "is_verified": True,
        "trust_level": "verified",
        "color": (16, 122, 87),  # green
        "with_logo": True,
        "description": "Synthetic demo financial-services employer used only for "
        "local development previews.",
    },
    {
        "key": "vinunilabs",
        "display_name": "VinUni Partner Labs",
        "industry": IND_IT,
        "company_size": SIZE_M,
        "city": "Hà Nội",
        "founded_year": 2020,
        "is_verified": True,
        "trust_level": "strategic",
        "color": (124, 58, 237),  # violet
        "with_logo": True,
        "description": "Fictional applied-research lab partner. Demo data for "
        "local visual review only.",
    },
    {
        "key": "saigonconsult",
        "display_name": "Saigon Advisory Group (Demo)",
        "industry": IND_CONSULTING,
        "company_size": SIZE_M,
        "city": "TP. Hồ Chí Minh",
        "founded_year": 2012,
        "is_verified": True,
        "trust_level": "verified",
        "color": (180, 83, 9),  # amber
        "with_logo": True,
        "description": "Synthetic management-consulting demo employer. Not a real "
        "firm.",
    },
    {
        "key": "deltahealth",
        "display_name": "Delta HealthTech (Demo)",
        "industry": IND_HEALTHCARE,
        "company_size": SIZE_M,
        "city": "Đà Nẵng",
        "founded_year": 2017,
        "is_verified": False,
        "trust_level": "standard",
        "color": (8, 145, 178),  # cyan
        "with_logo": True,
        "description": "Fictional digital-health employer used for local demo "
        "previews only.",
    },
    {
        "key": "norindustrial",
        "display_name": "Northern Industrial Demo Co.",
        "industry": IND_MANUFACTURING,
        "company_size": SIZE_XL,
        "city": "Hải Phòng",
        "founded_year": 2005,
        "is_verified": True,
        "trust_level": "verified",
        "color": (71, 85, 105),  # slate
        "with_logo": True,
        "description": "Synthetic manufacturing & engineering demo employer. Not a "
        "real company.",
    },
    {
        "key": "brightedu",
        "display_name": "BrightPath Education (Demo)",
        "industry": IND_EDUCATION,
        "company_size": SIZE_S,
        "city": "Hà Nội",
        "founded_year": 2018,
        "is_verified": False,
        "trust_level": "standard",
        "color": (219, 39, 119),  # pink
        "with_logo": True,
        "description": "Fictional education & research demo employer for local UI "
        "review.",
    },
    {
        "key": "mekongdata",
        "display_name": "Mekong Data Works (Demo)",
        "industry": IND_IT,
        "company_size": SIZE_S,
        "city": "Cần Thơ",
        "founded_year": 2021,
        "is_verified": False,
        "trust_level": "standard",
        "color": (5, 150, 105),  # emerald
        "with_logo": False,  # logo-less -> exercises initials fallback
        "description": "Synthetic data-engineering demo studio. Not a real "
        "company.",
    },
    {
        "key": "capitalcap",
        "display_name": "Capital Bridge Partners (Demo)",
        "industry": IND_FINANCE,
        "company_size": SIZE_M,
        "city": "Hà Nội",
        "founded_year": 2011,
        "is_verified": True,
        "trust_level": "verified",
        "color": (15, 118, 110),  # teal
        "with_logo": False,  # logo-less
        "description": "Fictional investment demo employer used only for local "
        "previews.",
    },
    {
        "key": "redrivermed",
        "display_name": "Red River MedLabs (Demo)",
        "industry": IND_HEALTHCARE,
        "company_size": SIZE_S,
        "city": "Hà Nội",
        "founded_year": 2019,
        "is_verified": False,
        "trust_level": "standard",
        "color": (190, 18, 60),  # rose
        "with_logo": False,  # logo-less
        "description": "Synthetic biotech demo employer. Not a real company.",
    },
    {
        "key": "annamconsult",
        "display_name": "Annam Audit & Advisory (Demo)",
        "industry": IND_CONSULTING,
        "company_size": SIZE_L,
        "city": "TP. Hồ Chí Minh",
        "founded_year": 2008,
        "is_verified": True,
        "trust_level": "verified",
        "color": (101, 116, 205),  # indigo
        "with_logo": False,  # logo-less
        "description": "Fictional audit & advisory demo firm for local UI review.",
    },
    {
        "key": "phoenixmfg",
        "display_name": "Phoenix Precision Mfg (Demo)",
        "industry": IND_MANUFACTURING,
        "company_size": SIZE_L,
        "city": "Bắc Ninh",
        "founded_year": 2007,
        "is_verified": False,
        "trust_level": "standard",
        "color": (217, 70, 39),  # orange-red
        "with_logo": False,  # logo-less
        "description": "Synthetic precision-manufacturing demo employer. Not real.",
    },
]


# Role templates spread across orgs (title, employment, location, skills).
_ROLE_TEMPLATES: list[dict] = [
    {
        "title": "Software Engineer (Backend)",
        "employment_type": "full_time",
        "location_type": "hybrid",
        "skills": ["python", "fastapi", "postgresql"],
        "preferred": ["docker", "redis"],
        "salary": (25_000_000, 45_000_000),
    },
    {
        "title": "Frontend Engineer Intern",
        "employment_type": "internship",
        "location_type": "onsite",
        "skills": ["javascript", "react", "typescript"],
        "preferred": ["nextjs", "tailwind"],
        "salary": None,
    },
    {
        "title": "Data Analyst",
        "employment_type": "full_time",
        "location_type": "remote",
        "skills": ["sql", "python", "excel"],
        "preferred": ["powerbi", "statistics"],
        "salary": (18_000_000, 32_000_000),
    },
    {
        "title": "Financial Analyst",
        "employment_type": "full_time",
        "location_type": "onsite",
        "skills": ["financial-modeling", "excel", "accounting"],
        "preferred": ["cfa", "valuation"],
        "salary": (20_000_000, 38_000_000),
    },
    {
        "title": "Management Consulting Associate",
        "employment_type": "full_time",
        "location_type": "hybrid",
        "skills": ["problem-solving", "powerpoint", "research"],
        "preferred": ["sql", "strategy"],
        "salary": (22_000_000, 40_000_000),
    },
    {
        "title": "Mechanical Engineer",
        "employment_type": "full_time",
        "location_type": "onsite",
        "skills": ["autocad", "solidworks", "manufacturing"],
        "preferred": ["lean", "six-sigma"],
        "salary": (16_000_000, 30_000_000),
    },
    {
        "title": "Clinical Data Coordinator",
        "employment_type": "contract",
        "location_type": "onsite",
        "skills": ["data-entry", "clinical-research", "attention-to-detail"],
        "preferred": ["redcap", "biostatistics"],
        "salary": (15_000_000, 24_000_000),
    },
    {
        "title": "Academic Program Coordinator",
        "employment_type": "part_time",
        "location_type": "hybrid",
        "skills": ["communication", "organization", "english"],
        "preferred": ["event-planning", "lms"],
        "salary": None,
    },
    {
        "title": "Product Manager (Associate)",
        "employment_type": "full_time",
        "location_type": "hybrid",
        "skills": ["product-discovery", "roadmapping", "analytics"],
        "preferred": ["figma", "sql"],
        "salary": (28_000_000, 50_000_000),
    },
    {
        "title": "Marketing Intern",
        "employment_type": "internship",
        "location_type": "remote",
        "skills": ["content-writing", "social-media", "canva"],
        "preferred": ["seo", "english"],
        "salary": None,
    },
]


# --------------------------------------------------------------------------- #
# Synthetic events (ADR-0008) — spread across the demo orgs                    #
# --------------------------------------------------------------------------- #
# Every event is partner-owned (demo orgs are ``partner`` type) and reaches
# ``published`` through the documented partner path (submit -> pending_review ->
# university approve) by setting exactly the fields ``event_service.submit_event``
# + ``event_moderation_service.approve_event`` set — never a raw status hack
# (mirrors how the job seed reaches ``active`` via :func:`_activate`).
#
# ``start_days`` is the offset from "now" so every event is upcoming/visible;
# ``registration_closes_at`` is set one day before ``starts_at`` by the upsert.
# ``capacity = None`` means unlimited. ``org_key`` ties the event to a demo org.
# V1 (migration 0016) has no ``online_link``/``meeting_link`` column (deferred,
# ADR-0008 §9): online events simply carry no venue; onsite/hybrid carry a venue.
_EVENT_SEED: list[dict] = [
    {
        "key": "career-day-2026",
        "org_key": "demotech",
        "title": "VinUni Career Day 2026 (Demo)",
        "event_type": "career_fair",
        "format": "onsite",
        "venue_name": "VinUni Campus Hall A",
        "venue_address": "Vinhomes Ocean Park, Gia Lâm, Hà Nội",
        "start_days": 21,
        "duration_hours": 6,
        "capacity": None,  # unlimited
        "is_sponsored": True,
        "is_featured": True,
    },
    {
        "key": "fintech-workshop",
        "org_key": "hanoifin",
        "title": "Hands-on FinTech Modelling Workshop (Demo)",
        "event_type": "workshop",
        "format": "online",
        "venue_name": None,
        "venue_address": None,
        "start_days": 10,
        "duration_hours": 3,
        "capacity": 50,
        "is_sponsored": False,
        "is_featured": False,
    },
    {
        "key": "labs-info-session",
        "org_key": "vinunilabs",
        "title": "VinUni Partner Labs Info Session (Demo)",
        "event_type": "info_session",
        "format": "hybrid",
        "venue_name": "Innovation Lab, Building B2",
        "venue_address": "Vinhomes Ocean Park, Gia Lâm, Hà Nội",
        "start_days": 14,
        "duration_hours": 2,
        "capacity": 100,
        "is_sponsored": True,
        "is_featured": False,
    },
    {
        "key": "consulting-networking",
        "org_key": "saigonconsult",
        "title": "Consulting Careers Networking Night (Demo)",
        "event_type": "networking",
        "format": "onsite",
        "venue_name": "Saigon Advisory Rooftop Lounge",
        "venue_address": "Quận 1, TP. Hồ Chí Minh",
        "start_days": 28,
        "duration_hours": 3,
        "capacity": 30,
        "is_sponsored": False,
        "is_featured": True,
    },
    {
        # The waitlist demo: capacity 2 + 2 confirmed synthetic students -> the
        # event is full, so a 3rd registration in the UI is waitlisted.
        "key": "health-masterclass",
        "org_key": "deltahealth",
        "title": "Digital Health Product Masterclass (Demo)",
        "event_type": "workshop",
        "format": "onsite",
        "venue_name": "Delta HealthTech Demo Room",
        "venue_address": "Hải Châu, Đà Nẵng",
        "start_days": 18,
        "duration_hours": 4,
        "capacity": 2,
        "is_sponsored": False,
        "is_featured": False,
        "fill_to_capacity": True,
    },
    {
        "key": "industrial-webinar",
        "org_key": "norindustrial",
        "title": "Smart Manufacturing Careers Webinar (Demo)",
        "event_type": "webinar",
        "format": "online",
        "venue_name": None,
        "venue_address": None,
        "start_days": 7,
        "duration_hours": 2,
        "capacity": None,  # unlimited
        "is_sponsored": False,
        "is_featured": False,
    },
    {
        "key": "edu-career-fair",
        "org_key": "brightedu",
        "title": "EdTech & Research Career Fair (Demo)",
        "event_type": "career_fair",
        "format": "hybrid",
        "venue_name": "BrightPath Learning Center",
        "venue_address": "Cầu Giấy, Hà Nội",
        "start_days": 35,
        "duration_hours": 5,
        "capacity": 200,
        "is_sponsored": False,
        "is_featured": False,
    },
    {
        "key": "data-info-session",
        "org_key": "mekongdata",
        "title": "Data Engineering Intern Info Session (Demo)",
        "event_type": "info_session",
        "format": "onsite",
        "venue_name": "Mekong Data Works Studio",
        "venue_address": "Ninh Kiều, Cần Thơ",
        "start_days": 12,
        "duration_hours": 2,
        "capacity": 40,
        "is_sponsored": False,
        "is_featured": False,
    },
]


# --------------------------------------------------------------------------- #
# Synthetic placeholder logo generation (obviously not real brand art)        #
# --------------------------------------------------------------------------- #


def _initials(display_name: str) -> str:
    """First letters of up to two meaningful words (skips the '(Demo)' tag)."""

    words = [
        w for w in display_name.replace("(", " ").replace(")", " ").split()
        if w and w.lower() != "demo"
    ]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "VN"


def _placeholder_logo_png(display_name: str, color: tuple[int, int, int]) -> bytes:
    """A 256x256 PNG: solid brand color, white initials, a small 'DEMO' tag.

    Uses Pillow (already a project dependency) to draw text; falls back to a
    flat solid-color PNG written with the stdlib only if Pillow is unavailable,
    so the logo pipeline is still exercised. Always a valid PNG (magic-byte
    validated by ``logo_media.validate_logo``).
    """

    try:
        from io import BytesIO

        from PIL import Image, ImageDraw, ImageFont

        size = 256
        img = Image.new("RGB", (size, size), color=color)
        draw = ImageDraw.Draw(img)

        initials = _initials(display_name)
        font = ImageFont.load_default(size=120)
        bbox = draw.textbbox((0, 0), initials, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - 10),
            initials,
            fill=(255, 255, 255),
            font=font,
        )

        # Obvious "DEMO" placeholder tag so the mark can never be mistaken for
        # real brand art.
        tag_font = ImageFont.load_default(size=28)
        tag = "DEMO"
        tbox = draw.textbbox((0, 0), tag, font=tag_font)
        tw2 = tbox[2] - tbox[0]
        draw.text(
            ((size - tw2) / 2 - tbox[0], size - 56),
            tag,
            fill=(255, 255, 255),
            font=tag_font,
        )

        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - fall back to a dependency-free solid PNG
        return _solid_png(color)


def _solid_png(color: tuple[int, int, int], size: int = 256) -> bytes:
    """A minimal valid solid-color PNG using only the stdlib (no Pillow)."""

    import struct
    import zlib

    r, g, b = color
    row = bytes([0]) + bytes([r, g, b]) * size  # filter byte 0 + RGB pixels
    raw = row * size

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(raw, 9)
    return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _assert_dev_environment() -> None:
    """Refuse to run outside a local/dev environment."""

    env = get_settings().app_env.strip().lower()
    if env not in _DEV_ENVIRONMENTS:
        print(
            f"\n✋ REFUSING TO RUN: app_env={env!r} is not a dev environment.\n"
            f"   The demo marketplace seed is LOCAL/DEV ONLY "
            f"(allowed: {sorted(_DEV_ENVIRONMENTS)}).\n",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _banner(action: str) -> None:
    env = get_settings().app_env
    print("=" * 70)
    print("⚠  DEV DEMO SEED — local only, synthetic data")
    print(f"   action={action}  app_env={env}")
    print("   All rows are fictional and tagged 'demo-'. Never run on prod.")
    print("=" * 70)


async def _ensure_poster(session: AsyncSession) -> User:
    """Upsert the synthetic poster user that owns the demo jobs."""

    user = (
        await session.execute(select(User).where(User.email == DEMO_POSTER_EMAIL))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=DEMO_POSTER_EMAIL,
            full_name=DEMO_POSTER_NAME,
            is_active=True,
            email_verified_at=datetime.now(tz=UTC),
        )
        session.add(user)
        await session.flush()
    return user


async def _ensure_students(session: AsyncSession) -> list[User]:
    """Upsert the synthetic demo students whose confirmed regs fill an event.

    Each gets a primary ``student`` identity so they are legitimate demo students
    (not just bare login rows). Idempotent by email.
    """

    students: list[User] = []
    for spec in _DEMO_STUDENTS:
        user = (
            await session.execute(select(User).where(User.email == spec["email"]))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=spec["email"],
                full_name=spec["name"],
                is_active=True,
                email_verified_at=datetime.now(tz=UTC),
            )
            session.add(user)
            await session.flush()
            session.add(
                Identity(user_id=user.id, persona="student", is_primary=True)
            )
            await session.flush()
        students.append(user)
    return students


def _apply_logo(org: Organization, *, display_name: str, color: tuple) -> None:
    """Generate + store a placeholder logo through the real storage/key pipeline."""

    storage = storage_backend.get_storage()
    if org.logo_path and storage.exists(org.logo_path):
        return  # idempotent: keep the existing logo
    data = _placeholder_logo_png(display_name, color)
    logo_media.validate_logo(  # same gate the real upload path uses
        data, "image/png", max_bytes=get_settings().org_logo_max_bytes
    )
    asset_id = uuid.uuid4()
    key = logo_media.storage_key_for(org.id, asset_id, ".png")
    storage.save(key, data)
    org.logo_path = key


async def _upsert_org(session: AsyncSession, spec: dict) -> Organization:
    """Upsert one demo organization by its stable ``demo-`` slug."""

    slug = f"{DEMO_SLUG_PREFIX}{spec['key']}"
    org = (
        await session.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()
    now = datetime.now(tz=UTC)
    if org is None:
        org = Organization(slug=slug, org_type="partner")
        session.add(org)
    org.display_name = spec["display_name"]
    org.description = spec["description"]
    org.industry = spec["industry"]
    org.company_size = spec["company_size"]
    org.headquarters_city = spec["city"]
    org.founded_year = spec["founded_year"]
    org.website_url = f"https://demo.local/companies/{spec['key']}"
    org.status = "active"  # active partner -> publicly listable
    org.is_verified = spec["is_verified"]
    org.verified_at = now if spec["is_verified"] else None
    org.trust_level = spec["trust_level"]
    org.subscription_tier = "free"
    await session.flush()

    if spec["with_logo"]:
        _apply_logo(org, display_name=spec["display_name"], color=spec["color"])
        await session.flush()
    return org


def _activate(job: Job, *, poster_id: uuid.UUID, now: datetime) -> None:
    """Drive a draft job to ``active`` via the documented lifecycle transitions.

    Mirrors ``moderation_service.approve_job`` field-setting (status=active,
    moderation=approved, published_at) rather than hard-coding a status string,
    and asserts each transition is legal via :mod:`lifecycle`.
    """

    assert lifecycle.can_transition("submit", job.status)
    job.status = lifecycle.target_state("submit")  # -> pending_review
    job.submitted_at = now
    assert lifecycle.can_transition("approve", job.status)
    job.status = lifecycle.target_state("approve")  # -> active
    job.moderation_status = lifecycle.MOD_APPROVED
    job.approved_by = poster_id
    job.approved_at = now
    job.published_at = now


async def _upsert_job(
    session: AsyncSession,
    *,
    org: Organization,
    poster: User,
    index: int,
    template: dict,
    is_sponsored: bool,
    is_featured: bool,
    deadline: datetime | None,
) -> Job:
    """Upsert one demo job by its stable ``demo-`` slug."""

    slug = f"{DEMO_SLUG_PREFIX}job-{org.slug.removeprefix(DEMO_SLUG_PREFIX)}-{index}"
    now = datetime.now(tz=UTC)
    job = (
        await session.execute(select(Job).where(Job.slug == slug))
    ).scalar_one_or_none()
    if job is None:
        job = Job(
            slug=slug,
            org_id=org.id,
            posted_by=poster.id,
            status=lifecycle.DRAFT,
            moderation_status=lifecycle.MOD_PENDING,
        )
        session.add(job)

    salary = template["salary"]
    job.org_id = org.id
    job.posted_by = poster.id
    job.title = f"{template['title']} — {org.display_name}"
    job.description = (
        f"[DEMO] Synthetic posting for local UI review at {org.display_name}. "
        f"This is not a real job. Role: {template['title']}."
    )
    job.requirements = "[DEMO] Synthetic requirements for local preview only."
    job.benefits = "[DEMO] Synthetic benefits for local preview only."
    job.employment_type = template["employment_type"]
    job.location_type = template["location_type"]
    job.location_city = org.headquarters_city
    job.location_country = "Vietnam"
    job.required_skills = list(template["skills"])
    job.preferred_skills = list(template["preferred"])
    job.salary_min = salary[0] if salary else None
    job.salary_max = salary[1] if salary else None
    job.salary_currency = "VND"
    job.salary_is_disclosed = salary is not None
    job.headcount = 1 + (index % 3)
    job.application_deadline = deadline
    job.visibility = lifecycle.PUBLIC
    job.is_sponsored = is_sponsored
    job.is_featured = is_featured
    # Reset to draft then drive through the lifecycle so re-runs stay consistent.
    job.status = lifecycle.DRAFT
    job.moderation_status = lifecycle.MOD_PENDING
    _activate(job, poster_id=poster.id, now=now)
    await session.flush()
    return job


# --------------------------------------------------------------------------- #
# Events                                                                       #
# --------------------------------------------------------------------------- #


def _publish_event(event: Event, *, approver_id: uuid.UUID, now: datetime) -> None:
    """Drive a draft event to ``published`` via the documented partner path.

    Sets exactly the fields the real transitions set — ``submit`` (partner ->
    ``pending_review``) then university ``approve`` (-> ``published`` + approved
    moderation) — asserting each transition is legal via
    :mod:`event_lifecycle`, rather than hard-coding a status string. Mirrors the
    job seed's :func:`_activate`.
    """

    assert event_lifecycle.can_transition("submit", event.status)
    event.status = event_lifecycle.PENDING_REVIEW  # partner submit target
    event.submitted_at = now
    assert event_lifecycle.can_transition("approve", event.status)
    event.status = event_lifecycle.target_state("approve")  # -> published
    event.moderation_status = event_lifecycle.MOD_APPROVED
    event.moderation_note = None
    event.approved_by = approver_id
    event.approved_at = now
    event.published_at = now


async def _upsert_event(
    session: AsyncSession,
    *,
    org: Organization,
    creator: User,
    spec: dict,
) -> Event:
    """Upsert one demo event by its stable ``demo-event-`` slug; drive to published."""

    slug = f"{DEMO_SLUG_PREFIX}event-{spec['key']}"
    now = datetime.now(tz=UTC)
    starts_at = now + timedelta(days=spec["start_days"])
    ends_at = starts_at + timedelta(hours=spec["duration_hours"])
    closes_at = starts_at - timedelta(days=1)  # deadline before the event starts

    event = (
        await session.execute(select(Event).where(Event.slug == slug))
    ).scalar_one_or_none()
    if event is None:
        event = Event(
            slug=slug,
            org_id=org.id,
            created_by=creator.id,
            status=event_lifecycle.DRAFT,
            moderation_status=event_lifecycle.MOD_PENDING,
        )
        session.add(event)

    event.org_id = org.id
    event.created_by = creator.id
    event.title = spec["title"]
    event.description = (
        f"[DEMO] Synthetic {spec['event_type']} for local UI review, hosted by "
        f"{org.display_name}. This is not a real event."
    )
    event.event_type = spec["event_type"]
    event.format = spec["format"]
    event.venue_name = spec["venue_name"]
    event.venue_address = spec["venue_address"]
    event.cover_image_path = None  # frontend falls back to a placeholder
    event.starts_at = starts_at
    event.ends_at = ends_at
    event.timezone = "Asia/Ho_Chi_Minh"
    event.registration_opens_at = None  # open immediately on publish
    event.registration_closes_at = closes_at
    event.capacity = spec["capacity"]
    event.visibility = event_lifecycle.PUBLIC
    event.is_sponsored = spec["is_sponsored"]
    event.is_featured = spec["is_featured"]
    event.tags = ["demo"]
    # Reset to draft then drive through the lifecycle so re-runs stay consistent.
    event.status = event_lifecycle.DRAFT
    event.moderation_status = event_lifecycle.MOD_PENDING
    _publish_event(event, approver_id=creator.id, now=now)
    await session.flush()
    return event


async def _ensure_confirmed_registration(
    session: AsyncSession, *, event: Event, student: User
) -> bool:
    """Add one confirmed registration for ``student`` (idempotent per (event,user)).

    Mirrors the ``registration_service.register`` confirmed branch — inserts a
    ``confirmed`` row — without re-running the locking/notification path (a seed
    is a single-writer offline context). Returns True if a new row was created.
    """

    existing = (
        await session.execute(
            select(EventRegistration).where(
                EventRegistration.event_id == event.id,
                EventRegistration.user_id == student.id,
                EventRegistration.status != event_lifecycle.REG_CANCELLED,
            )
        )
    ).scalars().first()
    if existing is not None:
        return False
    session.add(
        EventRegistration(
            event_id=event.id,
            user_id=student.id,
            status=event_lifecycle.REG_CONFIRMED,
            created_at=datetime.now(tz=UTC),
        )
    )
    await session.flush()
    return True


async def _sync_registration_count(session: AsyncSession, *, event: Event) -> None:
    """Set the denormalized ``registration_count`` to the live confirmed count."""

    confirmed = (
        await session.execute(
            select(func.count())
            .select_from(EventRegistration)
            .where(
                EventRegistration.event_id == event.id,
                EventRegistration.status == event_lifecycle.REG_CONFIRMED,
            )
        )
    ).scalar_one()
    event.registration_count = int(confirmed or 0)
    await session.flush()


# --------------------------------------------------------------------------- #
# Recruitment pipeline progression (real services, never a raw status hack)    #
# --------------------------------------------------------------------------- #


def _seed_ctx() -> RequestContext:
    """A synthetic request context for the offline single-writer seed."""

    return RequestContext(ip=None, user_agent="demo-marketplace-seed")


def _partner_principal(*, user_id: uuid.UUID, org_id: uuid.UUID) -> Principal:
    """A partner-of-org principal with a full grant (the poster is the org admin).

    The seed is a trusted offline single-writer; granting ``*`` mirrors a partner
    admin's wildcard so the real service RBAC gates all pass for the org that owns
    the job: ``applications:read`` + ``recruitment:{submit_scorecard,
    schedule_interview,create_offer,approve_offer,send_offer}``. Tenant isolation
    still binds the principal to ``org_id`` (it cannot touch another org).
    """

    return Principal(
        user_id=user_id,
        persona="partner_member",
        org_id=org_id,
        is_superadmin=False,
        permissions=frozenset({"*"}),
    )


async def _ensure_progression_student(session: AsyncSession) -> User:
    """Upsert the dedicated demo candidate (with a known dev login) by email.

    Gets a primary ``student`` identity + an Argon2 password hash so the offer card
    can be browser-verified by logging in as this student. Idempotent by email; the
    ``demo-…@demo.local`` shape means the existing ``--wipe`` user filter removes it.
    """

    user = (
        await session.execute(select(User).where(User.email == DEMO_CANDIDATE_EMAIL))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            email=DEMO_CANDIDATE_EMAIL,
            full_name=DEMO_CANDIDATE_NAME,
            is_active=True,
            email_verified_at=datetime.now(tz=UTC),
            password_hash=hash_password(DEMO_CANDIDATE_PASSWORD),
        )
        session.add(user)
        await session.flush()
        session.add(Identity(user_id=user.id, persona="student", is_primary=True))
        await session.flush()
    elif user.password_hash is None:
        # Keep the documented login working on a re-run of an older partial seed.
        user.password_hash = hash_password(DEMO_CANDIDATE_PASSWORD)
        await session.flush()
    return user


async def _active_member_user(
    session: AsyncSession, *, org_id: uuid.UUID, prefer_user_id: uuid.UUID | None
) -> User | None:
    """An ACTIVE member of the org (prefers ``prefer_user_id`` — the job poster)."""

    member_ids = list(
        (
            await session.execute(
                select(Membership.user_id).where(
                    Membership.org_id == org_id, Membership.status == "active"
                )
            )
        ).scalars().all()
    )
    if not member_ids:
        return None
    chosen = prefer_user_id if prefer_user_id in member_ids else member_ids[0]
    return (
        await session.execute(select(User).where(User.id == chosen))
    ).scalar_one_or_none()


async def _resolve_progression_target(
    session: AsyncSession,
) -> tuple[Job, Organization, User] | None:
    """Discover the (job, org, partner-reviewer) progression target at runtime.

    Returns ``None`` (progression skipped) when the target job, its org, or an
    active partner member cannot be found — so the marketplace seed still succeeds
    on a DB without the recruitment E2E fixtures.
    """

    job = (
        await session.execute(
            select(Job).where(
                Job.slug == DEMO_TARGET_JOB_SLUG, Job.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    org = (
        await session.execute(
            select(Organization).where(Organization.id == job.org_id)
        )
    ).scalar_one_or_none()
    if org is None:
        return None
    partner = await _active_member_user(
        session, org_id=org.id, prefer_user_id=job.posted_by
    )
    if partner is None:
        return None
    return job, org, partner


async def _ensure_demo_application(
    session: AsyncSession, *, job: Job, org: Organization, student: User
) -> Application:
    """Upsert the demo (non-anonymous) application by its stable idempotency key.

    Created directly in ``submitted`` (mirroring ``apply_service`` field-setting)
    WITHOUT a CV snapshot — the snapshot is only needed for CV download, not for the
    recruitment panels this fixture lights up. Non-anonymous so the reveal handshake
    is not required before interview/offer (the identity path is satisfied).
    """

    app = (
        await session.execute(
            select(Application).where(
                Application.idempotency_key == DEMO_APPLICATION_IDEMPOTENCY,
                Application.applicant_id == student.id,
                Application.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if app is None:
        app = Application(
            job_id=job.id,
            applicant_id=student.id,
            org_id=org.id,
            status=rec_lifecycle.SUBMITTED,
            cover_letter=(
                "[DEMO] Synthetic application for local recruitment-panel review."
            ),
            screening_answers={},
            is_anonymous=False,
            idempotency_key=DEMO_APPLICATION_IDEMPOTENCY,
        )
        session.add(app)
        await session.flush()
        # Keep the denormalized, partner-visible counter honest (mirrors
        # ``apply_service.apply_to_job``); ``--wipe`` decrements it back.
        job.application_count += 1
        await session.flush()
    return app


async def _ensure_sent_offer(
    session: AsyncSession,
    *,
    principal: Principal,
    app_id: uuid.UUID,
    now: datetime,
) -> uuid.UUID | None:
    """Drive the offer to ``sent`` via create -> submit -> approve -> send.

    Idempotent: drives forward from whatever LIVE state a partial prior run left
    (and is a no-op when a terminal offer already exists). Left at ``sent`` — never
    auto-accepted — so the student can accept/decline it in the browser.
    """

    offer = await offer_service._live_offer_for_application(
        session, application_id=app_id
    )
    if offer is None:
        existing = (
            await session.execute(
                select(Offer)
                .where(Offer.application_id == app_id)
                .order_by(Offer.created_at.desc())
            )
        ).scalars().first()
        if existing is not None:
            return existing.id  # already terminal (e.g. a prior accept) — leave it
        await offer_service.create_offer(
            session,
            principal=principal,
            application_id=app_id,
            position_title="Backend Engineer Intern",
            department="Engineering",
            salary_amount=15_000_000,
            salary_currency=offer_domain.DEFAULT_CURRENCY,
            salary_period=offer_domain.DEFAULT_PERIOD,
            benefits_summary="[DEMO] Synthetic benefits for local preview only.",
            expiry_date=now + timedelta(days=14),  # near-future response deadline
            ctx=_seed_ctx(),
        )
        offer = await offer_service._live_offer_for_application(
            session, application_id=app_id
        )

    guard = 0
    while offer is not None and offer.status != offer_domain.STATUS_SENT and guard < 6:
        guard += 1
        if offer.status == offer_domain.STATUS_DRAFT:
            await offer_service.submit_offer(
                session, principal=principal, offer_id=offer.id, ctx=_seed_ctx()
            )
        elif offer.status == offer_domain.STATUS_PENDING_APPROVAL:
            await offer_service.approve_offer(
                session,
                principal=principal,
                offer_id=offer.id,
                decision=offer_domain.APPROVE_DECISION,
                ctx=_seed_ctx(),
            )
        elif offer.status == offer_domain.STATUS_APPROVED:
            await offer_service.send_offer(
                session, principal=principal, offer_id=offer.id, ctx=_seed_ctx()
            )
        else:
            break
        offer = await offer_service._live_offer_for_application(
            session, application_id=app_id
        )
    return offer.id if offer is not None else None


async def progress_candidate(session: AsyncSession) -> dict[str, str] | None:
    """Progress one demo candidate to: under_review + scorecard + interview + sent
    offer, all via the REAL recruitment services. Returns a summary or ``None`` when
    the target job is absent (progression skipped)."""

    target = await _resolve_progression_target(session)
    if target is None:
        return None
    job, org, partner = target
    # Capture scalars BEFORE any service commit (an async session cannot lazily
    # refresh an expired ORM attribute).
    job_title, job_slug = job.title, job.slug
    org_name, org_id = org.display_name, org.id
    partner_id, partner_email = partner.id, partner.email

    student = await _ensure_progression_student(session)
    student_email = student.email
    app = await _ensure_demo_application(
        session, job=job, org=org, student=student
    )
    app_id = app.id
    await session.commit()

    principal = _partner_principal(user_id=partner_id, org_id=org_id)
    ctx = _seed_ctx()

    # 1. review: submitted -> under_review (+ materialize the stage-1 row).
    await decision_service.review_application(
        session, principal=principal, application_id=app_id, ctx=ctx
    )

    # 2. advance to the Interview stage (so the scorecard-gated stage is not the one
    #    a real candidate sits at). Guarded: skip when already at/after stage 2.
    active = await stage_service._active_stage(session, application_id=app_id)
    assert active is not None
    stage = await stage_service._load_stage(session, stage_id=active.stage_id)
    assert stage is not None
    if stage.sort_order < DEMO_PROGRESSION_STAGE_ORDER:
        await stage_service.advance_application_stage(
            session,
            principal=principal,
            application_id=app_id,
            idempotency_key="demo-progression-advance-1",
            ctx=ctx,
        )
        active = await stage_service._active_stage(session, application_id=app_id)
        assert active is not None
        stage = await stage_service._load_stage(session, stage_id=active.stage_id)
        assert stage is not None
    stage_id = stage.id

    # 3. flip the CURRENT stage to a scorecard advance-gate (idempotent; restored
    #    to ``manual`` by ``--wipe``).
    if stage.required_action != scorecard_domain.ACTION_SCORECARD:
        stage.required_action = scorecard_domain.ACTION_SCORECARD
        await session.commit()

    now = datetime.now(tz=UTC)

    # 4. schedule an interview at the current stage with the partner as the sole
    #    assignee (one OPEN interview per stage — skip if it already exists).
    open_iv = await interview_service._open_interview(
        session, application_id=app_id, stage_id=stage_id
    )
    if open_iv is None:
        await interview_service.schedule_interview(
            session,
            principal=principal,
            application_id=app_id,
            mode="online",
            scheduled_at=now + timedelta(days=2),
            assignee_ids=[partner_id],
            duration_minutes=45,
            meeting_link="https://meet.demo.local/backend-intern-interview",
            title="[DEMO] Phỏng vấn kỹ thuật",
            ctx=ctx,
        )

    # 5. submit the partner's scorecard for the current stage (UPSERT — idempotent).
    #    The full 4-criteria set + recommendation satisfies AND reveals the gate.
    await scorecard_service.submit_scorecard(
        session,
        principal=principal,
        application_id=app_id,
        recommendation="strong_yes",
        scores=[
            {"criterion_key": "technical", "score": 5},
            {"criterion_key": "communication", "score": 4},
            {"criterion_key": "culture_fit", "score": 4},
            {"criterion_key": "motivation", "score": 5},
        ],
        comment="[DEMO] Strong intern candidate — synthetic evaluation.",
        ctx=ctx,
    )

    # 6. offer: create -> submit -> approve -> send (left at ``sent``).
    offer_id = await _ensure_sent_offer(
        session, principal=principal, app_id=app_id, now=now
    )

    return {
        "application_id": str(app_id),
        "job_title": job_title,
        "job_slug": job_slug,
        "org": org_name,
        "partner_login": partner_email,
        "student_login": student_email,
        "student_password": DEMO_CANDIDATE_PASSWORD,
        "stage_id": str(stage_id),
        "offer_id": str(offer_id) if offer_id else "",
    }


async def _restore_target_stage(session: AsyncSession) -> None:
    """Restore the demo-flipped stage ``required_action`` back to ``manual``."""

    job = (
        await session.execute(
            select(Job).where(
                Job.slug == DEMO_TARGET_JOB_SLUG, Job.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if job is None:
        return
    tmpl = (
        await session.execute(
            select(PipelineTemplate).where(
                PipelineTemplate.org_id == job.org_id,
                PipelineTemplate.is_system.is_(True),
                PipelineTemplate.is_default.is_(True),
            )
        )
    ).scalar_one_or_none()
    if tmpl is None:
        return
    stage = (
        await session.execute(
            select(PipelineStage).where(
                PipelineStage.template_id == tmpl.id,
                PipelineStage.sort_order == DEMO_PROGRESSION_STAGE_ORDER,
            )
        )
    ).scalar_one_or_none()
    if stage is not None and stage.required_action == scorecard_domain.ACTION_SCORECARD:
        stage.required_action = rec_pipeline.ACTION_MANUAL


async def _demo_application_ids(session: AsyncSession) -> tuple[list[uuid.UUID], int]:
    """All application ids a demo wipe must remove + the count tied to the real job.

    Covers (a) the recruitment-progression app on the REAL job (stable
    ``idempotency_key``), AND (b) every application created against a demo org/job or
    by a demo user — e.g. a real student applying to a demo job in the browser. (b)
    is required for FK-safety: the existing job/org deletes below would otherwise hit
    ``applications_job_id_fkey``. Returns ``(app_ids, prog_count)`` where
    ``prog_count`` is the number on the real target job (for the counter decrement).
    """

    demo_user_ids = list(
        (
            await session.execute(
                select(User.id).where(User.email.like(DEMO_USER_EMAIL_LIKE))
            )
        ).scalars().all()
    )
    demo_org_ids = list(
        (
            await session.execute(
                select(Organization.id).where(
                    Organization.slug.like(f"{DEMO_SLUG_PREFIX}%")
                )
            )
        ).scalars().all()
    )
    job_clauses: list[ColumnElement[bool]] = [Job.slug.like(f"{DEMO_SLUG_PREFIX}%")]
    if demo_org_ids:
        job_clauses.append(Job.org_id.in_(demo_org_ids))
    demo_job_ids = list(
        (
            await session.execute(select(Job.id).where(or_(*job_clauses)))
        ).scalars().all()
    )
    clauses: list[ColumnElement[bool]] = [
        Application.idempotency_key == DEMO_APPLICATION_IDEMPOTENCY
    ]
    if demo_user_ids:
        clauses.append(Application.applicant_id.in_(demo_user_ids))
    if demo_org_ids:
        clauses.append(Application.org_id.in_(demo_org_ids))
    if demo_job_ids:
        clauses.append(Application.job_id.in_(demo_job_ids))
    app_ids = list(
        (
            await session.execute(select(Application.id).where(or_(*clauses)))
        ).scalars().all()
    )
    prog_count = await _count(
        session,
        select(func.count())
        .select_from(Application)
        .where(Application.idempotency_key == DEMO_APPLICATION_IDEMPOTENCY),
    )
    return app_ids, prog_count


async def _wipe_progression(session: AsyncSession) -> dict[str, int]:
    """Remove the demo application(s) + their recruitment children, FK-safe.

    Deletes the children before the application in an explicit order
    (scorecard_scores -> scorecards / interview_assignees -> interviews / offers /
    candidate_stages -> application) so it is correct on SQLite too (no reliance on
    ON DELETE CASCADE), restores the flipped stage, and decrements the real job's
    denormalized counter. Covers ALL demo-owned applications (see
    :func:`_demo_application_ids`) so the subsequent demo job/org deletes are
    FK-safe. The demo STUDENT itself is removed by the shared ``demo-…@demo.local``
    user filter in :func:`wipe` (which runs AFTER this).
    """

    counts = {
        "applications": 0,
        "candidate_stages": 0,
        "scorecards": 0,
        "interviews": 0,
        "offers": 0,
    }
    app_ids, prog_count = await _demo_application_ids(session)
    if app_ids:
        counts["scorecards"] = await _count(
            session,
            select(func.count())
            .select_from(Scorecard)
            .where(Scorecard.application_id.in_(app_ids)),
        )
        counts["interviews"] = await _count(
            session,
            select(func.count())
            .select_from(Interview)
            .where(Interview.application_id.in_(app_ids)),
        )
        counts["offers"] = await _count(
            session,
            select(func.count())
            .select_from(Offer)
            .where(Offer.application_id.in_(app_ids)),
        )
        counts["candidate_stages"] = await _count(
            session,
            select(func.count())
            .select_from(CandidateStage)
            .where(CandidateStage.application_id.in_(app_ids)),
        )
        counts["applications"] = len(app_ids)

        sc_ids = list(
            (
                await session.execute(
                    select(Scorecard.id).where(Scorecard.application_id.in_(app_ids))
                )
            ).scalars().all()
        )
        if sc_ids:
            await session.execute(
                delete(ScorecardScore).where(ScorecardScore.scorecard_id.in_(sc_ids))
            )
        iv_ids = list(
            (
                await session.execute(
                    select(Interview.id).where(Interview.application_id.in_(app_ids))
                )
            ).scalars().all()
        )
        if iv_ids:
            await session.execute(
                delete(InterviewAssignee).where(
                    InterviewAssignee.interview_id.in_(iv_ids)
                )
            )
        await session.execute(
            delete(Scorecard).where(Scorecard.application_id.in_(app_ids))
        )
        await session.execute(
            delete(Interview).where(Interview.application_id.in_(app_ids))
        )
        await session.execute(delete(Offer).where(Offer.application_id.in_(app_ids)))
        await session.execute(
            delete(CandidateStage).where(CandidateStage.application_id.in_(app_ids))
        )
        # Decrement the REAL job's denormalized counter for the progression app(s)
        # only (apps on demo jobs are removed with their soon-to-be-deleted job).
        if prog_count:
            job = (
                await session.execute(
                    select(Job).where(
                        Job.slug == DEMO_TARGET_JOB_SLUG, Job.deleted_at.is_(None)
                    )
                )
            ).scalar_one_or_none()
            if job is not None:
                job.application_count = max(0, job.application_count - prog_count)
        # The remaining application children (application_cv_snapshots,
        # application_reveal_requests) are ON DELETE CASCADE, so the application
        # delete removes them.
        await session.execute(delete(Application).where(Application.id.in_(app_ids)))

    await _restore_target_stage(session)
    await session.flush()
    return counts


# --------------------------------------------------------------------------- #
# Messaging threads (real services, never a raw insert)                        #
# --------------------------------------------------------------------------- #


def _student_principal(*, user_id: uuid.UUID) -> Principal:
    """A student-side principal (no org) — the candidate replying into a thread."""

    return Principal(user_id=user_id, persona=messaging_rules.STUDENT, org_id=None)


def _university_principal(*, user_id: uuid.UUID, org_id: uuid.UUID) -> Principal:
    """A university-staff principal scoped to the university org.

    ``evaluate_open`` lets ``university_staff`` initiate a direct thread to anyone;
    the thread is org-scoped to ``org_id`` (the university org). ``is_superadmin`` is
    left False so the thread behaves as a normal university↔X channel (the moderator
    label path is not exercised by the seed).
    """

    return Principal(
        user_id=user_id,
        persona=messaging_rules.UNIVERSITY_STAFF,
        org_id=org_id,
        is_superadmin=False,
    )


async def _resolve_university_sender(
    session: AsyncSession,
) -> tuple[Organization, User] | None:
    """Discover (university org, a university sender) at runtime.

    Sender preference: an active platform superadmin (the documented
    ``superadmin@vinuni.edu.vn`` login), else any ``university_staff`` identity.
    Returns ``None`` when no university org or sender exists (messaging seed skips
    the university threads but the rest still succeeds).
    """

    org = (
        await session.execute(
            select(Organization).where(
                Organization.org_type == "university",
                Organization.deleted_at.is_(None),
            )
        )
    ).scalars().first()
    if org is None:
        return None
    sender = (
        await session.execute(
            select(User)
            .where(User.is_superadmin.is_(True), User.is_active.is_(True))
            .order_by(User.created_at)
        )
    ).scalars().first()
    if sender is None:
        staff_id = (
            await session.execute(
                select(Identity.user_id).where(
                    Identity.persona == messaging_rules.UNIVERSITY_STAFF
                )
            )
        ).scalars().first()
        if staff_id is not None:
            sender = (
                await session.execute(select(User).where(User.id == staff_id))
            ).scalar_one_or_none()
    if sender is None:
        return None
    return org, sender


async def _find_demo_thread(
    session: AsyncSession, *, subject: str, created_by: uuid.UUID
) -> MessageThread | None:
    """An existing demo thread by its stable subject + author (manual idempotency).

    The application-context partner↔candidate thread is deduped by the service
    itself (one thread per (application, org)); the university support threads have
    NO service-side dedupe, so this guard keeps re-runs from creating duplicates.
    """

    return (
        await session.execute(
            select(MessageThread).where(
                MessageThread.subject == subject,
                MessageThread.created_by == created_by,
                MessageThread.deleted_at.is_(None),
            )
        )
    ).scalars().first()


async def seed_messaging(session: AsyncSession) -> dict[str, str]:
    """Seed institutional demo threads via the REAL messaging services.

    1. partner↔candidate on the demo application (partner intro + candidate reply +
       partner follow-up) — created by the partner that owns the job so the PARTNER
       inbox shows it and the candidate STUDENT inbox shows it.
    2. university↔student to ``browser_smoke_001`` — so that student inbox + the
       university inbox have content.
    3. university↔partner to the same partner — a second university-inbox thread.

    Idempotent: (1) re-uses the service's per-application dedupe; (2)+(3) are guarded
    by :func:`_find_demo_thread`. All bodies are clearly ``[DEMO]``-tagged.
    """

    summary: dict[str, str] = {}

    # 1. partner↔candidate on the demo recruitment application.
    target = await _resolve_progression_target(session)
    partner_id: uuid.UUID | None = None
    if target is not None:
        _job, org, partner = target
        org_id, partner_id = org.id, partner.id
        app = (
            await session.execute(
                select(Application).where(
                    Application.idempotency_key == DEMO_APPLICATION_IDEMPOTENCY,
                    Application.org_id == org_id,
                    Application.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if app is not None:
            app_id, applicant_id = app.id, app.applicant_id
            partner_principal = _partner_principal(user_id=partner_id, org_id=org_id)
            # recipient_ids are IGNORED for the partner+application path (the service
            # resolves the bound applicant server-side); pass [] explicitly.
            created = await thread_service.create_thread(
                session,
                principal=partner_principal,
                kind=messaging_rules.KIND_DIRECT,
                context_type=messaging_rules.CONTEXT_APPLICATION,
                context_id=app_id,
                recipient_ids=[],
                subject=_MSG_SUBJECT_PARTNER_CANDIDATE,
                first_message=(
                    "[DEMO] Chào bạn, cảm ơn bạn đã ứng tuyển vị trí Backend "
                    "Engineer Intern. Bạn có thời gian trao đổi nhanh trong tuần "
                    "này không?"
                ),
                ctx=_seed_ctx(),
            )
            thread_id = uuid.UUID(created["id"])
            # Candidate reply (student principal) — idempotent on the dedupe key.
            await message_service.send_message(
                session,
                principal=_student_principal(user_id=applicant_id),
                thread_id=thread_id,
                body=(
                    "[DEMO] Em chào anh/chị, em rất sẵn lòng ạ. Em trống lịch "
                    "chiều thứ Năm tuần này."
                ),
                client_dedupe_key="demo-msg-candidate-reply-1",
                ctx=_seed_ctx(),
            )
            # Partner follow-up — idempotent on the dedupe key.
            await message_service.send_message(
                session,
                principal=partner_principal,
                thread_id=thread_id,
                body=(
                    "[DEMO] Tuyệt vời. Bộ phận tuyển dụng sẽ gửi lịch phỏng vấn "
                    "chi tiết cho bạn qua kênh này."
                ),
                client_dedupe_key="demo-msg-partner-candidate-2",
                ctx=_seed_ctx(),
            )
            summary["partner_candidate_thread"] = str(thread_id)
            summary["partner_login"] = partner.email
            summary["candidate_login"] = DEMO_CANDIDATE_EMAIL

    # 2 + 3. university-authored threads.
    uni = await _resolve_university_sender(session)
    if uni is not None:
        uni_org, uni_sender = uni
        uni_principal = _university_principal(
            user_id=uni_sender.id, org_id=uni_org.id
        )
        summary["university_login"] = uni_sender.email

        # 2. university↔student to the browser-smoke student.
        student = (
            await session.execute(
                select(User).where(User.email == DEMO_MSG_STUDENT_EMAIL)
            )
        ).scalar_one_or_none()
        if student is not None:
            existing = await _find_demo_thread(
                session,
                subject=_MSG_SUBJECT_UNI_STUDENT,
                created_by=uni_sender.id,
            )
            if existing is None:
                created = await thread_service.create_thread(
                    session,
                    principal=uni_principal,
                    kind=messaging_rules.KIND_DIRECT,
                    context_type=messaging_rules.CONTEXT_SUPPORT,
                    context_id=None,
                    recipient_ids=[student.id],
                    subject=_MSG_SUBJECT_UNI_STUDENT,
                    first_message=(
                        "[DEMO] Chào bạn, Trung tâm Hướng nghiệp VinUni mời bạn "
                        "tham gia buổi tư vấn CV sắp tới. Bạn quan tâm chứ?"
                    ),
                    ctx=_seed_ctx(),
                )
                summary["uni_student_thread"] = str(created["id"])
            else:
                summary["uni_student_thread"] = str(existing.id)
            summary["student_login"] = student.email

        # 3. university↔partner (only if the partner was discovered above).
        if partner_id is not None:
            existing = await _find_demo_thread(
                session,
                subject=_MSG_SUBJECT_UNI_PARTNER,
                created_by=uni_sender.id,
            )
            if existing is None:
                created = await thread_service.create_thread(
                    session,
                    principal=uni_principal,
                    kind=messaging_rules.KIND_DIRECT,
                    context_type=messaging_rules.CONTEXT_SUPPORT,
                    context_id=None,
                    recipient_ids=[partner_id],
                    subject=_MSG_SUBJECT_UNI_PARTNER,
                    first_message=(
                        "[DEMO] Kính gửi đối tác, VinUni cảm ơn sự hợp tác tuyển "
                        "dụng. Chúng tôi muốn trao đổi kế hoạch tuyển dụng học kỳ "
                        "tới."
                    ),
                    ctx=_seed_ctx(),
                )
                summary["uni_partner_thread"] = str(created["id"])
            else:
                summary["uni_partner_thread"] = str(existing.id)

    return summary


async def _wipe_messaging(session: AsyncSession) -> dict[str, int]:
    """Remove ONLY demo-tagged threads + their messages/participants, FK-safe.

    Demo threads are identified by the stable ``DEMO_THREAD_SUBJECT_PREFIX`` subject
    (never a real thread). Children are deleted before the thread in an explicit
    order (messages -> participants -> threads) so it is correct on SQLite too (no
    reliance on ON DELETE CASCADE) and so the participant rows referencing the demo
    candidate are gone before the shared user filter deletes that user.
    """

    counts = {"threads": 0, "messages": 0, "participants": 0}
    thread_ids = list(
        (
            await session.execute(
                select(MessageThread.id).where(
                    MessageThread.subject.like(f"{DEMO_THREAD_SUBJECT_PREFIX}%")
                )
            )
        ).scalars().all()
    )
    if thread_ids:
        counts["messages"] = await _count(
            session,
            select(func.count())
            .select_from(Message)
            .where(Message.thread_id.in_(thread_ids)),
        )
        counts["participants"] = await _count(
            session,
            select(func.count())
            .select_from(MessageThreadParticipant)
            .where(MessageThreadParticipant.thread_id.in_(thread_ids)),
        )
        counts["threads"] = len(thread_ids)
        await session.execute(
            delete(Message).where(Message.thread_id.in_(thread_ids))
        )
        await session.execute(
            delete(MessageThreadParticipant).where(
                MessageThreadParticipant.thread_id.in_(thread_ids)
            )
        )
        await session.execute(
            delete(MessageThread).where(MessageThread.id.in_(thread_ids))
        )
    await session.flush()
    return counts


# --------------------------------------------------------------------------- #
# Sponsored/banner ad inventory (B-546)                                       #
# --------------------------------------------------------------------------- #
#
# Real, ACTIVE ``SponsoredPlacement`` + APPROVED ``CampaignCreative`` rows —
# the actual source of truth for the homepage hero/right-rail banners and the
# job-recommendations sponsored slot (``advertising.inventory_facade`` /
# ``discovery.ranking_service``). Distinct from the ``is_sponsored``/
# ``is_featured`` demo flags set directly on jobs/events above, which drive the
# separate homepage sponsored/featured *list* rails (``opportunities.
# public_read``). Without this, those two placement-backed rails render empty
# in a fresh dev environment even after the flag-based seed runs.
#
# Driven through the REAL service entry points (create -> submit -> mark_paid
# -> approve -> upload creative -> review creative), same discipline as the
# recruitment-progression seed above. Idempotent: skips a target that already
# has an in-flight/active demo placement (``moderation_note`` marker).

_AD_DEMO_MARKER = "[DEMO-SEED-AD]"
_AD_PACKAGE_CODE = "sponsored_14d"


def _ad_seed_ctx() -> RequestContext:
    return RequestContext(ip=None, user_agent="demo-marketplace-seed:ads")


def _ad_moderator_principal(*, user_id: uuid.UUID) -> Principal:
    """A superadmin principal for the university-side approve/pay/review steps.

    Mirrors ``_partner_principal``'s trusted-offline-writer rationale — the
    real RBAC gates (``_require_advertising_moderator``) all pass via
    ``is_superadmin``, and this seed never touches another org's data.
    """

    return Principal(
        user_id=user_id, persona="university_staff", is_superadmin=True,
        permissions=frozenset({"*"}),
    )


async def _existing_demo_placement(
    session: AsyncSession, *, target_type: str, target_id: uuid.UUID
):
    from app.modules.advertising.domain.models import SponsoredPlacement

    return (
        await session.execute(
            select(SponsoredPlacement).where(
                SponsoredPlacement.target_type == target_type,
                SponsoredPlacement.target_id == target_id,
                SponsoredPlacement.moderation_note == _AD_DEMO_MARKER,
                SponsoredPlacement.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _seed_one_placement(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    org_id: uuid.UUID,
    poster_id: uuid.UUID,
    slot: str,
    label: str,
) -> bool:
    """Create + activate one demo placement with an approved creative for ``slot``.

    Returns ``False`` (no-op) if a demo placement for this target already
    exists — re-running the seed never duplicates or re-submits inventory.
    """

    from app.modules.advertising.application import (
        creative_service,
        moderation_service,
        placement_service,
    )
    from app.modules.advertising.domain.models import AdPackage

    if await _existing_demo_placement(
        session, target_type=target_type, target_id=target_id
    ) is not None:
        return False

    pkg = (
        await session.execute(
            select(AdPackage).where(AdPackage.code == _AD_PACKAGE_CODE)
        )
    ).scalar_one_or_none()
    if pkg is None:
        return False  # migration 0017 seed data not present — nothing to attach to

    ctx = _ad_seed_ctx()
    partner = _partner_principal(user_id=poster_id, org_id=org_id)
    moderator = _ad_moderator_principal(user_id=poster_id)
    now = datetime.now(tz=UTC)

    created = await placement_service.create_placement(
        session, principal=partner,
        payload={
            "target_type": target_type,
            "target_id": target_id,
            "placement_type": "sponsored",
            "package_id": pkg.id,
            "start_at": now,
            "disclosure_confirmed": True,
        },
        ctx=ctx,
    )
    placement_id = uuid.UUID(created["id"])
    await placement_service.submit_placement(
        session, principal=partner, placement_id=placement_id, ctx=ctx,
        disclosure_confirmed=True,
    )
    await moderation_service.mark_paid(
        session, principal=moderator, placement_id=placement_id,
        payment_reference="DEMO-SEED-PAYMENT", ctx=ctx,
    )
    await moderation_service.approve_placement(
        session, principal=moderator, placement_id=placement_id,
        note=_AD_DEMO_MARKER, ctx=ctx,
    )

    creative = await creative_service.upload_creative(
        session, principal=partner, placement_id=placement_id, slot=slot,
        data=_placeholder_logo_png(label, (60, 60, 60)), content_type="image/png",
        alt_vi=f"[DEMO] {label}", alt_en=f"[DEMO] {label}",
        click_target=f"/{target_type}s", ctx=ctx,
    )
    await moderation_service.review_creative(
        session, principal=moderator, creative_id=uuid.UUID(creative["id"]),
        decision="approve", note=_AD_DEMO_MARKER, ctx=ctx,
    )
    return True


async def _seed_sponsored_placements(
    session: AsyncSession,
    *,
    jobs: list[Job],
    event: Event | None,
    poster: User | uuid.UUID,
) -> dict[str, int]:
    """Seed varied ACTIVE sponsored inventory: 2 jobs (hero + rail) + 1 event."""

    poster_id = poster if isinstance(poster, uuid.UUID) else poster.id
    slots = [
        ("homepage_hero", jobs[0] if len(jobs) > 0 else None),
        ("right_rail", jobs[1] if len(jobs) > 1 else None),
    ]
    created = 0
    for slot, job in slots:
        if job is None:
            continue
        if await _seed_one_placement(
            session, target_type="job", target_id=job.id, org_id=job.org_id,
            poster_id=poster_id, slot=slot, label=job.title,
        ):
            created += 1

    if event is not None:
        if await _seed_one_placement(
            session, target_type="event", target_id=event.id, org_id=event.org_id,
            poster_id=poster_id, slot="event_banner", label=event.title,
        ):
            created += 1

    return {"sponsored_placements_seeded": created}


# --------------------------------------------------------------------------- #
# Seed / wipe                                                                  #
# --------------------------------------------------------------------------- #


async def seed(session: AsyncSession) -> dict[str, int]:
    poster = await _ensure_poster(session)
    students = await _ensure_students(session)
    orgs: list[Organization] = []
    orgs_by_key: dict[str, Organization] = {}
    logo_count = 0
    for spec in _ORG_SEED:
        org = await _upsert_org(session, spec)
        orgs.append(org)
        orgs_by_key[spec["key"]] = org
        if org.logo_path:
            logo_count += 1

    now = datetime.now(tz=UTC)
    past = now - timedelta(days=3)
    future = now + timedelta(days=30)

    job_total = 0
    sponsored_total = 0
    featured_total = 0
    expired_total = 0
    placement_job_candidates: list[Job] = []
    # ~30 jobs: ~2-3 per org, cycling role templates. A small number are
    # sponsored / featured (real flags) and 2 are past-deadline (must NOT show
    # in active listings — exercises the visibility predicate).
    counter = 0
    for org_idx, org in enumerate(orgs):
        per_org = 2 + (org_idx % 2)  # 2 or 3 jobs
        for j in range(per_org):
            template = _ROLE_TEMPLATES[counter % len(_ROLE_TEMPLATES)]
            is_sponsored = counter in (0, 5, 11)
            is_featured = counter in (1, 6, 12)
            # Two past-deadline postings to test the visibility predicate.
            is_expired = counter in (3, 17)
            deadline = past if is_expired else (future if counter % 2 == 0 else None)
            job = await _upsert_job(
                session,
                org=org,
                poster=poster,
                index=j,
                template=template,
                is_sponsored=is_sponsored,
                is_featured=is_featured,
                deadline=deadline,
            )
            job_total += 1
            sponsored_total += int(is_sponsored)
            featured_total += int(is_featured)
            expired_total += int(is_expired)
            # Two NOT-otherwise-flagged, non-expired jobs anchor the real
            # SponsoredPlacement + creative inventory below (B-546) — kept
            # distinct from the is_sponsored/is_featured demo flags above so
            # the placement-driven hero/rail rails are exercised by their own,
            # real source of truth rather than the decorative flag.
            if not (is_sponsored or is_featured or is_expired) and len(
                placement_job_candidates
            ) < 2:
                placement_job_candidates.append(job)
            counter += 1

    # ~8 events spread across the demo orgs, each driven to ``published`` via the
    # documented partner submit -> university-approve path. One (capacity 2) is
    # filled by the demo students so a 3rd UI registration waitlists.
    event_total = 0
    event_sponsored_total = 0
    event_featured_total = 0
    registration_total = 0
    placement_event_candidate: Event | None = None
    for spec in _EVENT_SEED:
        org = orgs_by_key[spec["org_key"]]
        event = await _upsert_event(session, org=org, creator=poster, spec=spec)
        if spec.get("fill_to_capacity") and event.capacity is not None:
            for student in students[: event.capacity]:
                if await _ensure_confirmed_registration(
                    session, event=event, student=student
                ):
                    registration_total += 1
        await _sync_registration_count(session, event=event)
        event_total += 1
        event_sponsored_total += int(spec["is_sponsored"])
        event_featured_total += int(spec["is_featured"])
        if (
            placement_event_candidate is None
            and not spec["is_sponsored"]
            and not spec["is_featured"]
        ):
            placement_event_candidate = event

    placement_stats = await _seed_sponsored_placements(
        session,
        jobs=placement_job_candidates,
        event=placement_event_candidate,
        poster=poster,
    )

    await session.commit()
    return {
        "orgs": len(orgs),
        "orgs_with_logo": logo_count,
        "jobs": job_total,
        "sponsored": sponsored_total,
        "featured": featured_total,
        "past_deadline": expired_total,
        "events": event_total,
        "events_sponsored": event_sponsored_total,
        "events_featured": event_featured_total,
        "registrations": registration_total,
        **placement_stats,
    }


async def _count(session: AsyncSession, stmt) -> int:
    return int((await session.execute(stmt)).scalar_one() or 0)


async def wipe(session: AsyncSession) -> dict[str, int]:
    """Remove ONLY demo-tagged rows (slug prefix + fixed poster email)."""

    storage = storage_backend.get_storage()

    # Messaging first: remove the demo threads + their messages/participants BEFORE
    # the demo candidate user is deleted below (participant rows reference it).
    messaging = await _wipe_messaging(session)

    # Recruitment progression first: remove the demo application + its
    # scorecards/interviews/offers/candidate_stages (and restore the flipped stage)
    # BEFORE the demo students are deleted below — the application FK to the student
    # is ``ON DELETE RESTRICT``.
    progression = await _wipe_progression(session)

    demo_orgs = list(
        (
            await session.execute(
                select(Organization).where(
                    Organization.slug.like(f"{DEMO_SLUG_PREFIX}%")
                )
            )
        ).scalars().all()
    )
    demo_org_ids = [o.id for o in demo_orgs]

    # Delete the placeholder logo objects from storage (best-effort).
    for org in demo_orgs:
        if org.logo_path:
            try:
                storage.delete(org.logo_path)
            except Exception:  # noqa: BLE001 - storage cleanup is non-critical
                pass

    # Jobs first (FK to orgs + poster). Match by demo slug OR demo org ownership.
    job_filter: ColumnElement[bool] = Job.slug.like(f"{DEMO_SLUG_PREFIX}%")
    if demo_org_ids:
        job_filter = or_(job_filter, Job.org_id.in_(demo_org_ids))
    # Events: same matching as jobs (demo slug OR demo org ownership).
    event_filter: ColumnElement[bool] = Event.slug.like(f"{DEMO_SLUG_PREFIX}%")
    if demo_org_ids:
        event_filter = or_(event_filter, Event.org_id.in_(demo_org_ids))
    org_filter = Organization.slug.like(f"{DEMO_SLUG_PREFIX}%")
    # All demo users (poster + demo students) share the demo-…@demo.local shape.
    user_filter = User.email.like(DEMO_USER_EMAIL_LIKE)

    # Registrations belong to demo events (delete before events + users to respect
    # the event_id/user_id FKs explicitly, not just the ON DELETE CASCADE).
    demo_event_ids = list(
        (
            await session.execute(select(Event.id).where(event_filter))
        ).scalars().all()
    )
    reg_filter: ColumnElement[bool] | None = (
        EventRegistration.event_id.in_(demo_event_ids) if demo_event_ids else None
    )

    # Count before delete (type-clean + backend-agnostic, no rowcount reliance).
    regs_deleted = (
        await _count(
            session,
            select(func.count()).select_from(EventRegistration).where(reg_filter),
        )
        if reg_filter is not None
        else 0
    )
    events_deleted = await _count(
        session, select(func.count()).select_from(Event).where(event_filter)
    )
    jobs_deleted = await _count(
        session, select(func.count()).select_from(Job).where(job_filter)
    )
    orgs_deleted = await _count(
        session, select(func.count()).select_from(Organization).where(org_filter)
    )
    users_deleted = await _count(
        session, select(func.count()).select_from(User).where(user_filter)
    )

    # Demo sponsored placements + creatives (B-546) — no FK to jobs/events (the
    # target is polymorphic), so delete by the ``[DEMO-SEED-AD]`` marker before
    # the jobs/events they target are removed below.
    from app.modules.advertising.domain.models import CampaignCreative, SponsoredPlacement

    demo_placement_ids = list(
        (
            await session.execute(
                select(SponsoredPlacement.id).where(
                    SponsoredPlacement.moderation_note == _AD_DEMO_MARKER
                )
            )
        ).scalars().all()
    )
    placements_deleted = len(demo_placement_ids)
    if demo_placement_ids:
        await session.execute(
            delete(CampaignCreative).where(
                CampaignCreative.placement_id.in_(demo_placement_ids)
            )
        )
        await session.execute(
            delete(SponsoredPlacement).where(
                SponsoredPlacement.id.in_(demo_placement_ids)
            )
        )

    # FK-safe order: registrations -> events -> jobs -> orgs -> users.
    if reg_filter is not None:
        await session.execute(delete(EventRegistration).where(reg_filter))
    await session.execute(delete(Event).where(event_filter))
    await session.execute(delete(Job).where(job_filter))
    await session.execute(delete(Organization).where(org_filter))
    await session.execute(delete(User).where(user_filter))
    await session.commit()
    return {
        "registrations": regs_deleted,
        "events": events_deleted,
        "jobs": jobs_deleted,
        "orgs": orgs_deleted,
        "demo_users": users_deleted,
        "sponsored_placements": placements_deleted,
        "prog_applications": progression["applications"],
        "prog_candidate_stages": progression["candidate_stages"],
        "prog_scorecards": progression["scorecards"],
        "prog_interviews": progression["interviews"],
        "prog_offers": progression["offers"],
        "msg_threads": messaging["threads"],
        "msg_messages": messaging["messages"],
        "msg_participants": messaging["participants"],
    }


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="DEV-ONLY synthetic marketplace demo seed (idempotent)."
    )
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Remove only demo-seeded rows (slug prefix 'demo-' + demo poster).",
    )
    args = parser.parse_args()

    _assert_dev_environment()
    _banner("wipe" if args.wipe else "seed")

    import_all_models()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        if args.wipe:
            result = await wipe(session)
            print(
                "seed_demo_marketplace: WIPED "
                f"registrations={result['registrations']} "
                f"events={result['events']} jobs={result['jobs']} "
                f"orgs={result['orgs']} demo_users={result['demo_users']}"
            )
            print(
                "seed_demo_marketplace: WIPED progression "
                f"applications={result['prog_applications']} "
                f"candidate_stages={result['prog_candidate_stages']} "
                f"scorecards={result['prog_scorecards']} "
                f"interviews={result['prog_interviews']} "
                f"offers={result['prog_offers']} "
                "(scorecard-gated stage restored to manual)"
            )
            print(
                "seed_demo_marketplace: WIPED messaging "
                f"threads={result['msg_threads']} "
                f"messages={result['msg_messages']} "
                f"participants={result['msg_participants']}"
            )
        else:
            result = await seed(session)
            print(
                "seed_demo_marketplace: SEEDED "
                f"orgs={result['orgs']} "
                f"(with_logo={result['orgs_with_logo']}, "
                f"logoless={result['orgs'] - result['orgs_with_logo']}) "
                f"jobs={result['jobs']} "
                f"(sponsored={result['sponsored']}, featured={result['featured']}, "
                f"past_deadline={result['past_deadline']}) "
                f"events={result['events']} "
                f"(sponsored={result['events_sponsored']}, "
                f"featured={result['events_featured']}, "
                f"registrations={result['registrations']})"
            )
            progression = await progress_candidate(session)
            if progression is None:
                print(
                    "seed_demo_marketplace: progression SKIPPED "
                    f"(job slug '{DEMO_TARGET_JOB_SLUG}' not found)"
                )
            else:
                print(
                    "seed_demo_marketplace: PROGRESSED candidate "
                    f"application={progression['application_id']} "
                    f"job='{progression['job_title']}' org='{progression['org']}' "
                    f"offer={progression['offer_id'] or '(none)'}"
                )
                print(
                    "  partner candidate-detail (3 panels) login: "
                    f"{progression['partner_login']}  ->  job '{progression['job_title']}'"
                )
                print(
                    "  student offer-card login: "
                    f"{progression['student_login']} / {progression['student_password']}"
                )
            messaging = await seed_messaging(session)
            await session.commit()
            if not messaging:
                print(
                    "seed_demo_marketplace: messaging SKIPPED "
                    "(no demo application and no university sender found)"
                )
            else:
                print(
                    "seed_demo_marketplace: SEEDED messaging threads "
                    f"partner_candidate={messaging.get('partner_candidate_thread', '(skip)')} "
                    f"uni_student={messaging.get('uni_student_thread', '(skip)')} "
                    f"uni_partner={messaging.get('uni_partner_thread', '(skip)')}"
                )
                if "partner_candidate_thread" in messaging:
                    print(
                        "  partner inbox login: "
                        f"{messaging.get('partner_login', '?')}  (candidate thread)"
                    )
                    print(
                        "  candidate inbox login: "
                        f"{messaging.get('candidate_login', '?')} / "
                        f"{DEMO_CANDIDATE_PASSWORD}  (partner thread)"
                    )
                if "uni_student_thread" in messaging:
                    print(
                        "  student inbox login: "
                        f"{messaging.get('student_login', '?')}  (university thread)"
                    )
                if "university_login" in messaging:
                    print(
                        "  university inbox login: "
                        f"{messaging['university_login']}  (uni↔student + uni↔partner)"
                    )
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
