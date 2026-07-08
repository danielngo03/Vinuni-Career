# JD Ingestion Cascade — Design Spec

**Date:** 2026-07-05
**Owner decision source:** conversation 2026-07-05 (partner JD upload / auto-fill)
**Status:** approved design → implementation planning
**Scope of THIS slice:** backend JD extraction engine + full-field auto-fill + API contract.
Frontend redesign (two-pane form + preview with tabs) is the *next* sub-project, documented in §9 but NOT built here.

---

## 1. Problem & Goal

Partners already have a written job description (PDF, DOCX, or a photo/scan). The product goal
is to let them **upload that JD and have the job-posting form auto-fill itself** so they don't
retype everything into a long form.

Today's JD upload ([jd_upload_service.py](../../../backend/app/modules/opportunities/application/jd_upload_service.py))
is the weak link:

- Accepts **PDF/DOCX/TXT only** — no image/photo/scan support.
- **Single tier** (native text → LLM). No OCR tier, no vision-LLM tier (docstring lies about OCR).
- **No "is this actually a JD?" gate** — feeding it a CV or an invoice produces hallucinated job fields.
- Extraction schema fills only a **subset** of fields — it does NOT populate `candidate_requirements`
  (gender/age/marital/nationality/language/certifications/work-auth), `salary_mode/period/gross_net`,
  `experience_mode`, `seniority_level`, `industry`, or `application_deadline`.

Meanwhile the **backend `Job` model is already realistic** — see
[models.py](../../../backend/app/modules/opportunities/domain/models.py) and
[schemas.py](../../../backend/app/modules/opportunities/api/schemas.py): multi-location `locations[]`
with per-location onsite/remote/hybrid, structured salary, experience modes, seniority, industry,
and a rich `candidate_requirements` JSON (gender, age 14–80, marital status, nationalities, languages,
certifications, work authorization, education). The realistic fields exist; nothing auto-fills them.

**Goal:** rebuild JD extraction as a **strong, cost-tiered, multi-tier cascade** that reuses the CV
pipeline's *generic document-reading* primitives, supports images/scans, validates that the file is a
JD, and extracts **every field the backend already supports** so the form can prefill them.

### 1.1 CV vs JD — separate flows, shared reader only

The CV flow (student uploads résumé → **stored** for library/matching) and the JD flow (partner
uploads JD → **auto-fill the posting form → NOT saved to DB**) are **separate features** with
different users, purposes, and persistence. The **only** overlap is the low-level, generic
"read a PDF/image → text/structured data via OCR + vision-LLM" machinery. The JD engine is its own
module with its own JD-validity gate, its own JD schema, and its own prompts, and never touches CV data.

---

## 2. Non-Goals

- **No DB persistence of extraction.** Upload-JD only returns fields to prefill the form. Nothing is
  written to `jobs` or any table. (Unchanged from today.)
- **No change to the "must be complete to publish" rule.** Required API fields + the deterministic
  JD quality gate ([jd_quality.py](../../../backend/app/modules/opportunities/domain/jd_quality.py))
  still govern publish. Extraction only prefills; blanks stay blank.
- **No generalizing the CV cascade** into a shared engine (high collision risk with the concurrent
  CV-extraction session). We reuse *stable primitives* read-only; we do not refactor `cv_*` files.
- **No new strongly-typed columns** for gender/age/marital in this slice. They stay in the existing
  flexible `candidate_requirements` JSON. (Queryability is a future concern.)
- Frontend redesign is out of scope for this slice (see §9).

---

## 3. Architecture — approach

**Chosen approach: a self-contained JD extraction package that reuses CV's generic primitives.**

New package `backend/app/ai/extraction/jd/`:

```
backend/app/ai/extraction/jd/
  __init__.py
  cascade.py        # run_jd_cascade(...) -> JdExtractionOutcome  (orchestration)
  policy.py         # JdEnginePolicy + resolve_policy() from Settings
  validation.py     # is-JD classifier + user-safe status codes (+ reuse generic security gate)
  structuring.py    # text-LLM structuring into the JD schema (secrets redacted, text-only)
  vision.py         # JD vision extraction: JD prompt + normalize (reuses shared image prep)
  schema.py         # JDExtractionSchema (extended) + per-field needs_review scoring
backend/app/ai/prompts/jd_extraction/
  v2.py             # new prompt builders (text variant + vision variant) for the FULL field set
```

