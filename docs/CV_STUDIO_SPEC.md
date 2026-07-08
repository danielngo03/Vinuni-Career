# CV Studio Spec — VinUni Career Platform

> Source of truth for CV upload, CV builder, AI-assisted CV creation, templates, exports, versioning, and CV-to-job optimization.
> Detailed uploaded-file ingestion, OCR/layout extraction, LLM fallback, and
> import behavior lives in `docs/CV_INGESTION_EXTRACTION_SPEC.md`.

> **UPDATE 2026-07-05 (owner decision — supersedes the field-review wording below):**
> The uploaded-CV flow is **upload → confirm file → name the CV → done**. Backend
> extraction is authoritative and creates the versioned draft directly; the student
> does NOT review or edit extracted fields (the field-review/diff screen was removed
> as wrong UX). Extraction accuracy is a backend responsibility because it feeds
> CV-JD matching. Where sentences below say "student reviews extracted fields",
> "field-by-field review", or "review/diff", read them as historical. The
> extraction cascade also gains a cheap **vision-LLM tier** that may receive
> DOWNSCALED document images for images and styled/scanned PDFs; the text-LLM
> structuring tier still receives text only. (This does NOT change the separate
> in-editor rule that natural-language CV Studio edits require a structured diff +
> student confirmation.)

## 1. Product Goal

CV Studio helps every student create, import, refine, tailor, and submit credible job-ready CVs.

It is not only for users who do not have a CV yet. It supports students who already have a CV, students who want a better template, and students who want AI help filling or improving a selected template.

CV Studio is **CV-first**, not profile-form-first. Students must not be forced
to manually enter education, experience, projects, and skills into a separate
profile form before using the product. Profile data is optional supporting
context: career preferences, privacy settings, notification settings, verified
VinUni facts, and facts the student has explicitly confirmed from a CV.

It supports five creation paths:

1. Upload an existing CV and extract structured data.
2. Choose a university-approved template and edit it manually like a document.
3. Fill a chosen template from uploaded CV extraction, confirmed profile facts,
   another CV, and/or raw notes.
4. Duplicate an existing builder CV and change template/content for a target role.
5. Use AI to fill, draft, rewrite, tailor, and review CV content with explicit user approval.

AI never silently edits or publishes a CV. AI proposes a diff; the student accepts, edits, or rejects it.

## 2. Personas

| Persona | Needs |
|---|---|
| First-time student | Upload a rough CV, choose a template, or ask AI to draft from notes without completing a long profile form first. |
| Experienced student | Up to the tier limit of tailored CVs per target role, version history, ATS/JD checks, and fast duplication. |
| External/general user | Template builder with quota-limited AI assistance and clear upgrade/request-more states. |
| Partner recruiter | Watermarked, permission-filtered CV preview/download during recruitment. |
| University admin | Aggregate CV quality/readiness analytics, no raw CV text unless explicitly permitted. |

## 3. Core Capabilities

### Upload And Import

- Upload existing CV files: PDF, DOCX, DOC, image.
- Extract structured content from an uploaded CV directly into a versioned builder
  draft. (Updated 2026-07-05: extraction is backend-authoritative; there is no
  manual review-source step.)
- Upload UX is preview-first: students see the original document/file preview
  before choosing to ingest/import it.
- Backend owns extraction. The UI must not require the student to understand or
  manually trigger parser/OCR/LLM steps.
- The student names the CV and confirms the file; the backend extraction produces
  the draft directly. (Updated 2026-07-05: no manual field-review step —
  backend-authoritative extraction; accuracy feeds CV-JD matching.)
- Import can target:
  - a new template CV,
  - an existing draft,
  - a duplicated CV for a new target role.
- Imported content never overwrites accepted CV content silently; it creates a preview/diff.
- Uploaded CV file remains available as original document, while builder CV becomes structured editable content.

### Template Marketplace And Manual Builder

- Template library with university-approved templates, preview thumbnails,
  categories, language support, premium/locked labels, and "best for" guidance.
- First screen is a CV library/template marketplace, not a data-entry profile
  wizard. Primary actions: Upload CV, Choose template, Ask AI to draft from
  notes, Duplicate existing CV.
- Editor should feel document-like and practical: section blocks, drag/drop
  reorder, inline text editing, quick style/template switch, and A4 preview.
