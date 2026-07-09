"""ORM -> friendly, leak-safe response shapes for the documents / CV API.

Hard rules enforced here (``docs/SECURITY_PRIVACY.md``):

- ``storage_path`` / ``storage_key`` are NEVER included in any response.
- parse-run internals (``provider_alias``, ``confidence``, ``error_message``) are
  NEVER included. ``extracted_data`` / ``review_fields`` appear ONLY in the
  owner-only parse-run view (no raw text leaves any other endpoint).
- every raw enum code is paired with a localized label.
"""

from __future__ import annotations

from app.ai.extraction import cv_validation
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import (
    CvAiSuggestion,
    CvExport,
    CvIngestion,
    CvParseRun,
    CvProfile,
    CvSection,
    CvTemplate,
    CvVersion,
    Document,
)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def template(t: CvTemplate, *, locale: str = "vi", include_admin_fields: bool = False) -> dict:
    data = {
        "id": str(t.id),
        "key": t.key,
        "name": t.name_vi if locale == "vi" else t.name_en,
        "category": t.category,
        # Full visual theme (layout/palette/typography/photo/sectionStyle/regions/
        # order) — the renderer's single source of truth. Aliased as ``theme`` too.
        "layout_schema": t.layout_schema or {},
        "theme": t.layout_schema or {},
        "is_active": t.is_active,
        "status": t.status,
        "version": t.version,
        # Filled CV previews are private; template preview images are rendered by
        # the frontend gallery from the theme (no stored crop), so null here.
        "preview_url": t.preview_image,
    }
    if include_admin_fields:
        data["name_vi"] = t.name_vi
        data["name_en"] = t.name_en
    return data


def section(s: CvSection) -> dict:
    return {
        "id": str(s.id),
        "section_type": s.section_type,
        "title": s.title,
        "sort_order": s.sort_order,
        "content": s.content_json or {},
        "is_visible": s.is_visible,
    }


def cv_summary(p: CvProfile, *, locale: str = "vi") -> dict:
    return {
        "id": str(p.id),
        "title": p.title,
        "source_type": p.source_type,
        "source_label": catalog.source_label(p.source_type, locale=locale),
        "template_id": str(p.template_id) if p.template_id else None,
        "language": p.language,
        "status": p.status,
        "status_label": catalog.status_label(p.status, locale=locale),
        # Two-tier library lifecycle: a ``ready`` CV is in the library (counts to
        # the 5-cap, usable for apply/job-fit); ``draft`` is an unlimited scratch CV.
        # ``finalized_at`` is when it was committed (null for drafts).
        "in_library": p.status == catalog.CV_READY,
        "finalized_at": _iso(p.finalized_at),
        "version": p.version,
        "last_edited_at": _iso(p.last_edited_at),
        "canvas": p.canvas_json or {},
    }


def cv_version_summary(v: CvVersion, *, is_current: bool, locale: str = "vi") -> dict:
    """A leak-safe entry in a CV's version history.

    Exposes the ``cv_versions`` row id (needed by export + application apply),
    its monotonic ``version`` number, and friendly change metadata. The immutable
    ``snapshot_json`` itself is never returned here (history is a list, not a diff).
    """

    return {
        "id": str(v.id),
        "version": v.version_number,
        "change_source": v.change_source,
        "change_summary": v.change_summary,
        "is_current": is_current,
        "created_at": _iso(v.created_at),
    }


def cv_detail(
    p: CvProfile,
    *,
    sections: list[CvSection],
    versions: list[CvVersion] | None = None,
    locale: str = "vi",
) -> dict:
    data = cv_summary(p, locale=locale)
    data["sections"] = [section(s) for s in sections]
    data["created_at"] = _iso(p.created_at)
    # ``versions`` is newest-first; the head is the current accepted snapshot.
    rows = versions or []
    current_id = str(rows[0].id) if rows else None
    data["current_version_id"] = current_id
    data["versions"] = [
        cv_version_summary(v, is_current=(str(v.id) == current_id), locale=locale) for v in rows
    ]
    return data


