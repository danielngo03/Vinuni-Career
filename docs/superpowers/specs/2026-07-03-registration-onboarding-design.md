# Registration & Onboarding Overhaul — Design Spec
**Date:** 2026-07-03  
**Status:** Approved — proceeding to implementation

---

## 1. Problem Statement

The current registration flow has several critical gaps:
- Auth pages (login/register) render inside `(public)` route group → header and footer appear on auth screens
- Registration auto-assigns `student` identity with no role selection
- No onboarding wizard exists — users land on dashboard with no profile setup
- No email system is wired (SMTP not configured)
- No employer verification pipeline (document upload, AI check, tax ID)
- No student sub-type verification (student email OTP + ID card AI check)

---

## 2. Approved Flow: Email-First → Onboarding Wizard

```
[Register Form] name · email · password
      ↓
[Email Verification — Dual Mode]
  Option A: OTP 6 số (10 min TTL, max 3 attempts)
  Option B: Magic link click (24h TTL, single-use)
      ↓ (auto-redirect after verify)
[Onboarding Step 1 — Role Selection]
  ┌────────────────────┐   ┌────────────────────┐
  │ 🔍 Người tìm việc  │   │ 🏢 Nhà tuyển dụng  │
  └────────────────────┘   └────────────────────┘
```

### 2a. Người tìm việc (Job Seeker) path

```
Step 2 — Seeker Type
  🎓 Sinh viên (đang học) | 💼 Đang đi làm | 🌟 Mới tốt nghiệp

Step 3a — Sinh viên:
  → Tên trường (searchable dropdown)
  → Mã số sinh viên
  → Upload ảnh thẻ sinh viên
  → Email sinh viên (.edu domain)
  → OTP gửi đến email sinh viên → verify
  → AI check thẻ SV (format, not expired, text legible)
  → Status: student_verified ✓ (badge on profile)

Step 3b — Đang đi làm:
  → Chức vụ · Công ty hiện tại · Ngành · Năm kinh nghiệm

Step 3c — Mới tốt nghiệp:
  → Trường TN · Chuyên ngành · Năm tốt nghiệp

→ Complete → redirect to job_seeker workspace (student shell)
```

### 2b. Nhà tuyển dụng (Employer) path

```
Step 2 — Company Info
  → Tên công ty · Ngành nghề · Quy mô · Địa chỉ · Vị trí người đăng ký

Step 3 — Document Upload
  → Upload Giấy ĐKKD / Giấy phép kinh doanh (PDF/JPG/PNG ≤ 10MB)
  → Async AI pipeline (Celery task):
      1. OCR: extract tên công ty, MST, ngày ĐK, địa chỉ, người đại diện
      2. Tamper detection: font consistency, PDF metadata, pixel artifacts
      3. GDT API: verify MST → so sánh tên với OCR result
      4. Decision:
         - ai_score ≥ 80 + MST match → high_confidence (admin fast-track)
         - ai_score 50-79 → manual_review queue
         - ai_score < 50 OR MST mismatch → rejected

→ Submit → "Đang xét duyệt" holding screen
→ Email notification khi admin approve / reject
→ Approved → access employer workspace (partner shell)
```

---

## 3. Email System (SMTP: mail.ter.vn)

**Outgoing SMTP:** `mail.ter.vn:465` (SSL), `no-reply@ter.vn`  
Credentials stored in `backend/.env` only — never committed.

| Email Template | Trigger | Content |
|---------------|---------|---------|
| `verify_account` | Register | OTP 6 số + magic link (both in same email) |
| `verify_student_email` | Student onboarding | OTP 6 số |
| `employer_application_received` | Employer submit docs | Confirmation + timeline |
| `employer_approved` | Admin approve | Welcome + login link |
| `employer_rejected` | Admin reject | Reason + resubmit instructions |
| `welcome_job_seeker` | Onboarding complete | Welcome + profile completion tips |

**OTP rules:** 6-digit numeric, TTL 10 min, max 3 wrong attempts → invalidate + force resend, rate-limit 3 sends/hour/email.

---

## 4. Backend Schema Changes

### 4a. Extend `email_verifications` table
```sql
ALTER TABLE email_verifications
  ADD COLUMN otp_code_hash VARCHAR(128),    -- hashed 6-digit OTP
  ADD COLUMN otp_attempts  SMALLINT DEFAULT 0;
-- purpose enum gains new value: 'student_email'
```