- Section editor: summary, education, experience, projects, skills, certifications, awards, languages, publications, activities, custom sections.
- Guided empty states for users with no CV and quick-import states for users who already have uploaded CV data or confirmed facts.
- Import confirmed profile facts only when the student asks; never require it as
  a prerequisite and never assume unconfirmed profile text is CV-ready truth.
- Duplicate an existing CV to create a role-specific variant without changing the original.
- Drag reorder sections and bullets.
- Inline validation: missing dates, overly long bullets, empty required sections.
- Autosave draft every 5 seconds after local change, debounced.
- Version history and restore.
- Preview in A4 format with page-break warnings.
- Export PDF in v1; DOCX export later unless explicitly requested.

### Visual Canvas Editor Contract

The primary editor is a visual document canvas. It must not be implemented as a
long form where students edit name, phone, education, experience, and skills in
separate input panels as the main experience.

Required editor behavior:

- A4 page canvas with accurate page boundaries, print/export-safe spacing, and
  page-break warnings.
- Inline text editing for headings, bullets, dates, contact lines, links, and
  custom text blocks.
- Selectable content blocks/elements with a compact inspector for typography,
  spacing, visibility, ordering, and section metadata.
- Drag/drop reorder for sections and items, plus keyboard-accessible move
  controls.
- Photo placeholder support: upload, replace, crop, remove, and fit-to-shape.
- Template switch preview that preserves confirmed content where bindings match.
- Undo/redo, autosave, version history, and restore.
- Responsive editing: desktop canvas + inspector; mobile review/edit modes with
  section navigation, not a broken scaled desktop canvas.
- Export preview uses the same render pipeline as generated PDF.

Template records must represent both layout and content binding:

- `layout_schema`: pages, elements, typography tokens, grid/column geometry,
  spacing, page rules, and responsive editor hints.
- `content_binding_schema`: how structured CV facts bind to visual elements,
  repeatable section rules, fallbacks, max lines, and overflow behavior.
- `preview_image`: generated from the real template renderer, not a manually
  cropped mock.
- ownership/version fields so university staff can create, clone, publish,
  archive, and audit approved templates.

University template operations:

- Upload or create a template draft.
- Validate required bindings, overflow rules, localization, preview render, and
  export render.
- Publish/archive a version without breaking existing student CVs.
- Curate templates by industry/role family, language, and target audience.

### Natural-Language AI Editing

Students can ask the AI to edit the CV in natural language, for example:
"0324xx0898 is my phone number", "make this summary more suitable for data
analyst roles", or "move projects above experience for this internship".

This is a write-action flow:

1. Resolve the target CV, current version, selected element/section if any, and
   allowed source facts.
2. Produce a structured patch/diff against the canvas/content model.
3. Show the proposed change on the canvas and in a compact diff panel.
4. Require the student to accept, edit, or reject.
5. On accept, create a new `cv_versions` row and audit event.

The AI must not mutate the CV directly, invent facts, or apply hidden style
changes that the student cannot review.

### AI-Assisted Builder

- Generate first draft from raw notes, uploaded CV extraction, confirmed profile
  facts, selected template, and an optional short guided questionnaire.
- Fill a selected template from uploaded CV extraction, another builder CV, raw
  notes, and confirmed profile facts.
- Generate bullet points from raw experience notes.
- Rewrite a selected bullet/section using user instruction.
- Convert casual text into professional Vietnamese/English CV language.
- Tailor CV to a specific job while preserving factual truth.
- Recommend the best CV to use for a target job from the student's CV library.
- Score CV-to-job fit on a user-facing 0-100 scale with explainable categories:
  required skills, nice-to-have skills, education/eligibility, experience/project
  evidence, language/location/work-mode fit, and CV quality/staleness.
- ATS keyword suggestions with exact source from JD.
- Grammar, clarity, repetition, and impact checks.
- Translate section content vi/en with tone preservation.

AI output is stored as `cv_ai_suggestions` until accepted. Accepting creates a new `cv_versions` row and audit event.

### Job-Tailored Optimization

- Student selects a target job.
- System compares every eligible active CV against JD requirements and suggests:
  best CV to apply with, alternatives, and why.
- The match score is a product score, not a model confidence score. It must be
  explainable, reproducible enough for the same inputs, and backed by visible
  evidence categories rather than vague "AI thinks you match" copy.