**Reused generic primitives (import read-only; do NOT modify):**

- [text_extraction.py](../../../backend/app/ai/extraction/text_extraction.py): `sniff_kind`, `extract_text`, `FileKind`, `ExtractionError`
- [adapters/native_text.py](../../../backend/app/ai/extraction/adapters/native_text.py): `NativeTextAdapter`
- [adapters/ocr.py](../../../backend/app/ai/extraction/adapters/ocr.py): `TesseractOcrAdapter`, `get_ocr_adapter`, `set_ocr_adapter`
- [adapters/vision.py](../../../backend/app/ai/extraction/adapters/vision.py): image-prep helpers (downscale/rasterize) and JSON/text cleaners. **If they are not importable without editing `vision.py`, add a small JD-local copy in `jd/vision.py` rather than editing the shared file** (isolation from the CV session).
- [adapters/base.py](../../../backend/app/ai/extraction/adapters/base.py): `redact_secrets`
- [cv_validation.py](../../../backend/app/ai/extraction/cv_validation.py): `security_gate`, `compute_checksum` (generic, not CV-specific — reuse; do not edit).
- Gateway: [factory.py](../../../backend/app/ai/gateway/factory.py) `get_provider_for_alias`, [runtime_config.py](../../../backend/app/ai/gateway/runtime_config.py) `current()`, plus the existing generic JSON helper `generate_json_note` ([app/ai/cv/llm.py](../../../backend/app/ai/cv/llm.py)).

Rejected alternatives: (B) generalize CV cascade into a shared `DocumentIngestionCascade` — high
collision risk + over-abstraction for two doc types; (C) bolt OCR/vision inline onto the existing
single-file `jd_upload_service` — recreates the messy monolith, weak is-JD gate, hard to test.

---

## 4. The cascade — tiers & cost model

`run_jd_cascade(filename: str, data: bytes, *, policy: JdEnginePolicy) -> JdExtractionOutcome`

| Tier | Action | Cost |
|---|---|---|
| 0 | **File & security gate**: size cap (`jd_max_upload_bytes`), `sniff_kind` (accept **PDF/DOCX/TXT/IMAGE** — images now included), `security_gate` (EICAR/malware). | Free |
| 1 | **Native text**: PDF (pymupdf4llm/pdfplumber), DOCX (python-docx), TXT. Yields text, page_count, has_images, disordered heuristic. | Free |
| 2 | **Escalation decision**: enough digital text & not an image → go to text structuring (Tier 6). Image / scanned PDF (little native text + has_images) / heavily styled → escalate to Tier 3. | Free |
| 3 | **Vision-LLM** (images & scanned/styled PDFs): downscale image (long-edge `jd_vision_max_image_px`) / rasterize first `jd_vision_max_pages` PDF pages to JPEG → call `vision_cheap` (gemini-2.5-flash) with the JD **vision** prompt; pass native text as reference for exact numbers/emails/dates. Returns full JD JSON incl. `is_jd`. | **1 cheap call, only when needed** |
| 4 | **Local OCR fallback**: if vision unavailable/failed and it's an image/scanned PDF → Tesseract `vie+eng` → text, then continue to Tier 5/6. | Free |
| 5 | **JD-validity gate** (text path; vision returns `is_jd` directly): `jd_validation.classify_content(text)` → `ok` / `blank` / `not_a_jd` / `low_quality_scan` / `insufficient`. Reject non-JD. | Free |
| 6 | **Text-LLM structuring**: `redact_secrets(text)` then `chat_cheap` (deepseek) with the JD **text** prompt → full JD JSON. Text-only, never bytes. | **1 cheap call** |
| 7 | **Validate + score**: validate against `JDExtractionSchema`, drop invalid fields (keep partial), compute `needs_review` per field (verbatim-quotable heuristic, retained from current service), default absent requirement groups to `not_required`. Map to the create-job form contract. | Free |

