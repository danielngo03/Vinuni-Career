# CV Ingestion And Extraction Spec

> Source of truth for uploaded-CV preview, backend ingestion, OCR/layout extraction, LLM fallback, review/import, and recovery states.

> **UPDATE 2026-07-05 (owner decisions — supersede parts of this spec):**
> 1. **No manual field-review step.** The flow is **upload → confirm file → name
>    the CV → done**. The backend extraction is authoritative and produces the
>    versioned draft directly; the student does NOT review or edit extracted fields
>    (the field-review screen and per-field confirmation gate were removed — they
>    were judged wrong UX). Sections marked "Review Screen" / "review/import
>    per-field decisions" below are historical and no longer implemented.
> 2. **Vision-LLM tier added.** Extraction is a cost-tiered cascade: native text
>    (free) → local OCR → a **cheap vision-LLM** (Gemini-class) that reads the
>    document **image** for images and styled/multi-column scanned PDFs, then does
>    OCR + structuring in one call. Sending DOWNSCALED images to this model is
>    permitted (supersedes any "text-only to LLM" wording here); the text-LLM
>    structuring tier still gets text only. For PDFs the native text is passed
>    alongside the image so exact emails/phones/dates come from the embedded text.
> 3. **Structured, matching-ready output.** Each job/degree is one coherent entry
>    (role — org | dates + bullets); skill/language proficiency shown as
>    stars/bars/words is captured (e.g. "— 4/5"). Non-CV/blank/corrupt uploads are
>    rejected with a clear status and are never fabricated into a CV.

## 1. Product Principle

CV upload is a user-facing document workflow, not a parser demo.

The student should experience (per the 2026-07-05 update above):

1. choose or drag a CV file;
2. see a faithful preview or file summary;
3. name the CV and click one clear action such as `Save this CV`;
4. let the backend process extraction and store it — no manual field review;
5. land on the resulting draft CV, which they may refine with AI/editor tools
   later without losing factual control.

The user does not need to know whether the system used native text extraction,
OCR, layout analysis, or an LLM. Internal parser/provider details are never
shown in end-user UI.

## 2. UX Contract

### Upload Preview First

- PDF upload shows an in-browser document preview with page thumbnails, zoom,
  and file metadata before import.
- Image upload shows image preview.
- DOC/DOCX upload shows file metadata and a rendered text/thumbnail preview when
  available; otherwise show a polished "Preview after processing" state.
- The first user decision is not "trust parser output"; it is "this is the CV I
  want to use".

### Backend Processing

After confirmation, backend creates an ingestion job. The UI shows friendly
states:

- `Checking file`
- `Reading document`
- `Improving layout`
- `Reading scanned pages` only if OCR is needed
- `Preparing review`
- `Needs your review`
- `Ready to import`

Do not expose engine names, model names, prompt names, token counts, raw
confidence, storage keys, or stack traces.

### Review Screen

Desktop layout:

```text
Original preview       Extracted fields / diff          Template preview / actions
PDF/image pages        contact, education, skills       choose template, import, save
page highlight         low-confidence badges            AI improve, rewrite, export
```

Mobile layout:

- Tabs: Original | Review | Template.
- Sticky actions: Use as original, Import to template, Upload another.

Required review behavior:

- Field-level confidence is translated into user language such as "Check this"
  rather than numeric confidence.
- Low-confidence fields are editable before import.
- Missing sections offer manual add and AI draft from confirmed text.
- Import creates a draft/version; it never silently overwrites an accepted CV.
- Student can keep the uploaded file as an original CV even when structured
  extraction needs review, subject to quota and application rules.

## 3. Extraction Cascade

Use a local-first adapter cascade. Keep each engine behind an interface so the
project can switch without rewriting business logic.

1. **Security and file gates**
   - size, extension/MIME, magic bytes, duplicate checksum;
   - malware/security scan hook;
   - password/corrupt detection;
   - unsupported type rejection.
2. **Native text extraction**
   - preferred lightweight PDF engine: `pymupdf4llm` or PyMuPDF-backed adapter
     for structured Markdown/JSON and multi-column/layout signals;
   - fallback text engine: `pdfplumber`;
   - DOCX: `python-docx`;
   - TXT: UTF-8/Latin fallback.
3. **Layout-aware extraction**
   - if native text is disordered, sparse, or column-heavy, run a layout adapter;
   - preferred local candidates: `pymupdf4llm` for lightweight PDF layout,
     `docling` for broader document/layout/OCR capability;
   - `marker` is optional/task-gated because it adds heavier PyTorch/GPL/model
     tradeoffs; do not make it default without an ADR.
4. **OCR fallback**
   - use only when pages/images have too little readable native text;
   - default local OCR language config: `vie+eng`;
   - tolerate mixed Vietnamese/English CVs;
   - record OCR-used internally but show only user-friendly copy.
5. **CV classifier and quality checks**
   - blank document;
   - not a CV/resume;
   - low-quality scan;
   - insufficient CV content;
   - language review required;
   - duplicate existing file.
6. **Deterministic structuring**
   - parse contact, summary, education, experience, projects, skills,
     certifications, awards, languages, activities, custom sections;
   - preserve original text spans when possible for review highlights.
