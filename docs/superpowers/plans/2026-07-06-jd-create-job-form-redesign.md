# Create-Job Form Redesign (partner) — Implementation Plan

> **For agentic workers:** Execute task-by-task. Each task lists exact files, the contract, and a verification gate. Frontend gate = `cd frontend && pnpm typecheck` (fast, per task) and `pnpm build` (at integration tasks). Do NOT run git/commit — leave changes in the working tree (concurrent session shares the repo).

**Goal:** Redesign the partner "create job posting" form into a two-pane **tabbed form + live preview**, expose the full realistic field set the backend now supports (structured salary, experience mode, seniority, and the `candidate_requirements` eligibility block: gender/age/marital/nationality/languages/certifications/work-authorization/education), and wire JD-upload auto-fill (incl. images) to populate all of it with FILLED / needs-review provenance chips.

**Architecture:** Keep the existing react-hook-form + Zod core, `toBody()`/`detailToValues()`, amendment policy, quality-check inline notes, and version-conflict handling intact. Manage the new nested `candidate_requirements` as external component state (mirroring the existing `locations` state pattern). Split the fieldsets into `Tabs` panels; add a `JobPreview` right-rail driven by `watch()`.

**Design system (v9 Monochrome — bind to these):** ink `--brand-primary #171717` is the ONLY action color; teal `--color-success #059669` = AI/FILLED/verified; amber `--color-warning #d97706` = needs-review/disclosure; VinUni red `--color-error #c83538` = destructive. Full gray ramp for hierarchy; no blue/navy; no gradients on operational surfaces; `backdrop-blur` only on the topbar/slide-in panels. Fonts: Plus Jakarta Sans (sans), JetBrains Mono (data/labels). Inputs: `rounded-xl`, focus `border-[var(--field-focus-border)] shadow-[0_0_0_4px_var(--field-focus-ring)]`.

## Global Constraints

- Reuse existing shared components: `Tabs`, `TabPanel`, `Input`, `Textarea`, `Select`, `Switch`, `Button`, `Modal`, `StatusBadge`, `useToast`. Build new primitives only where none exists (SegmentedControl, RequirementGroupField, AgeRequirementField, repeatable rows, TagInput, FieldProvenance chip).
- Preserve ALL existing behavior: create vs edit(active) mode, amendment badges + re-moderation confirmation modal, screening-locked-on-active, quality-check inline `JdFieldIssueNote`, version-conflict toast, JD Writer button.
- i18n every user string via `next-intl` (`useTranslations("jobs.form")` etc.); add keys to BOTH `frontend/src/messages/en/student/jobs.json` and `frontend/src/messages/vi/student/jobs.json`. No hardcoded vi/en literals in components.
- Sensitive eligibility fields default to `mode: "not_required"` ("Không yêu cầu") and only reveal value controls when set to required/preferred (owner decision: extract as-is, default not-required).
- `salary_is_disclosed` is derived (backend authoritative). Frontend sends `salary_mode` (+ numbers/period/gross_net/currency) and also sets `salary_is_disclosed` locally for backward compat (`negotiable`/`hidden` → false, else true).
- **Industry picker is DEFERRED** (hierarchical taxonomy picker is its own task): add `industry_id` to the body type as optional, carry the extracted `industry` name as a read-only suggestion note only; do NOT build the picker this slice.
- Accessibility floor: labeled controls, visible keyboard focus, `role` semantics on custom controls (segmented = radiogroup), reduced-motion respected. Responsive to mobile (preview collapses to a toggle).
- Do not remove sponsored/disclosure labels; do not touch unrelated modules.

---

### Task F1 — Extend API types (`frontend/src/lib/api/jobs.ts`)

**Add these types** (near `JobLocationItem`):

