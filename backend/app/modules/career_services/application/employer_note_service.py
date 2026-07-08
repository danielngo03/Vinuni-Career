"""Employer relationship notes (B-554).

RBAC resource: ``career_services_notes``. ``visibility`` is metadata only in
this slice (no cross-counselor read filtering is implemented yet beyond org
scoping) — see the handoff "open questions" for the department-scoped filter
follow-up.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.career_services.application.common import audit_ctx, require_org
from app.modules.career_services.domain import catalog
from app.modules.career_services.domain.models import EmployerRelationshipNote
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = "career_services_notes"


def _presenter(note: EmployerRelationshipNote, *, locale: str = "vi") -> dict:
    return {
        "id": str(note.id),
        "employer_org_id": str(note.employer_org_id),
        "author_id": str(note.author_id),
        "category": note.category,
        "category_label": catalog.note_category_label(note.category, locale=locale),
        "visibility": note.visibility,
        "visibility_label": catalog.note_visibility_label(note.visibility, locale=locale),
        "note_text": note.note_text,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


async def _get_note(
    session: AsyncSession, *, org_id: uuid.UUID, note_id: uuid.UUID
) -> EmployerRelationshipNote | None:
    stmt = select(EmployerRelationshipNote).where(
        EmployerRelationshipNote.id == note_id,
        EmployerRelationshipNote.org_id == org_id,
        EmployerRelationshipNote.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_note(
    session: AsyncSession,
    *,
    principal: Principal,
    employer_org_id: uuid.UUID,
    category: str,
    visibility: str,
    note_text: str,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(
        principal, _RESOURCE, "create", resource_org_id=org_id
    )
    if category not in catalog.NOTE_CATEGORIES:
        raise ValidationFailedError(details={"reason": "invalid_category"})
    if visibility not in catalog.NOTE_VISIBILITIES:
        raise ValidationFailedError(details={"reason": "invalid_visibility"})
    if not note_text or not note_text.strip():
        raise ValidationFailedError(details={"reason": "note_text_required"})

    note = EmployerRelationshipNote(
        org_id=org_id,
        employer_org_id=employer_org_id,
        author_id=principal.user_id,
        category=category,
        visibility=visibility,
        note_text=note_text.strip(),
    )
    session.add(note)
    await session.flush()
    await write_audit(
        session,
        action="career_services.employer_note.created",
        resource_type="career_services_employer_note",
        resource_id=note.id,
        context=audit_ctx(principal, ctx),
        after={"employer_org_id": str(employer_org_id), "category": category},
    )
    await session.commit()
    return _presenter(note, locale=locale)


async def list_notes(
    session: AsyncSession,
    *,
    principal: Principal,
    employer_org_id: uuid.UUID | None = None,
    locale: str = "vi",
) -> list[dict]:
    org_id = require_org(principal)
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=org_id)
    stmt = select(EmployerRelationshipNote).where(
        EmployerRelationshipNote.org_id == org_id,
        EmployerRelationshipNote.deleted_at.is_(None),
    )
    if employer_org_id is not None:
        stmt = stmt.where(EmployerRelationshipNote.employer_org_id == employer_org_id)
    stmt = stmt.order_by(EmployerRelationshipNote.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [_presenter(n, locale=locale) for n in rows]


async def update_note(
    session: AsyncSession,
    *,
    principal: Principal,
    note_id: uuid.UUID,
    note_text: str | None,
    category: str | None,
    visibility: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    org_id = require_org(principal)
    permission_checker.require(
        principal, _RESOURCE, "update", resource_org_id=org_id
    )
    note = await _get_note(session, org_id=org_id, note_id=note_id)
    if note is None:
        raise ResourceNotFoundError()
    if category is not None:
        if category not in catalog.NOTE_CATEGORIES:
            raise ValidationFailedError(details={"reason": "invalid_category"})
        note.category = category
    if visibility is not None:
        if visibility not in catalog.NOTE_VISIBILITIES:
            raise ValidationFailedError(details={"reason": "invalid_visibility"})
        note.visibility = visibility
    if note_text is not None:
        if not note_text.strip():
            raise ValidationFailedError(details={"reason": "note_text_required"})
        note.note_text = note_text.strip()
    await session.flush()
    await session.refresh(note)
    await write_audit(
        session,
        action="career_services.employer_note.updated",
        resource_type="career_services_employer_note",
        resource_id=note.id,
        context=audit_ctx(principal, ctx),
    )
    await session.commit()
    return _presenter(note, locale=locale)
