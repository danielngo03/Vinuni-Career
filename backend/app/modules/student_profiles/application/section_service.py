"""Owner-only CRUD for the profile child collections: education, experience,
skills, and links.

All four share the same shape: a child belongs to exactly one profile, is only
ever touched by that profile's owner (cross-owner access returns ``404``), carries
its own optimistic ``version``, is soft-deleted, and refreshes the parent
profile's completion cache on every write. Every write is audited.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.student_profiles.api import presenters
from app.modules.student_profiles.application import _shared, loaders
from app.modules.student_profiles.application.errors import (
    DuplicateSkillError,
    InvalidProfileFieldError,
    ProfileVersionConflictError,
)
from app.modules.student_profiles.domain import vocab
from app.modules.student_profiles.domain.models import (
    StudentEducation,
    StudentExperience,
    StudentLink,
    StudentProfile,
    StudentSkill,
)
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


@dataclass(slots=True)
class _Spec:
    model: type[Any]
    audit_type: str
    presenter: Callable[..., dict]
    apply: Callable[[Any, dict], None]


# --------------------------------------------------------------------------- #
# Field appliers (validation + assignment)                                     #
# --------------------------------------------------------------------------- #


def _apply_education(row: StudentEducation, payload: dict) -> None:
    if "institution" in payload:
        institution = (payload["institution"] or "").strip()
        if not institution:
            raise InvalidProfileFieldError(field="institution")
        row.institution = institution
    for f in ("degree", "field_of_study", "description"):
        if f in payload:
            setattr(row, f, payload[f])
    if "start_date" in payload:
        row.start_date = _shared.parse_date(payload["start_date"], field="start_date")
    if "end_date" in payload:
        row.end_date = _shared.parse_date(payload["end_date"], field="end_date")
    if "is_current" in payload:
        row.is_current = bool(payload["is_current"])
    if "gpa" in payload:
        row.gpa = payload["gpa"]
    if "sort_order" in payload and payload["sort_order"] is not None:
        row.sort_order = int(payload["sort_order"])


def _apply_experience(row: StudentExperience, payload: dict) -> None:
    if "company_name" in payload:
        company = (payload["company_name"] or "").strip()
        if not company:
            raise InvalidProfileFieldError(field="company_name")
        row.company_name = company
    if "title" in payload:
        title = (payload["title"] or "").strip()
        if not title:
            raise InvalidProfileFieldError(field="title")
        row.title = title
    if "employment_type" in payload:
        et = payload["employment_type"]
        if et is not None and et not in vocab.EMPLOYMENT_TYPES:
            raise InvalidProfileFieldError(field="employment_type")
        row.employment_type = et
    if "location" in payload:
        row.location = payload["location"]
    if "description" in payload:
        row.description = payload["description"]
    if "start_date" in payload:
        row.start_date = _shared.parse_date(payload["start_date"], field="start_date")
    if "end_date" in payload:
        row.end_date = _shared.parse_date(payload["end_date"], field="end_date")
    if "is_current" in payload:
        row.is_current = bool(payload["is_current"])
    if "skills_used" in payload:
        skills = payload["skills_used"]
        if skills is not None and not isinstance(skills, list):
            raise InvalidProfileFieldError(field="skills_used")
        row.skills_used = list(skills or [])
    if "sort_order" in payload and payload["sort_order"] is not None:
        row.sort_order = int(payload["sort_order"])


def _apply_skill(row: StudentSkill, payload: dict) -> None:
    if "name" in payload:
        name = (payload["name"] or "").strip()
        if not name:
            raise InvalidProfileFieldError(field="name")
        row.name = name
    if "category" in payload:
        cat = payload["category"]
        if cat is not None and cat not in vocab.SKILL_CATEGORIES:
            raise InvalidProfileFieldError(field="category")
        row.category = cat
    if "proficiency" in payload:
        prof = payload["proficiency"]
        if prof is not None and (not isinstance(prof, int) or not 1 <= prof <= 5):
            raise InvalidProfileFieldError(field="proficiency")
        row.proficiency = prof
    if "sort_order" in payload and payload["sort_order"] is not None:
        row.sort_order = int(payload["sort_order"])


def _apply_link(row: StudentLink, payload: dict) -> None:
    if "url" in payload:
        url = (payload["url"] or "").strip()
        if not url:
            raise InvalidProfileFieldError(field="url")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValidationFailedError("Đường liên kết phải bắt đầu bằng http(s)://.")
        row.url = url
    if "label" in payload:
        row.label = payload["label"]
    if "sort_order" in payload and payload["sort_order"] is not None:
        row.sort_order = int(payload["sort_order"])


_SPECS: dict[str, _Spec] = {
    "education": _Spec(
        StudentEducation, "student_education", presenters.education, _apply_education
    ),
    "experience": _Spec(
        StudentExperience, "student_experience", presenters.experience, _apply_experience
    ),
    "skill": _Spec(StudentSkill, "student_skill", presenters.skill, _apply_skill),
    "link": _Spec(StudentLink, "student_link", presenters.link, _apply_link),
}


# --------------------------------------------------------------------------- #
# Generic helpers                                                              #
# --------------------------------------------------------------------------- #


async def _next_sort_order(
    session: AsyncSession, *, spec: _Spec, student_id: uuid.UUID
) -> int:
    rows = (
        await session.execute(
            select(spec.model.sort_order).where(
                spec.model.student_id == student_id,
                spec.model.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return (max(rows, default=0) or 0) + 10


async def _load_owned_child(
    session: AsyncSession,
    *,
    spec: _Spec,
    profile: StudentProfile,
    child_id: uuid.UUID,
    lock: bool = False,
) -> Any:
    stmt = select(spec.model).where(
        spec.model.id == child_id,
        spec.model.student_id == profile.id,
        spec.model.deleted_at.is_(None),
    )
    if lock and _shared.use_for_update():
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ResourceNotFoundError()
    return row


# --------------------------------------------------------------------------- #
# Create / update / delete / list                                             #
# --------------------------------------------------------------------------- #


async def create_item(
    session: AsyncSession,
    *,
    kind: str,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    spec = _SPECS[kind]
    permission_checker.require(principal, _RESOURCE, "create")
    profile = await _shared.load_owned_profile(session, principal=principal, lock=True)

    if kind == "skill":
        await _ensure_skill_unique(session, profile=profile, name=payload.get("name"))

    row = spec.model(student_id=profile.id)
    spec.apply(row, payload)
    if payload.get("sort_order") is None:
        row.sort_order = await _next_sort_order(session, spec=spec, student_id=profile.id)
    session.add(row)
    await session.flush()

    await loaders.recompute_completion(session, profile=profile)
    await write_audit(
        session,
        action=f"{spec.audit_type}.created",
        resource_type=spec.audit_type,
        resource_id=row.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"profile_id": str(profile.id)},
    )
    await session.commit()
    await session.refresh(row)
    return spec.presenter(row, locale=locale)


async def update_item(
    session: AsyncSession,
    *,
    kind: str,
    principal: Principal,
    child_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    spec = _SPECS[kind]
    permission_checker.require(principal, _RESOURCE, "update")
    profile = await _shared.load_owned_profile(session, principal=principal, lock=True)
    row = await _load_owned_child(
        session, spec=spec, profile=profile, child_id=child_id, lock=True
    )

    expected = payload.get("expected_version")
    if expected is not None and expected != row.version:
        raise ProfileVersionConflictError(current_version=row.version)

    if kind == "skill" and payload.get("name"):
        await _ensure_skill_unique(
            session, profile=profile, name=payload["name"], exclude_id=row.id
        )

    spec.apply(row, payload)
    row.version += 1
    await session.flush()

    await loaders.recompute_completion(session, profile=profile)
    await write_audit(
        session,
        action=f"{spec.audit_type}.updated",
        resource_type=spec.audit_type,
        resource_id=row.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"profile_id": str(profile.id)},
    )
    await session.commit()
    await session.refresh(row)
    return spec.presenter(row, locale=locale)


async def delete_item(
    session: AsyncSession,
    *,
    kind: str,
    principal: Principal,
    child_id: uuid.UUID,
    ctx: RequestContext,
) -> dict:
    spec = _SPECS[kind]
    permission_checker.require(principal, _RESOURCE, "delete")
    profile = await _shared.load_owned_profile(session, principal=principal, lock=True)
    row = await _load_owned_child(
        session, spec=spec, profile=profile, child_id=child_id, lock=True
    )

    row.deleted_at = _shared.now()
    await session.flush()

    await loaders.recompute_completion(session, profile=profile)
    await write_audit(
        session,
        action=f"{spec.audit_type}.deleted",
        resource_type=spec.audit_type,
        resource_id=row.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"profile_id": str(profile.id)},
    )
    await session.commit()
    return {"id": str(child_id), "deleted": True}


_LIST_LOADERS: dict[str, Callable] = {
    "education": loaders.load_education,
    "experience": loaders.load_experience,
    "skill": loaders.load_skills,
    "link": loaders.load_links,
}


async def list_items(
    session: AsyncSession, *, kind: str, principal: Principal, locale: str = "vi"
) -> list[dict]:
    spec = _SPECS[kind]
    permission_checker.require(principal, _RESOURCE, "read")
    profile = await _shared.load_owned_profile(session, principal=principal)
    rows = await _LIST_LOADERS[kind](session, student_id=profile.id)
    return [spec.presenter(r, locale=locale) for r in rows]


# --------------------------------------------------------------------------- #
# Skill uniqueness (per profile, case-insensitive)                            #
# --------------------------------------------------------------------------- #


async def _ensure_skill_unique(
    session: AsyncSession,
    *,
    profile: StudentProfile,
    name: str | None,
    exclude_id: uuid.UUID | None = None,
) -> None:
    if not name:
        return
    normalized = name.strip().lower()
    rows = (
        await session.execute(
            select(StudentSkill).where(
                StudentSkill.student_id == profile.id,
                StudentSkill.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for r in rows:
        if r.id == exclude_id:
            continue
        if (r.name or "").strip().lower() == normalized:
            raise DuplicateSkillError()