```typescript
export type RequirementMode = "not_required" | "required" | "preferred";
export type AgeMode = "not_required" | "at_least" | "up_to" | "range";
export type SalaryMode = "negotiable" | "hidden" | "fixed" | "range" | "from" | "to";
export type SalaryPeriod = "monthly" | "yearly";
export type SalaryGrossNet = "unspecified" | "gross" | "net";
export type ExperienceMode = "no_requirement" | "fresher" | "range" | "min" | "max";

export interface RequirementGroup { mode: RequirementMode; values: string[]; note?: string | null; }
export interface AgeRequirement { mode: AgeMode; min?: number | null; max?: number | null; }
export interface LanguageRequirement { language: string; proficiency?: string | null; required: boolean; }
export interface CertificationRequirement { name: string; required: boolean; }
export interface CandidateRequirements {
  education?: RequirementGroup;
  nationalities?: RequirementGroup;
  gender?: RequirementGroup;
  age?: AgeRequirement;
  marital_status?: RequirementGroup;
  languages?: LanguageRequirement[];
  certifications?: CertificationRequirement[];
  work_authorization?: RequirementGroup;
  note?: string | null;
}
```

**Extend `JobCreateBody`** with (all optional):
```typescript
  salary_mode?: string | null;
  salary_period?: string;
  salary_gross_net?: string;
  experience_mode?: string | null;
  seniority_level?: string | null;
  industry_id?: string | null;
  candidate_requirements?: CandidateRequirements | null;
```

**Extend `JdUploadResult`** with the fields the rebuilt backend now returns:
```typescript
  status?: "ok" | "not_a_jd" | "blank" | "low_quality_scan" | "insufficient" | "ai_unavailable" | string;
  needs_review?: boolean;
  field_confidence?: Record<string, { needs_review: boolean }>;
  salary_mode?: string | null;
  salary_period?: string | null;
  salary_gross_net?: string | null;
  experience_mode?: string | null;
  seniority_level?: string | null;
  industry?: string | null;
  application_deadline?: string | null;
  candidate_requirements?: CandidateRequirements | null;
  // extend the existing locations item to carry per-site type
```
Update the `locations?` item type in `JdUploadResult` to `Array<{ type?: string | null; city: string | null; province_code?: string | null; country: string }>`.

**Also extend `OwnerJobDetail` / `PublicJobDetail`** (whichever `detailToValues` reads) to include the new fields returned by the backend job presenter so edit-mode can hydrate them: `salary_mode`, `salary_period`, `salary_gross_net`, `experience_mode`, `seniority_level`, `candidate_requirements`. (Add as optional; do not break existing readers.)

**Gate:** `cd frontend && pnpm typecheck` → no new errors. (Types only; nothing consumes them yet.)

---

### Task F2 — Form model: schema, defaults, toBody, detailToValues, amendment sets

**Files:** `frontend/src/lib/validation/jobs.ts`, `frontend/src/lib/jobs/amendment.ts`, and the `detailToValues` helper (in `job-form.tsx` or its module).

1. **`JobFormValues` + `jobFormSchema`:** add scalar fields
   - `salary_mode: z.enum(["negotiable","hidden","fixed","range","from","to"])` (default `"negotiable"`)
   - `salary_period: z.enum(["monthly","yearly"])` (default `"monthly"`)
   - `salary_gross_net: z.enum(["unspecified","gross","net"])` (default `"unspecified"`)
   - `experience_mode: z.enum(["no_requirement","fresher","range","min","max"])` (default `"no_requirement"`)
   - `seniority_level: z.string().optional().or(z.literal(""))` (values: not_required|intern|fresher|junior|middle|senior|lead|manager|director|executive)
   - Keep `salary_min/max` string rules; refine: `range` needs both, `from` needs min, `to` needs max, `fixed` needs one amount, `negotiable` needs none. Add message keys `salaryModeNeedsRange`, etc.
   - `candidate_requirements` is NOT in Zod — it is external state (see Task F6), validated lightly in `toBody`.
2. **`JOB_FORM_DEFAULTS`:** add the new scalar defaults above; keep `salary_is_disclosed:false`.
3. **`toBody(v, locations, candidateRequirements, opts)`** — extend signature to accept `candidateRequirements: CandidateRequirements`:
   - emit `salary_mode`, `salary_period`, `salary_gross_net`, `experience_mode`, `seniority_level`.
   - derive `salary_is_disclosed = !(salary_mode === "negotiable" || salary_mode === "hidden")`.
   - emit `salary_min/max` per mode (negotiable → null/null; from → min/null; to → null/max; fixed → min/min; range/hidden → min/max as entered).
   - emit `candidate_requirements` = the external state, but PRUNE it: drop groups whose `mode === "not_required"` and empty; keep only active requirements + non-empty languages/certs/note. If everything is empty, send `undefined`.
   - keep the existing screening/deadline/location logic unchanged.
