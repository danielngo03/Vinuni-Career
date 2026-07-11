"""CV ingestion orchestration (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3/§5).

Owns the explicit ingestion API alongside the legacy ``/cvs/upload`` path:

- :func:`create_upload`  -> ``POST /api/v1/cv-uploads`` (store original + preview meta)
- :func:`start_ingestion` -> ``POST /api/v1/cv-uploads/{id}/ingest`` (start/resume)
- :func:`get_ingestion`   -> ``GET /api/v1/cv-ingestions/{id}`` (user-safe status)
- :func:`import_ingestion`-> ``POST /api/v1/cv-ingestions/{id}/import`` (new draft)

The cascade runs through the background queue when ``cv_ingestion_async`` is true
(idempotent + resumable); the inline local queue executes it synchronously so the
behaviour is deterministic in tests. RBAC + ownership are enforced here and a
cross-owner access returns ``404``.

Privacy: engine internals, storage keys, and raw extracted text never leave this
layer. Audit/analytics payloads carry ids/codes/lengths only — never raw CV text.
"""

from __future__ import annotations

import asyncio
import copy
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.extraction import cv_validation
from app.ai.extraction.adapters import resolve_policy
from app.ai.extraction.cv_ingestion_cascade import IngestionOutcome, run_cascade
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.worker import get_queue
from app.modules.auth.application.context import RequestContext
from app.modules.documents.api import presenters
from app.modules.documents.application import (
    _shared,
    cv_creation_service,
    cv_section_service,
    cv_service,
)
from app.modules.documents.application.errors import FactConfirmationFieldsRequiredError
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import CvIngestion, Document
from app.modules.documents.infrastructure import storage
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE
_SECURITY_REJECT = "FILE_REJECTED_SECURITY"
_TASK_NAME = "cv.ingestion.run"


# --------------------------------------------------------------------------- #
# next_actions per terminal status                                            #
# --------------------------------------------------------------------------- #


def _next_actions(status: str, quality_code: str | None) -> list[str]:
    if status == catalog.INGEST_READY:
        return ["import_to_cv", "keep_original", "upload_another"]
    if status == catalog.INGEST_NEEDS_REVIEW:
        return ["review_fields", "import_to_cv", "keep_original"]
    if status == catalog.INGEST_FAILED and quality_code:
        _vi, _en, _recover, actions = cv_validation.copy_for(quality_code)
        return actions
    return ["wait"]


def _preview_url(document: Document, *, accessor_id: uuid.UUID) -> str:
    token = storage.make_signed_token(
        {"kind": "document", "id": str(document.id), "uid": str(accessor_id), "purpose": "preview"}
    )
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/cv-files/{token}"


# --------------------------------------------------------------------------- #
# Upload (store original + preview metadata)                                  #
# --------------------------------------------------------------------------- #