- AI suggestions are grouped:
  - missing-but-true information to add,
  - wording improvement,
  - ordering/priority,
  - keyword coverage,
  - evidence gaps.
- Score bands:
  - `85-100` strong fit: ready to apply after final review.
  - `70-84` good fit: apply after addressing a small number of gaps.
  - `50-69` possible fit: review eligibility and improve evidence before apply.
  - `<50` weak fit: show honest guidance and adjacent roles/learning paths.
- AI cannot invent education, employer, award, GPA, certification, dates, or quantified outcomes.
- If the AI suggests an unverified fact, the UI labels it "Cần xác nhận" and requires user confirmation/edit.

## 4. CV Document Lifecycle

```text
DRAFT
  -> READY
  -> ARCHIVED

Draft edits:
  section update -> autosave draft version
  AI suggestion -> pending suggestion
  accept suggestion -> new version
  export -> cv_exports row + generated document
```

Uploaded CV lifecycle:

```text
UPLOADED
  -> VIRUS_SCANNING
  -> EXTRACTING
  -> REVIEW_REQUIRED
  -> CONFIRMED
  -> ARCHIVED

Failure branches:
  VIRUS_SCANNING -> REJECTED_SECURITY
  EXTRACTING -> FAILED_PASSWORD_PROTECTED
  EXTRACTING -> FAILED_CORRUPT
  EXTRACTING -> FAILED_BLANK
  EXTRACTING -> FAILED_NOT_CV
  EXTRACTING -> FAILED_LOW_QUALITY
  EXTRACTING -> REVIEW_REQUIRED_LOW_CONFIDENCE
```

(Updated 2026-07-05: `REVIEW_REQUIRED` / `REVIEW_REQUIRED_LOW_CONFIDENCE` no
longer surface a manual field-review screen to the student. Extraction is
backend-authoritative; these remain internal quality states that the backend
resolves before producing the versioned draft. Blank/not-CV/corrupt uploads are
rejected and are never fabricated into a CV.)

Builder-generated CVs and uploaded CVs share the same student-facing CV list, but they are stored differently:

- uploaded originals are `documents` rows and appear in UI with `source_type = uploaded`;
- builder/template CVs are `cv_profiles` rows with `source_type = builder`;
- imported/derived builder CVs use `source_type = uploaded_import`,
  `confirmed_facts_import`, `duplicate_existing`, or `ai_draft`.

## 5. Business Rules

- Tier config controls max active CVs, max templates, AI credits, and export quota.
- Default student quota is **5 active CV library items** unless university admin
  changes the tier limit. Active items include usable uploaded CV originals and
  builder/template CVs shown as selectable application CVs. Archived CVs and
  immutable application snapshots do not count.
- Every student can create at least one non-AI CV for free even if AI is disabled.
- Existing uploaded CVs can be imported into templates; upload remains immutable original evidence.
- Duplicate/retarget actions create a new CV profile; they never mutate the original CV.
- If the student reaches the active CV limit, the UI offers archive/delete,
  duplicate into an existing draft, request more quota, or upgrade where
  applicable. It must not silently fail.
- Setting primary CV is a write action and must be audited.
- Deleting a CV archives it; existing applications retain the submitted CV snapshot.
- CV used in an application is immutable for that application; later CV edits do not change submitted applications.
- Partner download always uses a watermarked rendered PDF.
- Anonymous applications use redacted preview generated from submitted snapshot, not live current CV.
- AI CV suggestions consume credits only when generation succeeds.
- Upload validation failures before AI generation do not consume AI credits.
- Regeneration overwrites only the pending suggestion, never the accepted CV.
- Exported files expire from temporary storage unless attached to an application snapshot.

## 5A. Upload Validation And Failure Handling

Use with `docs/EDGE_CASES_FAILURE_MODES.md`.
For detailed extraction architecture and UI acceptance criteria, use
`docs/CV_INGESTION_EXTRACTION_SPEC.md`.

Before a file can be imported into a builder CV:

1. Validate MIME and extension.
2. Compute checksum and detect duplicate uploads for the same user.
3. Run virus scan.
4. Store immutable original and create an ingestion/parse job.
5. Extract native text when possible.
6. Run layout-aware extraction when native text is disordered, sparse, or
   column/canvas-heavy.
