# CV Library Lifecycle — Draft vs Analyzed (Design Spec)

Date: 2026-07-05 · Owner-approved direction. Supersedes the earlier "P3 = AI fill" framing.

## Problem

The student CV library is capped at **5 CVs**, but today **every** CV is created as
`status="draft"` and the quota counts *all* non-archived CVs — so scratch/design
CVs eat quota slots, and nothing ever promotes a CV to a "finalized" state. There
is no explicit "commit this CV to my library" step.

Owner's intent (2026-07-05): the 5-CV cap exists to **bound the cost of preparing
a CV for JD matching**. A student should design freely (unlimited drafts, no cost),
and only when they **commit a CV to their library** does the system spend effort to
make it matching-ready. That committed set is capped at 5.

### Honest technical grounding (verified in code)

- CV-JD matching (`app/ai/cv/job_fit.py`, `job_fit_service.py`) reads `cv_sections`
  **live** and scores **deterministically** — no embeddings, no model tokens at
  match time. The token-expensive work is the **upload extraction** pipeline
  (OCR → vision-LLM → text-LLM structuring) that turns a raw image/PDF into
  structured sections.
- A **template CV is already structured** (the student typed field-by-field into
  the exact `cv_sections` shape matching consumes). So a template CV needs **no
  OCR and no re-extraction** — running AI extraction on it would waste tokens and
  risk overwriting the student's own entries.

Therefore "finalize" is **not** "re-extract". It is: validate + commit to the
library (quota-gated) + mark analyzed. The heavy AI enrichment (normalize skills,
derive competencies, embeddings) is a **future stage** gated by the same 5-cap; the
service is wired so it can plug in without changing the lifecycle. Upload keeps its
real extraction (that IS its analysis).

## Model: two tiers using the existing `draft`/`ready` status

| | Not analyzed — unlimited, free | In library — max 5, "analyzed" |
|---|---|---|
| status | `draft` | `ready` |
| Template | design/edit freely on canvas | **"Lưu vào thư viện CV"** → validate + quota + commit |
| Upload | uploading / extracting | extraction done → enters library |
| Counts to quota? | **No** | **Yes** |
| Usable for apply / job-fit? | **No** | **Yes** |

Naming (owner asked; chosen for a real system):
- Library section: **"Thư viện CV của tôi (x/5)"** — *CV đã phân tích, sẵn sàng ứng tuyển & so khớp việc làm*.
- Draft section: **"Bản nháp"** — *đang thiết kế, chưa tính vào giới hạn, chưa dùng để ứng tuyển*.
- Builder action: **"Lưu vào thư viện CV"** → progress "Đang xử lý CV…" → done badge **"Sẵn sàng ứng tuyển"** (green ✓); draft badge **"Bản nháp"**.

## Backend changes

1. **Quota counts only `ready`.** `_cv_core._active_cv_count_stmt`: `status == CV_READY`
   (was `!= CV_ARCHIVED`). Single source of truth; `count_cvs`/`cv_library_quota`
   inherit it.
2. **Drafts are free.** Remove `_enforce_active_cv_quota` from `create_cv` and
   `duplicate_cv` (template/blank/notes/duplicate/AI create → `draft`, unlimited).
3. **Upload → library.** `create_cv_from_sections` (the only caller is upload
   import): create with `status=CV_READY`; **keep** the quota gate (an uploaded CV
   is an analyzed library CV). Add a quota **pre-check at upload start** if clean,
   so extraction tokens aren't spent when the library is already full (else record
   as follow-up).
4. **Finalize service + endpoint.** `POST /cvs/{cv_id}/finalize`:
   - owner-only (404 cross-owner); RBAC at service layer.
   - idempotent: already `ready` → return current detail (no error, no re-count).
   - validate **non-empty**: require a header name or ≥1 visible section carrying
     real content; else `409/422` with a user-safe "CV trống" message + recovery.
   - enforce quota (only here for template CVs) → `409 QUOTA_EXCEEDED` with actions.
   - `status = ready`, set `finalized_at = now()`.
   - version snapshot (`_snapshot_version`) + audit `cv.finalized`.
   - return full detail.
   - (Enrichment seam: a `_analyze_for_matching(cv, sections)` hook, deterministic
     no-op for structured template CVs now; documented for future AI enrichment.)
5. **Eligibility → ready only.** `job_fit_service._load_active_cvs`: `status == CV_READY`.
   Apply (`apply_service`/`snapshot_service`): reject applying with a non-`ready`
   CV (clear error); apply/job-fit CV pickers only see `ready`.
6. **Schema:** add `cv_profiles.finalized_at TIMESTAMPTZ NULL`. Migration upgrades
   **existing non-archived CVs → `ready` + `finalized_at=now()`** (they were usable
   before; preserve that) and adds the column. Downgrade drops the column. PG-guarded
   data step, idempotent.
7. **Status label:** `CV_READY` → "Sẵn sàng ứng tuyển" / "Ready".

## Frontend changes

- **CV Studio landing:** two clearly separated groups — **"Thư viện CV của tôi (x/5)"**
  (status `ready`, with quota meter) and **"Bản nháp"** (status `draft`, unlimited).
  Uploaded + finalized CVs live in the library. Modern, tinh gọn, card-based per
  DESIGN v9 Monochrome; ready badge green ✓, draft badge neutral.
- **Builder (template draft):** "Bản nháp" badge + primary **"Lưu vào thư viện CV"**
  button (replaces/augments the current header). Click → "Đang xử lý CV…" →
  success flips to library + "Sẵn sàng ứng tuyển"; quota-full → dialog with recovery
  ("Thư viện đầy 5/5 — quản lý thư viện"). Empty-CV → inline guidance, block finalize.
- **Apply / job-fit CV pickers:** only `ready` CVs; empty state when none ("Chưa có
  CV trong thư viện — lưu một CV để ứng tuyển"), linking to CV Studio.
- i18n vi/en for all new copy. Breakpoints 375/768/1024/1440, light+dark.

## Edge cases

- Finalize empty CV → blocked with clear message.
- Finalize when library full → 409 + recovery actions; nothing mutated.
- Finalize already-ready → idempotent success.
- Delete/archive a ready CV frees a slot immediately.
- Draft cannot be used to apply / cannot appear in job-fit.
- Upload when library full → blocked (ideally before extraction to save tokens).

## Out of scope (follow-ups)

- Real AI enrichment stage (skill normalization, competencies, embeddings) behind
  the finalize seam.
- Re-analyze / "revert to draft".
- The in-builder AI chat assist tab (separate, confirmation-gated).

## Tests

- Quota counts only ready; drafts unlimited; create/duplicate no longer quota-gated.
- Finalize: happy path (draft→ready, version+audit, finalized_at), empty rejected,
  quota-full 409, idempotent when ready, cross-owner 404.
- Upload import lands `ready` + quota-checked.
- job-fit/apply only see ready; draft rejected on apply.
- Migration up/down + backfill (existing non-archived → ready).
