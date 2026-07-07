"""CV AI suggestion orchestration (documents module).

Bridges the CV Studio data layer (``cv_service`` / ``cv_profiles`` / ``cv_sections``
/ ``cv_versions``) and the provider-agnostic CV AI task layer (``app.ai.cv``).

Guarantees (``docs/CV_STUDIO_SPEC.md`` §3, ``docs/SECURITY_PRIVACY.md``):

- AI is NON-DESTRUCTIVE: a request creates a pending ``cv_ai_suggestions`` diff and
  never mutates the CV. Acceptance creates a NEW ``cv_versions`` row.
- Owner-only; cross-owner access returns 404. Every write is audited.
- Suggest + accept are idempotent.
- Explicit ``fact_confirmation`` is required before accepting a suggestion whose
  diff is flagged ``requires_fact_confirmation``.
- No provider/model/token/prompt internals ever reach the response, the stored
  diff, or the audit log (the AI layer scrubs model text via the output guard;
  CV content is grounded deterministically).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import CvAiContext, generate_cv_edit_patch, run_cv_task
from app.ai.cv.edit_command import TASK_TYPE as _EDIT_COMMAND_TASK_TYPE
from app.ai.safety import input_guard
from app.modules.auth.application.context import RequestContext
from app.modules.documents.api import presenters
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import (
    AiSourceRequiredError,
    FactConfirmationRequiredError,
    InvalidCvFieldError,
    InvalidTaskTypeError,
    SuggestionNotApplicableError,
    SuggestionNotPendingError,
)
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import (
    CvAiSuggestion,
    CvParseRun,
    CvProfile,
    CvSection,
)
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import permission_checker

_RESOURCE = _shared.RESOURCE


# --------------------------------------------------------------------------- #
# Grounding assembly                                                           #
# --------------------------------------------------------------------------- #


def _section_dict(s: CvSection) -> dict:
    return {
        "section_id": str(s.id),
        "section_type": s.section_type,
        "title": s.title,
        "sort_order": s.sort_order,
        "content": s.content_json or {},
    }


async def _gather_context(
    session: AsyncSession,
    *,
    principal,
    cv: CvProfile,
    task_type: str,
    instruction: str | None,
    raw_notes: str | None,
    target_section_id: uuid.UUID | None,
    job_id: uuid.UUID | None,
    source_ids: dict,
    target_language: str | None = None,
) -> CvAiContext:
    sections = await _cv_core._load_sections(session, cv_id=cv.id)
    cv_sections = [_section_dict(s) for s in sections]

    target_section = None
    if target_section_id is not None:
        target_section = next(
            (d for d in cv_sections if d["section_id"] == str(target_section_id)), None
        )
        if target_section is None:
            raise ResourceNotFoundError()

    # The profile is identity-only (owner decision 2026-07-06) — it no longer holds
    # any CV-usable career content, so CV AI grounding never pulls from it. Career
    # evidence comes from the CV itself, an uploaded-CV extraction, a source CV, or
    # the student's pasted notes.
    profile_sections = None

    upload_extracted = None
    parse_run_id = _shared.to_uuid(source_ids.get("cv_parse_run_id"))
    if parse_run_id is not None:
        run = (
            await session.execute(
                select(CvParseRun).where(CvParseRun.id == parse_run_id)
            )
        ).scalar_one_or_none()
        # Confirm the run belongs to a document owned by the caller.
        if run is not None:
            from app.modules.documents.domain.models import Document

            doc = (
                await session.execute(
                    select(Document).where(Document.id == run.document_id)
                )
            ).scalar_one_or_none()
            if doc is not None and doc.user_id == principal.user_id:
                upload_extracted = run.extracted_data or {}

    source_cv_sections = None
    source_cv_id = _shared.to_uuid(source_ids.get("source_cv_id"))
    if source_cv_id is not None:
        src = await _cv_core._load_owned_cv(
            session, principal=principal, cv_id=source_cv_id
        )
        src_sections = await _cv_core._load_sections(session, cv_id=src.id)
        source_cv_sections = [_section_dict(s) for s in src_sections]

    job = None
    if job_id is not None:
        # JD text is grounded from the student's pasted notes/instruction for this
        # slice; wiring live job text via an opportunities read interface is a
        # follow-up. The job_id is validated + recorded for traceability.
        job = {"id": str(job_id), "text": raw_notes or instruction or ""}

    return CvAiContext(
        task_type=task_type,
        # Detected/declared CV language drives the default user-facing output
        # language; an explicit ``target_language`` (when supplied) overrides it.
        language=cv.language or "vi",
        target_language=target_language,
        instruction=instruction,
        raw_notes=raw_notes,
        cv_sections=cv_sections,
        target_section=target_section,
        profile_sections=profile_sections,
        upload_extracted=upload_extracted,
        source_cv_sections=source_cv_sections,
        job=job,
    )


# --------------------------------------------------------------------------- #
# Request a suggestion (write-pending: creates a diff, never mutates the CV)   #
# --------------------------------------------------------------------------- #


async def request_suggestion(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None

    task_type = payload.get("task_type")
    if task_type not in catalog.AI_TASK_TYPES:
        raise InvalidTaskTypeError()

    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id)

    # Idempotent replay: same (cv, key) -> return the existing suggestion.
    idempotency_key = payload.get("idempotency_key")
    if idempotency_key:
        existing = (
            await session.execute(
                select(CvAiSuggestion).where(
                    CvAiSuggestion.cv_id == cv.id,
                    CvAiSuggestion.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return presenters.ai_suggestion(existing, locale=locale)

    target_section_id = _shared.to_uuid(payload.get("target_section_id"))
    job_id = _shared.to_uuid(payload.get("job_id"))
    if task_type in catalog.SECTION_TARGETED_TASKS and target_section_id is None:
        raise AiSourceRequiredError(field="target_section_id")
    if task_type in catalog.JOB_TARGETED_TASKS and job_id is None:
        raise AiSourceRequiredError(field="job_id")

    instruction, _i_flags = input_guard.sanitize_instruction(payload.get("instruction"))
    raw_notes, _n_flags = input_guard.sanitize_notes(payload.get("raw_notes"))
    source_ids = payload.get("source_ids") or {}

    context = await _gather_context(
        session,
        principal=principal,
        cv=cv,
        task_type=task_type,
        instruction=instruction,
        raw_notes=raw_notes,
        target_section_id=target_section_id,
        job_id=job_id,
        source_ids=source_ids,
        target_language=payload.get("target_language"),
    )

    # May raise AIUnavailableError -> mapped to the friendly AI_UNAVAILABLE envelope.
    result = await run_cv_task(context)

    suggestion = CvAiSuggestion(
        cv_id=cv.id,
        requested_by=principal.user_id,
        task_type=task_type,
        target_section_id=target_section_id,
        job_id=job_id,
        status=catalog.SUGGESTION_PENDING,
        diff_json=result.to_diff(),
        credits_charged=result.credits,
        idempotency_key=idempotency_key,
    )
    session.add(suggestion)
    await session.flush()

    await write_audit(
        session,
        action="cv.ai_suggestion.requested",
        resource_type="cv_ai_suggestion",
        resource_id=suggestion.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "cv_id": str(cv.id),
            "task_type": task_type,
            "requires_fact_confirmation": result.requires_fact_confirmation,
            "applicable": result.applicable,
            "credits_charged": result.credits,
        },
    )
    await session.commit()
    await session.refresh(suggestion)
    return presenters.ai_suggestion(suggestion, locale=locale)


# --------------------------------------------------------------------------- #
# Natural-language AI edit command (``docs/CV_STUDIO_SPEC.md`` "Natural-        #
# Language AI Editing"): produces a pending diff through the SAME             #
# cv_ai_suggestions accept/reject/version/audit pipeline as every other task.  #
# --------------------------------------------------------------------------- #


async def request_edit_command(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Turn a free-text CV edit instruction into a pending structured diff.

    NEVER mutates the CV. The student must accept/reject via the existing
    ``POST /cvs/{cv_id}/ai-suggestions/{suggestion_id}/accept|reject`` endpoints
    (this reuses ``CvAiSuggestion`` and its accept -> new-version + audit path
    unchanged).
    """

    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None

    instruction_raw = payload.get("instruction")
    if not isinstance(instruction_raw, str) or not instruction_raw.strip():
        raise AiSourceRequiredError(field="instruction")

    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id)

    idempotency_key = payload.get("idempotency_key")
    if idempotency_key:
        existing = (
            await session.execute(
                select(CvAiSuggestion).where(
                    CvAiSuggestion.cv_id == cv.id,
                    CvAiSuggestion.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return presenters.ai_suggestion(existing, locale=locale)

    target_section_id = _shared.to_uuid(payload.get("target_section_id"))
    instruction, _flags = input_guard.sanitize_instruction(instruction_raw)

    context = await _gather_context(
        session,
        principal=principal,
        cv=cv,
        task_type=_EDIT_COMMAND_TASK_TYPE,
        instruction=instruction,
        raw_notes=None,
        target_section_id=target_section_id,
        job_id=None,
        source_ids={},
    )

    # May raise AIUnavailableError -> mapped to the friendly AI_UNAVAILABLE envelope.
    result = await generate_cv_edit_patch(context)

    suggestion = CvAiSuggestion(
        cv_id=cv.id,
        requested_by=principal.user_id,
        task_type=_EDIT_COMMAND_TASK_TYPE,
        target_section_id=target_section_id,
        status=catalog.SUGGESTION_PENDING,
        diff_json=result.to_diff(),
        credits_charged=result.credits,
        idempotency_key=idempotency_key,
    )
    session.add(suggestion)
    await session.flush()

    await write_audit(
        session,
        action="cv.ai_edit_command.requested",
        resource_type="cv_ai_suggestion",
        resource_id=suggestion.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "cv_id": str(cv.id),
            "requires_fact_confirmation": result.requires_fact_confirmation,
            "applicable": result.applicable,
            "credits_charged": result.credits,
        },
    )
    await session.commit()
    await session.refresh(suggestion)
    return presenters.ai_suggestion(suggestion, locale=locale)


# --------------------------------------------------------------------------- #
# Apply an accepted diff                                                       #
# --------------------------------------------------------------------------- #


async def _apply_after(
    session: AsyncSession, *, cv: CvProfile, after: dict
) -> None:
    specs = (after or {}).get("sections") or []
    sections = await _cv_core._load_sections(session, cv_id=cv.id)
    by_id = {str(s.id): s for s in sections}
    max_order = max((s.sort_order for s in sections), default=0)

    for spec in specs:
        section_type = spec.get("section_type") or "custom"
        if section_type not in catalog.SECTION_TYPES:
            raise InvalidCvFieldError(field="section_type")
        sid = spec.get("section_id")
        content = spec.get("content")
        if sid is not None and str(sid) in by_id:
            sec = by_id[str(sid)]
            if content is not None:
                sec.content_json = content
            if spec.get("title") is not None:
                sec.title = spec["title"]
            if spec.get("sort_order") is not None:
                sec.sort_order = spec["sort_order"]
        else:
            max_order += 10
            session.add(
                CvSection(
                    cv_id=cv.id,
                    section_type=section_type,
                    title=spec.get("title"),
                    sort_order=spec.get("sort_order") or max_order,
                    content_json=content or {},
                    is_visible=True,
                )
            )
    await session.flush()


async def accept_suggestion(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None
    cv = await _cv_core._load_owned_cv(
        session, principal=principal, cv_id=cv_id, lock=True
    )

    suggestion = (
        await session.execute(
            select(CvAiSuggestion).where(
                CvAiSuggestion.id == suggestion_id, CvAiSuggestion.cv_id == cv.id
            )
        )
    ).scalar_one_or_none()
    if suggestion is None or suggestion.requested_by != principal.user_id:
        raise ResourceNotFoundError()

    accept_key = payload.get("idempotency_key")
    if (
        accept_key
        and suggestion.status == catalog.SUGGESTION_ACCEPTED
        and suggestion.accept_idempotency_key == accept_key
    ):
        return await _cv_core._detail_response(session, cv=cv, locale=locale)

    if suggestion.status != catalog.SUGGESTION_PENDING:
        raise SuggestionNotPendingError(status=suggestion.status)

    diff = suggestion.diff_json or {}
    if not diff.get("applicable", False):
        raise SuggestionNotApplicableError()
    if diff.get("requires_fact_confirmation") and payload.get("fact_confirmation") is not True:
        raise FactConfirmationRequiredError()

    # Apply the diff the student reviewed (server-stored ``after`` is canonical).
    await _apply_after(session, cv=cv, after=diff.get("after") or {})

    cv.version += 1
    cv.last_edited_at = _shared.now()
    await session.flush()

    version = await _cv_core._snapshot_version(
        session,
        cv=cv,
        change_source="ai_suggestion",
        change_summary=(diff.get("summary") or "AI suggestion")[:500],
        created_by=principal.user_id,
    )

    suggestion.status = catalog.SUGGESTION_ACCEPTED
    suggestion.resolved_at = _shared.now()
    suggestion.applied_version_id = version.id
    suggestion.accept_idempotency_key = accept_key

    await write_audit(
        session,
        action="cv.ai_suggestion.accepted",
        resource_type="cv_ai_suggestion",
        resource_id=suggestion.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "cv_id": str(cv.id),
            "task_type": suggestion.task_type,
            "applied_version_id": str(version.id),
            "fact_confirmation": bool(payload.get("fact_confirmation")),
            "client_accepted_diff": payload.get("accepted_diff") is not None,
        },
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)


async def get_suggestion(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Return the current status and diff of a suggestion (owner-only, read-only)."""
    permission_checker.require(principal, _RESOURCE, "read")
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id)
    suggestion = (
        await session.execute(
            select(CvAiSuggestion).where(
                CvAiSuggestion.id == suggestion_id, CvAiSuggestion.cv_id == cv.id
            )
        )
    ).scalar_one_or_none()
    if suggestion is None or suggestion.requested_by != principal.user_id:
        raise ResourceNotFoundError()
    return presenters.ai_suggestion(suggestion, locale=locale)


async def reject_suggestion(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id)
    suggestion = (
        await session.execute(
            select(CvAiSuggestion).where(
                CvAiSuggestion.id == suggestion_id, CvAiSuggestion.cv_id == cv.id
            )
        )
    ).scalar_one_or_none()
    if suggestion is None or suggestion.requested_by != principal.user_id:
        raise ResourceNotFoundError()
    if suggestion.status != catalog.SUGGESTION_PENDING:
        raise SuggestionNotPendingError(status=suggestion.status)

    suggestion.status = catalog.SUGGESTION_REJECTED
    suggestion.resolved_at = _shared.now()
    await write_audit(
        session,
        action="cv.ai_suggestion.rejected",
        resource_type="cv_ai_suggestion",
        resource_id=suggestion.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"cv_id": str(cv.id), "task_type": suggestion.task_type},
    )
    await session.commit()
    await session.refresh(suggestion)
    return presenters.ai_suggestion(suggestion, locale=locale)