4. **`detailToValues(job)`:** hydrate the new scalar fields from `job` (fallback to defaults); return the candidate_requirements object too (or expose a separate `detailToCandidateRequirements(job)` used by F6).
5. **`amendment.ts`:** add the new fields to the RE-MODERATION set: `salary_mode`, `salary_period`, `salary_gross_net`, `experience_mode`, `seniority_level`, `candidate_requirements`. Add friendly names in the amendment field-name map (F9 provides i18n). Keep `application_deadline`/`headcount`/`visibility`/`benefits` free-amend.

**Gate:** `pnpm typecheck` → clean. (Consumers updated in F6; if a temporary unused-var appears, it's resolved by F6 — still must typecheck.)

---

### Task F3 — SegmentedControl primitive (`frontend/src/components/ui/segmented-control.tsx`)

Accessible radiogroup rendered as a pill segmented control (used for salary_mode, experience_mode, requirement mode). Export from `ui/index.ts`.

```typescript
export interface SegmentedOption { value: string; label: string; }
export interface SegmentedControlProps {
  value: string;
  onValueChange: (value: string) => void;
  options: SegmentedOption[];
  ariaLabel: string;
  size?: "sm" | "md";
  disabled?: boolean;
  id?: string;
}
```
- `role="radiogroup"`, each option `role="radio"` + `aria-checked`; roving arrow-key nav (mirror the pattern in `ui/tabs.tsx`).
- Selected segment: ink background `--btn-primary-bg`, white text; unselected: `--text-secondary` on transparent, hover `--bg-subtle`. Container `border --border-default rounded-xl p-0.5`. No gradients.
- Respect `disabled` (used when editing an active job's locked fields).

**Gate:** `pnpm typecheck`.

---

### Task F4 — Eligibility field controls (`frontend/src/components/jobs/eligibility/`)

Build the `candidate_requirements` controls. All take a value + onChange (controlled), i18n labels via props or `useTranslations("jobs.form.eligibility")`.

1. **`RequirementGroupField.tsx`** — one row: label + `SegmentedControl` for mode (`not_required`/`required`/`preferred`, localized "Không yêu cầu / Bắt buộc / Ưu tiên"). When mode ≠ not_required, reveal a value control:
   - `variant="chips"` → a `TagInput` of preset+custom chips (used by gender [male/female/other], marital_status [single/married], nationalities [free chips], work_authorization, education).
   - Props: `{ label, value: RequirementGroup, onChange, presets?: {value,label}[], variant, disabled }`.
2. **`AgeRequirementField.tsx`** — label + SegmentedControl mode (`not_required`/`at_least`/`up_to`/`range`) → conditional number inputs (min / max / both, 14–80). Props `{ value: AgeRequirement, onChange, disabled }`.
3. **`RepeatableRows.tsx`** (generic) + **`LanguageRows`**/**`CertificationRows`** wrappers — add/remove rows; language row = `{language, proficiency?, required}`, cert row = `{name, required}`. Reuse `Input` + `Switch` + a ghost remove button (Phosphor `Trash` icon, `--text-muted`).
4. **`TagInput.tsx`** (`components/ui/` or eligibility/) — chips input: type + Enter to add, backspace to remove, optional preset suggestions. Chips: `bg-[--bg-subtle] text-[--text-primary] rounded-full`, remove `×`.

**Gate:** `pnpm typecheck`.

---

### Task F5 — Provenance chips (`frontend/src/components/jobs/field-provenance.tsx`)

Small marker shown beside auto-filled fields.

```typescript
export type Provenance = "filled" | "review";
export interface FieldProvenanceProps { state: Provenance | null; onClear?: () => void; }
```
- `filled` → teal mono chip "Đã điền / Filled" (`text-[--color-success]`, `bg-[--ai-accent-soft]`, `font-mono text-[11px]`).
- `review` → amber chip "Cần kiểm tra / Check this" (`text-[--color-warning]`).
- Provide a tiny controller hook `useProvenance()` returning `{ get(field), setAll(map), clear(field) }` backed by a `Record<string, Provenance>` state; `clear(field)` is called on a field's change/blur. (Field keys match form field names + eligibility group keys.)

**Gate:** `pnpm typecheck`.

---

### Task F6 — Tabbed form shell + new sections (`frontend/src/components/jobs/job-form.tsx`)

The big integration. Refactor the existing form into the `Tabs` layout while preserving all behavior.

1. **Add external state:** `const [candidateReq, setCandidateReq] = useState<CandidateRequirements>(job ? detailToCandidateRequirements(job) : EMPTY_CANDIDATE_REQ)` (mirror `locations`). `EMPTY_CANDIDATE_REQ` = all groups `not_required`, empty arrays.
2. **Provenance:** instantiate `useProvenance()`; pass a clear-callback into fields so editing a field clears its chip.
3. **Tabs:** use `Tabs` with items `basics|role|comp|eligibility|screening|review`; render each panel via `TabPanel`. Keep the JD upload card + amendment banner ABOVE the tabs (they apply across all).
   - **Basics:** title, employment_type, `JobLocationPicker`, description (+ `JdWriterButton`).
   - **Role & requirements:** requirements, required/preferred skills, **experience_mode** SegmentedControl → conditional min/max, **seniority_level** Select, degree_required. (Industry: render the extracted `industry` name as a read-only muted note if present; no picker.)
   - **Compensation:** **salary_mode** SegmentedControl → conditional min/max (labels adapt per mode) + `salary_period` Select + `salary_gross_net` Select + currency; headcount; application_deadline; visibility. Remove the old `salary_is_disclosed` Switch (mode replaces it).
   - **Eligibility:** RequirementGroupField for gender/marital_status/nationalities/work_authorization/education, AgeRequirementField, LanguageRows, CertificationRows, and a free-text `note` Textarea. All read/write `candidateReq`.
   - **Screening:** existing screening-questions block (keep locked-on-active behavior).
   - **Review:** a read-only summary of key fields + the existing quality-check surface + the submit/save actions. (Actions may also live in a sticky footer — see F7.)
4. **Wire disabled state:** when `isActive`, pass `disabled` into re-moderation controls (segmented/eligibility) the same way existing inputs are gated, and keep the re-moderation confirmation modal — extend its changed-field detection to include the new fields + `candidateReq` (compare against `detailToCandidateRequirements(job)`).
5. **`toBody` call:** pass `candidateReq`. Keep create/update/version logic identical.
6. **Quality-check `JdFieldIssueNote`:** keep rendering under the matching fields (now inside their tabs). If a tab contains a field with a blocking issue, surface a small amber dot on that tab trigger (compute from `qualityIssues`).

**Gate:** `pnpm typecheck` AND `cd frontend && pnpm build` → succeeds (this is the first integration checkpoint).

---

### Task F7 — Live preview pane (`frontend/src/components/jobs/job-preview.tsx`) + two-pane layout

`JobPreview` renders how the posting will read, from live `watch()` values + `locations` + `candidateReq` + partner company context.

- Content: title; company name + primary location; a chip row (employment type, location type(s), salary display, seniority); description; requirements; benefits; required/preferred skill chips; an **Eligibility** summary line (only the active requirement groups, e.g. "Nữ · 22–30 tuổi · Tiếng Anh"); deadline; "N screening questions". Empty fields show muted placeholders ("Chưa có mô tả").
- Salary display helper: format from mode (negotiable → "Thỏa thuận"; range → "20–30 triệu/tháng"; hidden → "Không công khai"; etc.).
- Card styling: `--surface-card`, `rounded-2xl`, `shadow-sm`, hairline divider; this is app chrome (monochrome), not user-themed.
- **Layout in the create/edit page:** two columns on `lg+` (`grid lg:grid-cols-[minmax(0,1fr)_380px]`), form left, sticky preview right (`sticky top-24`). Below `lg`: single column; add a "Xem trước / Preview" button that opens the preview in a `Sheet`/`Modal`.
- Sticky footer action bar (Back/Next between tabs; Save draft; Submit for review) so actions are reachable from any tab.

**Gate:** `pnpm typecheck` + `pnpm build`.

---

### Task F8 — Auto-fill wiring + image upload

**Files:** `job-form.tsx` (`handleJdExtracted`), `frontend/src/components/jobs/jd-upload-button.tsx`.

1. **`jd-upload-button.tsx`:** extend `accept` to `.pdf,.docx,.txt,.png,.jpg,.jpeg`; update the hint copy ("PDF, DOCX, hoặc ảnh"). Handle rejects: if the upload call throws a validation error with `details.reason` in {not_a_jd, blank, low_quality_scan}, show a specific toast (from i18n `uploadJdRejected.*`) instead of the generic error.
2. **`handleJdExtracted(result)`:** on `result.status === "ai_unavailable"` → keep the raw-text fallback toast. On `ok`:
   - Keep all existing `setValue` mappings.
   - Add: `salary_mode`, `salary_period`, `salary_gross_net`, `experience_mode`, `seniority_level`, `application_deadline` (→ set the datetime-local value), and `locations` now carry `type` per site.
   - Set `candidateReq` from `result.candidate_requirements` (merge over `EMPTY_CANDIDATE_REQ` so absent groups stay not_required).
   - **Provenance:** for every field present in `result`, mark `filled`; for every field whose `result.field_confidence[field]?.needs_review === true`, mark `review` (amber overrides filled). Include `candidate_requirements` as one `review` marker on the Eligibility tab when its confidence flags review. Store via `useProvenance().setAll(...)`.
   - Toast "Đã điền form từ tài liệu — hãy kiểm tra các mục được đánh dấu".

**Gate:** `pnpm typecheck` + `pnpm build`.

---

### Task F9 — i18n keys (`messages/en/student/jobs.json` + `messages/vi/student/jobs.json`)

Add, in BOTH files, under the existing `jobs.form` namespace (+ nested), keys for: tab titles (`tabs.basics|role|comp|eligibility|screening|review`); salary mode options + labels + help + validation (`salaryMode`, `salaryModeOpts.*`, `salaryPeriod`, `salaryGrossNet`, `salaryModeNeedsRange`…); experience mode (`experienceMode`, `experienceModeOpts.*`); seniority (`seniority`, `seniorityOpts.*`); eligibility (`eligibility.legend`, `eligibility.gender|age|marital|nationality|workAuth|education|languages|certifications|note` + `mode.notRequired|required|preferred` + preset value labels + `age.*` + row add/remove); provenance (`provenance.filled`, `provenance.review`); preview (`preview.title`, `preview.empty*`, `preview.salaryNegotiable|hidden`, `preview.eligibilitySummary`); upload rejects (`uploadJdRejected.notAJd|blank|lowQuality`); amendment field names for the new fields; sticky footer (`back`, `next`, `saveDraft`, `submitReview`). Keep vi as the human-facing default; en mirrors it.

**Gate:** `pnpm build` (next-intl fails the build on some misuse; also grep the components for `t("…")` keys and confirm each exists in both json files).

---

### Task F10 — Quality gate

- `cd frontend && pnpm typecheck` → clean.
- `pnpm lint` → no new errors in changed files (fix ours; leave pre-existing).
- `pnpm build` → succeeds with no new warnings in the job-form/preview/eligibility files (the audit noted pre-existing warnings elsewhere — leave those).
- If a `vitest` suite exists for jobs validation, run `pnpm test -- jobs` and keep green; add a small test for `toBody` salary-mode + candidate_requirements pruning if the repo has a validation test file.

---

### Task F11 — Browser verification

Get the app running and verify the real flow (see the run/verify steps in the controller). Confirm: tabs switch; a text JD upload auto-fills fields across tabs with FILLED/Check-this chips; salary-mode segmented reveals the right inputs; eligibility rows expand from "Không yêu cầu"; the live preview updates as you type; a non-JD upload shows the reject toast; required-field validation still blocks submit; editing an active job still shows amendment badges + re-moderation modal. Capture screenshots (desktop + mobile widths).

---

## Notes / deferred

- **Industry picker** (hierarchical taxonomy select) is deferred to a follow-up; `industry_id` is in the body type but no control is built. The extracted industry name is shown as a read-only hint only.
- Real vision-LLM/OCR auto-fill from an image JD depends on backend `AI_REAL_CALLS_ENABLED` + keys; the frontend path is exercised with a text/digital JD in F11.