7. **LLM structuring fallback**
   - only after local extraction has produced text/markdown;
   - never send raw binary files to an LLM;
   - redact obvious secrets and keep provider/model internals hidden;
   - use cheap/provider-configured models only when enabled by admin/env;
   - output a pending structured draft/diff that requires user confirmation.
8. **Review/import**
   - persist engine version, extraction version, warnings, and review fields;
   - user accepts/edits/rejects before builder content is created or changed.

## 4. Engine Policy

Local development should stay lightweight by default.

Suggested env/config flags:

- `CV_NATIVE_PDF_ENGINE=pymupdf4llm|pdfplumber`
- `CV_LAYOUT_ENGINE=none|pymupdf4llm|docling|marker`
- `CV_OCR_ENGINE=none|tesseract|docling|marker`
- `CV_OCR_LANGS=vie+eng`
- `CV_LLM_STRUCTURING_ENABLED=false`
- `CV_LLM_STRUCTURING_PROVIDER_ALIAS=openrouter_deepseek_cheap`
- `CV_INGESTION_ASYNC=true`

Defaults for local v1:

- native PDF: PyMuPDF/PyMuPDF4LLM adapter when dependency is available, else
  `pdfplumber`;
- DOCX/TXT: lightweight deterministic parsers;
- OCR: Tesseract `vie+eng` when installed, otherwise record
  `LOW_QUALITY_SCAN`;
- LLM: disabled unless AI settings/env explicitly enable it.

## 5. Data And API Contract

The existing `documents`, `cv_parse_runs`, `cv_profiles`, and `cv_versions`
concepts can remain, but the product contract needs explicit ingestion state.

Required persisted facts:

- original document id and immutable checksum;
- ingestion job id;
- status and user-safe quality code;
- parser engine family and version internally;
- detected language and mixed-language flags;
- page count and text length internally;
- review fields with paths, values, and needs-review markers;
- source document span/page reference where available;
- created/updated/completed timestamps;
- owner user id and audit trail.

Minimum API shape:

- `POST /api/v1/cv-uploads` stores the original file and returns preview/upload
  metadata, not final builder content.
- `POST /api/v1/cv-uploads/{document_id}/ingest` starts or resumes ingestion.
- `GET /api/v1/cv-ingestions/{ingestion_id}` returns user-safe status, quality
  message, review fields, detected language, and next actions.
- `POST /api/v1/cv-ingestions/{ingestion_id}/import` creates a new builder CV
  or imports into a chosen draft/template after user confirmation.
- `GET /api/v1/cv-files/{token}` returns signed file/preview access.

All endpoints are owner-scoped. Raw storage paths, parser logs, engine stack
traces, provider names, prompts, and model names never leave the backend.

## 6. CV Studio Editor Contract

The editor is a document builder similar in spirit to a professional template
tool, not a long profile form.

Required surfaces:

- template marketplace with preview thumbnails and category filters;
- document canvas with section blocks;
- drag/drop reorder plus keyboard reorder;
- inline text editing;
- A4 preview with page-break warnings;
- version history and restore;
- AI suggestion drawer with before/after diff;
- job-fit rail showing recommended CV, 0-100 product fit, gaps, and actions;
- original uploaded document preview for imported CVs;
- export PDF.

AI may draft, rewrite, translate, tailor, and fill templates, but every write
creates a pending suggestion/diff until the student accepts it.

## 7. Failure And Recovery States

Every failure must give the user a practical next action.

| Case | User-facing response |
|---|---|
| Blank PDF/page | "We could not find readable content" + upload another / create from template |
| Non-CV file | "This does not look like a CV" + upload CV / start template |
| Password-protected PDF | ask user to remove password |
| Corrupt file | ask user to export a fresh copy |
| Low-quality scan | upload clearer file / manually create / try OCR if enabled |
| Duplicate file | use existing CV / upload another |
| OCR unavailable | tell user review/manual path is available; do not say engine missing |
| LLM unavailable | continue deterministic review/import; no broken AI dead-end |
| Quota reached | archive/delete/request more/upgrade before import |
| Extraction low confidence | open review screen with highlighted fields |

## 8. Evaluation Set

Before marking this slice complete, create a local fixture set:

- text-selectable one-page English CV;
- text-selectable Vietnamese CV;
- two-column PDF;
- image/scanned CV;
- canvas/vector-heavy PDF with sparse native text;
- DOCX CV;
- blank PDF;
- non-CV PDF;
- password-protected PDF fixture or mocked extractor error;
- corrupt PDF fixture or mocked extractor error;
- duplicate upload;
- mixed vi/en CV.

Minimum acceptance:

- no raw CV text in analytics/log payload assertions;
- blank/not-CV/password/corrupt/duplicate/low-quality outcomes are classified
  correctly;
- deterministic structuring captures contact + at least key sections for normal
  text PDFs/DOCX;
- OCR fallback path is tested even if OCR engine is mocked locally;
- LLM fallback path is tested as disabled/unavailable and enabled-with-fake
  provider;
- review/import creates a versioned draft and never overwrites accepted content;
- UI screenshot/browser pass covers upload preview, processing, review, import,
  quota reached, and failure recovery at 375/768/1024/1440.

## 9. Next Implementation Priority

If current code only offers upload + parser status + extracted field list, it is
functional-only. The next implementation batch must be:

**CV Ingestion & CV Studio Product Rescue**

Do this before `ai_settings`, messaging, or broad roadmap expansion unless there
is a hard blocker.