**Token economy:** digital PDF/DOCX/TXT → **0 vision cost**, just one cheap text call. Only
images/scans reach the vision tier (one call, bounded pages/px). OCR is local/free. This is the exact
CV cost-tier model and satisfies "mạnh mẽ nhưng tiết kiệm token".

`JdExtractionOutcome` (dataclass): `status` (`ok|blank|not_a_jd|low_quality_scan|insufficient|ai_unavailable`),
`fields: dict` (the extracted JD field set), `field_confidence: dict`, `needs_review: bool`,
`raw_text_preview: str | None` (fallback for `ai_unavailable`), `detected_language`, plus internal-only
diagnostics (`ocr_used`, `vision_used`, `llm_used`, `engine_family`, …) that are **never** returned to clients.

---

## 5. Extended extraction schema — full field coverage

`JDExtractionSchema` (Pydantic v2) extends the current one to cover **everything the backend `Job`
model + `JobCreateRequest` support**. Golden rules (per owner):

- **Present in JD → fill it. Absent → leave blank** (numbers/text) **or `not_required`** (requirement groups).
- **Never fabricate.** Normalized/interpreted fields (enums, currency conversion, year counts, parsed
  dates) always carry `needs_review=true` so the form flags "please double-check".

**Content (existing, retained):** `title`, `title_en`, `description_vi/en`, `requirements_vi/en`,
`benefits_vi/en`, `employment_type`, `required_skills[]`, `preferred_skills[]`, `headcount`.

**Locations (upgraded):** `locations[]` where each item carries its **own** `type`
(`onsite|remote|hybrid`) + `province_code?`/`city?`/`ward?` + `country`. Supports "vừa văn phòng vừa
từ xa" and multi-office postings. Primary location also mirrors legacy `location_type`/`location_city`.

**Salary (NEW structured):** `salary_min`, `salary_max`, `salary_currency`, `salary_mode`
(`negotiable|hidden|fixed|range|from|to`), `salary_period` (`monthly|yearly`), `salary_gross_net`
(`unspecified|gross|net`). `salary_is_disclosed` is derived server-side from `salary_mode` (client value
ignored, as today).

**Experience/seniority/industry (NEW):** `experience_min_years`, `experience_max_years`,
`experience_mode` (`no_requirement|fresher|range|min|max`), `seniority_level`, `degree_required`,
`industry` (free-text name; UI maps to `industry_id`, left blank if no confident match).

**Deadline (NEW):** `application_deadline` (parsed date; `needs_review=true`).

**candidate_requirements (NEW — the "realistic eligibility" block):** mirrors the backend
`CandidateRequirements` schema, each defaulting to `not_required` when absent:
- `gender` — RequirementGroup (e.g. female-only postings, when stated in the JD).
- `age` — `{mode: not_required|at_least|up_to|range, min?, max?}` (14–80).
- `marital_status` — RequirementGroup.
- `nationalities` — RequirementGroup.
- `languages[]` — `{language, proficiency?, required}` (max 20).
- `certifications[]` — `{name, required}` (max 30).
- `work_authorization` — RequirementGroup.
- `education` — RequirementGroup.
- `note` — free-text catch-all (max 2000) for anything unusual the JD states that has no dedicated field.

**Eligibility policy (owner decision 2026-07-05):** extract these as-is — if the JD states a
requirement (gender/age/marital/etc.), fill it; if not, default `not_required`. No extra gate beyond
the existing advisory AI bias check ([jd_ai_service.py](../../../backend/app/modules/opportunities/application/jd_ai_service.py)).

---

## 6. API contract

`POST /api/v1/jobs/upload-jd` (multipart, unchanged path & no-DB-write behavior). Extend the
`JdUploadResult` response:

- `status`: `ok | not_a_jd | blank | low_quality_scan | insufficient | ai_unavailable`.
- On `ok`: `fields` (full §5 set mapped to `JobCreateRequest` shape, incl. nested `locations[]` and
  `candidate_requirements`), `field_confidence` (per-field `{needs_review}`), `needs_review` (bool).
