"""Pydantic request schemas for the documents / CV Studio API.

HTTP validation only; vocabulary checks and business rules live in the services.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class CvSourceInput(BaseModel):
    import_profile: bool = False
    uploaded_document_id: uuid.UUID | None = None
    cv_parse_run_id: uuid.UUID | None = None
    source_cv_id: uuid.UUID | None = None
    source_cv_version_id: uuid.UUID | None = None
    raw_notes: str | None = Field(default=None, max_length=5000)


class CreateCvRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    template_id: uuid.UUID | None = None
    creation_mode: str = Field(default="blank_template", max_length=40)
    language: str = Field(default="vi", max_length=10)
    source: CvSourceInput | None = None


class UpdateCvRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = Field(default=None, max_length=10)
    status: str | None = Field(default=None, max_length=20)
    template_id: uuid.UUID | None = None
    is_primary: bool | None = None
    expected_version: int | None = None


class SectionUpsertRequest(BaseModel):
    section_type: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=200)
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    is_visible: bool | None = None
    content: dict | None = None
    expected_version: int | None = None


class CreateSectionRequest(BaseModel):
    """Create a new section on a CV. Same shape as the section upsert; ``sort_order``
    is optional (the new section is appended after the current last section)."""

    section_type: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=200)
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    is_visible: bool | None = None
    content: dict | None = None
    expected_version: int | None = None


class RestoreVersionRequest(BaseModel):
    expected_version: int | None = None


class DuplicateCvRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    template_id: uuid.UUID | None = None
    target_job_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


class ExportCvRequest(BaseModel):
    version_id: uuid.UUID
    format: str = Field(default="pdf", max_length=10)
    idempotency_key: str | None = Field(default=None, max_length=200)


class AiSuggestionSourceIds(BaseModel):
    profile: bool = False
    uploaded_document_id: uuid.UUID | None = None
    cv_parse_run_id: uuid.UUID | None = None
    source_cv_id: uuid.UUID | None = None


class AiSuggestionRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=50)
    target_section_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    instruction: str | None = Field(default=None, max_length=5000)
    raw_notes: str | None = Field(default=None, max_length=10000)
    source_ids: AiSuggestionSourceIds | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


class AcceptAiSuggestionRequest(BaseModel):
    accepted_diff: dict | None = None
    fact_confirmation: bool = False
    idempotency_key: str | None = Field(default=None, max_length=200)


class AiEditCommandRequest(BaseModel):
    """Natural-language CV edit request (``docs/CV_STUDIO_SPEC.md``
    "Natural-Language AI Editing"). Always produces a pending diff; never
    mutates the CV directly."""

    instruction: str = Field(min_length=1, max_length=2000)
    target_section_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


class CvCanvasBlock(BaseModel):
    """A single canvas block layout entry (presentation metadata only; CV facts
    stay in the referenced section's ``content_json``)."""

    id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=30)
    section_id: uuid.UUID | None = None
    order: int = Field(default=0, ge=0, le=100000)
    visible: bool = True
    style: dict | None = None


class UpdateCvCanvasRequest(BaseModel):
    """Partial update: only the keys provided are replaced. The photo binding
    (managed by ``PATCH /cvs/{cv_id}/photo``) is left untouched here."""

    blocks: list[CvCanvasBlock] | None = Field(default=None, max_length=300)
    page: dict | None = None
    expected_version: int | None = None


class IngestRequest(BaseModel):
    """Start/resume ingestion for an uploaded document."""

    idempotency_key: str | None = Field(default=None, max_length=200)


class IngestionFieldOverride(BaseModel):
    """A single per-field review decision carried into the imported draft.

    ``path`` must match a field the ingestion actually produced in
    ``review_fields`` (e.g. ``contact.email`` or ``skills[2].text``); the service
    rejects/ignores any path outside that allowlist. When ``accepted`` is
    ``True`` (default), ``value`` is the student's own typed correction (or the
    original extracted value, unchanged) and is imported. When ``accepted`` is
    ``False`` the field is EXCLUDED from the imported draft entirely (the item is
    dropped / the contact field is left unset) — this is the explicit "reject"
    path so the review screen is a real accept/edit/reject diff, not a single
    blanket confirmation checkbox.
    """

    path: str = Field(min_length=1, max_length=120)
    value: str = Field(default="", max_length=5000)
    accepted: bool = True


class ImportIngestionRequest(BaseModel):
    """Confirm + import a reviewed ingestion into a NEW or DRAFT builder CV."""

    title: str | None = Field(default=None, max_length=200)
    template_id: uuid.UUID | None = None
    target_cv_id: uuid.UUID | None = None
    fact_confirmation: bool = False
    overrides: list[IngestionFieldOverride] | None = Field(default=None, max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=200)


class CvTemplateCreateRequest(BaseModel):
    key: str = Field(min_length=2, max_length=100)
    name_vi: str = Field(min_length=2, max_length=200)
    name_en: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=2, max_length=50)
    layout_schema: dict = Field(default_factory=dict)
    is_premium: bool = False
    is_active: bool = True

    model_config = ConfigDict(extra="forbid")


class CvTemplateUpdateRequest(BaseModel):
    key: str | None = Field(default=None, min_length=2, max_length=100)
    name_vi: str | None = Field(default=None, min_length=2, max_length=200)
    name_en: str | None = Field(default=None, min_length=2, max_length=200)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    layout_schema: dict | None = None
    is_premium: bool | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")