def parse_run(run: CvParseRun, *, locale: str = "vi") -> dict:
    """Owner-only parse-run view: friendly status + review fields.

    Never includes provider alias, confidence, error message, or storage paths.
    """

    code = run.quality_code or "REVIEW_REQUIRED"
    vi, en, _recover, actions = cv_validation.copy_for(code)
    return {
        "id": str(run.id),
        "document_id": str(run.document_id),
        "status": run.status,
        "status_label": catalog.parse_status_label(run.status, locale=locale),
        "quality_code": code,
        "user_message": vi if locale == "vi" else en,
        "next_actions": actions,
        "detected_language": run.detected_language,
        "review_fields": run.review_fields or [],
    }


def upload_preview(
    document: Document, *, preview_url: str | None, page_count: int | None = None
) -> dict:
    """Preview/upload metadata for a freshly stored original (NOT builder content).

    Storage paths are never included — preview is served by a signed token only.
    """

    return {
        "document_id": str(document.id),
        "filename": document.original_name,
        "content_type": document.mime_type,
        "size": document.file_size_bytes,
        "page_count": page_count,
        "preview_url": preview_url,
    }


def ingestion(ing: CvIngestion, *, locale: str = "vi") -> dict:
    """User-safe ingestion status (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §5).

    NEVER includes engine family/version, text length, raw confidence, error
    internals, storage keys, or stack traces. ``review_fields`` carry field-level
    needs-review markers (the "Check this" UX), not numeric confidence.
    """

    code = ing.quality_code
    quality_message: str | None = None
    if code:
        vi, en, _recover, _actions = cv_validation.copy_for(code)
        quality_message = vi if locale == "vi" else en
    return {
        "id": str(ing.id),
        "ingestion_id": str(ing.id),
        "document_id": str(ing.document_id),
        "status": ing.status,
        "status_label": catalog.ingestion_status_label(ing.status, locale=locale),
        "quality_code": code,
        "quality_message": quality_message,
        "detected_language": ing.detected_language,
        "mixed_language": ing.mixed_language,
        "review_fields": ing.review_fields or [],
        "next_actions": ing.next_actions or [],
        "imported_cv_id": str(ing.imported_cv_id) if ing.imported_cv_id else None,
    }


def ai_suggestion(s: CvAiSuggestion, *, locale: str = "vi") -> dict:
    """Leak-safe AI suggestion view.

    ``diff_json`` is already metadata + grounded content only (no provider/model/
    token/prompt internals — the AI layer scrubs model text and grounds CV facts
    deterministically). The diff carries ``summary``/``before``/``after``/
    ``requires_fact_confirmation`` (``docs/API_CONTRACTS.md``) plus advisory extras.
    """

    diff = s.diff_json or {}
    return {
        "suggestion_id": str(s.id),
        "id": str(s.id),
        "cv_id": str(s.cv_id),
        "task_type": s.task_type,
        "task_label": catalog.task_label(s.task_type, locale=locale),
        "status": s.status,
        "status_label": catalog.suggestion_status_label(s.status, locale=locale),
        "credits_charged": s.credits_charged,
        "diff": diff,
        "applied_version_id": str(s.applied_version_id) if s.applied_version_id else None,
        "created_at": _iso(s.created_at),
        "resolved_at": _iso(s.resolved_at),
    }


def export(e: CvExport, *, download_url: str | None = None, locale: str = "vi") -> dict:
    return {
        "id": str(e.id),
        "export_id": str(e.id),
        "cv_id": str(e.cv_id),
        "version_id": str(e.version_id),
        "format": e.export_format,
        "status": e.status,
        "status_label": catalog.export_status_label(e.status, locale=locale),
        "download_url": download_url,
        "created_at": _iso(e.created_at),
        "completed_at": _iso(e.completed_at),
    }
