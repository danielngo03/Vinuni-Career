"""Documents / CV Studio ORM models (``docs/DATA_MODEL.md`` §7, §9).

Owns uploaded CV originals, parse runs, builder CVs (profiles + sections +
immutable versions), templates, exports, signed-file access audit, and immutable
application CV snapshots.

Types use the shared cross-database variants (``JsonType``, ``Uuid``) so the same
models run on PostgreSQL (runtime) and SQLite (unit tests). Postgres-only
constructs (partial/GIN indexes, ``set_updated_at`` trigger, template seeds) live
in migration ``0005`` only.

Documented deviations from the canonical ``docs/DATA_MODEL.md`` columns
(necessary because the ``recruitment`` / ``student_profiles`` modules are not yet
built):

- ``documents.idempotency_key`` — upload idempotency (per ``docs/API_CONTRACTS.md``
  upload contract requires an idempotency key).
- ``cv_profiles.idempotency_key`` — duplicate idempotency.
- ``cv_exports.idempotency_key`` / ``cv_exports.storage_key`` — export idempotency
  and the rendered-file storage key (kept off ``documents`` since an export is not
  a user upload; ``document_id`` is reserved for when an export is attached to an
  application snapshot).
- ``signed_file_accesses`` generalized with ``resource_kind`` / ``resource_id`` so
  the same audit trail covers exports and snapshots, not just uploaded documents
  (``document_id`` made nullable).
- ``application_cv_snapshots.user_id`` — owner column for tenant isolation /
  ownership checks without joining ``applications`` (which do not exist yet);
  ``application_id`` is a nullable bare UUID (FK + NOT NULL added by the
  ``recruitment`` migration when ``applications`` exists).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import Base, JsonType


class CvTemplate(Base):
    """University-approved CV template carrying a full visual theme + governance.

    ``layout_schema`` holds the versioned visual theme (layout/palette/typography/
    photo/sectionStyle/regions/order) consumed by the renderer — the single source
    of visual truth (``domain.themes``). Governance columns (``status`` /
    ``version`` / ``owner_org_id`` / ``published_at`` / ``archived_at``) let a
    university publish/archive templates without breaking student CVs bound to an
    older ``cv_template_versions`` snapshot.
    """

    __tablename__ = "cv_templates"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name_vi: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    layout_schema: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    preview_image: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Governance: draft | published | archived. Only published + active templates
    # are offered to students (``GET /cv-templates``).
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="published"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # NULL = built-in/global template; set = university-owned.
    owner_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class CvTemplateVersion(Base):
    """Immutable published snapshot of a template's design.

    Publishing a new template version inserts one of these rows and never mutates
    prior versions, so a ``cv_profiles.template_version_id`` bound to an older
    version keeps rendering exactly as it did (design spec §4.1).
    """

    __tablename__ = "cv_template_versions"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "version_number", name="uq_cv_template_versions_num"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cv_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    design_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    preview_image: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Document(Base):
    """An uploaded original document (CV/cover-letter/etc.). Soft-deleted only.

    ``storage_path`` is an internal storage key and is **never** exposed in any
    API response or log.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False, default="cv")
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    virus_scan_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    virus_scan_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CvParseRun(Base):
    """Result of a deterministic upload parse (``docs/CV_STUDIO_SPEC.md`` §5A).

    Internal-only columns (``provider_alias``, ``confidence``, ``error_message``)
    are never surfaced to clients.
    """

    __tablename__ = "cv_parse_runs"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    quality_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extracted_data: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    review_fields: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CvIngestion(Base):
    """An adapter-based CV ingestion job (``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §5).

    The product-facing ingestion state for an uploaded document: a user-safe
    ``status`` from the friendly vocabulary (checking/reading/improving_layout/
    reading_scanned/preparing_review/needs_review/ready/failed), a user-safe
    ``quality_code``, field-level ``review_fields`` (needs-review markers, NOT
    numeric confidence), ``next_actions``, and ``detected_language``.

    INTERNAL-only columns (``engine_family``, ``engine_version``, ``text_length``,
    ``error_code``, ``extracted_data``) are never surfaced in any user response;
    ``extracted_data`` is read only by the owner's import step. Re-ingestion is
    idempotent: one job per (document, attempt) resolved by the service.
    """

    __tablename__ = "cv_ingestions"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    quality_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    mixed_language: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # INTERNAL diagnostics — never returned to clients.
    text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engine_family: Mapped[str | None] = mapped_column(String(60), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Owner-only structured payload (used at import); never logged.
    extracted_data: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    review_fields: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    next_actions: Mapped[list | None] = mapped_column(JsonType, nullable=True)
    imported_cv_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class CvProfile(Base):
    """A student-owned builder CV. Soft-deleted (archived) only."""

    __tablename__ = "cv_profiles"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="builder")
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_templates.id", ondelete="SET NULL"), nullable=True
    )
    # The exact template design version this CV is bound to. Nullable: existing CVs
    # and CVs created before a template is versioned resolve to the template's
    # current ``layout_schema``; a bound version pins the look against later admin
    # republishes (design spec §4.1).
    template_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_template_versions.id", ondelete="SET NULL"), nullable=True
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # When this CV was committed into the student's library (draft -> ready): set on
    # finalize and on upload-import (an uploaded CV is analyzed on arrival). NULL while
    # it is still an unlimited, non-matchable draft. The two-tier library lifecycle
    # (design spec 2026-07-05): only ``ready`` CVs count to the 5-cap and are usable
    # for apply / job-fit.
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Canvas/block-level layout metadata for the visual document editor
    # (``docs/CV_STUDIO_SPEC.md`` "Visual Canvas Editor Contract"): per-block
    # ordering/position/visibility overrides keyed by ``section_id``/``block_id``,
    # plus the profile-photo binding (``{"photo": {"document_id", "crop", "shape"}}``).
    # This is presentation/layout metadata ONLY — section CONTENT (the CV facts)
    # still lives in ``cv_sections.content_json``; the canvas never duplicates or
    # overrides facts. Included in every version snapshot so restore/versioning
    # covers layout too.
    canvas_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    # INTERNAL matching representation derived at finalize from the structured
    # sections (normalized skills, keyword set, contact presence, experience entry
    # count) — see ``cv_lifecycle_service._analyze_for_matching``. Deterministic,
    # no OCR/AI. NULL for drafts (set only when a CV is committed into the library).
    # NEVER surfaced in a student-facing response (internal read model for CV-JD
    # matching only); presenters must not include it.
    matching_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)


