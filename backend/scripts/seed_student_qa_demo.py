# ruff: noqa: E501
"""QA-enablement seed: real CV-fit + competition signals for the BMS job drawers.

Purpose (browser-verification only — NOT app source, NOT prod):
  Seed the RUNNING QA database so the logged-in student job-detail
  "Analyze CV" + "Competition" drawers show REAL deterministic signals for the
  VinFast "Battery Management System (BMS) Software Engineer" job:

    1. A content-rich, matching-ready READY library CV for ``student@vinuni.edu.vn``
       whose skills/experience are a GOOD-but-imperfect match to the BMS JD (mid-high
       fit with a few genuine gaps to surface in the Analyze drawer). It reuses the
       app's real ingestion -> creation path
       (``ingestion_service._sections_from_extracted`` ->
       ``cv_creation_service.create_cv_from_sections``) so the CV lands
       ``status='ready'`` WITH a version-stamped ``matching_json`` exactly like an
       uploaded-CV import.

    2. A realistic competition pool: several CLEARLY-MARKED synthetic demo student
       applicants of VARYING strength each create a READY CV and APPLY to the BMS job
       through the real ``recruitment.apply_service.apply_to_job`` — so each
       application gets an immutable CV snapshot WITH the apply-time deterministic
       ``fit_score`` frozen on it (WS-5). With >= MIN_QUALITY_POOL (5) scored
       applicants the Competition drawer resolves REAL quality-adjusted bands
       (strong-competitor density, applicant-quality bucket, the student's standing)
       instead of ``low_signal``.

    3. The ``job_competition_daily`` projection is refreshed for the BMS job.

  The script prints a summary (student CV id + deterministic BMS fit, the competition
  pool composition + resulting bands) so the drawers' expected content is known.

Scoring is 100% deterministic (``app.ai.cv.job_fit``) — no model call is made, which
is correct for the offline QA environment.

Idempotency:
  - Re-running does NOT duplicate: synthetic applicants are keyed by a stable demo
    email; their apply calls carry a stable idempotency_key; the student's demo CV
    is keyed by title. An existing student demo CV / applicant CV is reused.
  - ``QA_DEMO_RESET=1`` first deletes the demo-scoped applications + CVs (never the
    real seed data) so the CV *content* can be re-tuned on a fresh run. Demo users
    themselves are kept (get-or-create), which keeps append-only logs valid.

Usage (ALWAYS target the QA DB, never the default ``vinuni_career``):
    cd backend
    export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/vinuni_student_qa"
    uv run python scripts/seed_student_qa_demo.py            # idempotent seed
    QA_DEMO_RESET=1 uv run python scripts/seed_student_qa_demo.py   # re-tune content
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Make the backend package importable when run from repo root or scripts/.
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import dispose_engine, get_sessionmaker  # noqa: E402
from app.modules.auth.application.context import RequestContext  # noqa: E402
from app.modules.auth.domain.personas import permissions_for  # noqa: E402
from app.modules.auth.infrastructure.passwords import hash_password  # noqa: E402
from app.modules.documents.application import (  # noqa: E402
    cv_creation_service,
    ingestion_service,
    job_fit_service,
)
from app.modules.documents.domain import catalog  # noqa: E402
from app.modules.documents.domain.models import CvProfile, CvVersion  # noqa: E402
from app.modules.opportunities.application import (  # noqa: E402
    competition_projection_service as projection_service,
)
from app.modules.opportunities.application import competition_service  # noqa: E402
from app.modules.opportunities.domain import competition_scoring as scoring  # noqa: E402
from app.modules.opportunities.domain.models import Job  # noqa: E402
from app.modules.recruitment.application import apply_service  # noqa: E402
from app.modules.users.domain.models import Identity, User, UserPreference  # noqa: E402
from app.shared.permissions import Principal  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

BMS_JOB_ID = uuid.UUID("ffe6fbef-b69a-4d6b-b5fc-6d56decc0d60")
STUDENT_EMAIL = "student@vinuni.edu.vn"

STUDENT_CV_TITLE = "Embedded Firmware Engineer — CV (QA Demo)"
DEMO_EMAIL_DOMAIN = "vinuni.demo"
DEMO_CV_TITLE = "BMS / Embedded CV (QA Demo Applicant)"

CTX = RequestContext(ip="127.0.0.1", user_agent="qa-seed-student-demo")
STUDENT_PERMS = permissions_for("student")


# --------------------------------------------------------------------------- #
# Extracted-dict builder (matches ingestion_service._sections_from_extracted)  #
# --------------------------------------------------------------------------- #
#
# The ingestion importer consumes an ``extracted``-shaped dict:
#   contact  -> header {name, headline, email, phone, location, links[]}
#   entry sections (education/experience/projects/certifications):
#              {"entries": [{heading, subheading, timeframe, location, note,
#                            highlights: [str,...]}]}
#   list/skill sections (skills):  {"items": [{name, level}]}  (level 0-100)
#   text sections (summary):       {"items": [{"text": ...}]}


def _skill_items(pairs: list[tuple[str, int]]) -> dict:
    return {"items": [{"name": name, "level": level} for name, level in pairs]}


def _experience_entry(
    *, role: str, org: str, timeframe: str, location: str, highlights: list[str]
) -> dict:
    return {
        "heading": role,
        "subheading": org,
        "timeframe": timeframe,
        "location": location,
        "highlights": list(highlights),
    }


def _build_extracted(spec: dict) -> dict:
    """Turn a compact profile spec into an ``extracted``-shaped dict."""

    contact: dict = {
        "name": spec["name"],
        "headline": spec["headline"],
        "location": "Hà Nội, Vietnam",
    }
    if spec.get("email"):
        contact["email"] = spec["email"]
    extracted: dict = {
        "contact": contact,
        "summary": {"items": [{"text": spec["summary"]}]},
        "education": {"entries": [spec["education"]]},
        "experience": {"entries": spec["experience"]},
        "skills": _skill_items(spec["skills"]),
    }
    if spec.get("projects"):
        extracted["projects"] = {"entries": spec["projects"]}
    if spec.get("certifications"):
        extracted["certifications"] = {"items": [{"text": c} for c in spec["certifications"]]}
    if spec.get("languages"):
        # A ``languages`` section is a credential-type section (job_fit credentials
        # band), so English proficiency here satisfies the JD's English requirement.
        extracted["languages"] = {"items": list(spec["languages"])}
    return extracted


# Reusable English-proficiency languages block (credential-type section). Matches
# the BMS JD candidate_requirements languages term ("English", "Readable
# documentation") so it is not a spurious gap for strong candidates.
_ENGLISH_LANGUAGES = [
    {
        "name": "English",
        "note": "Professional working proficiency; readable documentation.",
    },
    {"name": "Vietnamese", "note": "Native"},
]


# --------------------------------------------------------------------------- #
# Profile specs                                                                #
# --------------------------------------------------------------------------- #
#
# BMS JD (VinFast): required = C, C++, Battery Systems, Embedded Linux, MATLAB;
#                   preferred = Python, ISO 26262, CAN, Simulink;
#                   experience_min_years = 2; seniority = middle; 1 seat.


STUDENT_SPEC = {
    "name": "Nguyễn Minh Anh",
    "headline": "Embedded Firmware Engineer — Battery & Motor Control",
    "email": STUDENT_EMAIL,
    # Good, on-target summary — covers most required skills + automotive/safety/HIL
    # JD vocabulary, but omits Python / ISO 26262 / CAN so the Analyze drawer surfaces
    # genuine, actionable gaps.
    "summary": (
        "Middle-level embedded firmware engineer with 2 years of hands-on experience "
        "building safety-critical C and C++ firmware for automotive battery systems on "
        "Embedded Linux and ARM Cortex-M microcontrollers. Experienced with State of "
        "Charge (SoC) and State of Health (SoH) estimation, cell balancing, and "
        "hardware-in-the-loop (HIL) testing. Comfortable modelling control algorithms in "
        "MATLAB and Simulink and communicating in English with engineering teams. Seeking "
        "a battery management system (BMS) software role."
    ),
    "education": _experience_entry(
        role="Bachelor of Science (B.Sc.) in Electrical & Computer Engineering",
        org="VinUniversity",
        timeframe="09/2019 - 06/2023",
        location="Hà Nội",
        highlights=["GPA 3.5/4.0", "Focus on embedded systems and control engineering"],
    ),
    "experience": [
        _experience_entry(
            role="Embedded Firmware Engineer",
            org="VinFast R&D — Battery Systems",
            timeframe="01/2023 - 12/2024",
            location="Hải Phòng",
            highlights=[
                "Designed and implemented safety-critical C and C++ firmware for an "
                "automotive battery management system on Embedded Linux and ARM Cortex-M.",
                "Developed State of Charge (SoC) and State of Health (SoH) estimation "
                "algorithms and improved accuracy by 12%.",
                "Modelled cell-balancing and thermal-management control logic in MATLAB "
                "and Simulink before porting to the target microcontroller.",
                "Built automated hardware-in-the-loop (HIL) test harnesses and led the "
                "firmware boot-time optimization effort, reducing boot time by 30%.",
                "Collaborated with cross-functional automotive engineering teams; strong "
                "problem-solving and communication skills, and wrote clear, readable "
                "documentation in English for firmware modules.",
            ],
        ),
        _experience_entry(
            role="Embedded Systems Intern",
            org="FPT Software — Automotive",
            timeframe="06/2022 - 12/2022",
            location="Hà Nội",
            highlights=[
                "Wrote C drivers for battery sensor peripherals on an Embedded Linux board.",
                "Automated hardware-in-the-loop (HIL) test scripts in MATLAB.",
            ],
        ),
    ],
    "projects": [
        _experience_entry(
            role="Open-source BMS simulator",
            org="Personal project",
            timeframe="2023",
            location="",
            highlights=[
                "Built a battery-pack simulator in C++ with a Simulink co-simulation model."
            ],
        )
    ],
    # Covers 5/5 required (C, C++, Battery Systems, Embedded Linux, MATLAB) + Simulink;
    # OMITS Python / ISO 26262 / CAN -> real preferred-skill gaps.
    "skills": [
        ("C", 88),
        ("C++", 82),
        ("Embedded Linux", 78),
        ("MATLAB", 80),
        ("Simulink", 72),
        ("Battery Systems", 70),
        ("ARM Cortex-M", 74),
        ("HIL Testing", 72),
        ("FreeRTOS", 70),
        ("English", 82),
        ("Git", 82),
    ],
    "certifications": ["Coursera — Introduction to Embedded Systems"],
    "languages": _ENGLISH_LANGUAGES,
}


# Synthetic demo applicants, strongest -> weakest. Clearly marked as QA demo data.
def _applicant_specs() -> list[dict]:
    return [
        # --- TOP tier (target fit >= 85): full required + all preferred, senior depth
        {
            "key": 1,
            "name": "[QA Demo] Trần Quốc Huy",
            "headline": "Senior BMS Firmware Engineer",
            "summary": (
                "Senior embedded engineer with 4 years building C and C++ battery "
                "management system firmware on Embedded Linux, MATLAB/Simulink control "
                "modelling, Python tooling, CAN bus integration, and ISO 26262 functional "
                "safety for automotive battery systems."
            ),
            "education": _experience_entry(
                role="Master of Science (M.Sc.) in Electrical Engineering",
                org="Hanoi University of Science and Technology",
                timeframe="09/2016 - 06/2018",
                location="Hà Nội",
                highlights=["Thesis on lithium-ion battery state estimation"],
            ),
            "experience": [
                _experience_entry(
                    role="Senior BMS Firmware Engineer",
                    org="VinFast — Battery Platform",
                    timeframe="01/2021 - 01/2025",
                    location="Hải Phòng",
                    highlights=[
                        "Led a team of 4 building safety-critical C and C++ battery "
                        "management system firmware on Embedded Linux and ARM Cortex-M "
                        "for automotive EV battery packs.",
                        "Owned the CAN bus communication stack and the ISO 26262 ASIL-C "
                        "safety case, and wrote MISRA-C compliant safety-critical code.",
                        "Developed State of Charge (SoC), State of Health (SoH), and "
                        "cell-balancing algorithms in MATLAB and Simulink, improving "
                        "efficiency by 18%.",
                        "Built Python automation for hardware-in-the-loop (HIL) validation, "
                        "cutting test time by 40%.",
                        "Communicated in English with international engineering teams and "
                        "mentored junior engineers; strong problem-solving and communication.",
                    ],
                )
            ],
            "skills": [
                ("C", 92), ("C++", 90), ("Battery Systems", 88), ("Embedded Linux", 86),
                ("MATLAB", 85), ("Simulink", 84), ("Python", 80), ("ISO 26262", 82),
                ("CAN", 84), ("RTOS", 82),
            ],
            "certifications": ["ISO 26262 Functional Safety Professional"],
            "languages": _ENGLISH_LANGUAGES,
        },
        # --- TOP tier (target fit >= 85)
        {
            "key": 2,
            "name": "[QA Demo] Lê Thị Mai",
            "headline": "Embedded Battery Systems Engineer",
            "summary": (
                "Embedded firmware engineer with 3 years of C and C++ development for "
                "battery systems on Embedded Linux, strong MATLAB and Simulink modelling, "
                "Python scripting, and CAN bus experience."
            ),
            "education": _experience_entry(
                role="Bachelor of Science (B.Sc.) in Mechatronics Engineering",
                org="Hanoi University of Science and Technology",
                timeframe="09/2016 - 06/2020",
                location="Hà Nội",
                highlights=["GPA 3.7/4.0"],
            ),
            "experience": [
                _experience_entry(
                    role="Battery Firmware Engineer",
                    org="Bosch Vietnam",
                    timeframe="07/2021 - 01/2025",
                    location="Hà Nội",
                    highlights=[
                        "Developed safety-critical C and C++ firmware for automotive "
                        "battery management systems on Embedded Linux and ARM Cortex-M.",
                        "Designed State of Charge (SoC) and cell-monitoring algorithms in "
                        "MATLAB and Simulink.",
                        "Integrated CAN bus communication with the vehicle control module "
                        "and increased data throughput by 25%.",
                        "Automated hardware-in-the-loop (HIL) regression tests in Python; "
                        "wrote English documentation and collaborated with engineering teams.",
                    ],
                )
            ],
            "skills": [
                ("C", 88), ("C++", 84), ("Battery Systems", 82), ("Embedded Linux", 82),
                ("MATLAB", 84), ("Simulink", 80), ("Python", 78), ("CAN", 80), ("RTOS", 76),
            ],
            "languages": _ENGLISH_LANGUAGES,
        },
        # --- STRONG tier (target 70-84): all required, few preferred
        {
            "key": 3,
            "name": "[QA Demo] Phạm Văn Long",
            "headline": "Embedded C/C++ Engineer",
            "summary": (
                "Embedded engineer with 2 years of C and C++ firmware for battery systems "
                "on Embedded Linux, with MATLAB and Simulink modelling experience."
            ),
            "education": _experience_entry(
                role="B.Sc. in Electronics & Telecommunications",
                org="Posts and Telecommunications Institute of Technology",
                timeframe="09/2017 - 06/2021",
                location="Hà Nội",
                highlights=["GPA 3.4/4.0"],
            ),
            "experience": [
                _experience_entry(
                    role="Embedded Software Engineer",
                    org="Viettel High Tech",
                    timeframe="03/2022 - 03/2024",
                    location="Hà Nội",
                    highlights=[
                        "Wrote C and C++ firmware for a battery management system on Embedded Linux.",
                        "Validated control logic in MATLAB and Simulink.",
                        "Improved firmware reliability, reducing field defects by 15%.",
                    ],
                )
            ],
            "skills": [
                ("C", 84), ("C++", 80), ("Battery Systems", 72), ("Embedded Linux", 78),
                ("MATLAB", 78), ("Simulink", 70), ("Git", 80),
            ],
            "languages": _ENGLISH_LANGUAGES,
        },
        # --- STRONG tier (target 70-84)
        {
            "key": 4,
            "name": "[QA Demo] Đỗ Hoàng Nam",
            "headline": "Firmware Engineer — Embedded Linux",
            "summary": (
                "Firmware engineer with 2 years of C and C++ development on Embedded Linux, "
                "MATLAB modelling, and Python tooling for embedded devices."
            ),
            "education": _experience_entry(
                role="B.Sc. in Computer Engineering",
                org="VNU University of Engineering and Technology",
                timeframe="09/2017 - 06/2021",
                location="Hà Nội",
                highlights=["GPA 3.3/4.0"],
            ),
            "experience": [
                _experience_entry(
                    role="Embedded Firmware Engineer",
                    org="Rikkeisoft",
                    timeframe="05/2022 - 05/2024",
                    location="Hà Nội",
                    highlights=[
                        "Built C and C++ firmware on Embedded Linux for IoT battery-powered devices.",
                        "Used MATLAB for signal processing and Python for build tooling.",
                        "Improved power efficiency by 10%.",
                    ],
                )
            ],
            "skills": [
                ("C", 82), ("C++", 78), ("Embedded Linux", 80), ("MATLAB", 74),
                ("Python", 76), ("Battery Systems", 60), ("Git", 78),
            ],
            "languages": _ENGLISH_LANGUAGES,
        },
        # --- MIXED tier (target 50-69): partial required, thin experience
        {
            "key": 5,
            "name": "[QA Demo] Nguyễn Thu Hà",
            "headline": "Junior Embedded Developer",
            "summary": (
                "Junior developer with 1 year of C and C++ experience and MATLAB coursework, "
                "interested in embedded and control systems."
            ),
            "education": _experience_entry(
                role="B.Sc. in Automation & Control",
                org="Thai Nguyen University of Technology",
                timeframe="09/2019 - 06/2023",
                location="Thái Nguyên",
                highlights=["GPA 3.1/4.0"],
            ),
            "experience": [
                _experience_entry(
                    role="Junior Embedded Developer",
                    org="MK Group",
                    timeframe="07/2023 - 07/2024",
                    location="Hà Nội",
                    highlights=[
                        "Assisted with C firmware for microcontroller boards.",
                        "Used MATLAB for basic signal analysis.",
                    ],
                )
            ],
            "skills": [
                ("C", 70), ("C++", 62), ("MATLAB", 66), ("Git", 68), ("Python", 55),
            ],
        },
        # --- MIXED tier (target 50-69)
        {
            "key": 6,
            "name": "[QA Demo] Vũ Đình Khoa",
            "headline": "Embedded Software Trainee",
            "summary": (
                "Embedded software trainee with C programming skills on Linux and some "
                "MATLAB experience from university projects."
            ),
            "education": _experience_entry(
                role="B.Sc. in Electronics Engineering",
                org="Le Quy Don Technical University",
                timeframe="09/2020 - 06/2024",
                location="Hà Nội",
                highlights=["GPA 3.0/4.0"],
            ),
            "experience": [
                _experience_entry(
                    role="Embedded Software Trainee",
                    org="Elcom",
                    timeframe="01/2024 - 10/2024",
                    location="Hà Nội",
                    highlights=[
                        "Supported C development on Embedded Linux for sensor gateways.",
                        "Helped run MATLAB test benches.",
                    ],
                )
            ],
            "skills": [
                ("C", 66), ("Embedded Linux", 58), ("MATLAB", 60), ("Git", 64),
            ],
        },
        # --- DEVELOPING tier (target < 50): little relevant overlap
        {
            "key": 7,
            "name": "[QA Demo] Hoàng Anh Tú",
            "headline": "Web Developer",
            "summary": (
                "Web developer with JavaScript and React experience, learning C on the side, "
                "exploring a move into embedded systems."
            ),
            "education": _experience_entry(
                role="B.Sc. in Information Technology",
                org="Hanoi Open University",
                timeframe="09/2019 - 06/2023",
                location="Hà Nội",
                highlights=["GPA 3.0/4.0"],
            ),
            "experience": [
                _experience_entry(
                    role="Frontend Web Developer",
                    org="Local software agency",
                    timeframe="08/2023 - 08/2024",
                    location="Hà Nội",
                    highlights=[
                        "Built React web applications with JavaScript and TypeScript.",
                        "Learning C programming in personal projects.",
                    ],
                )
            ],
            "skills": [
                ("JavaScript", 78), ("React", 74), ("C", 45), ("Git", 72),
            ],
        },
        # --- DEVELOPING tier (target < 50)
        {
            "key": 8,
            "name": "[QA Demo] Bùi Khánh Vy",
            "headline": "Data Analyst",
            "summary": (
                "Data analyst with MATLAB and Python skills for data processing, curious "
                "about hardware and battery systems."
            ),
            "education": _experience_entry(
                role="B.Sc. in Applied Mathematics",
                org="VNU University of Science",
                timeframe="09/2019 - 06/2023",
                location="Hà Nội",
                highlights=["GPA 3.4/4.0"],
            ),
            "experience": [
                _experience_entry(
                    role="Data Analyst",
                    org="Consumer research firm",
                    timeframe="07/2023 - 09/2024",
                    location="Hà Nội",
                    highlights=[
                        "Analyzed survey data in MATLAB and Python.",
                        "Produced dashboards and statistical reports.",
                    ],
                )
            ],
            "skills": [
                ("MATLAB", 72), ("Python", 76), ("SQL", 70), ("Statistics", 74),
            ],
        },
    ]


# --------------------------------------------------------------------------- #
# DB helpers                                                                    #
# --------------------------------------------------------------------------- #


async def _get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()


async def _get_or_create_demo_user(session: AsyncSession, *, email: str, name: str) -> User:
    existing = await _get_user_by_email(session, email)
    if existing is not None:
        return existing
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=name,
        password_hash=hash_password("123456"),
        is_active=True,
        is_superadmin=False,
        preferred_language="vi",
        email_verified_at=_now(),
    )
    session.add(user)
    await session.flush()
    session.add(UserPreference(user_id=user.id, locale="vi"))
    session.add(
        Identity(
            id=uuid.uuid4(),
            user_id=user.id,
            persona="student",
            org_id=None,
            is_primary=True,
        )
    )
    await session.flush()
    return user


def _now():
    from datetime import UTC, datetime

    return datetime.now(tz=UTC)


def _principal_for(user: User) -> Principal:
    return Principal(
        user_id=user.id,
        persona="student",
        org_id=None,
        is_superadmin=False,
        permissions=STUDENT_PERMS,
    )


async def _find_ready_cv(
    session: AsyncSession, *, user_id: uuid.UUID, title: str
) -> CvProfile | None:
    return (
        await session.execute(
            select(CvProfile).where(
                CvProfile.user_id == user_id,
                CvProfile.title == title,
                CvProfile.deleted_at.is_(None),
                CvProfile.status == catalog.CV_READY,
            )
        )
    ).scalar_one_or_none()


async def _latest_version_id(session: AsyncSession, *, cv_id: uuid.UUID) -> uuid.UUID:
    row = (
        await session.execute(
            select(CvVersion.id)
            .where(CvVersion.cv_id == cv_id)
            .order_by(CvVersion.version_number.desc())
        )
    ).scalars().first()
    assert row is not None, f"CV {cv_id} has no version row"
    return row


async def _create_ready_cv(
    session: AsyncSession, *, user: User, spec: dict, title: str
) -> CvProfile:
    """Create a READY library CV via the real ingestion -> creation path."""

    extracted = _build_extracted(spec)
    sections = ingestion_service._sections_from_extracted(extracted)
    principal = _principal_for(user)
    detail = await cv_creation_service.create_cv_from_sections(
        session,
        principal=principal,
        title=title,
        language="en",
        template_id=None,
        sections=sections,
        source_type=catalog.SOURCE_TYPE_FOR_MODE[catalog.CREATION_UPLOADED_IMPORT],
        change_source="import",
        ctx=CTX,
        audit_action="cv.imported_from_upload",
        audit_extra={"seed": "qa_student_demo"},
        locale="en",
    )
    cv = (
        await session.execute(
            select(CvProfile).where(CvProfile.id == uuid.UUID(detail["id"]))
        )
    ).scalar_one()
    return cv


# --------------------------------------------------------------------------- #
# Reset (demo-scoped only)                                                      #
# --------------------------------------------------------------------------- #


async def _reset_demo(session: AsyncSession) -> None:
    """Delete demo-scoped applications + CVs so content can be re-tuned.

    Scope is strictly the synthetic demo applicants (email domain) and the
    student's demo CV (by title). Real seed data is never touched. Demo users are
    kept (get-or-create). Applications cascade their snapshots; cv_profiles cascade
    sections/versions/fit rows.
    """

    demo_ids = list(
        (
            await session.execute(
                select(User.id).where(User.email.like(f"qa.demo.applicant.%@{DEMO_EMAIL_DOMAIN}"))
            )
        ).scalars().all()
    )
    if demo_ids:
        await session.execute(
            text("DELETE FROM applications WHERE applicant_id = ANY(:ids)"),
            {"ids": demo_ids},
        )
        await session.execute(
            text("DELETE FROM cv_profiles WHERE user_id = ANY(:ids)"),
            {"ids": demo_ids},
        )

    student = await _get_user_by_email(session, STUDENT_EMAIL)
    if student is not None:
        await session.execute(
            text(
                "DELETE FROM cv_profiles WHERE user_id = :uid AND title = :title"
            ),
            {"uid": student.id, "title": STUDENT_CV_TITLE},
        )
    await session.commit()
    print(f"[reset] cleared {len(demo_ids)} demo applicant(s) + student demo CV")


# --------------------------------------------------------------------------- #
# Main flow                                                                     #
# --------------------------------------------------------------------------- #


async def _seed_student_cv(session: AsyncSession) -> tuple[uuid.UUID, dict]:
    student = await _get_user_by_email(session, STUDENT_EMAIL)
    assert student is not None, (
        f"{STUDENT_EMAIL} not found in QA DB — run seed_dev.py against it first"
    )
    existing = await _find_ready_cv(session, user_id=student.id, title=STUDENT_CV_TITLE)
    if existing is not None:
        cv = existing
        print(f"[student] reusing existing demo CV {cv.id}")
    else:
        cv = await _create_ready_cv(
            session, user=student, spec=STUDENT_SPEC, title=STUDENT_CV_TITLE
        )
        print(f"[student] created ready CV {cv.id}")

    # Deterministic BMS fit for the student's library (what the Analyze drawer shows).
    principal = _principal_for(student)
    fit = await job_fit_service.job_fit_for_job(
        session, principal=principal, job_id=BMS_JOB_ID
    )
    return student.id, fit


async def _seed_applicants(session: AsyncSession) -> list[dict]:
    results: list[dict] = []
    for spec in _applicant_specs():
        email = f"qa.demo.applicant.{spec['key']}@{DEMO_EMAIL_DOMAIN}"
        user = await _get_or_create_demo_user(session, email=email, name=spec["name"])
        principal = _principal_for(user)

        cv = await _find_ready_cv(session, user_id=user.id, title=DEMO_CV_TITLE)
        if cv is None:
            cv = await _create_ready_cv(
                session, user=user, spec=spec, title=DEMO_CV_TITLE
            )
        version_id = await _latest_version_id(session, cv_id=cv.id)

        # Apply through the REAL apply flow (freezes the apply-time snapshot fit).
        app_view = await apply_service.apply_to_job(
            session,
            principal=principal,
            payload={
                "job_id": str(BMS_JOB_ID),
                "cv_selection": {
                    "type": "builder_cv",
                    "cv_profile_id": str(cv.id),
                    "cv_version_id": str(version_id),
                },
                "idempotency_key": f"qa-demo-apply:{email}:{BMS_JOB_ID}",
            },
            ctx=CTX,
            locale="en",
        )
        # Read back the frozen snapshot fit for the summary.
        fit_score = (
            await session.execute(
                text(
                    "SELECT s.fit_score FROM applications a"
                    " JOIN application_cv_snapshots s ON a.snapshot_id = s.id"
                    " WHERE a.id = :app_id"
                ),
                {"app_id": uuid.UUID(app_view["id"])},
            )
        ).scalar_one_or_none()
        results.append(
            {"name": spec["name"], "email": email, "cv_id": str(cv.id), "fit": fit_score}
        )
    return results


async def _refresh_and_read(
    session: AsyncSession, *, student_id: uuid.UUID, student_fit: int | None
) -> tuple[scoring.CompetitionStats, dict]:
    job = (
        await session.execute(select(Job).where(Job.id == BMS_JOB_ID))
    ).scalar_one()
    # Explicitly materialize the projection row for the BMS job (the per-apply
    # refresh inside apply_to_job is a no-op because JobRef carries no headcount —
    # see the handoff notes). Uses the live seat count.
    stats = await projection_service.refresh_job_competition(
        session, job_id=job.id, org_id=job.org_id, seats=job.headcount
    )
    await session.commit()

    # The exact student-facing competition sub-object the drawer renders.
    student = await _get_user_by_email(session, STUDENT_EMAIL)
    assert student is not None
    student_principal = _principal_for(student)
    comp = await competition_service.student_competition_intelligence(
        session,
        principal=student_principal,
        job_id=BMS_JOB_ID,
        student_fit_score=student_fit,
        locale="en",
    )
    return stats, comp


def _print_summary(
    *,
    student_id: uuid.UUID,
    student_fit: dict,
    applicants: list[dict],
    stats: scoring.CompetitionStats,
    comp: dict,
) -> None:
    print("\n" + "=" * 74)
    print("QA STUDENT DEMO — SUMMARY (BMS job", BMS_JOB_ID, ")")
    print("=" * 74)

    rec_cv = student_fit.get("recommended_cv_id")
    rec = next(
        (r for r in student_fit.get("results", []) if str(r.get("cv_id")) == str(rec_cv)),
        None,
    )
    print("\n[STUDENT — Analyze CV drawer]")
    print(f"  student user_id : {student_id}")
    print(f"  recommended CV  : {rec_cv}")
    if rec is not None:
        print(f"  deterministic fit: {rec.get('score')}  bands={rec.get('bands')}")
        print(f"  matched_skills  : {rec.get('matched_skills')}")
        print(f"  gaps            : {rec.get('gaps')}")
    print(f"  fit signal      : {student_fit.get('signal')}")

    print("\n[COMPETITION POOL — apply-time snapshot fits]")
    scored = [a["fit"] for a in applicants if a["fit"] is not None]
    for a in applicants:
        print(f"  fit={str(a['fit']).rjust(4)}  {a['name']}  ({a['email']})")
    print(f"\n  active applications : {stats.active_applications}")
    print(f"  scored applicants   : {stats.scored_applicants}  (fits: {sorted(scored)})")
    print(
        "  histogram           : "
        f"developing={stats.dist_developing} mixed={stats.dist_mixed} "
        f"strong={stats.dist_strong} top={stats.dist_top}  (seats={stats.seats})"
    )

    print("\n[COMPETITION drawer — student-facing signal]")
    for key in (
        "signal", "score", "label", "basis",
        "seats_bucket", "application_volume_bucket", "applicants_per_seat_band",
        "strong_competitor_density", "applicant_quality_bucket",
        "student_fit_bucket", "student_standing_bucket", "standing_vs_strong",
        "deadline_freshness",
    ):
        print(f"  {key:<26}: {comp.get(key)}")
    print(f"  guidance                  : {comp.get('guidance')}")
    print("=" * 74)


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if "vinuni_student_qa" not in db_url:
        raise SystemExit(
            "Refusing to run: DATABASE_URL must point at the QA DB "
            "(postgresql+asyncpg://.../vinuni_student_qa). Current: " + (db_url or "<unset>")
        )

    sessionmaker = get_sessionmaker()
    try:
        if os.environ.get("QA_DEMO_RESET") == "1":
            async with sessionmaker() as session:
                await _reset_demo(session)

        async with sessionmaker() as session:
            student_id, student_fit = await _seed_student_cv(session)

        async with sessionmaker() as session:
            applicants = await _seed_applicants(session)

        # Student fit score to feed the competition standing.
        rec_cv = student_fit.get("recommended_cv_id")
        student_fit_score = next(
            (
                r.get("score")
                for r in student_fit.get("results", [])
                if str(r.get("cv_id")) == str(rec_cv)
            ),
            None,
        )

        async with sessionmaker() as session:
            stats, comp = await _refresh_and_read(
                session, student_id=student_id, student_fit=student_fit_score
            )

        _print_summary(
            student_id=student_id,
            student_fit=student_fit,
            applicants=applicants,
            stats=stats,
            comp=comp,
        )
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