7. Run OCR fallback only when native text/layout extraction is empty or low
   quality.
8. Escalate to a cheap vision-LLM tier for images and styled/multi-column scanned
   PDFs when native text + local OCR are insufficient. (Updated 2026-07-05: this
   tier MAY receive DOWNSCALED document images; the separate text-LLM structuring
   tier still receives text/markdown only.)
9. Use optional text-LLM structuring only after local extraction has produced text
   or markdown and only when enabled by AI settings/env.
10. Classify whether the document is likely a CV/resume.
11. Check minimum usable content.
12. Create a parse result: `CONFIRMED`, `REVIEW_REQUIRED`, or a failure status.

Minimum CV signals:

- At least one contact/name/header signal OR student manually identifies the file as theirs.
- At least two of: education, experience, projects, skills, certifications, activities, awards, languages.
- Text length above configured minimum after extraction/OCR.

Failure behavior:

- `BLANK_DOCUMENT`, `NOT_A_CV`, `LOW_QUALITY_SCAN`, `PASSWORD_PROTECTED_FILE`, and `CORRUPT_FILE` are user-fixable failures.
- UI offers: upload another file, create from template, or manually enter content.
- Low-confidence extraction is resolved backend-side; it never silently overwrites
  an already-accepted CV. (Updated 2026-07-05: `REVIEW_REQUIRED` is an internal
  quality state, not a student-facing field-review screen.)
- Internal confidence/error details are logged internally only and never shown to the user.
- Parser/AI uncertainty must preserve student trust: say what happened and what to do next.
- The release UI must provide original preview + name-and-confirm import/template
  action, with mobile tabs and quota/failure recovery. (Updated 2026-07-05:
  uploaded-CV flow is upload-and-name; no manual field-review/diff step —
  backend-authoritative extraction produces the draft directly.)

## 6. Data Model Additions

Canonical tables are defined in `docs/DATA_MODEL.md`; this section explains intent.

| Entity | Purpose |
|---|---|
| `cv_templates` | University-approved templates with layout schema and preview image. |
| `cv_template_versions` | Immutable template layout/content-binding versions for published templates. |
| `cv_template_assets` | Template-owned fonts, sample photos, thumbnails, and render artifacts. |
| `cv_profiles` | Student-owned logical CV document, independent of file exports. |
| `cv_sections` | Structured editable sections and items. |
| `cv_versions` | Immutable snapshot of CV JSON after every meaningful save/accept. |
| `cv_ai_suggestions` | Pending AI suggestion/diff before user acceptance. |
| `cv_exports` | PDF/DOCX render jobs and generated file metadata. |
| `application_cv_snapshots` | Immutable snapshot of CV submitted to a job. |

## 7. API Surface

Detailed request/response conventions live in `docs/API_CONTRACTS.md`.

Minimum paths:

- `GET /api/v1/cv-templates`
- `POST /api/v1/admin/cv-templates`
- `PATCH /api/v1/admin/cv-templates/{template_id}`
- `POST /api/v1/admin/cv-templates/{template_id}/publish`
- `POST /api/v1/admin/cv-templates/{template_id}/archive`
- `POST /api/v1/admin/cv-templates/{template_id}/preview`
- `GET /api/v1/cvs`
- `POST /api/v1/cvs`
- `GET /api/v1/cvs/{cv_id}`
- `PATCH /api/v1/cvs/{cv_id}`
- `PATCH /api/v1/cvs/{cv_id}/canvas`
- `POST /api/v1/cvs/{cv_id}/duplicate`
- `POST /api/v1/cvs/{cv_id}/sections`
- `PATCH /api/v1/cvs/{cv_id}/sections/{section_id}`
- `POST /api/v1/cvs/{cv_id}/versions/{version_id}/restore`
- `POST /api/v1/cvs/{cv_id}/ai-edit-command`
- `POST /api/v1/cvs/{cv_id}/ai-suggestions`
- `POST /api/v1/cvs/{cv_id}/ai-suggestions/{suggestion_id}/accept`
- `POST /api/v1/cvs/{cv_id}/export`
- `GET /api/v1/cv-exports/{export_id}`

All mutating endpoints require RBAC ownership checks and audit.

## 8. AI Tool Contracts

