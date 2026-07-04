"""CV builder creation service: create (non-AI modes), create-from-sections, and
duplicate.

RBAC + ownership are enforced here (students hold ``cv:*``); a CV is only ever
accessed by its owner, and cross-owner access returns ``404``. Every accepted
creation writes an initial ``cv_versions`` row and an audit entry.

The ``ai_assisted_draft`` creation mode is delegated to ``cv_ai_service``
(requires ai-engineer-approved prompts/confirmation).
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import (
    CvSourceRequiredError,
    InvalidCvFieldError,
)
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import (
    CvParseRun,
    CvProfile,
    CvSection,
    CvTemplate,
    Document,
)
from app.modules.users.application import user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


# --------------------------------------------------------------------------- #
# Create                                                                      #
# --------------------------------------------------------------------------- #


async def create_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None

    # Active-CV library quota — enforced before any creation mode (including the
    # delegated AI draft, which also inserts a new CvProfile).
    await _cv_core._enforce_active_cv_quota(session, principal=principal)

    mode = payload.get("creation_mode", catalog.CREATION_BLANK)
    if mode == catalog.CREATION_AI_DRAFT:
        # Delegated to the AI slice: creates a blank draft + a pending AI
        # suggestion (ARCHITECTURE §4.3b). Lazy import avoids a circular import.
        from app.modules.documents.application import cv_ai_service

        return await cv_ai_service.create_ai_draft(
            session, principal=principal, payload=payload, ctx=ctx, locale=locale
        )
    if mode not in catalog.NON_AI_CREATION_MODES:
        raise InvalidCvFieldError(field="creation_mode")

    language = payload.get("language") or "vi"
    title = payload.get("title") or "Untitled CV"
    template_id = _shared.to_uuid(payload.get("template_id"))
    source = payload.get("source") or {}

    template: CvTemplate | None = None
    if template_id is not None:
        template = (
            await session.execute(select(CvTemplate).where(CvTemplate.id == template_id))
        ).scalar_one_or_none()
        if template is None or not template.is_active:
            raise InvalidCvFieldError(field="template_id")

    cv = CvProfile(
        user_id=principal.user_id,
        title=title,
        source_type=catalog.SOURCE_TYPE_FOR_MODE[mode],
        template_id=template.id if template else None,
        language=language,
        status=catalog.CV_DRAFT,
    )
    session.add(cv)
    await session.flush()

    # Build the section set per creation mode.
    if mode == catalog.CREATION_BLANK:
        await _cv_core._seed_sections(session, cv_id=cv.id, sections=catalog.DEFAULT_SECTIONS)
        change_source = "manual"
    elif mode == catalog.CREATION_PROFILE_IMPORT:
        sections = await _sections_from_profile(
            session, user_id=principal.user_id, notes=source.get("raw_notes")
        )
        await _cv_core._seed_sections(session, cv_id=cv.id, sections=sections)
        change_source = "import"
    elif mode == catalog.CREATION_NOTES_IMPORT:
        sections = _sections_from_notes(source.get("raw_notes"))
        await _cv_core._seed_sections(session, cv_id=cv.id, sections=sections)
        change_source = "import"
    elif mode == catalog.CREATION_UPLOADED_IMPORT:
        sections = await _sections_from_upload(session, principal=principal, source=source)
        await _cv_core._seed_sections(session, cv_id=cv.id, sections=sections)
        change_source = "import"
    else:  # duplicate_existing
        await _copy_sections_from_cv(
            session, principal=principal, source=source, target_cv_id=cv.id
        )
        change_source = "import"

    await _cv_core._snapshot_version(
        session, cv=cv, change_source=change_source,
        change_summary="initial", created_by=principal.user_id,
    )
    await write_audit(
        session, action="cv.created", resource_type="cv", resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"source_type": cv.source_type, "creation_mode": mode},
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)


async def create_cv_from_sections(
    session: AsyncSession,
    *,
    principal: Principal,
    title: str,
    language: str,
    template_id: uuid.UUID | None,
    sections: list[dict],
    source_type: str,
    change_source: str,
    ctx: RequestContext,
    audit_action: str = "cv.created",
    audit_extra: dict | None = None,
    locale: str = "vi",
) -> dict:
    """Create a NEW versioned draft CV from a prepared section set (owner-only).

    Shared by the blank/upload creation modes and the ingestion import flow so the
    quota gate (``409 QUOTA_EXCEEDED``), the initial immutable ``cv_versions``
    snapshot, and the audit write are enforced in exactly one place. Never mutates
    an existing CV.
    """

    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None
    await _cv_core._enforce_active_cv_quota(session, principal=principal)

    template_uuid = _shared.to_uuid(template_id)
    if template_uuid is not None:
        tpl = (
            await session.execute(select(CvTemplate).where(CvTemplate.id == template_uuid))
        ).scalar_one_or_none()
        if tpl is None or not tpl.is_active:
            raise InvalidCvFieldError(field="template_id")

    cv = CvProfile(
        user_id=principal.user_id,
        title=title or "Untitled CV",
        source_type=source_type,
        template_id=template_uuid,
        language=language or "vi",
        status=catalog.CV_DRAFT,
    )
    session.add(cv)
    await session.flush()

    await _cv_core._seed_sections(session, cv_id=cv.id, sections=sections)
    await _cv_core._snapshot_version(
        session, cv=cv, change_source=change_source,
        change_summary="initial", created_by=principal.user_id,
    )
    after = {"source_type": cv.source_type}
    if audit_extra:
        after.update(audit_extra)
    await write_audit(
        session, action=audit_action, resource_type="cv", resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx), after=after,
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)


async def _sections_from_profile(
    session: AsyncSession, *, user_id: uuid.UUID, notes: str | None
) -> list[dict]:
    """Prefill the CV from the student's structured profile (education / experience
    / skills) via the ``student_profiles`` service interface.

    Cross-module access goes through the ``student_profiles`` application interface
    (``build_cv_import_sections``), never an implementation import, so the seam
    stays clean. When the user has no profile yet, fall back to a minimal
    name/email summary seed.
    """

    from app.modules.student_profiles.application import profile_import

    sections = await profile_import.build_cv_import_sections(
        session, user_id=user_id, notes=notes
    )
    if sections is not None:
        return sections

    # Fallback: no structured profile yet -> minimal contact summary seed.
    user = await user_service.get_by_id(session, user_id)
    summary_items = []
    if user is not None:
        summary_items.append({"text": getattr(user, "full_name", "") or ""})
        summary_items.append({"text": getattr(user, "email", "") or ""})
    if notes:
        summary_items.append({"text": notes})
    fallback = [dict(s) for s in catalog.DEFAULT_SECTIONS]
    for s in fallback:
        if s["section_type"] == "summary":
            s["content_json"] = {"items": [i for i in summary_items if i["text"]]}
    return fallback


# --------------------------------------------------------------------------- #
# Deterministic "create from raw notes" seeding (CV-first; NO AI / model call)  #
# --------------------------------------------------------------------------- #
#
# docs/CV_STUDIO_SPEC.md requires CV creation to work from pasted raw notes
# WITHOUT a mandatory profile form. ``creation_mode=notes_import`` seeds the CV
# section skeleton purely from the student's own text: lines are split (same rule
# as the AI notes splitter) and routed into summary / experience / skills by a
# simple, deterministic header heuristic. Nothing is invented — every seeded item
# is a verbatim slice of the user's input.

# Mirrors ``app.ai.cv.tasks._split_notes`` so notes split identically whether the
# student picks the deterministic path or (later) the AI path. Kept local to the
# documents module to avoid importing AI-module internals across the boundary.
_NOTES_SPLIT_RE = re.compile(r"[\n;•]|(?<=[.])\s+")
_NOTES_STRIP = " -•\t"

# Header cues (vi + en) that re-route subsequent note lines into a section. Order
# does not matter; the first cue a line starts with wins.
_NOTES_SECTION_CUES: list[tuple[str, tuple[str, ...]]] = [
    (
        "summary",
        ("summary", "objective", "about me", "about", "profile",
         "mục tiêu", "muc tieu", "giới thiệu", "gioi thieu", "tóm tắt", "tom tat"),
    ),
    (
        "experience",
        ("experience", "work experience", "work history", "employment",
         "kinh nghiệm", "kinh nghiem", "công việc", "cong viec"),
    ),
    (
        "skills",
        ("technical skills", "skills", "skill",
         "kỹ năng", "ky nang", "kĩ năng"),
    ),
]


def _split_notes(notes: str | None) -> list[str]:
    if not notes:
        return []
    parts = _NOTES_SPLIT_RE.split(notes)
    return [p.strip(_NOTES_STRIP) for p in parts if p.strip(_NOTES_STRIP)]


def _match_notes_cue(line: str) -> tuple[str | None, str]:
    """If ``line`` begins with a recognized section header, return
    ``(section_type, remainder_after_separator)``; otherwise ``(None, line)``.

    Pure/deterministic. A cue only matches when it sits at the start of the line
    and is followed by a header boundary (separator or end-of-line), so a normal
    sentence that merely contains the word "skills" is NOT treated as a header.
    """

    low = line.lower().lstrip(_NOTES_STRIP)
    for section_type, cues in _NOTES_SECTION_CUES:
        for cue in cues:
            if low.startswith(cue):
                rest = low[len(cue):]
                if rest == "" or rest[0] in ":：-–—":
                    idx = line.lower().find(cue) + len(cue)
                    remainder = line[idx:].strip(" :：-–—\t")
                    return section_type, remainder
    return None, line


def _sections_from_notes(notes: str | None) -> list[dict]:
    """Deterministically seed CV sections from the user's pasted notes.

    No AI/model call. Lines before any recognized header default to ``summary``;
    a ``Skills:``-style header routes following lines (and inline comma items)
    into skills, ``Experience:`` into experience, etc. Returns the default section
    skeleton with seeded ``content_json={'items': [...]}`` where notes exist.
    """

    lines = _split_notes(notes)
    if not lines:
        raise CvSourceRequiredError(field="raw_notes")

    buckets: dict[str, list[dict]] = {"summary": [], "experience": [], "skills": []}
    current = "summary"
    for line in lines:
        section_type, remainder = _match_notes_cue(line)
        if section_type is not None:
            current = section_type
            if remainder:
                if current == "skills":
                    for piece in re.split(r"[,/]", remainder):
                        piece = piece.strip()
                        if piece:
                            buckets[current].append({"text": piece})
                else:
                    buckets[current].append({"text": remainder})
            continue
        if current == "skills":
            for piece in re.split(r"[,/]", line):
                piece = piece.strip()
                if piece:
                    buckets[current].append({"text": piece})
        else:
            buckets[current].append({"text": line})

    sections = [dict(s) for s in catalog.DEFAULT_SECTIONS]
    for s in sections:
        items = buckets.get(s["section_type"])
        if items:
            s["content_json"] = {"items": items}
    return sections


async def _sections_from_upload(
    session: AsyncSession, *, principal: Principal, source: dict
) -> list[dict]:
    document_id = _shared.to_uuid(source.get("uploaded_document_id"))
    parse_run_id = _shared.to_uuid(source.get("cv_parse_run_id"))
    if not document_id:
        raise CvSourceRequiredError(field="uploaded_document_id")

    document = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if document is None or document.user_id != principal.user_id:
        raise ResourceNotFoundError()

    run: CvParseRun | None = None
    if parse_run_id:
        run = (
            await session.execute(select(CvParseRun).where(CvParseRun.id == parse_run_id))
        ).scalar_one_or_none()
        if run is None or run.document_id != document.id:
            raise ResourceNotFoundError()

    sections = [dict(s) for s in catalog.DEFAULT_SECTIONS]
    extracted = (run.extracted_data if run else None) or {}
    for s in sections:
        section_data = extracted.get(s["section_type"])
        if isinstance(section_data, dict) and section_data.get("items"):
            s["content_json"] = {"items": list(section_data["items"])}
    return sections


async def _copy_sections_from_cv(
    session: AsyncSession, *, principal: Principal, source: dict, target_cv_id: uuid.UUID
) -> None:
    source_cv_id = _shared.to_uuid(source.get("source_cv_id"))
    if not source_cv_id:
        raise CvSourceRequiredError(field="source_cv_id")
    src = await _cv_core._load_owned_cv(session, principal=principal, cv_id=source_cv_id)
    src_sections = await _cv_core._load_sections(session, cv_id=src.id)
    for s in src_sections:
        session.add(
            CvSection(
                cv_id=target_cv_id,
                section_type=s.section_type,
                title=s.title,
                sort_order=s.sort_order,
                content_json=dict(s.content_json or {}),
                is_visible=s.is_visible,
            )
        )
    await session.flush()


# --------------------------------------------------------------------------- #
# Duplicate                                                                   #
# --------------------------------------------------------------------------- #


async def duplicate_cv(
    session: AsyncSession,
    *,
    principal: Principal,
    cv_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None

    idempotency_key = payload.get("idempotency_key")
    if idempotency_key:
        existing = (
            await session.execute(
                select(CvProfile).where(
                    CvProfile.user_id == principal.user_id,
                    CvProfile.idempotency_key == idempotency_key,
                    CvProfile.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await _cv_core._detail_response(session, cv=existing, locale=locale)

    # Active-CV library quota — enforced after the idempotency replay check (a
    # replay returns the existing copy and must not be blocked) and before insert.
    await _cv_core._enforce_active_cv_quota(session, principal=principal)

    source = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id)
    template_id = _shared.to_uuid(payload.get("template_id")) or source.template_id

    new_cv = CvProfile(
        user_id=principal.user_id,
        title=payload.get("title") or f"{source.title} (copy)",
        source_type=catalog.SOURCE_TYPE_FOR_MODE[catalog.CREATION_DUPLICATE],
        template_id=template_id,
        language=source.language,
        status=catalog.CV_DRAFT,
        idempotency_key=idempotency_key,
    )
    session.add(new_cv)
    await session.flush()

    # Copy sections from the source (source is never mutated).
    src_sections = await _cv_core._load_sections(session, cv_id=source.id)
    for s in src_sections:
        session.add(
            CvSection(
                cv_id=new_cv.id,
                section_type=s.section_type,
                title=s.title,
                sort_order=s.sort_order,
                content_json=dict(s.content_json or {}),
                is_visible=s.is_visible,
            )
        )
    await session.flush()

    await _cv_core._snapshot_version(
        session, cv=new_cv, change_source="import",
        change_summary=f"duplicate of {source.id}", created_by=principal.user_id,
    )
    await write_audit(
        session, action="cv.duplicated", resource_type="cv", resource_id=new_cv.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"source_cv_id": str(source.id)},
    )
    await session.commit()
    await session.refresh(new_cv)
    return await _cv_core._detail_response(session, cv=new_cv, locale=locale)