- On `ai_unavailable`: `raw_text_preview` (≤2000 chars) so the partner can fill manually.
- On reject statuses: a **user-safe** message (vi + en) + recovery actions (`upload_another`,
  `fill_manually`). Never expose model/provider/token/prompt/internal codes.

The create/publish path is unchanged: `POST /jobs` required fields + `POST /jobs/{id}/submit` quality gate.

---

## 7. Config additions

Add to [config.py](../../../backend/app/core/config.py) (independent of `cv_*`, defaulting to the same
proven values):

- `jd_max_upload_bytes` (default 10 MB)
- `jd_ocr_engine` (`tesseract`), `jd_ocr_langs` (`vie+eng`)
- `jd_vision_extraction_enabled` (bool), `jd_vision_provider_alias` (`vision_cheap`)
- `jd_vision_max_image_px` (2200), `jd_vision_max_pages` (4)
- `jd_llm_structuring_provider_alias` (`chat_cheap`)

All AI tiers gate on `runtime_config.current().real_calls_active` + adapter availability; degrade
gracefully to `ai_unavailable` (with raw-text fallback) when off.

---

## 8. Coordination, testing, edge cases

**Concurrent CV session:** import CV/extraction primitives **read-only**; do not edit `cv_*` files or
`adapters/vision.py`. If a shared helper isn't cleanly importable, add a small JD-local copy.

**Tests (mirror the CV ingestion checklist in [.claude/rules/backend.md](../../../.claude/rules/backend.md)):**
digital text PDF, Vietnamese JD, two-column PDF, **image/scan JD**, vector-heavy PDF, DOCX, **blank /
not-a-JD (feed a CV) / corrupt / password-protected**, OCR-unavailable, vision-disabled,
LLM-disabled. Assert: correct status codes, no fabricated fields, absent groups default `not_required`,
`needs_review` set on normalized fields, no AI internals leak, nothing persisted to DB.

**Edge cases (per [EDGE_CASES_FAILURE_MODES.md](../../../docs/EDGE_CASES_FAILURE_MODES.md)):**
file too large, unsupported type, empty text, AI timeout/unavailable, partial extraction — all return a
safe status and never raise to the client.

---

## 9. Next sub-project (frontend — direction locked, built later)

Two-pane **form + live preview**; the form is split into **tabs** for compactness. Tabs:
Basics → Role details → Compensation & logistics → Candidate eligibility → Screening → Review.
JD upload sits at the top and auto-fills across all tabs, with a "cần kiểm tra / needs-review" badge on
normalized fields, and blanks left empty. Exposes the **full** field set from §5 (candidate_requirements,
structured salary, experience mode, seniority, industry). Replaces the messy single long form + the
over-styled teal upload banner. Publish stays gated by required fields + the quality gate.

---

## 10. Acceptance criteria (this slice)

1. Uploading a **digital PDF/DOCX/TXT** JD returns `status=ok` with the full §5 field set, using **no
   vision call** (only one cheap text-LLM call).
2. Uploading a **JD photo/scan or image-only PDF** returns `status=ok` via the vision tier (or OCR
   fallback), with fields populated.
3. Uploading a **CV, invoice, blank, or corrupt file** returns the correct reject status
   (`not_a_jd`/`blank`/`low_quality_scan`) and **no fabricated job fields**.
4. `candidate_requirements` (gender/age/marital/nationality/language/cert/work-auth/education) is
   populated when stated in the JD and defaults to `not_required` otherwise.
5. Structured salary (`salary_mode/period/gross_net`), `experience_mode`, `seniority_level`,
   `industry`, and `application_deadline` are extracted when present.
6. Nothing is written to the database; the endpoint only returns prefill data.
7. With AI disabled, the endpoint returns `ai_unavailable` + `raw_text_preview` and never errors.
8. No AI provider/model/token/prompt/internal-code leaks in any response.
9. Backend quality gates green: `uv run ruff check app tests`, `uv run mypy app --ignore-missing-imports`,
   and the new test suite pass.