| Tool | Permission | Side Effect |
|---|---|---|
| `draft_cv_from_sources` | `confirmation_required` | creates pending builder draft from raw notes, uploaded extraction, selected template, and confirmed facts |
| `fill_cv_template_from_sources` | `confirmation_required` | creates pending draft/diff from selected sources |
| `generate_cv_bullets` | `confirmation_required` | creates pending suggestion |
| `rewrite_cv_section` | `confirmation_required` | creates pending suggestion |
| `optimize_cv_for_job` | `confirmation_required` | creates pending suggestion tied to job |
| `recommend_cv_for_job` | `read_only` | returns ranked CV options and 0-100 fit explanation |
| `ats_keyword_suggestions` | `read_only` | returns advice only |
| `cv_fabrication_check` | `human_review` when high risk | flags suspicious claims |

Confirmation copy must show:

- target CV,
- sections affected,
- before/after diff,
- credits used,
- warning that the student is responsible for factual accuracy.

## 9. UI Requirements

Primary routes:

- `/student/cv`: CV library, upload/import status, template marketplace, quota,
  and job-fit recommendations.
- `/student/cv/builder`: focused editor for one CV.

Desktop layout:

```text
CV Library / Templates        Center editor                  Right preview / AI panel
Upload/import status          Document-like section blocks    A4 preview
Template categories           Inline validation               Job-fit / ATS drawer
Versions                      Autosave status                 AI suggestions/diff
```

Mobile layout:

- Tabs: Sections | Edit | Preview | AI.
- Sticky bottom action bar for Save, Preview, Export.
- No horizontal overflow; A4 preview scales down with zoom controls.

Required states:

- No CV yet: guided start wizard.
- CV quota reached: show active CV count, archive/delete/request-more/upgrade actions.
- Has uploaded CV: import-to-template path.
- Has builder CV: duplicate/change-template path.
- Draft autosaving.
- AI suggestion pending.
- Job selected: rank all eligible CVs, show recommended CV, score bands, gaps,
  and "improve this CV" action.
- Export queued/running/ready/failed.
- Template locked by tier.
- Credit exhausted.
- Offline/reconnect with unsaved local draft preserved.
- Upload rejected with friendly reason and next action.
- Uploaded file not recognized as CV: upload another file or start from template.
- Blank/low-quality scan: explain unreadable file and suggest clearer PDF/DOCX.
- Low-quality extraction: the backend resolves it and produces the best draft it
  can; the student refines it later in the editor. (Updated 2026-07-05: no manual
  field-by-field review step — backend-authoritative extraction.)

## 10. Accessibility And UX

- All section controls keyboard accessible.
- Drag reorder has keyboard alternative.
- A4 preview is not the only way to read content; editor text remains semantic HTML.
- Error messages explain the fix.
- Changes from AI are shown as accessible diff, not only color.
- Respect `prefers-reduced-motion`.
- No emoji as icons; use the project icon set.

## 11. Analytics

Events:

- `cv.builder.started`
- `cv.section.created`
- `cv.section.updated`
- `cv.ai_suggestion.requested`
- `cv.ai_suggestion.accepted`
- `cv.ai_suggestion.rejected`
- `cv.export.requested`
- `cv.export.completed`
- `cv.primary_set`
- `cv.used_for_application`

No raw CV text in analytics payloads.

## 12. Tests

Required coverage:

- Create CV from blank template.
- Import from profile.
- Import from uploaded CV extraction.
- Upload preview and import confirmation for PDF/image/DOCX.
- Upload invalid file, blank PDF, password-protected PDF, corrupt file, duplicate file, non-CV PDF, low-quality scan, two-column PDF, canvas/vector-heavy PDF, and scanned/image CV.
- OCR fallback mocked or real for `vie+eng`.
- Layout extraction fallback for sparse/disordered native text.
- LLM structuring disabled/unavailable and enabled-with-fake-provider paths.
- Duplicate existing CV and change template.
- AI fills selected template from permitted sources.
- Autosave and restore version.
- AI suggestion creates pending diff, not direct edit.
- Accepting AI suggestion creates new version and audit.
- Export PDF success/failure.
- Application snapshot remains immutable after CV edits.
- Partner download is watermarked.
- Anonymous preview redacts PII.
- Credit/quota enforcement.
- Accessibility for section editor, tabs, diff viewer, template chooser.