class CvSection(Base):
    """A structured, editable CV section (CASCADE on profile delete)."""

    __tablename__ = "cv_sections"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    content_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class CvVersion(Base):
    """Immutable snapshot of CV JSON after a meaningful save/accept."""

    __tablename__ = "cv_versions"
    __table_args__ = (UniqueConstraint("cv_id", "version_number", name="uq_cv_versions_cv_num"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    change_source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    change_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CvAiSuggestion(Base):
    """A pending AI suggestion/diff for a CV before user acceptance.

    AI is non-destructive: this row stores a reviewable diff (``diff_json``) and is
    NOT applied to the CV until the owner accepts (which creates a new
    ``cv_versions`` row). ``diff_json`` is metadata + grounded content only — it
    never contains provider/model/token internals or prompt text
    (``docs/SECURITY_PRIVACY.md`` AI Safety; ``docs/CV_STUDIO_SPEC.md`` §3).

    ``job_id`` is a bare nullable UUID (no FK) to avoid coupling ``documents`` to
    the ``opportunities`` module; ``target_section_id`` / ``applied_version_id``
    use ``SET NULL`` so history survives section/version churn.
    """

    __tablename__ = "cv_ai_suggestions"
    __table_args__ = (
        UniqueConstraint("cv_id", "idempotency_key", name="uq_cv_ai_suggestions_idem"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_sections.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    diff_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    credits_charged: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    accept_idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    applied_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CvExport(Base):
    """A PDF render job + generated-file metadata."""

    __tablename__ = "cv_exports"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cv_versions.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    export_format: Mapped[str] = mapped_column(String(20), nullable=False, default="pdf")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SignedFileAccess(Base):
    """Audit trail for every signed-file download/preview (``docs/SECURITY_PRIVACY.md``)."""

    __tablename__ = "signed_file_accesses"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    # resource_kind: one of export | snapshot | document
    resource_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    accessor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    accessor_org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    has_watermark: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    watermark_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signed_url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ApplicationCvSnapshot(Base):
    """Immutable CV snapshot scoped to an application (no update/delete).

    ``application_id`` is a bare nullable UUID until the ``recruitment`` module's
    ``applications`` table exists; ``user_id`` is the owner for tenant isolation.
    """

    __tablename__ = "application_cv_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cv_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="SET NULL"), nullable=True
    )
    cv_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_versions.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    snapshot_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    redacted_json: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CvJobFitScore(Base):
    """Persisted, version-stamped CV-to-job fit result (the fit-score store).

    One row per ``(cv_id, job_id)`` pair. Stores the DETERMINISTIC 6-criteria product
    score plus the OPTIONAL AI ``explanation`` for the recommended CV, stamped with
    the CV/JD content versions and the deterministic ``scorer_version`` at compute
    time. A row is only recomputed when one of those stamps no longer matches the
    live content (see ``fit_store.is_fresh``), so reloads reuse the stored value and
    the expensive LLM explanation is generated once per content version, not per
    request (owner requirement 2026-07-06). PII-safe: only the user-facing
    explanation text is stored — never provider/model/token/prompt internals.
    """

    __tablename__ = "cv_job_fit_scores"
    __table_args__ = (
        UniqueConstraint("cv_id", "job_id", name="uq_cv_job_fit_scores_cv_job"),
        Index("ix_cv_job_fit_scores_user_job", "user_id", "job_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cv_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Deterministic result (product score + 6-criterias + surfaced evidence).
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    bands: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    matched_skills: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    gaps: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    signal: Mapped[str] = mapped_column(String(20), nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_updated_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Avg self-rated skill proficiency (0-100); RANKING TIE-BREAKER only, never
    # part of the score. Neutral 50.0 when the CV states no numeric levels.
    avg_skill_level: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)

    # Version stamps — a row is fresh only when all three match the live inputs.
    cv_version: Mapped[int] = mapped_column(Integer, nullable=False)
    job_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scorer_version: Mapped[str] = mapped_column(String(20), nullable=False)

    # Optional AI explanation for the recommended CV (regenerated only when the
    # content version or prompt version/language changes).
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation_prompt_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    explanation_lang: Mapped[str | None] = mapped_column(String(5), nullable=True)
    explanation_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class CvFitExplanationCache(Base):
    """Cross-CV reuse cache for CV-JD fit EXPLANATIONS (the "learning" cache).

    At scale many DIFFERENT students apply to the SAME popular JD. Two CVs that
    produce the SAME deterministic evidence (matched skills + gaps) against the
    SAME JD version share ONE generated explanation — the second CV reuses the
    first CV's summary at 0 extra tokens instead of triggering its own LLM call.

    Keyed by a content ``fingerprint`` (a sha256 hex of job id + job version +
    sorted matched skills + sorted gaps + prompt version + language). The stored
    ``explanation`` text is REQUIREMENT-CENTRIC and CV-AGNOSTIC by construction
    (prompt v3 rule 9), so sharing it can never leak another CV's unique details.

    PII-safe: stores ONLY the user-facing explanation text — no ``user_id``,
    ``cv_id``, provider/model/token/prompt internals. The text is not
    user-specific by construction, so no owner column is needed.
    """

    __tablename__ = "cv_fit_explanation_cache"

    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    lang: Mapped[str] = mapped_column(String(5), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class SkillTranslationCache(Base):
    """Permanent VN→EN canonical-skill-term translation cache.

    Cross-lingual CV-JD matching translates every non-English skill term to its
    canonical English form once (temperature 0, so the translation is stable) and
    reuses it forever. Keyed by the LOWERCASED, whitespace-normalized source term
    (``source_norm``), so "Quản lý chuỗi cung ứng" and "quản lý  chuỗi cung ứng"
    share one row. The stored ``translated`` value is the concise English skill
    term a recruiter would list (e.g. "supply chain management").

    PII-safe: stores ONLY generic, domain-neutral skill strings — never user data,
    CV text, provider/model/token/prompt internals. The mapping is not
    user-specific, so no owner column is needed and the cache is shared across all
    students (a translation done for one CV serves every future CV).
    """

    __tablename__ = "skill_translation_cache"

    source_norm: Mapped[str] = mapped_column(String(255), primary_key=True)
    translated: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
