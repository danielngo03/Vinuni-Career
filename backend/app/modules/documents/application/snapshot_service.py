"""Application CV snapshot service — the documents module's PUBLIC interface for
the future ``recruitment`` module.

``recruitment`` must depend ONLY on the functions in this module (not on the other
documents services or ORM internals). At application-submit time it calls
:func:`create_application_cv_snapshot` to capture an IMMUTABLE snapshot from either
a builder CV version or an uploaded document. Snapshots are never updated or
deleted (``docs/CV_STUDIO_SPEC.md`` §5; ``docs/SECURITY_PRIVACY.md``).

Partner CV view/download serves the STUDENT'S ORIGINAL file (owner decision
2026-07-10) via :func:`build_partner_cv_view` / :func:`build_snapshot_original_download`
— NOT a watermarked derivative. The recruitment service verifies org ownership +
CV-access RBAC before minting the signed URL, and every byte fetch is audited.

The legacy watermarked authorizer seam (:func:`set_snapshot_access_authorizer` /
:func:`get_snapshot_download`) is retained for the owner self-download path (and
backward compatibility); until an authorizer is wired, only the snapshot owner can
use that path and everyone else gets ``404``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import _shared
from app.modules.documents.application.errors import CvNotInLibraryError
from app.modules.documents.domain import catalog
from app.modules.documents.domain.models import (
    ApplicationCvSnapshot,
    CvParseRun,
    CvProfile,
    CvVersion,
    Document,
)
from app.modules.documents.infrastructure import storage
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError, ValidationFailedError
from app.shared.permissions import Principal


@dataclass(slots=True)
class SnapshotAccess:
    """Result of an authorizer check granting partner access to a snapshot."""

    watermark_text: str | None


# Authorizer seam: (principal, snapshot) -> SnapshotAccess | None.
SnapshotAccessAuthorizer = Callable[[Principal, ApplicationCvSnapshot], SnapshotAccess | None]
_authorizer: SnapshotAccessAuthorizer | None = None


def set_snapshot_access_authorizer(authorizer: SnapshotAccessAuthorizer | None) -> None:
    """Wire the recruitment-supplied partner-access check (default unset)."""

    global _authorizer
    _authorizer = authorizer


def _sections_from_extracted(extracted: dict) -> list[dict]:
    sections: list[dict] = []
    for key, value in (extracted or {}).items():
        if key == "contact":
            continue
        if isinstance(value, dict) and value.get("items"):
            sections.append({"title": key.title(), "content_json": {"items": value["items"]}})
    return sections


async def create_application_cv_snapshot(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    cv_selection: dict,
    application_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    ctx: RequestContext,
    commit: bool = True,
) -> ApplicationCvSnapshot:
    """Create an immutable application CV snapshot for ``owner_id``.

    ``cv_selection`` matches ``docs/API_CONTRACTS.md`` Application CV Selection:
    ``{"type": "builder_cv"|"uploaded_document", "cv_profile_id", "cv_version_id",
    "uploaded_document_id"}``. Verifies ownership of every referenced resource.
    """

    application_id = _shared.to_uuid(application_id)

    # Idempotency: one snapshot per application; or per (owner, idempotency_key).
    if application_id is not None:
        prior = (
            await session.execute(
                select(ApplicationCvSnapshot).where(
                    ApplicationCvSnapshot.application_id == application_id
                )
            )
        ).scalar_one_or_none()
        if prior is not None:
            return prior
    if idempotency_key:
        prior = (
            await session.execute(
                select(ApplicationCvSnapshot).where(
                    ApplicationCvSnapshot.user_id == owner_id,
                    ApplicationCvSnapshot.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if prior is not None:
            return prior

    sel_type = cv_selection.get("type")
    snapshot = ApplicationCvSnapshot(
        application_id=application_id,
        user_id=owner_id,
        idempotency_key=idempotency_key,
    )

    if sel_type == "builder_cv":
        cv_id = _shared.to_uuid(cv_selection.get("cv_profile_id"))
        version_id = _shared.to_uuid(cv_selection.get("cv_version_id"))
        if not cv_id or not version_id:
            raise ValidationFailedError("Thiếu CV hoặc phiên bản CV để nộp.")
        cv = (
            await session.execute(select(CvProfile).where(CvProfile.id == cv_id))
        ).scalar_one_or_none()
        if cv is None or cv.user_id != owner_id:
            raise ResourceNotFoundError()
        # Only a committed library CV (``ready``) is analyzed/matchable and may be
        # submitted with an application (design spec 2026-07-05). A draft CV must be
        # finalized into the library first — reject with a clear, recoverable error
        # (the apply CV picker only offers ``ready`` CVs, so this guards the API).
        if cv.status != catalog.CV_READY:
            raise CvNotInLibraryError(status=cv.status)
        version = (
            await session.execute(
                select(CvVersion).where(CvVersion.id == version_id, CvVersion.cv_id == cv.id)
            )
        ).scalar_one_or_none()
        if version is None:
            raise ResourceNotFoundError()
        snapshot.cv_id = cv.id
        snapshot.cv_version_id = version.id
        snapshot.snapshot_json = dict(version.snapshot_json or {})
    elif sel_type == "uploaded_document":
        document_id = _shared.to_uuid(cv_selection.get("uploaded_document_id"))
        if not document_id:
            raise ValidationFailedError("Thiếu tài liệu CV đã tải lên để nộp.")
        document = (
            await session.execute(
                select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if document is None or document.user_id != owner_id:
            raise ResourceNotFoundError()
        run = (
            (
                await session.execute(
                    select(CvParseRun)
                    .where(CvParseRun.document_id == document.id)
                    .order_by(CvParseRun.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        extracted = (run.extracted_data if run else None) or {}
        snapshot.uploaded_document_id = document.id
        snapshot.snapshot_json = {
            "title": document.original_name,
            "source_type": "uploaded",
            "document_id": str(document.id),
            "sections": _sections_from_extracted(extracted),
        }
    else:
        raise ValidationFailedError("Loại CV nộp không hợp lệ.")

    session.add(snapshot)
    await session.flush()
    await write_audit(
        session,
        action="cv.snapshot.created",
        resource_type="application_cv_snapshot",
        resource_id=snapshot.id,
        context=_shared.audit_ctx(Principal(user_id=owner_id), ctx),
        after={
            "selection_type": sel_type,
            "application_id": str(application_id) if application_id else None,
        },
    )
    if commit:
        await session.commit()
        await session.refresh(snapshot)
    return snapshot


async def _load_snapshot(session: AsyncSession, *, snapshot_id: uuid.UUID) -> ApplicationCvSnapshot:
    snap = (
        await session.execute(
            select(ApplicationCvSnapshot).where(ApplicationCvSnapshot.id == snapshot_id)
        )
    ).scalar_one_or_none()
    if snap is None:
        raise ResourceNotFoundError()
    return snap


async def get_snapshot_json_for_application(
    session: AsyncSession, *, application_id: uuid.UUID
) -> dict | None:
    """The most recent immutable snapshot's structured JSON for ``application_id``.

    Read-only, privacy-neutral projection for advisory surfaces (e.g. the
    recruitment AI screening brief) that need CV content shape but must never
    import ``ApplicationCvSnapshot`` directly. Returns ``None`` if no snapshot
    exists for the application. The caller remains responsible for its own PII
    handling of the returned structure (e.g. skipping contact sections).
    """

    snap = (
        (
            await session.execute(
                select(ApplicationCvSnapshot)
                .where(ApplicationCvSnapshot.application_id == application_id)
                .order_by(ApplicationCvSnapshot.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    return dict(snap.snapshot_json or {}) if snap is not None else None


async def get_snapshot_download(
    session: AsyncSession, *, principal: Principal, snapshot_id: uuid.UUID
) -> dict:
    """Return a signed download URL for a snapshot.

    Owner -> unwatermarked. Authorized partner (via the authorizer seam) ->
    watermarked. Anyone else -> ``404`` (enumeration hiding).
    """

    snap = await _load_snapshot(session, snapshot_id=snapshot_id)
    watermark: str | None = None
    if principal.user_id is not None and snap.user_id == principal.user_id:
        watermark = None  # owner self-download is not watermarked
    else:
        access = _authorizer(principal, snap) if _authorizer is not None else None
        if access is None:
            raise ResourceNotFoundError()
        watermark = access.watermark_text or "VinUni Career"

    token = storage.make_signed_token(
        {
            "kind": "snapshot",
            "id": str(snap.id),
            "uid": str(principal.user_id),
            "purpose": "application_review" if watermark else "download",
            "wm": watermark or False,
        }
    )
    base = get_settings().app_url.rstrip("/")
    return {
        "snapshot_id": str(snap.id),
        "has_watermark": watermark is not None,
        "download_url": f"{base}/api/v1/cv-files/{token}",
    }


_DOC_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".doc")


def _snapshot_filename(body: dict) -> str:
    """Friendly display filename for a snapshot's ORIGINAL file.

    Uploaded-CV snapshots store the real ``document.original_name`` as ``title``
    (often already carrying an extension); builder-CV snapshots store the CV
    title (no extension → append ``.pdf`` since a builder CV renders to PDF).
    """

    raw_title = str(body.get("title") or "cv").strip() or "cv"
    if raw_title.lower().endswith(_DOC_EXTENSIONS):
        return raw_title
    return f"{raw_title}.pdf"


def _original_cv_url(snap: ApplicationCvSnapshot, *, actor_id: uuid.UUID | None, disp: str) -> str:
    """Mint a signed ``/cv-files`` URL that serves the snapshot's ORIGINAL bytes.

    ``disp`` is ``"inline"`` (embeddable view) or ``"attachment"`` (download). The
    token carries only a resource reference + access metadata (never a storage
    path) and NO watermark flag — the partner sees the student's real file.
    """

    token = storage.make_signed_token(
        {
            "kind": "snapshot_original",
            "id": str(snap.id),
            "uid": str(actor_id) if actor_id else "",
            "purpose": "application_review" if disp == "inline" else "application_download",
            "disp": disp,
        }
    )
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/cv-files/{token}"


async def build_partner_cv_view(
    session: AsyncSession,
    *,
    snapshot_id: uuid.UUID,
    actor_id: uuid.UUID | None,
) -> dict | None:
    """Mint an embeddable inline view + download URL for a snapshot's ORIGINAL file.

    Owner decision 2026-07-10: the partner sees the STUDENT'S ORIGINAL CV — the
    file the student uploaded, or the template CV's rendered PDF — NOT a
    watermarked derivative. The recruitment service calls this AFTER it has
    verified the partner's org ownership + CV-access RBAC for the application, so
    this trusts the caller (no authorizer seam). Returns ``{snapshot_id,
    filename, view_url, download_url}``:

    - ``view_url`` serves the original ``inline`` (``Content-Disposition: inline``,
      no ``X-Frame-Options``) so the frontend can embed it in an ``<iframe>``.
    - ``download_url`` serves the same original bytes as an ``attachment``.

    Both point at the token-authorized ``/api/v1/cv-files`` endpoint; the token
    carries only a resource reference (never a storage path) and every byte fetch
    is audited via ``signed_file_accesses``.

    Returns ``None`` when the snapshot is missing or retention-tombstoned (nothing
    renderable), so the caller surfaces ``cv: null``.
    """

    snap = await _load_snapshot(session, snapshot_id=snapshot_id)
    body = snap.snapshot_json if isinstance(snap.snapshot_json, dict) else {}
    if not body or body.get(_RETENTION_TOMBSTONE_MARKER):
        return None

    return {
        "snapshot_id": str(snap.id),
        "filename": _snapshot_filename(body),
        "view_url": _original_cv_url(snap, actor_id=actor_id, disp="inline"),
        "download_url": _original_cv_url(snap, actor_id=actor_id, disp="attachment"),
        # Explicit for the frontend + audits: the partner CV is the original file,
        # never a watermarked copy (owner decision 2026-07-10).
        "has_watermark": False,
    }


async def build_snapshot_original_download(
    session: AsyncSession,
    *,
    snapshot_id: uuid.UUID,
    actor_id: uuid.UUID | None,
) -> dict:
    """Return a signed download URL for a snapshot's ORIGINAL file (no watermark).

    Used by the recruitment ``/applications/{id}/cv-download`` endpoint for the
    partner path. The caller MUST have already verified org ownership +
    ``download_cv`` RBAC. Shaped like :func:`get_snapshot_download` (``{snapshot_id,
    has_watermark, download_url}``) so the response contract is unchanged, but the
    bytes are the student's original file served as an attachment.
    """

    snap = await _load_snapshot(session, snapshot_id=snapshot_id)
    return {
        "snapshot_id": str(snap.id),
        "has_watermark": False,
        "download_url": _original_cv_url(snap, actor_id=actor_id, disp="attachment"),
    }


# --------------------------------------------------------------------------- #
# Retention sweep (compliance module's scheduled job hook, ADR-0014 §35)      #
# --------------------------------------------------------------------------- #

_RETENTION_TOMBSTONE_MARKER = "_retention_anonymized"


async def anonymize_expired_snapshots(session: AsyncSession, *, older_than) -> int:
    """Anonymize snapshots created before ``older_than`` (a ``datetime``).

    Called ONLY by ``compliance.application.retention_service`` — the
    ``documents`` module never imports ``compliance`` (no direct cross-module
    ORM writes; this is the facade seam). Idempotent: a row already tombstoned
    (``snapshot_json`` carries the marker) is skipped on re-run, so running the
    sweep twice never double-processes. Snapshots stay immutable in every other
    sense (never deleted, ``application_id``/``id`` preserved) — only the PII
    payload is scrubbed in place, matching "soft-delete/anonymize" per the ADR.
    """

    rows = list(
        (
            await session.execute(
                select(ApplicationCvSnapshot).where(ApplicationCvSnapshot.created_at < older_than)
            )
        )
        .scalars()
        .all()
    )
    count = 0
    for row in rows:
        if isinstance(row.snapshot_json, dict) and row.snapshot_json.get(
            _RETENTION_TOMBSTONE_MARKER
        ):
            continue
        row.snapshot_json = {_RETENTION_TOMBSTONE_MARKER: True}
        row.redacted_json = None
        count += 1
    await session.flush()
    return count