### 4b. New table `onboarding_states`
```sql
CREATE TABLE onboarding_states (
  user_id         UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  role            VARCHAR(20),       -- 'job_seeker' | 'employer'
  seeker_type     VARCHAR(30),       -- 'student' | 'professional' | 'fresh_graduate'
  current_step    VARCHAR(50),       -- 'role_select' | 'seeker_type' | 'profile_info'
                                     -- | 'student_verify' | 'employer_info'
                                     -- | 'employer_docs' | 'complete'
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4c. New table `student_verifications`
```sql
CREATE TABLE student_verifications (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  university_name          VARCHAR(255) NOT NULL,
  student_id_number        VARCHAR(50)  NOT NULL,
  student_email            VARCHAR(320) NOT NULL,
  student_email_verified_at TIMESTAMPTZ,
  id_card_file_path        VARCHAR(500),
  ai_check_status          VARCHAR(30) DEFAULT 'pending',
                           -- 'pending'|'passed'|'failed'|'manual_review'
  ai_check_result          JSONB,
  verified_at              TIMESTAMPTZ,
  status                   VARCHAR(20) DEFAULT 'unverified',
                           -- 'unverified'|'verified'|'rejected'
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4d. Extend `partner_registration_requests` table
```sql
ALTER TABLE partner_registration_requests
  ADD COLUMN tax_id               VARCHAR(20),
  ADD COLUMN tax_id_verified      BOOLEAN DEFAULT FALSE,
  ADD COLUMN tax_id_api_result    JSONB,
  ADD COLUMN document_path        VARCHAR(500),
  ADD COLUMN ai_doc_status        VARCHAR(30) DEFAULT 'pending',
                                  -- 'pending'|'passed'|'tampered'|'manual_review'
  ADD COLUMN ai_doc_result        JSONB,
  ADD COLUMN submitted_by_user_id UUID REFERENCES users(id);
```

### 4e. Map personas to product roles
| Product Role | Backend Persona | Notes |
|-------------|----------------|-------|
| Người tìm việc | `student` | All seeker types share student workspace |
| Nhà tuyển dụng | `partner_member` | Org-scoped, pending until approved |

---

## 5. New API Endpoints

```
# Onboarding flow (require auth, require email_verified)
GET  /api/v1/onboarding/status
POST /api/v1/onboarding/role                    body: { role }
POST /api/v1/onboarding/seeker-type             body: { seeker_type }
POST /api/v1/onboarding/seeker-profile          body: { title, company, industry, years_exp }
                                                     | { university, major, graduation_year }
POST /api/v1/onboarding/student-verify/request  body: { university_name, student_id_number, student_email }
POST /api/v1/onboarding/student-verify/confirm  body: { otp_code } + multipart: id_card_image
POST /api/v1/onboarding/employer-info           body: { company_name, industry, size, address, registrant_role }
POST /api/v1/onboarding/employer-docs           multipart: business_document (PDF/image ≤ 10MB)
GET  /api/v1/onboarding/employer-docs/status    → poll AI processing result

# Auth (new)
POST /api/v1/auth/verify-email/otp              body: { email, otp_code }
```

---

## 6. AI Document Verification Pipeline

**Runtime:** Celery async task, triggered after `/onboarding/employer-docs` upload.

```python
# Task: verify_employer_document(request_id: UUID)
1. Load document from storage
2. OCR extraction:
   - PDF native text → pdfplumber
   - Scanned image → pytesseract (fallback)
   - Extract: company_name, tax_id (MST), reg_date, address, representative
3. Tamper detection:
   - PDF: check metadata consistency, creation tool, font embedding
   - Image: pixel artifact scoring via PIL/numpy heuristics
   - LLM cross-check: "Does this look like an authentic Vietnamese ĐKKD?"
   - Output: tamper_score 0-100 (higher = more suspicious)
4. GDT Tax ID lookup:
   - POST to tax lookup API with MST
   - Compare returned company_name vs OCR company_name (fuzzy match ≥ 85%)
   - Timeout 10s → fallback to manual_review
5. Decision matrix:
   - tamper_score < 30 AND gdt_match = True → ai_doc_status = 'passed', confidence = 'high'
   - tamper_score 30-60 OR gdt_match = False → 'manual_review'
   - tamper_score > 60 → 'tampered' → auto-reject + notify user
6. Update partner_registration_requests, notify admin queue
```

---

## 7. Frontend Structure

### New route group: `(auth)` — no header/footer
```
src/app/[locale]/
├── (auth)/
│   ├── layout.tsx              ← AuthShell only (centered card, logo, no nav)
│   ├── auth/
│   │   ├── login/page.tsx      ← moved from (public)
│   │   ├── register/page.tsx   ← moved from (public)
│   │   ├── verify-email/page.tsx
│   │   ├── forgot-password/page.tsx
│   │   └── reset-password/page.tsx
│   └── onboarding/
│       ├── layout.tsx           ← OnboardingShell (progress bar, step indicator)
│       ├── role/page.tsx        ← Step 1: role card selection
│       ├── seeker-type/page.tsx ← Step 2a: seeker sub-type
│       ├── seeker-profile/page.tsx ← Step 3: profile info (dynamic per type)
│       ├── student-verify/page.tsx ← Step 3a: student email + card upload
│       ├── employer-info/page.tsx  ← Step 2b: company info form
│       ├── employer-docs/page.tsx  ← Step 3b: document upload + AI status poll
│       └── pending/page.tsx        ← Employer waiting screen
└── (public)/                   ← remove auth pages, keep marketplace
```

### Auth page UI polish
- No header/footer (new `(auth)` group)
- Logo centered top
- Monochrome card — white bg, gray-100 border, ink text
- OTP input: 6 separate single-digit boxes with auto-focus
- Magic link + OTP both shown in verify screen ("Nhập mã bên dưới hoặc click link trong email")
- Progress indicator on onboarding (Step X / 3)
- Role selection: two large cards with icon, title, description, hover ink border

---

## 8. Redirect Guard Logic

After login, before showing workspace:
```
if onboarding_state.current_step !== 'complete':
  redirect to /onboarding/{current_step}
elif user.role === 'employer' AND org.status === 'pending':
  redirect to /onboarding/pending
else:
  redirect to workspace dashboard
```

This ensures users who abandon mid-onboarding always resume where they left off.

---

## 9. Security Considerations

- OTP hashed (SHA-256) before storage — plain code never persisted
- Student email verified separately from account email — two independent OTP flows
- Employer documents stored in private bucket — signed URLs only, never public
- AI verification results stored in JSONB — no LLM prompts or raw provider names exposed to frontend
- GDT API calls proxied through backend — API key not exposed
- Rate limits: 3 OTP sends/hour, 3 wrong attempts before invalidation
- Document upload: max 10MB, whitelist PDF/JPG/PNG, virus scan via clamd (if available)

---

## 10. Out of Scope (for this spec)

- Admin UI for reviewing employer applications (separate spec)
- University staff registration (invite-only flow, separate spec)
- Social login (Google, LinkedIn) — later phase
- Alumni verification via graduation certificate — later phase
