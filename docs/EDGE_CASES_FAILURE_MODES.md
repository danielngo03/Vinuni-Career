# Edge Cases & Failure Modes — VinUni Career Platform

> Purpose: force realistic product behavior. Every major feature must define bad inputs, partial failures, recovery, and user-safe messaging before it is marked complete.

---

## 1. Global Failure Contract

Every workflow must define:

- `detect`: how the system identifies the issue.
- `status`: stable backend status or error code.
- `user_message_vi` / `user_message_en`: friendly message with next step.
- `recoverability`: `retry`, `fix_input`, `manual_review`, `contact_support`, or `blocked`.
- `audit`: whether to write audit/security event.
- `analytics`: metadata-only event, never PII/raw content.
- `fallback`: deterministic path when AI/worker/provider is unavailable.

Do not expose stack traces, provider names, model names, token counts, OCR internals, storage paths, raw confidence, or raw parser errors to end users.

---

## 2. CV Upload And Extraction Edge Cases

### 2.1 File Validation

| Case | Detect | Status / Code | User Action |
|---|---|---|---|
| Unsupported type | MIME sniffing + extension mismatch | `UNSUPPORTED_FILE_TYPE` | Upload PDF/DOCX/TXT/image CV |
| File too large | size > configured limit | `FILE_TOO_LARGE` | Compress/split file |
| Virus/threat | scan infected or scan failed fail-secure | `FILE_REJECTED_SECURITY` | Upload a clean file |
| Password-protected PDF | parser cannot open | `PASSWORD_PROTECTED_FILE` | Remove password and upload again |
| Corrupt file | parser cannot parse bytes | `CORRUPT_FILE` | Export/download a fresh file and retry |
| Duplicate upload | checksum already exists for same user | `DUPLICATE_FILE` | Use existing CV or upload a different file |

### 2.2 Content Quality

| Case | Detect | Status / Code | User Action |
|---|---|---|---|
| Blank PDF / white pages | no text + OCR finds near-empty pages | `BLANK_DOCUMENT` | Upload another CV or create from template |
| Scanned but unreadable | OCR text length/quality below threshold | `LOW_QUALITY_SCAN` | Upload clearer scan or DOCX/PDF text |
| Not a CV/resume | classifier finds no CV signals | `NOT_A_CV` | Upload a CV or start with template builder |
| Missing minimum sections | no name/contact + no education/experience/project/skills | `INSUFFICIENT_CV_CONTENT` | Review manually or create from template |
| Too many pages | page count over CV limit | `CV_TOO_LONG` | Upload first N pages or shorten CV |
| Unsupported language quality | detected language outside supported set and low parse quality | `LANGUAGE_REVIEW_REQUIRED` | Continue manual review or switch to vi/en |
| Mixed layout/table heavy | parser low confidence on sections | `REVIEW_REQUIRED` | Review extracted fields before import |

### 2.3 AI And Parser Behavior

- Deterministic parser runs first.
- OCR runs only when native extraction is empty/low quality.
- LLM structuring runs only after extraction has enough text and `AI_REAL_CALLS_ENABLED` policy allows the environment.
- If classifier says `NOT_A_CV`, do not call LLM by default. Offer manual template creation.
- If confidence is low, mark fields `needs_review`; never silently import.
- AI never spends credits for validation failures before generation.
- AI credits are charged only when a suggestion/draft is successfully produced.

### 2.3A CV Library, Quota, And Job-Fit

| Case | Detect | Status / Code | User Action |
|---|---|---|---|
| Active CV limit reached | active library count >= tier limit | `QUOTA_EXCEEDED` | Archive/delete CV, request more quota, or upgrade |
| No eligible CV for job fit | no active ready/uploaded CV | `NO_ELIGIBLE_CV` | Upload CV, create from template, or draft from notes |
| Stale CV | last edited older than configured threshold (default 60 days) | `STALE_CV_WARNING` | Review/update before applying |
| Job no longer open | job closed/deadline passed during fit/apply | `JOB_NOT_OPEN` | Browse similar jobs |
| Job-fit AI unavailable | provider disabled/timeout/cost cap | `AI_UNAVAILABLE` | Show deterministic skills/JD diff or retry later |
| JD too vague | job lacks enough requirements | `INSUFFICIENT_JD_CONTENT` | Show general CV quality advice and report issue |

CV-to-job fit scores are user-facing product scores. They must never expose raw
confidence, embedding similarity, provider/model names, prompts, or token data.
Missing gaps are suggestions to add evidence only if true, never instructions to
fabricate.

### 2.4 User-Facing Copy Examples

`BLANK_DOCUMENT`

- vi: "Tệp này có vẻ là trang trắng hoặc không có nội dung đọc được. Bạn có thể tải lên tệp khác hoặc tạo CV bằng mẫu có sẵn."
- en: "This file looks blank or unreadable. Upload another file or create a CV from a template."

`NOT_A_CV`

- vi: "Tệp này không giống CV/hồ sơ ứng tuyển. Hãy tải lên CV, hoặc bắt đầu bằng mẫu CV và nhập thông tin thủ công."
- en: "This file does not look like a CV/resume. Upload a CV or start from a template."

`LOW_QUALITY_SCAN`

- vi: "Bản scan quá mờ nên hệ thống không đọc chính xác. Hãy tải bản rõ hơn, DOCX, hoặc PDF có thể chọn text."
- en: "The scan is too unclear to read reliably. Upload a clearer scan, DOCX, or text-selectable PDF."

`REVIEW_REQUIRED`

- vi: "Chúng tôi đã trích xuất được một số thông tin nhưng cần bạn kiểm tra trước khi nhập vào CV."
- en: "We extracted some information, but you need to review it before importing."

---

## 3. Common Product Edge Cases

### Auth And Account

- Same email tries multiple personas: require explicit identity selection.
- New login from new device: create security event and mandatory notification.
- Remote logout current device: require confirmation and redirect to login.
- TOTP required for university staff but not configured: force setup before admin pages.

### Applications

- Apply deadline passed during form fill: block submit with refreshed job status.
- Selected CV archived during apply: ask student to choose another CV.
- Application duplicate due double-click/retry: idempotency returns existing application.
- Anonymous apply to job that does not allow it: explain policy before submit.

### Partner Pipeline

- Two recruiters move candidate at same time: optimistic conflict, reload stage.
- Required scorecard missing: block stage transition with exact missing field.
- Candidate withdrawn by student: partner actions disabled with explanation.

### Notifications

- Template missing required variable: skip send, mark delivery failed, alert admin if recurring.
- User opted out of optional digest: do not send email/push, keep mandatory in-app when required.
- SMTP unavailable: product write succeeds, outbox retries; UI does not fail original action.

### AI

- Provider unavailable: deterministic fallback message and no credit charge.
- Prompt injection asks for internals: refuse and continue normal help.
- Low confidence or conflicting sources: ask user to review, do not auto-write.
- AI suggests unsupported claim: mark `requires_fact_confirmation`.

---

## 4. Required Test Pattern

For each major feature, include tests for:

- invalid input;
- empty input;
- duplicate/idempotent retry;
- permission denied;
- resource changed concurrently;
- async worker failure;
- AI/provider unavailable if AI is involved;
- mobile/responsive error state if user-facing;
- audit/log privacy.

If a feature lacks failure-mode tests, it is not complete.