async def create_upload(
    session: AsyncSession,
    *,
    principal: Principal,
    filename: str,
    data: bytes,
    content_type: str | None,
    idempotency_key: str | None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Store the original file and return preview/upload metadata (not builder content).

    Cheap pre-storage gates only (size / type / security); password/corrupt
    detection and content classification happen later in :func:`start_ingestion`.
    """

    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None
    settings = get_settings()

    if idempotency_key:
        prior = (
            await session.execute(
                select(Document).where(
                    Document.user_id == principal.user_id,
                    Document.idempotency_key == idempotency_key,
                    Document.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if prior is not None:
            return presenters.upload_preview(
                prior, preview_url=_preview_url(prior, accessor_id=principal.user_id)
            )

    # Cheap gates — never store an oversized/unsupported/infected file.
    if len(data) > settings.max_upload_bytes:
        _reject("FILE_TOO_LARGE", locale=locale)
    from app.ai.extraction.text_extraction import sniff_kind  # local import (cheap)

    kind = sniff_kind(filename, data)
    from app.ai.extraction.text_extraction import FileKind

    if kind not in {FileKind.PDF, FileKind.DOCX, FileKind.TXT, FileKind.IMAGE}:
        _reject("UNSUPPORTED_FILE_TYPE", locale=locale)
    if cv_validation.security_gate(data, filename) is not None:
        _reject("FILE_REJECTED_SECURITY", locale=locale)

    # An image CV is converted to a PDF for the served/downloaded artifact; the
    # checksum stays that of the ORIGINAL bytes so duplicate detection is stable
    # (a re-generated PDF is not byte-identical across runs).
    from app.modules.documents.infrastructure.image_pdf import served_upload_artifact

    original_checksum = cv_validation.compute_checksum(data)
    stored_bytes, stored_mime, stored_name, stored_ext = served_upload_artifact(
        filename, data, content_type
    )

    document_id = uuid.uuid4()
    storage_key = f"cv-uploads/{principal.user_id}/{document_id}{stored_ext}"
    storage.get_storage().save(storage_key, stored_bytes)

    document = Document(
        id=document_id,
        user_id=principal.user_id,
        doc_type="cv",
        original_name=stored_name,
        storage_path=storage_key,
        mime_type=stored_mime,
        file_size_bytes=len(stored_bytes),
        checksum_sha256=original_checksum,
        virus_scan_status="clean",
        virus_scan_at=_shared.now(),
        idempotency_key=idempotency_key,
    )
    session.add(document)
    await session.flush()
    await write_audit(
        session,
        action="cv.upload.stored",
        resource_type="document",
        resource_id=document.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"size": document.file_size_bytes, "content_type": document.mime_type},
    )
    await session.commit()
    await session.refresh(document)
    return presenters.upload_preview(
        document, preview_url=_preview_url(document, accessor_id=principal.user_id)
    )


def _reject(code: str, *, locale: str) -> None:
    vi, en, _recover, actions = cv_validation.copy_for(code)
    raise ValidationFailedError(
        vi if locale == "vi" else en, details={"quality_code": code, "actions": actions}
    )


# --------------------------------------------------------------------------- #
# Ownership helpers                                                            #
# --------------------------------------------------------------------------- #


async def _load_owned_document(
    session: AsyncSession, *, principal: Principal, document_id: uuid.UUID
) -> Document:
    document = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if document is None or document.user_id != principal.user_id:
        raise ResourceNotFoundError()
    return document


async def _load_owned_ingestion(
    session: AsyncSession, *, principal: Principal, ingestion_id: uuid.UUID
) -> CvIngestion:
    ing = (
        await session.execute(select(CvIngestion).where(CvIngestion.id == ingestion_id))
    ).scalar_one_or_none()
    if ing is None or ing.user_id != principal.user_id:
        raise ResourceNotFoundError()
    return ing


# --------------------------------------------------------------------------- #
# Start / resume ingestion                                                     #
# --------------------------------------------------------------------------- #


async def start_ingestion(
    session: AsyncSession,
    *,
    principal: Principal,
    document_id: uuid.UUID,
    ctx: RequestContext,
    idempotency_key: str | None = None,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None
    document = await _load_owned_document(session, principal=principal, document_id=document_id)

    # Resumable/idempotent: reuse an existing ingestion for this document.
    ing = (
        (
            await session.execute(
                select(CvIngestion)
                .where(CvIngestion.document_id == document.id)
                .order_by(CvIngestion.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if ing is None:
        # Upload-start quota pre-check: an uploaded CV lands DIRECTLY in the library
        # (``ready``), so if the library is already full there is no point spending
        # the (token-expensive) extraction cascade — reject up front with the same
        # ``409 QUOTA_EXCEEDED`` + recovery actions the import step would raise. Only
        # gates a genuinely NEW ingestion; a resume/retry of an in-flight one is not
        # re-checked here (import remains the authoritative gate). Lazy import keeps
        # the ``_cv_core`` seam local to this create path.
        from app.modules.documents.application import _cv_core

        await _cv_core._enforce_active_cv_quota(session, principal=principal)
        ing = CvIngestion(
            document_id=document.id,
            user_id=principal.user_id,
            status=catalog.INGEST_QUEUED,
            idempotency_key=idempotency_key,
            started_at=_shared.now(),
        )
        session.add(ing)
        await session.flush()
        await write_audit(
            session,
            action="cv.ingestion.started",
            resource_type="cv_ingestion",
            resource_id=ing.id,
            context=_shared.audit_ctx(principal, ctx),
            after={"document_id": str(document.id)},
        )
        await session.commit()

    ingestion_id = ing.id
    settings = get_settings()
    if settings.cv_ingestion_async:
        get_queue().register(_TASK_NAME, _ingestion_task)
        await get_queue().enqueue(_TASK_NAME, {"ingestion_id": str(ingestion_id)})
    else:
        await _execute_ingestion(session, ingestion_id=ingestion_id)
        await session.commit()

    refreshed = await _load_owned_ingestion(session, principal=principal, ingestion_id=ingestion_id)
    await session.refresh(refreshed)
    return presenters.ingestion(refreshed, locale=locale)


async def _ingestion_task(payload: dict) -> None:
    """Background handler: run the cascade in its own session (idempotent)."""

    ingestion_id = uuid.UUID(str(payload["ingestion_id"]))
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await _execute_ingestion(session, ingestion_id=ingestion_id)
        await session.commit()


async def _execute_ingestion(session: AsyncSession, *, ingestion_id: uuid.UUID) -> None:
    """Run the extraction cascade and persist the result. Safe to re-run.

    Re-ingestion recomputes from the stored original; the row is overwritten with
    the fresh outcome. No raw CV text is ever logged or audited.
    """

    ing = (
        await session.execute(select(CvIngestion).where(CvIngestion.id == ingestion_id))
    ).scalar_one_or_none()
    if ing is None:
        return
    document = (
        await session.execute(select(Document).where(Document.id == ing.document_id))
    ).scalar_one_or_none()
    if document is None or not document.storage_path:
        ing.status = catalog.INGEST_FAILED
        ing.quality_code = "CORRUPT_FILE"
        ing.next_actions = _next_actions(catalog.INGEST_FAILED, "CORRUPT_FILE")
        ing.completed_at = _shared.now()
        await session.flush()
        return

    ing.status = catalog.INGEST_CHECKING
    await session.flush()

    try:
        data = storage.get_storage().load(document.storage_path)
    except storage.StorageError:
        ing.status = catalog.INGEST_FAILED
        ing.quality_code = "CORRUPT_FILE"
        ing.next_actions = _next_actions(catalog.INGEST_FAILED, "CORRUPT_FILE")
        ing.completed_at = _shared.now()
        await session.flush()
        return

    # Duplicate detection excludes the document itself.
    others = (
        (
            await session.execute(
                select(Document.checksum_sha256).where(
                    Document.user_id == ing.user_id,
                    Document.id != document.id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    policy = resolve_policy()
    # run_cascade is synchronous and CPU/IO-heavy (PDF rasterization, PIL
    # resize/encode, blocking vision HTTP). Offload to a thread so it never
    # blocks the request event loop (the inline queue runs this on the loop).
    outcome: IngestionOutcome = await asyncio.to_thread(
        run_cascade,
        document.original_name,
        data,
        max_bytes=get_settings().max_upload_bytes,
        existing_checksums=list(others),
        policy=policy,
        # The stored bytes may be a derived PDF (image CVs are converted on
        # upload); pin duplicate detection to the document's original-bytes
        # checksum so identical image uploads are still caught.
        precomputed_checksum=document.checksum_sha256,
    )

    _apply_outcome(ing, outcome)
    await session.flush()
    await write_audit(
        session,
        action="cv.ingestion.completed",
        resource_type="cv_ingestion",
        resource_id=ing.id,
        context=None,
        after={
            "quality_code": ing.quality_code,
            "status": ing.status,
            "text_length": ing.text_length,
            "page_count": ing.page_count,
            "mixed_language": ing.mixed_language,
            "engine_family": ing.engine_family,
        },
    )


def _apply_outcome(ing: CvIngestion, outcome: IngestionOutcome) -> None:
    if outcome.accepted:
        status = catalog.INGEST_NEEDS_REVIEW if outcome.needs_review else catalog.INGEST_READY
    else:
        status = catalog.INGEST_FAILED
    ing.status = status
    ing.quality_code = outcome.quality_code
    ing.detected_language = outcome.detected_language
    ing.mixed_language = outcome.mixed_language
    ing.page_count = outcome.page_count or None
    ing.text_length = outcome.text_length or None
    ing.engine_family = outcome.engine_family
    ing.engine_version = outcome.engine_version
    ing.error_code = None if outcome.accepted else outcome.quality_code
    ing.extracted_data = outcome.extracted_data
    ing.review_fields = outcome.review_fields
    ing.next_actions = _next_actions(status, outcome.quality_code)
    ing.completed_at = _shared.now()


# --------------------------------------------------------------------------- #
# Read                                                                         #
# --------------------------------------------------------------------------- #


async def get_ingestion(
    session: AsyncSession, *, principal: Principal, ingestion_id: uuid.UUID, locale: str = "vi"
) -> dict:
    permission_checker.require(principal, _RESOURCE, "read")
    ing = await _load_owned_ingestion(session, principal=principal, ingestion_id=ingestion_id)
    return presenters.ingestion(ing, locale=locale)


# --------------------------------------------------------------------------- #
# Import (create a NEW versioned draft; never overwrite an accepted CV)        #
# --------------------------------------------------------------------------- #


# Titles for extracted section types that are not part of the default template
# (awards / languages / activities). Extraction can surface these — especially the
# vision tier on styled CVs — and they must not be silently dropped at import.
_EXTRA_SECTION_TITLES: dict[str, str] = {
    "awards": "Awards",
    "languages": "Languages",
    "activities": "Activities",
    "publications": "Publications",
    "interests": "Interests",
    "references": "References",
}


def _section_content(section_data: object) -> dict | None:
    """Return the render-ready content_json for a section, or ``None`` if empty.

    Sections are structured: entry sections carry ``{"entries": [...]}`` and
    list/skill/text sections carry ``{"items": [...]}``. Both are passed through
    to ``cv_sections.content_json`` verbatim.
    """

    if not isinstance(section_data, dict):
        return None
    entries = section_data.get("entries")
    items = section_data.get("items")
    if isinstance(entries, list) and entries:
        return {"entries": list(entries)}
    if isinstance(items, list) and items:
        return {"items": list(items)}
    return None


# Header fields imported from the extraction's ``contact`` object. Empty values are
# dropped so a partially-extracted CV does not carry blank contact lines.
_HEADER_CONTACT_FIELDS = ("name", "headline", "email", "phone", "location")


def _header_content(contact: object) -> dict | None:
    """Build the header section's ``content_json`` from the extracted contact.

    Header content is neither ``entries`` nor ``items`` — it is a flat contact
    object ``{name, headline, email, phone, location, links:[{label,url}]}``. Empty
    fields are omitted; returns ``None`` when nothing usable was extracted so the
    header stays empty rather than carrying blank keys.
    """

    if not isinstance(contact, dict):
        return None
    content: dict = {}
    for field in _HEADER_CONTACT_FIELDS:
        value = contact.get(field)
        if isinstance(value, str) and value.strip():
            content[field] = value.strip()
    links_raw = contact.get("links")
    if isinstance(links_raw, list):
        links: list[dict] = []
        for link in links_raw:
            if not isinstance(link, dict):
                continue
            url = link.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            label = link.get("label")
            links.append(
                {
                    "label": label.strip()
                    if isinstance(label, str) and label.strip()
                    else url.strip(),
                    "url": url.strip(),
                }
            )
        if links:
            content["links"] = links
    return content or None


def _sections_from_extracted(extracted: dict | None) -> list[dict]:
    sections = [dict(s) for s in catalog.DEFAULT_SECTIONS]
    data = extracted or {}
    known = {s["section_type"] for s in sections}
    for s in sections:
        if s["section_type"] == catalog.HEADER_SECTION_TYPE:
            # The header carries the person's name + contact, not entries/items.
            content = _header_content(data.get("contact"))
            if content is not None:
                s["content_json"] = content
            continue
        content = _section_content(data.get(s["section_type"]))
        if content is not None:
            s["content_json"] = content
    # Append any extracted section the default template doesn't carry, so an
    # imported CV keeps every section the ingestion found (never lose awards /
    # languages / activities). Ordered after the defaults, in a stable order.
    next_order = max((s.get("sort_order", 0) for s in sections), default=0) + 10
    for section_type, title in _EXTRA_SECTION_TITLES.items():
        if section_type in known:
            continue
        content = _section_content(data.get(section_type))
        if content is not None:
            sections.append(
                {
                    "section_type": section_type,
                    "title": title,
                    "sort_order": next_order,
                    "content_json": content,
                }
            )
            next_order += 10
    return sections


# --------------------------------------------------------------------------- #
# Review-field overrides (student-edited low-confidence fields)                #
# --------------------------------------------------------------------------- #
#
# The review screen lets the student correct low-confidence fields before
# import. Each override is ``{path, value}`` where ``path`` MUST be one the
# ingestion itself emitted in ``review_fields`` — we never accept an arbitrary
# path, so an override can only edit an existing extracted field, never inject a
# new structure. Supported paths: ``contact.<name|email|phone>`` and
# ``<section_type>[<idx>].text``. Values are the user's own typed corrections
# (fact-grounded, safe to persist); they are sanitised like extracted text.

_OVERRIDE_ITEM_PATH_RE = re.compile(r"^(?P<section>[a-z_]+)\[(?P<idx>\d+)\]\.text$")
_OVERRIDE_CONTACT_PATH_RE = re.compile(r"^contact\.(?P<field>name|email|phone)$")
_OVERRIDE_VALUE_MAX_CHARS = 5000
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_override_value(value: object) -> str:
    """Sanitise an override value the way the structuring path treats text.

    Coerce to ``str``, drop control/binary bytes, normalise newlines, strip outer
    whitespace, and cap length. No HTML escaping (mirrors how extracted text is
    stored verbatim; render-layer escaping is the frontend's responsibility).
    """

    text = value if isinstance(value, str) else str(value or "")
    text = _CONTROL_CHARS_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:_OVERRIDE_VALUE_MAX_CHARS]


def _apply_overrides(
    extracted: dict | None,
    review_fields: list[dict] | None,
    overrides: list[dict] | None,
) -> dict | None:
    """Return a COPY of ``extracted`` with allowlisted per-field decisions applied.

    Never mutates the ingestion row's stored ``extracted_data`` (deep-copied).
    Unknown / non-allowlisted / malformed paths are ignored — no arbitrary
    injection. Everything not overridden is preserved exactly.

    Each override is ``{path, value, accepted}``:

    - ``accepted`` (default ``True``): ``value`` (the student's own typed
      correction, or the original extracted value unchanged) is imported.
    - ``accepted = False``: the field is EXCLUDED from the imported draft
      entirely — the item is dropped from its section's ``items`` list, or the
      contact field is left unset — so the review screen is a real
      accept/edit/reject diff, not a single blanket confirmation checkbox
      (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §6 review/import).
    """

    if not overrides:
        return extracted

    allowed_paths = {
        f.get("path")
        for f in (review_fields or [])
        if isinstance(f, dict) and isinstance(f.get("path"), str)
    }
    data: dict = copy.deepcopy(extracted) if isinstance(extracted, dict) else {}
    rejected_items: dict[str, set[int]] = {}

    for override in overrides:
        if not isinstance(override, dict):
            continue
        path = override.get("path")
        if not isinstance(path, str) or path not in allowed_paths:
            continue  # unknown/forbidden path -> ignored (no injection)
        accepted = override.get("accepted", True)

        contact_match = _OVERRIDE_CONTACT_PATH_RE.match(path)
        if contact_match is not None:
            contact = data.get("contact")
            if not isinstance(contact, dict):
                contact = {}
                data["contact"] = contact
            field = contact_match.group("field")
            if accepted:
                contact[field] = _clean_override_value(override.get("value"))
            else:
                contact.pop(field, None)  # rejected -> excluded from import
            continue

        item_match = _OVERRIDE_ITEM_PATH_RE.match(path)
        if item_match is not None:
            section_key = item_match.group("section")
            section = data.get(section_key)
            if not isinstance(section, dict):
                continue
            items = section.get("items")
            idx = int(item_match.group("idx"))
            if not isinstance(items, list) or idx >= len(items):
                continue
            if accepted:
                if isinstance(items[idx], dict):
                    items[idx]["text"] = _clean_override_value(override.get("value"))
            else:
                rejected_items.setdefault(section_key, set()).add(idx)

    for section_key, indices in rejected_items.items():
        section = data.get(section_key)
        if isinstance(section, dict) and isinstance(section.get("items"), list):
            section["items"] = [item for i, item in enumerate(section["items"]) if i not in indices]

    return data


def _needs_review_paths(review_fields: list[dict] | None) -> set[str]:
    return {
        str(f.get("path"))
        for f in (review_fields or [])
        if isinstance(f, dict) and f.get("needs_review") and isinstance(f.get("path"), str)
    }


async def import_ingestion(
    session: AsyncSession,
    *,
    principal: Principal,
    ingestion_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Create a NEW versioned draft CV from a reviewed ingestion.

    Requires the ingestion to be importable (``ready``/``needs_review``). Respects
    the active-CV quota (``409 QUOTA_EXCEEDED``). Importing into an existing CV is
    allowed only when that CV is a DRAFT owned by the caller — an accepted/ready CV
    is never silently overwritten.
    """

    permission_checker.require(principal, _RESOURCE, "create")
    assert principal.user_id is not None
    ing = await _load_owned_ingestion(session, principal=principal, ingestion_id=ingestion_id)

    if ing.status not in (catalog.INGEST_READY, catalog.INGEST_NEEDS_REVIEW):
        raise ValidationFailedError(
            "CV chưa sẵn sàng để nhập. Vui lòng kiểm tra lại trước khi nhập.",
            details={"reason": "ingestion_not_ready", "status": ing.status},
        )

    # Idempotent re-import: return the already-created draft.
    if ing.imported_cv_id is not None:
        return await cv_service.get_cv(
            session, principal=principal, cv_id=ing.imported_cv_id, locale=locale
        )

    # Per-field confirmation gate (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §6):
    # when the ingestion flagged specific fields as needing review, the student
    # must explicitly accept or reject EACH one (via ``overrides``) before import,
    # unless they pass a blanket ``fact_confirmation`` to accept everything as-is.
    if ing.status == catalog.INGEST_NEEDS_REVIEW and not payload.get("fact_confirmation"):
        needs_review = _needs_review_paths(ing.review_fields)
        decided = {
            o.get("path")
            for o in (payload.get("overrides") or [])
            if isinstance(o, dict) and isinstance(o.get("path"), str)
        }
        missing = sorted(needs_review - decided)
        if missing:
            raise FactConfirmationFieldsRequiredError(fields=missing)

    title = (payload.get("title") or "").strip()
    document = (
        await session.execute(select(Document).where(Document.id == ing.document_id))
    ).scalar_one_or_none()
    if not title and document is not None:
        title = document.original_name or "Imported CV"
    # Apply the student's reviewed corrections to a COPY of the extracted data
    # BEFORE structuring sections; the stored ingestion row is never mutated.
    effective_extracted = _apply_overrides(
        ing.extracted_data, ing.review_fields, payload.get("overrides")
    )
    sections = _sections_from_extracted(effective_extracted)
    template_id = _shared.to_uuid(payload.get("template_id"))

    target_cv_id = _shared.to_uuid(payload.get("target_cv_id"))
    if target_cv_id is not None:
        detail = await _import_into_draft(
            session,
            principal=principal,
            target_cv_id=target_cv_id,
            sections=sections,
            ctx=ctx,
            locale=locale,
        )
        imported_id = uuid.UUID(detail["id"])
    else:
        detail = await cv_creation_service.create_cv_from_sections(
            session,
            principal=principal,
            title=title,
            language=ing.detected_language or "vi",
            template_id=template_id,
            sections=sections,
            source_type=catalog.SOURCE_TYPE_FOR_MODE[catalog.CREATION_UPLOADED_IMPORT],
            change_source="import",
            ctx=ctx,
            audit_action="cv.imported_from_upload",
            audit_extra={"ingestion_id": str(ing.id)},
            locale=locale,
        )
        imported_id = uuid.UUID(detail["id"])

    # Link the ingestion to the created draft (separate commit; create_* committed).
    ing_row = await _load_owned_ingestion(session, principal=principal, ingestion_id=ing.id)
    ing_row.imported_cv_id = imported_id
    await session.flush()
    await session.commit()
    return detail


async def _import_into_draft(
    session: AsyncSession,
    *,
    principal: Principal,
    target_cv_id: uuid.UUID,
    sections: list[dict],
    ctx: RequestContext,
    locale: str,
) -> dict:
    """Merge extracted sections into an existing DRAFT CV (new version).

    Guards against overwriting accepted content: the target must be a draft.
    """

    from app.modules.documents.domain.models import CvProfile

    cv = (
        await session.execute(
            select(CvProfile).where(CvProfile.id == target_cv_id, CvProfile.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if cv is None or cv.user_id != principal.user_id:
        raise ResourceNotFoundError()
    if cv.status != catalog.CV_DRAFT:
        raise ValidationFailedError(
            "Chỉ có thể nhập vào CV ở trạng thái nháp.",
            details={"reason": "target_not_draft"},
        )
    # Fill empty sections from the import without clobbering existing content.
    for s in sections:
        payload = {
            "section_type": s["section_type"],
            "title": s.get("title"),
            "content": s.get("content_json") or {},
        }
        # Only seed sections that carry imported content (entries or items).
        if not (payload["content"].get("entries") or payload["content"].get("items")):
            continue
        await cv_section_service.create_section(
            session, principal=principal, cv_id=cv.id, payload=payload, ctx=ctx, locale=locale
        )
    return await cv_service.get_cv(session, principal=principal, cv_id=cv.id, locale=locale)


__all__ = [
    "create_upload",
    "start_ingestion",
    "get_ingestion",
    "import_ingestion",
]
