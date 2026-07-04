# Data Model — VinUni Career Platform

> Phiên bản: 2.0 | Cập nhật: 26/06/2026  
> Source of truth for canonical greenfield entities, tenancy, auditing, soft delete, and projections.

---

## 0. Product Reality Data Rule

Data changes must satisfy `docs/PRODUCT_REALITY_REBUILD_SPEC.md`. Do not add
display-only strings or disconnected seed objects when the real workflow needs
structured salary, experience, eligibility, taxonomy, location, media, audit,
quota, notification, analytics, or projection data.

Seed/crawled data must link to canonical tables, use accurate logos/media where
available, and cover realistic edge cases such as negotiable salary, salary
range/from/to, no experience requirement, multiple locations, expired/pending
jobs, sponsored inventory, verified/unverified companies, and varied candidate
pipelines.

Broad rebuild slices must model these data families when the workflow touches
them:

- `application_snapshots` / `application_cv_snapshots` / screening-answer
  snapshots so submissions are historically stable.
- `consents`, `privacy_requests`, and `security_events` for compliance and
  student-visible account history. Retention constants are hardcoded (not a
  `retention_policies` table) per ADR-0014/E36 — see §22.
- Platform support actions reuse `audit_logs` (`resource_type` prefixed
  `support_*`) and `human_review_queue` (`source="support_case"`) — there is
  **no** separate `support_audit_events` or `support_cases` table (ADR-0014
  supersedes the earlier anticipation of those names).
- `content_reports` + `human_review_queue` (source `user_report` alongside
  the existing `fraud_detection`) cover abuse/fraud escalations for
  companies, jobs, and messages — there is **no** separate `fraud_signals`
  table (ADR-0014).
- Read-model metadata such as source event, refresh time, stale flag, and
  reconciliation status for dashboards, recommendations, analytics, and
  competition intelligence.

---

## 1. Tenancy Model

- User account can have multiple identities (student, partner member, university staff, alumni).
- Identity determines persona and permissions for the current session.
- Partner and university staff actions are organization-scoped (`org_id` on every write).
- Student-owned data is scoped to the user/student identity.
- Cross-tenant reads must be blocked at query/service level — never rely on router-layer filtering alone.

---

## 2. Database Setup Requirements

```sql
-- Enable these extensions before running migrations
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pgvector";      -- Vector similarity search (RAG)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- Trigram fuzzy search (job/company search)
CREATE EXTENSION IF NOT EXISTS "btree_gin";     -- Composite GIN indexes
CREATE EXTENSION IF NOT EXISTS "unaccent";      -- Vietnamese accent-insensitive search
```

---

## 3. Shared Column Conventions

Most persisted entities include these columns:

```sql
id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()  -- updated via trigger
created_by      UUID REFERENCES users(id)           -- actor who created
updated_by      UUID REFERENCES users(id)           -- actor who last updated
deleted_at      TIMESTAMPTZ                         -- soft delete; NULL = active
version         INT NOT NULL DEFAULT 1              -- optimistic locking
```

**Soft delete rule:** `WHERE deleted_at IS NULL` on all normal queries. Alembic view `active_{table}` provides filtered access.

**`updated_at` trigger:**
```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
-- Applied to every mutable table via Alembic baseline migration.
```

---

## 4. Identity & Auth

### `users`
```sql
CREATE TABLE users (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email               VARCHAR(320) NOT NULL UNIQUE,
  email_verified_at   TIMESTAMPTZ,
  password_hash       VARCHAR(255),           -- NULL if SSO-only
  is_active           BOOLEAN NOT NULL DEFAULT TRUE,
  is_superadmin       BOOLEAN NOT NULL DEFAULT FALSE,  -- platform-level only
  preferred_language  VARCHAR(5) NOT NULL DEFAULT 'vi', -- 'vi' | 'en'
  last_login_at       TIMESTAMPTZ,
  login_count         INT NOT NULL DEFAULT 0,
  timezone            VARCHAR(50) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at          TIMESTAMPTZ
);
CREATE INDEX idx_users_email ON users(email) WHERE deleted_at IS NULL;
```

### `identities`
One user can hold multiple roles (student AND alumni AND staff).
```sql
CREATE TABLE identities (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  persona         VARCHAR(30) NOT NULL,  -- 'student' | 'partner_member' | 'university_staff' | 'alumni' | 'guest'
  org_id          UUID REFERENCES organizations(id), -- NULL for student/alumni
  is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, persona, org_id)
);
CREATE INDEX idx_identities_user ON identities(user_id);
```

### `oidc_accounts` (SSO / OAuth linking)

Links a user to a third-party identity provider (`docs/API_CONTRACTS.md` "OAuth
Account Linking"). No raw provider access/id tokens are persisted — nothing
downstream of login needs them, so there is no token-at-rest exposure to
manage; only the provider's stable subject id and non-sensitive profile claims
are kept.

```sql
CREATE TABLE oidc_accounts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider         VARCHAR(50) NOT NULL,  -- 'google' | 'facebook' | 'vinuni_sso' (future)
  provider_user_id VARCHAR(255) NOT NULL,
  extra_claims     JSONB NOT NULL DEFAULT '{}',  -- non-sensitive profile claims only, never raw tokens
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(provider, provider_user_id)
);
```

Linking rules: a verified-by-provider email with no existing account creates a
new user. An existing account with no password set (SSO-only/invited) auto-links
silently. An existing account **with** a password set requires an explicit
password-confirmation step before the row is created (`link-confirm` in
`docs/API_CONTRACTS.md`) — this is the OAuth "conflict" state; no row is written
until the owner confirms.

### `sessions`

> **Ratified deviation (Phase 1a, ADR-0001):** `sessions` no longer stores the
> refresh token. A session is now pure device/metadata; the refresh secret lives
> in a dedicated `refresh_tokens` history table (below) that records the rotation
> chain and enables reuse detection. See `docs/adr/ADR-0001-refresh-token-rotation-history.md`.

```sql
CREATE TABLE sessions (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  identity_id           UUID NOT NULL REFERENCES identities(id),
  device_hint           VARCHAR(200),          -- user-agent family summary (not raw)
  ip_hash               VARCHAR(128),          -- SHA-256 of IP (never raw)
  city_level_location   VARCHAR(200),          -- coarse, optional, security-explanation only
  expires_at            TIMESTAMPTZ NOT NULL,
  last_seen_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked_at            TIMESTAMPTZ,
  revoked_reason        VARCHAR(50)            -- 'logout' | 'reuse_detected' | 'password_reset' | ...
);
CREATE INDEX idx_sessions_user ON sessions(user_id) WHERE revoked_at IS NULL;
```

### `refresh_tokens`
One-row-per-issued-refresh-token rotation history. On refresh, the presented token
is verified by hash, marked `rotated_at`, and a new row is inserted with
`replaced_by_id` pointing back, forming a chain. Presenting an already-rotated or
revoked token (reuse) revokes the whole session.
```sql
CREATE TABLE refresh_tokens (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  token_hash      VARCHAR(128) NOT NULL UNIQUE,  -- SHA-256; raw token never stored
  expires_at      TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  rotated_at      TIMESTAMPTZ,                   -- set when this token is exchanged
  revoked_at      TIMESTAMPTZ,
  replaced_by_id  UUID REFERENCES refresh_tokens(id)  -- next token in the chain
);
CREATE INDEX idx_refresh_tokens_session ON refresh_tokens(session_id);
```

### `user_totp`

TOTP secrets are sensitive credentials. Store encrypted secret material only; do
not log or expose the raw secret after setup.

```sql
CREATE TABLE user_totp (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  encrypted_secret  TEXT NOT NULL,              -- encrypted at rest
  verified_at       TIMESTAMPTZ,
  disabled_at       TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_user_totp_active
  ON user_totp(user_id)
  WHERE disabled_at IS NULL;
```

Login must enforce TOTP for users with active verified TOTP and for identities
whose policy requires TOTP.

### `email_verifications`

Dual-mode: one issuance carries both a magic-link token and a 6-digit OTP
(`otp_code_hash`), so either the link or the code completes the same record.
`otp_attempts` counts wrong-code guesses; the record is force-used once
`otp_max_attempts` (default 3, `docs/API_CONTRACTS.md`) is reached, requiring a
fresh resend.

```sql
CREATE TABLE email_verifications (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash      VARCHAR(255) NOT NULL UNIQUE,
  otp_code_hash   VARCHAR(255),          -- SHA-256 of the 6-digit OTP; NULL for legacy link-only rows
  otp_attempts    INT NOT NULL DEFAULT 0,
  purpose         VARCHAR(30) NOT NULL,  -- 'register' | 'change_email' | 'password_reset' | 'student_email'
  expires_at      TIMESTAMPTZ NOT NULL,
  used_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `auth_throttles`

Anti-spam/anti-enumeration throttle for `forgot-password`, `verify-email/resend`,
and pending-registration resume. Keyed by the **normalized email itself**
(hashed), never by `user_id`, so throttling behaves identically whether or not
an account exists for the email — see `docs/API_CONTRACTS.md` "Resend cooldown
and rate limiting".

```sql
CREATE TABLE auth_throttles (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope               VARCHAR(50) NOT NULL,  -- 'forgot_password' | 'resend_verification' | 'register_resume'
  key_hash            VARCHAR(128) NOT NULL, -- SHA-256 of the normalized email
  window_started_at   TIMESTAMPTZ NOT NULL,
  attempt_count       INT NOT NULL DEFAULT 0,
  last_attempt_at     TIMESTAMPTZ NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(scope, key_hash)
);
```

### Onboarding state machine

Tracks first-login role selection through profile completion. Draft state is
resumable at any step; completing onboarding sets `completed_at` but never
deletes prior `student_verifications`/audit rows, so support/compliance history
survives (`CLAUDE.md` onboarding rule).

```sql
CREATE TABLE onboarding_states (
  user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  role          VARCHAR(20),   -- 'job_seeker' | 'employer'
  seeker_type   VARCHAR(20),   -- 'student' | 'professional' | 'fresh_graduate' (job_seeker only)
  current_step  VARCHAR(30) NOT NULL DEFAULT 'role_select',
  -- job_seeker: role_select -> seeker_type -> seeker_profile -> student_verify -> complete
  -- employer:   role_select -> employer_info -> employer_docs -> pending -> complete
  completed_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE student_verifications (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  university_name         VARCHAR(255),
  student_id_number       VARCHAR(100),
  student_email           VARCHAR(320),
  student_email_verified_at TIMESTAMPTZ,
  id_card_file_path       VARCHAR(500),
  ai_check_status         VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending'|'passed'|'failed'|'manual_review'
  ai_check_result         JSONB,
  status                  VARCHAR(20) NOT NULL DEFAULT 'unverified', -- 'unverified'|'verified'|'rejected'
  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Employer onboarding reuses the partner-registration tax-id/document-verification
columns on the organization/partner-registration entities (see §"Partner &
Student Registration Contracts" in `docs/API_CONTRACTS.md`), not a separate table.

---

## 5. Organization & RBAC

### `organizations`
```sql
CREATE TABLE organizations (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug                VARCHAR(100) NOT NULL UNIQUE,
  display_name        VARCHAR(255) NOT NULL,
  org_type            VARCHAR(20) NOT NULL,  -- 'partner' | 'university'
  logo_path           VARCHAR(500),
  website_url         VARCHAR(500),
  description         TEXT,
  industry            VARCHAR(100),          -- partner only
  company_size        VARCHAR(30),           -- '1-10' | '11-50' | '51-200' | '201-500' | '500+'
  founded_year        SMALLINT,
  headquarters_city   VARCHAR(100),
  is_verified         BOOLEAN NOT NULL DEFAULT FALSE,
  verified_at         TIMESTAMPTZ,
  verified_by         UUID REFERENCES users(id),
  status              VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending' | 'active' | 'suspended'
  subscription_tier   VARCHAR(20) NOT NULL DEFAULT 'free',     -- 'free' | 'basic' | 'premium' | 'enterprise'
  trust_level         VARCHAR(20) NOT NULL DEFAULT 'standard', -- partner trust set at approval: 'standard' | 'verified' | 'strategic'
  settings            JSONB NOT NULL DEFAULT '{}',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at          TIMESTAMPTZ,
  version             INT NOT NULL DEFAULT 1
);
CREATE INDEX idx_orgs_slug ON organizations(slug) WHERE deleted_at IS NULL;
CREATE INDEX idx_orgs_type ON organizations(org_type, status) WHERE deleted_at IS NULL;
```

`logo_path` is an internal storage key, not a public URL. Public projections must
derive `logo_url` through an organization-media delivery contract
(`docs/API_CONTRACTS.md`), and must never serialize `logo_path` to guest,
student, partner-public, dashboard, analytics, or log payloads. Partner admins
and university admins manage logo/media through validated upload records; if no
validated logo exists, UI renders an initials fallback.

### `departments`
```sql
CREATE TABLE departments (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name        VARCHAR(200) NOT NULL,
  parent_id   UUID REFERENCES departments(id),  -- hierarchical departments
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, name)
);
```

### `roles`
```sql
CREATE TABLE roles (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name        VARCHAR(100) NOT NULL,
  description TEXT,
  is_system   BOOLEAN NOT NULL DEFAULT FALSE,  -- system roles cannot be deleted
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, name)
);
```

### `permissions`
```sql
CREATE TABLE permissions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  resource_type   VARCHAR(100) NOT NULL,  -- 'job' | 'application' | 'candidate' | etc.
  action          VARCHAR(50) NOT NULL,   -- 'read' | 'write' | 'delete' | 'approve' | 'export'
  UNIQUE(role_id, resource_type, action)
);
```

### `memberships`
```sql
CREATE TABLE memberships (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  identity_id     UUID NOT NULL REFERENCES identities(id),
  status          VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active' | 'suspended' | 'left'
  joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  left_at         TIMESTAMPTZ,
  version         INT NOT NULL DEFAULT 1,                 -- optimistic locking for concurrent role/dept edits
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, org_id)
);
CREATE INDEX idx_memberships_org ON memberships(org_id) WHERE status = 'active';
```

### `membership_roles` (M2M)
```sql
CREATE TABLE membership_roles (
  membership_id   UUID NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
  role_id         UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  assigned_by     UUID REFERENCES users(id),
  PRIMARY KEY(membership_id, role_id)
);
```

### `membership_departments` (M2M)
Member ↔ Department assignment (ARCHITECTURE §4.4 `Member (n) ── (m) Departments`).
```sql
CREATE TABLE membership_departments (
  membership_id   UUID NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
  department_id   UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
  assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  assigned_by     UUID REFERENCES users(id),
  PRIMARY KEY(membership_id, department_id)
);
```

### `invitations`
Canonical org-invitation entity. The `organization` module exposes this concept
under `/organizations/invitations`; the table name remains `invitations`.
```sql
CREATE TABLE invitations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email           VARCHAR(320) NOT NULL,
  role_id         UUID REFERENCES roles(id),
  department_id   UUID REFERENCES departments(id),  -- optional initial department
  token_hash      VARCHAR(255) NOT NULL UNIQUE,
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending' | 'accepted' | 'revoked' | 'expired'
  invited_by      UUID NOT NULL REFERENCES users(id),
  expires_at      TIMESTAMPTZ NOT NULL,
  accepted_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_invitations_pending_email
  ON invitations(org_id, lower(email)) WHERE status = 'pending';
```

### `partner_registration_requests`
Pending partner self-registration. The organization is created only on **approval**
(anti-spam: rejected/abandoned requests never create an org or squat a slug). The
admin approve/reject path param `{partner_id}` resolves to this row's `id` while
`pending_review`; the approved org id is returned on success.
```sql
CREATE TABLE partner_registration_requests (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name        VARCHAR(255) NOT NULL,
  tax_code            VARCHAR(50),                 -- dedupe key (normalized)
  company_website     VARCHAR(500),
  company_size        VARCHAR(30),
  industry            VARCHAR(100),
  description         TEXT,
  contact_name        VARCHAR(255) NOT NULL,
  contact_title       VARCHAR(150),
  contact_email       VARCHAR(320) NOT NULL,       -- becomes first admin user
  contact_phone       VARCHAR(30),
  logo_upload_id      UUID,                        -- optional pre-uploaded logo (documents module, later)
  status              VARCHAR(20) NOT NULL DEFAULT 'pending_review',
  -- 'pending_review' | 'approved' | 'rejected'
  review_note         TEXT,                        -- approval note or rejection reason
  reviewed_by         UUID REFERENCES users(id),
  reviewed_at         TIMESTAMPTZ,
  created_org_id      UUID REFERENCES organizations(id),  -- set on approval
  version             INT NOT NULL DEFAULT 1,      -- optimistic locking (concurrent approve/reject)
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Block duplicate live registrations by tax code and by contact email.
CREATE UNIQUE INDEX uq_partner_reg_taxcode
  ON partner_registration_requests(tax_code) WHERE status = 'pending_review' AND tax_code IS NOT NULL;
CREATE UNIQUE INDEX uq_partner_reg_email
  ON partner_registration_requests(lower(contact_email)) WHERE status = 'pending_review';
```

---

## 6. Student Profile

### `student_profiles`
```sql
CREATE TABLE student_profiles (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  student_id          VARCHAR(50) UNIQUE,           -- VinUni student ID (encrypted)
  full_name           VARCHAR(255) NOT NULL,
  full_name_en        VARCHAR(255),
  avatar_path         VARCHAR(500),
  headline            VARCHAR(255),                 -- "AI Engineer @ VinUni | Python, LLMs"
  bio                 TEXT,
  phone               VARCHAR(30),                  -- encrypted at rest
  date_of_birth       DATE,                         -- encrypted at rest; access per policy
  gender              VARCHAR(20),                  -- 'male' | 'female' | 'other' | 'prefer_not_say'
  nationality         VARCHAR(100),
  location_city       VARCHAR(100),
  location_country    VARCHAR(100) NOT NULL DEFAULT 'Vietnam',
  linkedin_url        VARCHAR(500),
  github_url          VARCHAR(500),
  portfolio_url       VARCHAR(500),
  gpa                 NUMERIC(3,2),                 -- access controlled per privacy setting
  graduation_year     SMALLINT,
  major               VARCHAR(200),
  degree_level        VARCHAR(30),  -- 'undergraduate' | 'graduate' | 'phd'
  enrollment_status   VARCHAR(30) NOT NULL DEFAULT 'enrolled',  -- 'enrolled' | 'graduated' | 'on_leave'
  tier                VARCHAR(30) NOT NULL DEFAULT 'general',   -- 'vinuni_student' | 'alumni' | 'external' | 'general'
  profile_completion  SMALLINT NOT NULL DEFAULT 0,  -- 0–100
  is_open_to_work     BOOLEAN NOT NULL DEFAULT FALSE,
  open_to_work_types  VARCHAR[] NOT NULL DEFAULT '{}',  -- ['full_time','internship','part_time']
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at          TIMESTAMPTZ
);
```

### `educations`
```sql
CREATE TABLE educations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      UUID NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
  institution     VARCHAR(255) NOT NULL,
  degree          VARCHAR(100),
  field_of_study  VARCHAR(200),
  start_date      DATE NOT NULL,
  end_date        DATE,
  is_current      BOOLEAN NOT NULL DEFAULT FALSE,
  gpa             NUMERIC(3,2),
  activities      TEXT,
  description     TEXT,
  sort_order      SMALLINT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `work_experiences`
```sql
CREATE TABLE work_experiences (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      UUID NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
  company_name    VARCHAR(255) NOT NULL,
  org_id          UUID REFERENCES organizations(id),  -- linked if company is on platform
  title           VARCHAR(255) NOT NULL,
  employment_type VARCHAR(30),  -- 'full_time' | 'part_time' | 'internship' | 'contract'
  location        VARCHAR(200),
  start_date      DATE NOT NULL,
  end_date        DATE,
  is_current      BOOLEAN NOT NULL DEFAULT FALSE,
  description     TEXT,
  skills_used     VARCHAR[] NOT NULL DEFAULT '{}',
  sort_order      SMALLINT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `student_skills`
```sql
CREATE TABLE student_skills (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      UUID NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
  name            VARCHAR(100) NOT NULL,
  category        VARCHAR(50),   -- 'technical' | 'language' | 'soft'
  proficiency     SMALLINT,      -- 1-5
  endorsed_count  INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(student_id, name)
);
```

### `privacy_settings`
```sql
CREATE TABLE privacy_settings (
  student_id          UUID PRIMARY KEY REFERENCES student_profiles(id) ON DELETE CASCADE,
  show_email          VARCHAR(20) NOT NULL DEFAULT 'invited',   -- 'public' | 'invited' | 'hidden'
  show_phone          VARCHAR(20) NOT NULL DEFAULT 'hidden',
  show_gpa            VARCHAR(20) NOT NULL DEFAULT 'invited',
  show_dob            VARCHAR(20) NOT NULL DEFAULT 'hidden',
  show_address        VARCHAR(20) NOT NULL DEFAULT 'hidden',
  allow_cv_download   BOOLEAN NOT NULL DEFAULT TRUE,
  require_watermark   BOOLEAN NOT NULL DEFAULT TRUE,
  anonymous_apply     BOOLEAN NOT NULL DEFAULT FALSE,           -- hide name/photo to recruiter
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `career_preferences`
```sql
CREATE TABLE career_preferences (
  student_id              UUID PRIMARY KEY REFERENCES student_profiles(id) ON DELETE CASCADE,
  desired_roles           VARCHAR[] NOT NULL DEFAULT '{}',
  desired_industries      VARCHAR[] NOT NULL DEFAULT '{}',
  desired_locations       VARCHAR[] NOT NULL DEFAULT '{}',
  desired_employment_types VARCHAR[] NOT NULL DEFAULT '{}',
  expected_salary_min     INT,
  expected_salary_max     INT,
  expected_salary_currency VARCHAR(5) NOT NULL DEFAULT 'VND',
  available_from          DATE,
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 7. Documents & CVs

### `documents`
```sql
CREATE TABLE documents (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  doc_type        VARCHAR(30) NOT NULL,   -- 'cv' | 'cover_letter' | 'portfolio' | 'certificate'
  original_name   VARCHAR(500) NOT NULL,
  storage_path    VARCHAR(1000) NOT NULL, -- internal storage key (never exposed raw)
  mime_type       VARCHAR(100) NOT NULL,
  file_size_bytes INT NOT NULL,
  checksum_sha256 VARCHAR(64) NOT NULL,
  virus_scan_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending' | 'clean' | 'infected' | 'failed'
  virus_scan_at   TIMESTAMPTZ,
  is_primary      BOOLEAN NOT NULL DEFAULT FALSE,  -- primary CV for quick apply
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_documents_user ON documents(user_id, doc_type) WHERE deleted_at IS NULL;
```

### `cv_parse_runs`
```sql
CREATE TABLE cv_parse_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id     UUID NOT NULL REFERENCES documents(id),
  status          VARCHAR(30) NOT NULL DEFAULT 'queued',
  -- 'queued' | 'running' | 'review_required' | 'completed' | 'failed'
  quality_code    VARCHAR(80),
  -- 'BLANK_DOCUMENT' | 'NOT_A_CV' | 'LOW_QUALITY_SCAN' | etc. from EDGE_CASES_FAILURE_MODES.md
  detected_language VARCHAR(10),
  page_count      INT,
  text_length     INT,
  provider_alias  VARCHAR(100),         -- internal alias, never exposed
  extracted_data  JSONB,                -- structured CV fields
  review_fields   JSONB,                -- fields requiring student review before import
  confidence      NUMERIC(4,3),         -- internal only, never in API responses
  error_message   TEXT,                 -- internal only
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cv_parse_runs_doc ON cv_parse_runs(document_id, created_at DESC);
```

### `cv_templates`
```sql
CREATE TABLE cv_templates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key             VARCHAR(100) NOT NULL UNIQUE,
  owner_org_id    UUID REFERENCES organizations(id),
  -- NULL = platform seed template; university org = university-approved template owner
  name_vi         VARCHAR(200) NOT NULL,
  name_en         VARCHAR(200) NOT NULL,
  category        VARCHAR(50) NOT NULL,  -- 'classic' | 'technical' | 'business' | 'research' | 'creative'
  status          VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'published' | 'archived'
  schema_version  SMALLINT NOT NULL DEFAULT 1,
  layout_schema   JSONB NOT NULL,
  -- pages, canvas elements, typography tokens, grid/columns, spacing, page rules, editor hints
  content_binding_schema JSONB NOT NULL DEFAULT '{}',
  -- structured CV fact bindings, repeatable section rules, overflow rules, localization fallbacks
  target_role_families VARCHAR[] NOT NULL DEFAULT '{}',
  preview_image   VARCHAR(1000),          -- internal storage key generated from real renderer
  is_premium      BOOLEAN NOT NULL DEFAULT FALSE,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  created_by      UUID REFERENCES users(id),
  published_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

`cv_templates` describes a visual document/canvas template, not just section
order. Student CVs reference the template version used at creation/export time
so later template edits do not silently change submitted or exported CVs.

### `cv_template_versions`
```sql
CREATE TABLE cv_template_versions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id     UUID NOT NULL REFERENCES cv_templates(id) ON DELETE CASCADE,
  version_number  INT NOT NULL,
  layout_schema   JSONB NOT NULL,
  content_binding_schema JSONB NOT NULL DEFAULT '{}',
  preview_image   VARCHAR(1000),
  status          VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'published' | 'archived'
  created_by      UUID REFERENCES users(id),
  published_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(template_id, version_number)
);
CREATE INDEX idx_cv_template_versions_template
  ON cv_template_versions(template_id, version_number DESC);
```

### `cv_template_assets`
```sql
CREATE TABLE cv_template_assets (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id     UUID NOT NULL REFERENCES cv_templates(id) ON DELETE CASCADE,
  version_id      UUID REFERENCES cv_template_versions(id) ON DELETE CASCADE,
  asset_type      VARCHAR(30) NOT NULL,
  -- 'thumbnail' | 'sample_photo' | 'font' | 'export_preview' | 'other'
  storage_key     VARCHAR(1000) NOT NULL,
  metadata_json   JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `cv_profiles` (builder CVs)
```sql
CREATE TABLE cv_profiles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title           VARCHAR(200) NOT NULL,
  source_type     VARCHAR(30) NOT NULL DEFAULT 'builder',
  -- 'builder' | 'blank_template' | 'confirmed_facts_import' | 'uploaded_import' | 'duplicate_existing' | 'ai_draft'
  template_id     UUID REFERENCES cv_templates(id),
  language        VARCHAR(10) NOT NULL DEFAULT 'vi',
  status          VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'ready' | 'archived'
  is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
  last_edited_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_cv_profiles_user ON cv_profiles(user_id, status) WHERE deleted_at IS NULL;
```

### `cv_sections`
```sql
CREATE TABLE cv_sections (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cv_id           UUID NOT NULL REFERENCES cv_profiles(id) ON DELETE CASCADE,
  section_type    VARCHAR(50) NOT NULL,
  -- 'summary' | 'education' | 'experience' | 'projects' | 'skills' | 'certifications' | 'awards' | 'languages' | 'activities' | 'custom'
  title           VARCHAR(200),
  sort_order      SMALLINT NOT NULL,
  content_json    JSONB NOT NULL DEFAULT '{}', -- structured section items, never raw PDF
  is_visible      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cv_sections_cv ON cv_sections(cv_id, sort_order);
```

### `cv_versions`
```sql
CREATE TABLE cv_versions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cv_id           UUID NOT NULL REFERENCES cv_profiles(id) ON DELETE CASCADE,
  version_number  INT NOT NULL,
  snapshot_json   JSONB NOT NULL,          -- full structured CV snapshot
  change_source   VARCHAR(30) NOT NULL,    -- 'manual' | 'ai_accept' | 'restore' | 'import'
  change_summary  VARCHAR(500),
  created_by      UUID NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(cv_id, version_number)
);
CREATE INDEX idx_cv_versions_cv ON cv_versions(cv_id, version_number DESC);
```

### `cv_ai_suggestions`
```sql
CREATE TABLE cv_ai_suggestions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cv_id           UUID NOT NULL REFERENCES cv_profiles(id) ON DELETE CASCADE,
  job_id          UUID REFERENCES jobs(id),
  task_type       VARCHAR(100) NOT NULL,
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'accepted' | 'rejected' | 'expired'
  target_section_id UUID REFERENCES cv_sections(id),
  prompt_version  SMALLINT,
  input_summary   JSONB NOT NULL DEFAULT '{}', -- no raw prompt or full CV text
  diff_json       JSONB NOT NULL,              -- before/after structured diff
  credits_charged INT NOT NULL DEFAULT 0,
  created_by      UUID NOT NULL REFERENCES users(id),
  accepted_version_id UUID REFERENCES cv_versions(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at     TIMESTAMPTZ
);
CREATE INDEX idx_cv_ai_suggestions_cv ON cv_ai_suggestions(cv_id, status, created_at DESC);
```

### `cv_job_fit_reports`
```sql
CREATE TABLE cv_job_fit_reports (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  cv_id           UUID NOT NULL REFERENCES cv_profiles(id) ON DELETE CASCADE,
  cv_version_id   UUID NOT NULL REFERENCES cv_versions(id),
  score           SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 100),
  score_label     VARCHAR(30) NOT NULL,
  -- 'strong_fit' | 'good_fit' | 'possible_fit' | 'weak_fit'
  categories_json JSONB NOT NULL DEFAULT '{}',
  matched_evidence JSONB NOT NULL DEFAULT '[]',
  gaps_json       JSONB NOT NULL DEFAULT '[]',
  staleness_warning VARCHAR(100),
  generated_by    VARCHAR(30) NOT NULL DEFAULT 'deterministic',
  -- 'deterministic' | 'ai_explained'
  prompt_version  SMALLINT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at      TIMESTAMPTZ,
  UNIQUE(user_id, job_id, cv_id, cv_version_id)
);
CREATE INDEX idx_cv_job_fit_reports_user_job
  ON cv_job_fit_reports(user_id, job_id, score DESC);
```

This table stores user-facing product scores and explanations. It must not store
raw prompt text, raw CV text, embedding similarity, model confidence, provider
names, or token counts.

### `student_job_competition_reports`
```sql
CREATE TABLE student_job_competition_reports (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  cv_id           UUID REFERENCES cv_profiles(id) ON DELETE SET NULL,
  cv_version_id   UUID REFERENCES cv_versions(id) ON DELETE SET NULL,
  score           SMALLINT CHECK (score BETWEEN 0 AND 100),
  score_label     VARCHAR(30) NOT NULL,
  -- 'low' | 'moderate' | 'high' | 'very_high' | 'low_signal'
  seats_bucket    VARCHAR(30),
  application_volume_bucket VARCHAR(30),
  applicant_quality_bucket VARCHAR(30),
  student_fit_bucket VARCHAR(30),
  student_fit_percentile_bucket VARCHAR(30),
  source_mix_json JSONB NOT NULL DEFAULT '{}',
  explanation_json JSONB NOT NULL DEFAULT '{}',
  generated_by    VARCHAR(30) NOT NULL DEFAULT 'deterministic',
  -- 'deterministic' | 'ai_explained'
  prompt_version  SMALLINT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at      TIMESTAMPTZ,
  UNIQUE(user_id, job_id, cv_id, cv_version_id)
);
CREATE INDEX idx_student_job_competition_reports_user_job
  ON student_job_competition_reports(user_id, job_id, created_at DESC);
```

This report is visible only to the authenticated student it was generated for.
It stores aggregate/bucketed guidance and must not store other applicants' raw
CV text, identities, exact ranks, provider/model names, prompts, token counts,
or raw model confidence.

### `cv_exports`
```sql
CREATE TABLE cv_exports (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cv_id           UUID NOT NULL REFERENCES cv_profiles(id),
  version_id      UUID NOT NULL REFERENCES cv_versions(id),
  document_id     UUID REFERENCES documents(id),
  export_format   VARCHAR(20) NOT NULL DEFAULT 'pdf', -- 'pdf' v1, 'docx' later
  status          VARCHAR(20) NOT NULL DEFAULT 'queued',
  -- 'queued' | 'running' | 'ready' | 'failed'
  error_message   TEXT,
  requested_by    UUID NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ
);
CREATE INDEX idx_cv_exports_cv ON cv_exports(cv_id, created_at DESC);
```

### `signed_file_accesses` (audit trail for downloads)
```sql
CREATE TABLE signed_file_accesses (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id     UUID NOT NULL REFERENCES documents(id),
  accessor_id     UUID NOT NULL REFERENCES users(id),
  accessor_org_id UUID REFERENCES organizations(id),
  purpose         VARCHAR(50) NOT NULL,  -- 'preview' | 'download' | 'application_review'
  has_watermark   BOOLEAN NOT NULL DEFAULT FALSE,
  watermark_text  VARCHAR(500),
  signed_url_hash VARCHAR(64),           -- hash of the signed URL for audit
  ip_hash         VARCHAR(64),
  accessed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_file_access_doc ON signed_file_accesses(document_id, accessed_at DESC);
```

---

## 8. Opportunities (Jobs)

### `jobs`
```sql
CREATE TABLE jobs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              UUID NOT NULL REFERENCES organizations(id),
  posted_by           UUID NOT NULL REFERENCES users(id),
  title               VARCHAR(255) NOT NULL,
  slug                VARCHAR(300) NOT NULL UNIQUE,
  description         TEXT NOT NULL,
  requirements        TEXT,
  benefits            TEXT,
  employment_type     VARCHAR(30) NOT NULL,   -- 'full_time' | 'part_time' | 'internship' | 'contract'
  location_type       VARCHAR(20) NOT NULL,   -- 'onsite' | 'remote' | 'hybrid'
  location_city       VARCHAR(100),
  location_country    VARCHAR(100) NOT NULL DEFAULT 'Vietnam',
  required_skills     VARCHAR[] NOT NULL DEFAULT '{}',
  preferred_skills    VARCHAR[] NOT NULL DEFAULT '{}',
  experience_min_years SMALLINT,
  experience_max_years SMALLINT,
  degree_required     VARCHAR(30),
  salary_min          INT,
  salary_max          INT,
  salary_currency     VARCHAR(5) NOT NULL DEFAULT 'VND',
  salary_is_disclosed BOOLEAN NOT NULL DEFAULT FALSE,
  salary_mode         VARCHAR(20),
  -- 'negotiable' | 'hidden' | 'fixed' | 'range' | 'from' | 'to'; authoritative
  -- over salary_is_disclosed/min/max (B-544/B-545). 'hidden' means a real
  -- number exists (partner budget/reporting/export use) but is not publicly
  -- disclosed; 'negotiable' means no real number exists at all.
  salary_period       VARCHAR(10) NOT NULL DEFAULT 'monthly',
  -- 'monthly' | 'yearly'
  salary_gross_net    VARCHAR(15) NOT NULL DEFAULT 'unspecified',
  -- 'unspecified' | 'gross' | 'net'
  experience_mode     VARCHAR(20),
  -- 'no_requirement' | 'fresher' | 'range' | 'min' | 'max'; authoritative over
  -- experience_min_years/experience_max_years (B-544/B-545). 'fresher' means
  -- both years are explicitly 0 (entry-level); 'no_requirement' means the
  -- employer does not care either way (both years NULL).
  headcount           SMALLINT NOT NULL DEFAULT 1,
  application_deadline TIMESTAMPTZ,
  status              VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'pending_review' | 'active' | 'closed' | 'expired' | 'rejected'
  moderation_status   VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'approved' | 'rejected' | 'flagged'
  moderation_note     TEXT,
  approved_by         UUID REFERENCES users(id),
  approved_at         TIMESTAMPTZ,
  published_at        TIMESTAMPTZ,
  closed_at           TIMESTAMPTZ,
  view_count          INT NOT NULL DEFAULT 0,
  application_count   INT NOT NULL DEFAULT 0,  -- denormalized counter
  is_featured         BOOLEAN NOT NULL DEFAULT FALSE,
  is_sponsored        BOOLEAN NOT NULL DEFAULT FALSE,
  settings            JSONB NOT NULL DEFAULT '{}',  -- advanced settings
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at          TIMESTAMPTZ,
  version             INT NOT NULL DEFAULT 1,
  -- Full-text search
  tsv_search          TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,''))
  ) STORED
);
CREATE INDEX idx_jobs_org ON jobs(org_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_jobs_status ON jobs(status, moderation_status, published_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_jobs_tsv ON jobs USING GIN(tsv_search);
CREATE INDEX idx_jobs_skills ON jobs USING GIN(required_skills);
```

### `screening_questions`
```sql
CREATE TABLE screening_questions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id      UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  question    TEXT NOT NULL,
  q_type      VARCHAR(20) NOT NULL,  -- 'text' | 'single_choice' | 'multiple_choice' | 'yes_no'
  options     JSONB,                  -- for choice types
  is_required BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order  SMALLINT NOT NULL DEFAULT 0
);
```

---

## 9. Recruitment

### `applications`
```sql
CREATE TABLE applications (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id              UUID NOT NULL REFERENCES jobs(id),
  student_id          UUID NOT NULL REFERENCES student_profiles(id),
  cv_document_id      UUID REFERENCES documents(id),     -- uploaded/original CV path
  cv_profile_id       UUID REFERENCES cv_profiles(id),   -- builder/template CV path
  cv_version_id       UUID REFERENCES cv_versions(id),   -- version used at submit time
  cover_letter        TEXT,
  screening_answers   JSONB NOT NULL DEFAULT '{}',
  is_anonymous        BOOLEAN NOT NULL DEFAULT FALSE,
  reveal_approved_by  UUID REFERENCES users(id),
  reveal_approved_at  TIMESTAMPTZ,
  status              VARCHAR(30) NOT NULL DEFAULT 'submitted',
  -- 'draft' | 'submitted' | 'screening' | 'interview' | 'offer' |
  -- 'offer_accepted' | 'offer_declined' | 'rejected' | 'withdrawn'
  rejection_reason    VARCHAR(50),    -- 'not_qualified' | 'position_filled' | 'budget' | 'other'
  rejection_note      TEXT,           -- internal note
  applied_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_status_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ai_match_score      NUMERIC(4,3),   -- internal only, never exposed raw
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at          TIMESTAMPTZ,
  version             INT NOT NULL DEFAULT 1,
  UNIQUE(job_id, student_id)
);
CREATE INDEX idx_applications_job ON applications(job_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_applications_student ON applications(student_id, status) WHERE deleted_at IS NULL;
```

### `application_cv_snapshots`
```sql
CREATE TABLE application_cv_snapshots (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  cv_id           UUID REFERENCES cv_profiles(id),
  cv_version_id   UUID REFERENCES cv_versions(id),
  uploaded_document_id UUID REFERENCES documents(id),
  snapshot_json   JSONB NOT NULL,          -- immutable submitted CV snapshot
  redacted_json   JSONB,                   -- generated for anonymous applications
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(application_id)
);
```

Every submitted application must create exactly one immutable CV snapshot, regardless of whether the student used an uploaded CV, a builder CV, or an AI-assisted template CV.

### `pipeline_templates`
```sql
CREATE TABLE pipeline_templates (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL REFERENCES organizations(id),
  name        VARCHAR(200) NOT NULL,
  is_default  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `pipeline_stages`
```sql
CREATE TABLE pipeline_stages (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id         UUID NOT NULL REFERENCES pipeline_templates(id) ON DELETE CASCADE,
  name                VARCHAR(100) NOT NULL,
  stage_type          VARCHAR(30) NOT NULL,  -- 'screening' | 'interview' | 'assessment' | 'offer' | 'custom'
  sort_order          SMALLINT NOT NULL,
  sla_hours           INT,                   -- SLA for stage completion
  is_rejection_point  BOOLEAN NOT NULL DEFAULT FALSE,
  automation_rules    JSONB NOT NULL DEFAULT '{}'
);
```

### `candidate_stages` (application pipeline position)
```sql
CREATE TABLE candidate_stages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  stage_id        UUID NOT NULL REFERENCES pipeline_stages(id),
  entered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  exited_at       TIMESTAMPTZ,
  moved_by        UUID REFERENCES users(id),
  notes           TEXT
);
CREATE INDEX idx_candidate_stages_app ON candidate_stages(application_id, entered_at DESC);
```

### `interviews`
```sql
CREATE TABLE interviews (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id      UUID NOT NULL REFERENCES applications(id),
  stage_id            UUID REFERENCES pipeline_stages(id),
  interview_type      VARCHAR(30) NOT NULL,  -- 'phone' | 'video' | 'onsite' | 'technical'
  scheduled_at        TIMESTAMPTZ NOT NULL,
  duration_minutes    SMALLINT NOT NULL DEFAULT 60,
  location            VARCHAR(500),           -- address or video link
  interviewers        UUID[] NOT NULL DEFAULT '{}',  -- user IDs
  status              VARCHAR(20) NOT NULL DEFAULT 'scheduled',
  -- 'scheduled' | 'confirmed' | 'completed' | 'cancelled' | 'no_show'
  student_confirmed_at TIMESTAMPTZ,
  meeting_url         VARCHAR(1000),          -- encrypted at rest
  notes               TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `scorecards`
```sql
CREATE TABLE scorecards (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  interview_id    UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
  reviewer_id     UUID NOT NULL REFERENCES users(id),
  recommendation  VARCHAR(20),  -- 'strong_yes' | 'yes' | 'neutral' | 'no' | 'strong_no'
  overall_score   NUMERIC(3,1), -- 1.0–5.0
  criteria        JSONB NOT NULL DEFAULT '{}',  -- {criterion: score, notes}
  private_notes   TEXT,
  submitted_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `offers`
```sql
CREATE TABLE offers (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id      UUID NOT NULL REFERENCES applications(id),
  created_by          UUID NOT NULL REFERENCES users(id),
  position_title      VARCHAR(255) NOT NULL,
  department          VARCHAR(200),
  start_date          DATE,
  salary_amount       INT NOT NULL,           -- encrypted at rest
  salary_currency     VARCHAR(5) NOT NULL DEFAULT 'VND',
  salary_period       VARCHAR(20) NOT NULL DEFAULT 'monthly',
  benefits_summary    TEXT,
  offer_letter_path   VARCHAR(1000),          -- encrypted storage path
  expiry_date         TIMESTAMPTZ NOT NULL,
  status              VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'sent' | 'accepted' | 'declined' | 'expired' | 'withdrawn'
  student_response_at TIMESTAMPTZ,
  decline_reason      TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  version             INT NOT NULL DEFAULT 1
);
```

---

## 10. Events

### `events`
```sql
CREATE TABLE events (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              UUID NOT NULL REFERENCES organizations(id),
  created_by          UUID NOT NULL REFERENCES users(id),
  title               VARCHAR(500) NOT NULL,
  slug                VARCHAR(600) NOT NULL UNIQUE,
  description         TEXT NOT NULL,
  event_type          VARCHAR(30) NOT NULL,  -- 'career_fair' | 'workshop' | 'seminar' | 'networking' | 'webinar'
  format              VARCHAR(20) NOT NULL,  -- 'onsite' | 'online' | 'hybrid'
  cover_image_path    VARCHAR(1000),
  venue_name          VARCHAR(300),
  venue_address       TEXT,
  online_link         VARCHAR(1000),         -- encrypted
  starts_at           TIMESTAMPTZ NOT NULL,
  ends_at             TIMESTAMPTZ NOT NULL,
  timezone            VARCHAR(50) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
  registration_opens_at  TIMESTAMPTZ,
  registration_closes_at TIMESTAMPTZ,
  status              VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'pending_review' | 'published' | 'cancelled' | 'completed'
  moderation_status   VARCHAR(20) NOT NULL DEFAULT 'pending',
  is_featured         BOOLEAN NOT NULL DEFAULT FALSE,
  is_sponsored        BOOLEAN NOT NULL DEFAULT FALSE,
  tags                VARCHAR[] NOT NULL DEFAULT '{}',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at          TIMESTAMPTZ
);
CREATE INDEX idx_events_org ON events(org_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_events_dates ON events(starts_at, status) WHERE deleted_at IS NULL;
```

### `ticket_types`
```sql
CREATE TABLE ticket_types (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name            VARCHAR(200) NOT NULL,
  description     TEXT,
  price           INT NOT NULL DEFAULT 0,     -- 0 = free
  currency        VARCHAR(5) NOT NULL DEFAULT 'VND',
  capacity        INT NOT NULL,
  available_count INT NOT NULL,               -- decremented on registration
  sale_starts_at  TIMESTAMPTZ,
  sale_ends_at    TIMESTAMPTZ,
  is_visible      BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order      SMALLINT NOT NULL DEFAULT 0
);
```

### `event_registrations`
```sql
CREATE TABLE event_registrations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id        UUID NOT NULL REFERENCES events(id),
  ticket_type_id  UUID NOT NULL REFERENCES ticket_types(id),
  user_id         UUID NOT NULL REFERENCES users(id),
  status          VARCHAR(20) NOT NULL DEFAULT 'confirmed',
  -- 'confirmed' | 'waitlisted' | 'cancelled' | 'attended'
  check_in_at     TIMESTAMPTZ,
  check_in_by     UUID REFERENCES users(id),
  qr_code_hash    VARCHAR(64) NOT NULL UNIQUE,
  payment_status  VARCHAR(20) NOT NULL DEFAULT 'free',  -- 'free' | 'pending' | 'paid'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(event_id, user_id)
);
```

---

## 11. Governance & Audit

### `audit_logs`
```sql
CREATE TABLE audit_logs (
  id              BIGSERIAL PRIMARY KEY,  -- BIGSERIAL for high-volume insert performance
  actor_id        UUID REFERENCES users(id),
  actor_org_id    UUID REFERENCES organizations(id),
  action          VARCHAR(100) NOT NULL,  -- 'job.approve' | 'application.status_change' | etc.
  resource_type   VARCHAR(100) NOT NULL,
  resource_id     UUID,
  before_snapshot JSONB,                  -- state before change
  after_snapshot  JSONB,                  -- state after change
  ip_hash         VARCHAR(64),            -- SHA-256 of IP — never raw IP
  user_agent_hash VARCHAR(64),
  session_id      UUID REFERENCES sessions(id),
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Partition by month in production (pg_partman)
CREATE INDEX idx_audit_actor ON audit_logs(actor_id, occurred_at DESC);
CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id, occurred_at DESC);
```

### `outbox_events`
```sql
CREATE TABLE outbox_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  aggregate_type  VARCHAR(100) NOT NULL,
  aggregate_id    UUID NOT NULL,
  event_type      VARCHAR(200) NOT NULL,  -- 'application.status_changed'
  payload         JSONB NOT NULL,
  actor_id        UUID REFERENCES users(id),
  published_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_outbox_unpublished ON outbox_events(created_at) WHERE published_at IS NULL;
```

### `moderation_items`
```sql
CREATE TABLE moderation_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_type   VARCHAR(50) NOT NULL,   -- 'job' | 'event' | 'ad' | 'organization' | 'review'
  resource_id     UUID NOT NULL,
  submitted_by    UUID REFERENCES users(id),
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'approved' | 'rejected' | 'flagged'
  priority        VARCHAR(10) NOT NULL DEFAULT 'normal',  -- 'low' | 'normal' | 'high' | 'urgent'
  ai_suggestion   VARCHAR(20),            -- AI's suggestion — advisory only
  ai_reasoning    TEXT,                   -- internal only
  assigned_to     UUID REFERENCES users(id),
  decision        VARCHAR(20),
  decision_reason TEXT NOT NULL DEFAULT '', -- required for 'rejected'
  decided_by      UUID REFERENCES users(id),
  decided_at      TIMESTAMPTZ,
  sla_deadline    TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_moderation_queue ON moderation_items(status, priority, sla_deadline)
  WHERE status = 'pending';
```

### `feature_flags`
```sql
CREATE TABLE feature_flags (
  key             VARCHAR(100) PRIMARY KEY,
  enabled         BOOLEAN NOT NULL DEFAULT FALSE,
  rollout_pct     SMALLINT NOT NULL DEFAULT 0,  -- 0-100 gradual rollout
  target_personas VARCHAR[] NOT NULL DEFAULT '{}',  -- empty = all
  description     TEXT,
  updated_by      UUID REFERENCES users(id),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 12. AI Tables

### `ai_sessions`
```sql
CREATE TABLE ai_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_id          UUID REFERENCES organizations(id),
  context_type    VARCHAR(30) NOT NULL DEFAULT 'general',  -- 'general' | 'job' | 'application' | 'kb'
  context_id      UUID,
  title           VARCHAR(255),
  history_summary TEXT,              -- compressed summary for long sessions
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_active_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_archived     BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_ai_sessions_user ON ai_sessions(user_id, last_active_at DESC) WHERE NOT is_archived;
```

### `ai_messages`
```sql
CREATE TABLE ai_messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      UUID NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
  role            VARCHAR(20) NOT NULL,  -- 'user' | 'assistant' | 'tool_call' | 'tool_result'
  content         TEXT,
  tool_name       VARCHAR(100),
  tool_call_id    VARCHAR(100),
  input_tokens    INT,
  output_tokens   INT,
  model_alias     VARCHAR(100),          -- internal alias, never in API responses
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_messages_session ON ai_messages(session_id, created_at ASC);
```

### `ai_usage_log`
```sql
CREATE TABLE ai_usage_log (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL REFERENCES organizations(id),
  user_id             UUID REFERENCES users(id),
  session_id          UUID REFERENCES ai_sessions(id),
  task_type           VARCHAR(100) NOT NULL,
  model_alias         VARCHAR(100) NOT NULL,
  provider_internal   VARCHAR(100) NOT NULL,  -- never in API responses
  input_tokens        INT NOT NULL,
  output_tokens       INT NOT NULL,
  cost_usd            NUMERIC(10,6) NOT NULL,
  latency_ms          INT NOT NULL,
  success             BOOLEAN NOT NULL,
  error_code          VARCHAR(50),
  prompt_version      SMALLINT,
  reranker_skipped    BOOLEAN NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Partition by month in production for large-scale insert throughput
CREATE INDEX idx_ai_usage_tenant ON ai_usage_log(tenant_id, created_at DESC);
CREATE INDEX idx_ai_usage_task ON ai_usage_log(task_type, created_at DESC);
```

### `ai_provider_configs`
```sql
CREATE TABLE ai_provider_configs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  provider_alias  VARCHAR(100) NOT NULL,  -- internal alias only
  provider_type   VARCHAR(50) NOT NULL,   -- 'openai_compatible' | 'gemini_native' | 'anthropic'
  api_endpoint    VARCHAR(500),
  api_key_enc     TEXT NOT NULL,          -- Fernet-encrypted API key
  is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
  priority        SMALLINT NOT NULL DEFAULT 1,  -- for fallback chain ordering
  monthly_token_budget INT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `ai_task_model_configs`
```sql
CREATE TABLE ai_task_model_configs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  task_type       VARCHAR(100) NOT NULL,
  model_alias     VARCHAR(100) NOT NULL,
  provider_config_id UUID NOT NULL REFERENCES ai_provider_configs(id),
  prompt_version  SMALLINT NOT NULL DEFAULT 1,
  prompt_ab_config JSONB,
  fallback_chain  UUID[] NOT NULL DEFAULT '{}',  -- ordered provider_config IDs
  enabled         BOOLEAN NOT NULL DEFAULT FALSE,
  max_tokens      INT NOT NULL DEFAULT 2000,
  temperature     NUMERIC(3,2) NOT NULL DEFAULT 0.7,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, task_type)
);
```

### `human_review_queue`
```sql
CREATE TABLE human_review_queue (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID REFERENCES organizations(id),
  review_type     VARCHAR(100) NOT NULL, -- 'ai_output' | 'fraud' | 'moderation' | 'cv_fabrication'
  target_type     VARCHAR(100) NOT NULL,
  target_id       UUID NOT NULL,
  priority        SMALLINT NOT NULL DEFAULT 3,
  status          VARCHAR(20) NOT NULL DEFAULT 'open',
  ai_reason       TEXT,
  assigned_to     UUID REFERENCES users(id),
  resolved_by     UUID REFERENCES users(id),
  resolution      VARCHAR(50),
  resolved_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_human_review_queue ON human_review_queue(status, priority, created_at);
```

### `ai_eval_samples`
```sql
CREATE TABLE ai_eval_samples (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_type       VARCHAR(100) NOT NULL,
  session_id      UUID REFERENCES ai_sessions(id),
  message_id      UUID REFERENCES ai_messages(id),
  input_summary   TEXT,
  output_summary  TEXT,
  model_alias     VARCHAR(100),
  prompt_version  SMALLINT,
  guard_flags     JSONB NOT NULL DEFAULT '{}',
  human_score     SMALLINT,
  reviewed_by     UUID REFERENCES users(id),
  reviewed_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_eval_samples_task ON ai_eval_samples(task_type, created_at DESC);
```

---

## 13. Knowledge Base (RAG)

### `knowledge_bases`
```sql
CREATE TABLE knowledge_bases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  kb_type         VARCHAR(20) NOT NULL,  -- 'platform' | 'partner' | 'per_job'
  job_id          UUID REFERENCES jobs(id),  -- non-null for per_job type
  name            VARCHAR(255) NOT NULL,
  description     TEXT,
  quota_mb        INT NOT NULL DEFAULT 500,
  used_mb         NUMERIC(8,2) NOT NULL DEFAULT 0,
  document_count  INT NOT NULL DEFAULT 0,
  chunk_count     INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at      TIMESTAMPTZ
);
```

### `knowledge_base_documents`
```sql
CREATE TABLE knowledge_base_documents (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kb_id           UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  document_id     UUID NOT NULL REFERENCES documents(id),
  uploaded_by     UUID NOT NULL REFERENCES users(id),
  processing_status VARCHAR(20) NOT NULL DEFAULT 'queued',
  -- 'queued' | 'scanning' | 'extracting' | 'chunking' | 'embedding' | 'ready' | 'failed'
  chunking_mode   VARCHAR(20) NOT NULL DEFAULT 'sliding_window',  -- 'sliding_window' | 'semantic'
  chunk_count     INT NOT NULL DEFAULT 0,
  error_message   TEXT,
  processing_started_at TIMESTAMPTZ,
  processing_completed_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `knowledge_base_chunks`
```sql
CREATE TABLE knowledge_base_chunks (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kb_id           UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  document_id     UUID NOT NULL REFERENCES knowledge_base_documents(id) ON DELETE CASCADE,
  chunk_index     INT NOT NULL,
  content         TEXT NOT NULL,
  section_heading VARCHAR(500),
  token_count     INT NOT NULL,
  embedding       VECTOR(1536),           -- dimension must match AI_EMBEDDING_MODEL
  tsv_content     TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
  is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(document_id, chunk_index)
);
CREATE INDEX idx_kb_chunks_embedding ON knowledge_base_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
  WHERE is_deleted = FALSE;
CREATE INDEX idx_kb_chunks_tsv ON knowledge_base_chunks
  USING GIN(tsv_content) WHERE is_deleted = FALSE;
CREATE INDEX idx_kb_chunks_kb ON knowledge_base_chunks(kb_id) WHERE is_deleted = FALSE;
```

---

## 14. Notifications

### `notifications`
```sql
CREATE TABLE notifications (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  sender_id       UUID REFERENCES users(id),
  notif_type      VARCHAR(100) NOT NULL,  -- 'application.status_changed' | 'interview.scheduled' | etc.
  title           VARCHAR(500) NOT NULL,
  body            TEXT NOT NULL,
  action_url      VARCHAR(500),
  is_read         BOOLEAN NOT NULL DEFAULT FALSE,
  read_at         TIMESTAMPTZ,
  channels        VARCHAR[] NOT NULL DEFAULT '{}',  -- ['in_app', 'email', 'push']
  delivered_at    JSONB NOT NULL DEFAULT '{}',  -- {channel: timestamp}
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_notif_recipient ON notifications(recipient_id, is_read, created_at DESC);
```

---

## 15. Read Models & Projections

Dashboards and high-volume lists read from materialized projections — no live JOIN across multiple domain tables.

```sql
-- Student dashboard projection (refresh: immediate on write + scheduled 5 min)
CREATE MATERIALIZED VIEW proj_student_dashboard AS
SELECT
  s.user_id,
  s.id AS student_id,
  s.profile_completion, -- secondary: preferences/confirmed facts/settings only
  s.is_open_to_work,
  COUNT(DISTINCT cv.id) FILTER (WHERE cv.status IN ('draft', 'ready') AND cv.deleted_at IS NULL) AS active_template_cvs,
  COUNT(DISTINCT d.id) FILTER (
    WHERE d.doc_type = 'cv'
      AND d.virus_scan_status = 'clean'
      AND d.deleted_at IS NULL
  ) AS active_uploaded_cvs,
  COUNT(DISTINCT a.id) FILTER (WHERE a.status NOT IN ('withdrawn', 'rejected')) AS active_applications,
  COUNT(DISTINCT a.id) FILTER (WHERE a.status = 'submitted') AS pending_review,
  COUNT(DISTINCT i.id) FILTER (WHERE i.scheduled_at > NOW() AND i.status = 'scheduled') AS upcoming_interviews,
  COUNT(DISTINCT o.id) FILTER (WHERE o.status = 'sent') AS pending_offers
FROM student_profiles s
LEFT JOIN cv_profiles cv ON cv.user_id = s.user_id AND cv.deleted_at IS NULL
LEFT JOIN documents d ON d.user_id = s.user_id AND d.doc_type = 'cv' AND d.deleted_at IS NULL
LEFT JOIN applications a ON a.student_id = s.id AND a.deleted_at IS NULL
LEFT JOIN interviews i ON i.application_id = a.id
LEFT JOIN offers o ON o.application_id = a.id
GROUP BY s.user_id, s.id, s.profile_completion, s.is_open_to_work;

CREATE UNIQUE INDEX ON proj_student_dashboard(user_id);
```

Student dashboard services derive `active_cv_library_items` from usable uploaded
CV originals plus active template/builder CVs, then compare it with the tier
limit. Application snapshots are not counted.

```sql
-- Partner pipeline projection
-- (refresh: immediate on every stage move / decision + scheduled 5 min)
--
-- ADR-0004 moved the FINE pipeline position out of applications.status (now the
-- COARSE outcome only: submitted | under_review | rejected | withdrawn [+ hired])
-- and into candidate_stages (one ACTIVE row per application). The by-stage buckets
-- are therefore counted from the ACTIVE candidate_stages rows, NOT from
-- applications.status (which no longer carries 'interview'/'offer'/… values).
-- The coarse outcome buckets (rejected/withdrawn/hired) stay sourced from
-- applications.status. A row is emitted per (job, stage) of the job's active
-- template plus one synthetic "new" (pre-pipeline) row per job.
--
-- Live read of record until this MV is built:
--   recruitment.dashboard_read.pipeline_counts_for_job / _for_org
--   (returns { new, by_stage:{stage_id:count}, active_total, rejected, withdrawn }).
CREATE MATERIALIZED VIEW proj_partner_pipeline AS
WITH active_stage_counts AS (
  -- Fine position: ACTIVE candidate_stages of under_review applications only.
  SELECT a.org_id, a.job_id, cs.stage_id, COUNT(*) AS candidate_count
  FROM candidate_stages cs
  JOIN applications a ON a.id = cs.application_id
  WHERE a.deleted_at IS NULL
    AND a.status = 'under_review'
    AND cs.status = 'ACTIVE'
  GROUP BY a.org_id, a.job_id, cs.stage_id
),
new_bucket AS (
  -- Pre-pipeline "new": active-outcome applications with no ACTIVE stage row.
  SELECT a.org_id, a.job_id, NULL::uuid AS stage_id, COUNT(*) AS candidate_count
  FROM applications a
  WHERE a.deleted_at IS NULL
    AND a.status IN ('submitted', 'under_review')
    AND NOT EXISTS (
      SELECT 1 FROM candidate_stages cs
      WHERE cs.application_id = a.id AND cs.status = 'ACTIVE'
    )
  GROUP BY a.org_id, a.job_id
),
outcomes AS (
  -- Coarse outcomes stay on applications.status.
  SELECT a.org_id, a.job_id,
    COUNT(*) FILTER (WHERE a.status = 'rejected')  AS rejected_count,
    COUNT(*) FILTER (WHERE a.status = 'withdrawn') AS withdrawn_count,
    COUNT(*) FILTER (WHERE a.status = 'hired')     AS hired_count
  FROM applications a
  WHERE a.deleted_at IS NULL
  GROUP BY a.org_id, a.job_id
)
SELECT
  j.org_id, j.id AS job_id, j.title,
  ps.id AS stage_id,                 -- NULL row = the "new" pre-pipeline bucket
  ps.sort_order,
  COALESCE(asc_.candidate_count, nb.candidate_count, 0) AS candidate_count,
  o.rejected_count, o.withdrawn_count, o.hired_count
FROM jobs j
LEFT JOIN pipeline_stages ps
  ON ps.template_id = (
    SELECT pt.id FROM pipeline_templates pt
    WHERE pt.org_id = j.org_id AND pt.is_default AND pt.is_system
    LIMIT 1
  )
LEFT JOIN active_stage_counts asc_
  ON asc_.job_id = j.id AND asc_.stage_id = ps.id
LEFT JOIN new_bucket nb ON nb.job_id = j.id AND ps.id IS NULL
LEFT JOIN outcomes o ON o.job_id = j.id
WHERE j.deleted_at IS NULL;

CREATE UNIQUE INDEX ON proj_partner_pipeline(job_id, stage_id);
CREATE INDEX ON proj_partner_pipeline(org_id);
```

```sql
-- University operations projection (refresh: immediate on moderation writes +
-- scheduled 5 min)
CREATE MATERIALIZED VIEW proj_university_operations_dashboard AS
WITH
partner_reviews AS (
  SELECT COUNT(*) AS pending_partner_reviews
  FROM partner_registration_requests
  WHERE status = 'pending'
),
job_reviews AS (
  SELECT
    COUNT(*) FILTER (WHERE moderation_status = 'pending') AS pending_job_reviews,
    COUNT(*) FILTER (WHERE moderation_status = 'flagged') AS flagged_jobs
  FROM jobs
  WHERE deleted_at IS NULL
),
partner_health AS (
  SELECT
    COUNT(*) FILTER (WHERE status = 'active') AS active_partners,
    COUNT(*) FILTER (WHERE status = 'suspended') AS suspended_partners
  FROM organizations
  WHERE org_type = 'partner' AND deleted_at IS NULL
)
SELECT now() AS generated_at, *
FROM partner_reviews, job_reviews, partner_health;
```

Dashboard projections should include only aggregate or permission-safe fields.
Admin-only operational metrics such as AI provider health stay on university
projections and are never included in student/partner/public projections.

---

## 16. Analytics Event Shape

```json
{
  "event_id": "uuid",
  "event_type": "job.viewed",
  "aggregate_type": "job",
  "aggregate_id": "uuid",
  "actor_id": "uuid-or-null",
  "actor_type": "student|partner_member|university_staff|guest|system",
  "occurred_at": "2026-06-26T12:00:00+07:00",
  "session_id": "string-or-null",
  "properties": {
    "source": "search_results",
    "query": null
  }
}
```

**Analytics event taxonomy:**
```
auth.*          login.success | login.failed | logout | password_reset
profile.*       profile.updated | cv.uploaded | cv.parsed
cv.*            cv.builder.started | cv.section.updated | cv.version.created | cv.export.completed
job.*           job.viewed | job.bookmarked | job.applied | job.shared
application.*   application.status_changed | application.withdrawn
interview.*     interview.scheduled | interview.cancelled | interview.attended
offer.*         offer.sent | offer.accepted | offer.declined
event.*         event.viewed | event.registered | event.attended
ai.*            ai.chat.started | ai.tool.called | ai.cv.analyzed
```

---

## 17. Privacy-Sensitive Fields

Encrypt at rest (Fernet) or access-control at query level:

| Field | Table | Protection |
|---|---|---|
| `phone` | `student_profiles` | Fernet encrypt + privacy policy check |
| `date_of_birth` | `student_profiles` | Fernet encrypt + policy check |
| `student_id` | `student_profiles` | Fernet encrypt |
| `government_id` | any | Fernet encrypt; not stored unless explicitly required |
| `gpa` | `student_profiles` | privacy_settings.show_gpa check |
| `salary_amount` | `offers` | Fernet encrypt; recruiter + student only |
| `api_key_enc` | `ai_provider_configs` | Fernet encrypt; never in API responses |
| `meeting_url` | `interviews` | Fernet encrypt; revealed only to attendees |
| `ip_hash` | `audit_logs`, `sessions` | SHA-256 hash only; no raw IP stored |
| `snapshot_json` | `cv_versions`, `application_cv_snapshots` | Access-control + no analytics logging |
| `diff_json` | `cv_ai_suggestions` | Owner-only; no raw prompt logging |

---

## 18. Soft Delete Summary

| Entity | Soft Delete | Hard Delete |
|---|---|---|
| `users` | `deleted_at` | Never (legal audit) |
| `organizations` | `deleted_at` | Never |
| `jobs` | `deleted_at` | Never |
| `applications` | `deleted_at` | Never |
| `documents` | `deleted_at` | Storage purge after 7-year retention |
| `cv_profiles` | `deleted_at` | Never hard-delete while referenced by applications |
| `cv_ai_suggestions` | status `expired` | Hard delete rejected/expired suggestions after 180 days |
| `events` | `deleted_at` | Never |
| `audit_logs` | Never soft-deleted | Never hard-deleted |
| `ai_usage_log` | Not deleted | Archive after 2 years |
| `knowledge_base_chunks` | `is_deleted` flag | Hard delete after 30 days |
| temp files (uploads) | — | Hard delete after virus scan + 15 min |

---

## 19. Subscriptions & Packages

### `partner_packages`
```sql
CREATE TABLE partner_packages (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                  VARCHAR(100) NOT NULL,
  slug                  VARCHAR(100) NOT NULL UNIQUE,
  description           TEXT,
  price_monthly         NUMERIC(12,2) NOT NULL,
  price_annual          NUMERIC(12,2) NOT NULL,       -- monthly × 12 × (1 - discount_rate)
  discount_rate_annual  NUMERIC(4,3) NOT NULL DEFAULT 0,  -- e.g. 0.20 = 20% off
  job_post_quota        INT NOT NULL DEFAULT 5,       -- -1 = unlimited
  featured_job_slots    INT NOT NULL DEFAULT 0,
  passive_search_quota  INT NOT NULL DEFAULT 0,
  email_blast_quota     INT NOT NULL DEFAULT 0,
  spotlight_slots       INT NOT NULL DEFAULT 0,       -- homepage banner, permanent (no monthly reset)
  pipeline_templates    INT NOT NULL DEFAULT 1,       -- -1 = unlimited
  max_team_members      INT NOT NULL DEFAULT 3,       -- -1 = unlimited
  analytics_level       VARCHAR(20) NOT NULL DEFAULT 'basic',  -- 'basic' | 'advanced' | 'enterprise'
  api_access            BOOLEAN NOT NULL DEFAULT FALSE,
  dedicated_support     BOOLEAN NOT NULL DEFAULT FALSE,
  is_visible            BOOLEAN NOT NULL DEFAULT TRUE, -- hide old plans
  sort_order            SMALLINT NOT NULL DEFAULT 0,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `partner_subscriptions`
```sql
CREATE TABLE partner_subscriptions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  package_id      UUID NOT NULL REFERENCES partner_packages(id),
  billing_cycle   VARCHAR(10) NOT NULL,  -- 'monthly' | 'annual'
  status          VARCHAR(20) NOT NULL DEFAULT 'active',
  -- 'active' | 'past_due' | 'cancelled' | 'expired'
  current_period_start  DATE NOT NULL,
  current_period_end    DATE NOT NULL,
  cancel_at_period_end  BOOLEAN NOT NULL DEFAULT FALSE,
  trial_ends_at         DATE,
  grace_period_ends_at  DATE,            -- payment failure grace (7 days)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_subscriptions_org ON partner_subscriptions(org_id, status);
```

### `quota_usage`
```sql
CREATE TABLE quota_usage (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  quota_type      VARCHAR(50) NOT NULL,
  -- 'job_post' | 'featured_job' | 'passive_search' | 'email_blast' | 'spotlight'
  period_start    DATE NOT NULL,
  period_end      DATE NOT NULL,
  used            INT NOT NULL DEFAULT 0,
  limit_value     INT NOT NULL,           -- -1 = unlimited
  carryover       INT NOT NULL DEFAULT 0,
  UNIQUE(org_id, quota_type, period_start)
);
CREATE INDEX idx_quota_usage_org ON quota_usage(org_id, quota_type, period_start);
```

### `payment_records`
```sql
CREATE TABLE payment_records (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  subscription_id UUID REFERENCES partner_subscriptions(id),
  amount          NUMERIC(12,2) NOT NULL,
  currency        VARCHAR(5) NOT NULL DEFAULT 'VND',
  payment_method  VARCHAR(30) NOT NULL DEFAULT 'bank_transfer',
  -- 'bank_transfer' | 'vnpay' | 'momo' | 'zalopay' (future)
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'confirmed' | 'failed' | 'refunded'
  reference_code  VARCHAR(200),           -- bank transfer reference
  confirmed_by    UUID REFERENCES users(id),  -- university admin who confirmed
  confirmed_at    TIMESTAMPTZ,
  description     TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_payment_records_org ON payment_records(org_id, created_at DESC);
```

### `student_subscriptions`
```sql
CREATE TABLE student_subscriptions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id),
  pack_name       VARCHAR(50) NOT NULL,   -- 'basic' | 'standard' | 'premium'
  status          VARCHAR(20) NOT NULL DEFAULT 'active',
  started_at      TIMESTAMPTZ NOT NULL,
  expires_at      TIMESTAMPTZ,            -- NULL = no expiry on lifetime packs
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_student_subs_user ON student_subscriptions(user_id, status);
```

### `student_ai_credits`
```sql
CREATE TABLE student_ai_credits (
  user_id           UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  balance           INT NOT NULL DEFAULT 0,
  lifetime_earned   INT NOT NULL DEFAULT 0,
  last_refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 20. Advertising

### `ad_campaigns`
```sql
CREATE TABLE ad_campaigns (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  created_by      UUID NOT NULL REFERENCES users(id),
  name            VARCHAR(300) NOT NULL,
  campaign_type   VARCHAR(10) NOT NULL,  -- 'CPM' | 'CPC' | 'FIXED'
  ad_placement    VARCHAR(50) NOT NULL,
  -- 'homepage_banner' | 'job_feed' | 'email_blast' | 'event_sponsor' | 'sidebar'
  headline        VARCHAR(200) NOT NULL,
  description     TEXT,
  image_path      VARCHAR(1000),         -- signed URL, never exposed raw
  cta_url         VARCHAR(1000) NOT NULL,
  bid_amount      NUMERIC(12,4),         -- per 1000 impressions or per click
  daily_budget    NUMERIC(12,2),
  total_budget    NUMERIC(12,2) NOT NULL,
  total_spent     NUMERIC(12,2) NOT NULL DEFAULT 0,
  daily_spent     NUMERIC(12,2) NOT NULL DEFAULT 0,
  daily_reset_at  DATE,
  starts_at       TIMESTAMPTZ,
  ends_at         TIMESTAMPTZ,
  status          VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'pending_review' | 'active' | 'paused' | 'rejected' | 'completed'
  moderation_note TEXT,
  approved_by     UUID REFERENCES users(id),
  approved_at     TIMESTAMPTZ,
  is_sponsored_label_confirmed  BOOLEAN NOT NULL DEFAULT FALSE,
  -- partner must confirm sponsored label before submit
  impression_count INT NOT NULL DEFAULT 0,
  click_count      INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_ad_campaigns_org ON ad_campaigns(org_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_ad_campaigns_active ON ad_campaigns(status, starts_at, ends_at)
  WHERE status = 'active' AND deleted_at IS NULL;
```

### `ad_campaign_targeting`
```sql
CREATE TABLE ad_campaign_targeting (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id     UUID NOT NULL REFERENCES ad_campaigns(id) ON DELETE CASCADE,
  dimension       VARCHAR(50) NOT NULL,
  -- 'user_tier' | 'interest_tags' | 'graduation_year' | 'industry_interest' | 'device_type'
  -- FORBIDDEN dimensions are rejected at API layer before storage
  values          VARCHAR[] NOT NULL DEFAULT '{}',
  UNIQUE(campaign_id, dimension)
);
```

---

## 21. Company Reviews

### `company_reviews`
```sql
CREATE TABLE company_reviews (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  reviewer_id     UUID NOT NULL REFERENCES users(id),
  eligibility_type VARCHAR(30) NOT NULL,
  -- 'system_verified_interview' | 'system_verified_offer' | 'self_declared' | 'partner_verified'
  title           VARCHAR(300) NOT NULL,
  body            TEXT NOT NULL,         -- minimum 50 chars enforced in service layer
  pros            TEXT,
  cons            TEXT,
  status          VARCHAR(20) NOT NULL DEFAULT 'pending_auto_review',
  -- 'pending_auto_review' | 'published' | 'flagged' | 'removed'
  published_at    TIMESTAMPTZ,           -- 2h delay after clean AI scan
  report_count    INT NOT NULL DEFAULT 0,
  is_anonymous    BOOLEAN NOT NULL DEFAULT FALSE,
  application_id  UUID REFERENCES applications(id),  -- NULL for self-declared
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, reviewer_id)            -- one review per reviewer per company
);
CREATE INDEX idx_reviews_org ON company_reviews(org_id, status, published_at DESC);
```

### `review_ratings`
```sql
CREATE TABLE review_ratings (
  review_id           UUID PRIMARY KEY REFERENCES company_reviews(id) ON DELETE CASCADE,
  overall             SMALLINT NOT NULL CHECK (overall BETWEEN 1 AND 5),
  work_life_balance   SMALLINT NOT NULL CHECK (work_life_balance BETWEEN 1 AND 5),
  culture_values      SMALLINT NOT NULL CHECK (culture_values BETWEEN 1 AND 5),
  compensation        SMALLINT NOT NULL CHECK (compensation BETWEEN 1 AND 5),
  career_growth       SMALLINT NOT NULL CHECK (career_growth BETWEEN 1 AND 5),
  interview_experience SMALLINT CHECK (interview_experience BETWEEN 1 AND 5)
  -- nullable: only relevant for interview-only reviewers
);
```

### Implemented (migration `0025_company_reviews_and_ratings`, ADR-0013)

The slice-1 build reconciles the draft above with platform conventions and adds a
report table + an aggregate read model. Authoritative columns as built:

- **`company_reviews`** — the draft columns PLUS shared conventions
  (`deleted_at` soft-delete, `version` optimistic lock, `created_at`/`updated_at`
  with the `set_updated_at` trigger) and moderation-actor fields
  (`moderation_note` internal-only, `moderated_by`, `moderated_at`). `status`
  vocabulary for slice-1 is `pending | published | flagged | removed`
  (PRE-moderation: a review is `pending` until a university moderator publishes;
  the `pending_auto_review` + `publish_after` auto-publish model is deferred to
  when AI moderation B-343 lands — see ADR-0013 / BUSINESS_LOGIC §7.3).
  `UNIQUE(org_id, reviewer_id)` is a plain (non-partial) constraint so a
  soft-deleted review still blocks a duplicate (re-review = edit/restore).
- **`review_reports`** (NEW) — `(id, review_id→company_reviews CASCADE,
  reporter_id→users, reporter_org_id?, reason_code, note?, created_at)`,
  `UNIQUE(review_id, reporter_id)` (one report per actor). A first report bumps
  `company_reviews.report_count` and flips `status→flagged` (the review STAYS
  published/visible until a moderator removes it — only `removed` drops it from
  the aggregate).
- **`proj_company_rating`** (NEW read model) — `(org_id PK→organizations CASCADE,
  review_count, overall_avg, overall_raw_avg, {category}_avg ×5, distribution
  JSONB, updated_at)`. Recompute-on-event (publish/remove/restore/author-edit)
  full-per-org (idempotent `ON CONFLICT`), read by the public company profile
  through `reviews.company_rating_facade` — no live JOIN on the guest surface.
  `overall_avg` is the Bayesian mean `(n·avg + 3·3.0)/(n+3)`; `n=0` → NULL (empty
  state, never the prior shown as a score).

---

## 22. Passive Search & Talent Pool

### `talent_pool_entries`
```sql
CREATE TABLE talent_pool_entries (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  student_id      UUID NOT NULL REFERENCES users(id),
  added_by        UUID NOT NULL REFERENCES users(id),
  label           VARCHAR(100),          -- partner's internal tag e.g. "Backend Q3"
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(org_id, student_id)
);
CREATE INDEX idx_talent_pool_org ON talent_pool_entries(org_id, created_at DESC);
```

### `passive_search_quota`
```sql
CREATE TABLE passive_search_quota (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id),
  quota_date      DATE NOT NULL,
  daily_sent      INT NOT NULL DEFAULT 0,
  daily_limit     INT NOT NULL DEFAULT 10,
  weekly_sent     INT NOT NULL DEFAULT 0,
  weekly_limit    INT NOT NULL DEFAULT 30,
  week_start      DATE NOT NULL,
  UNIQUE(org_id, quota_date)
);
```

### `contact_reveal_requests`
```sql
CREATE TABLE contact_reveal_requests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  UUID NOT NULL REFERENCES applications(id),
  requester_id    UUID NOT NULL REFERENCES users(id),
  requester_org_id UUID NOT NULL REFERENCES organizations(id),
  reason          TEXT NOT NULL,         -- min 20 chars
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'accepted' | 'declined' | 'expired'
  expires_at      TIMESTAMPTZ NOT NULL,  -- 72h after creation
  responded_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(application_id, requester_org_id)  -- one request per application per org
);
CREATE INDEX idx_reveal_requests_app ON contact_reveal_requests(application_id, status);
```

### `saved_jobs`
```sql
CREATE TABLE saved_jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, job_id)
);
CREATE INDEX idx_saved_jobs_user ON saved_jobs(user_id, created_at DESC);
```

---

## 23. Bulk Apply Cart

### `job_cart_items`
```sql
CREATE TABLE job_cart_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  cv_profile_id   UUID REFERENCES cv_profiles(id),
  cv_version_id   UUID REFERENCES cv_versions(id),
  uploaded_doc_id UUID REFERENCES documents(id),
  is_anonymous    BOOLEAN NOT NULL DEFAULT FALSE,
  added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, job_id)
);
CREATE INDEX idx_cart_user ON job_cart_items(user_id, added_at DESC);
```

### `cover_letter_drafts`
```sql
CREATE TABLE cover_letter_drafts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  content         TEXT NOT NULL,
  credits_used    INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, job_id)
);
```

---

## 24. Messaging

### `conversations`
```sql
CREATE TABLE conversations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  context_type    VARCHAR(30) NOT NULL DEFAULT 'direct',
  -- 'direct' | 'application' | 'broadcast_thread'
  context_id      UUID,                  -- application_id when context_type = 'application'
  title           VARCHAR(500),          -- display name for the conversation
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_conversations_last ON conversations(last_message_at DESC);

CREATE TABLE conversation_participants (
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role            VARCHAR(20) NOT NULL DEFAULT 'member',  -- 'member' | 'admin'
  last_read_at    TIMESTAMPTZ,
  joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_muted        BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (conversation_id, user_id)
);
CREATE INDEX idx_conv_participants_user ON conversation_participants(user_id, last_read_at);
```

### `messages`
```sql
CREATE TABLE messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender_id       UUID NOT NULL REFERENCES users(id),
  content         TEXT NOT NULL,
  message_type    VARCHAR(20) NOT NULL DEFAULT 'text',  -- 'text' | 'file' | 'system'
  attachments     JSONB NOT NULL DEFAULT '[]',
  reply_to_id     UUID REFERENCES messages(id),
  is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
  deleted_at      TIMESTAMPTZ,
  edited_at       TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at ASC)
  WHERE is_deleted = FALSE;
```

### `message_reads`
```sql
CREATE TABLE message_reads (
  message_id      UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  reader_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  read_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (message_id, reader_id)
);
```

### `broadcast_messages`
```sql
CREATE TABLE broadcast_messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sender_id       UUID NOT NULL REFERENCES users(id),
  segment         VARCHAR(50) NOT NULL,
  -- 'all_students' | 'vinuni_students' | 'alumni' | 'external' | 'all_partners' | 'custom'
  subject         VARCHAR(500) NOT NULL,
  body            TEXT NOT NULL,
  recipient_count INT NOT NULL DEFAULT 0,
  delivered_count INT NOT NULL DEFAULT 0,
  status          VARCHAR(20) NOT NULL DEFAULT 'queued',
  -- 'queued' | 'sending' | 'sent' | 'failed'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sent_at         TIMESTAMPTZ
);
```

---

## 25. Push Notification Subscriptions

```sql
CREATE TABLE user_push_subscriptions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  endpoint        TEXT NOT NULL,
  keys            JSONB NOT NULL,        -- {p256dh, auth} — encrypted VAPID keys
  device_hint     VARCHAR(50),           -- 'chrome_desktop' | 'safari_mobile' | etc.
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at    TIMESTAMPTZ,
  UNIQUE(user_id, endpoint)
);
```

---

## 26. Events — Seats & Promo Codes

### `event_seats`
```sql
CREATE TABLE event_seats (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  ticket_type_id  UUID REFERENCES ticket_types(id),
  row_label       VARCHAR(10),           -- e.g. 'A'
  seat_number     VARCHAR(10),           -- e.g. '12'
  section         VARCHAR(100),
  status          VARCHAR(20) NOT NULL DEFAULT 'available',
  -- 'available' | 'locked' | 'booked'
  locked_by       UUID REFERENCES users(id),
  locked_until    TIMESTAMPTZ,           -- Redis TTL mirrors this
  registration_id UUID REFERENCES event_registrations(id),
  UNIQUE(event_id, row_label, seat_number)
);
CREATE INDEX idx_seats_event ON event_seats(event_id, status);
```

### `promo_codes`
```sql
CREATE TABLE promo_codes (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id        UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  code            VARCHAR(50) NOT NULL,
  discount_type   VARCHAR(10) NOT NULL,  -- 'PERCENT' | 'FIXED'
  discount_value  NUMERIC(10,2) NOT NULL,
  min_order_value NUMERIC(10,2),
  max_uses        INT,                   -- NULL = unlimited
  max_uses_per_user INT NOT NULL DEFAULT 1,
  used_count      INT NOT NULL DEFAULT 0,
  valid_from      TIMESTAMPTZ NOT NULL,
  valid_until     TIMESTAMPTZ NOT NULL,
  applicable_ticket_type_ids UUID[] DEFAULT NULL,
  -- NULL = applies to all ticket types for this event
  created_by      UUID NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(event_id, code)
);

CREATE TABLE promo_code_uses (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  promo_code_id   UUID NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
  user_id         UUID NOT NULL REFERENCES users(id),
  registration_id UUID NOT NULL REFERENCES event_registrations(id),
  discount_applied NUMERIC(10,2) NOT NULL,
  used_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(promo_code_id, user_id)
);
```

---

## 27. Career Outcomes

### `career_outcome_records`
```sql
CREATE TABLE career_outcome_records (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id      UUID NOT NULL REFERENCES users(id),
  employer_name   VARCHAR(300),
  employer_org_id UUID REFERENCES organizations(id),  -- non-null when partner-confirmed
  position_title  VARCHAR(300),
  employment_type VARCHAR(30),  -- 'full_time' | 'part_time' | 'internship' | 'freelance'
  start_date      DATE,
  end_date        DATE,
  salary_amount   NUMERIC(12,2),                      -- encrypted at rest
  salary_currency VARCHAR(5) NOT NULL DEFAULT 'VND',
  trust_level     SMALLINT NOT NULL DEFAULT 3,
  -- 1=partner_confirmed | 2=linkedin_verified | 3=self_reported | 4=estimated
  source          VARCHAR(30) NOT NULL,
  -- 'partner_confirmed' | 'survey' | 'linkedin_import' | 'system_estimate'
  cohort_year     SMALLINT NOT NULL,
  consent_given   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_career_outcomes_student ON career_outcome_records(student_id, trust_level);
CREATE INDEX idx_career_outcomes_cohort ON career_outcome_records(cohort_year, trust_level);
```

> **Implementation status — phased build (migration `0018`).** The table above is
> the full target schema across all four trust sources. The shipped first slice
> (the ADR-0007 `offer.accepted` materializer, module `career_outcomes`) creates
> only the privacy-safe subset that the non-blocking `offer.accepted` event seam
> carries, since the seam intentionally holds NO student PII and NO salary:
> `application_id`, `offer_id`, `org_id`, `employer_org_id`, `position_title`,
> `start_date`, plus bookkeeping `outcome_type` (`'hired'`), `trust_level` (`4` =
> estimated), `source` (`'system_estimate'`), `source_event_id` (UNIQUE — the
> originating `outbox_events.id`, the materializer's idempotency guard),
> `recorded_at`, `created_at`/`updated_at`. Reporting indexes:
> `idx_career_outcomes_employer (employer_org_id, recorded_at)` and
> `idx_career_outcomes_recorded (recorded_at)`.
>
> The remaining columns — `student_id`, `employer_name`, `employment_type`,
> `end_date`, `salary_amount`/`salary_currency`, `cohort_year`, `consent_given` —
> and the `student`/`cohort` indexes belong to the **higher-trust sources**
> (partner-confirmed hire = level 1, LinkedIn = level 2, survey = level 3) and are
> added by a later migration when those write paths land. They are deliberately
> absent from the `0018` table rather than nullable-and-empty so the estimated
> source never carries fake unaudited PII/salary. When the higher-trust sources
> arrive, `student_id`/`cohort_year` are added NULLABLE (an estimated row has no
> confirmed student identity) — KPI numerators already exclude level 3/4 per
> `docs/BUSINESS_LOGIC.md` §13, so trust-level filtering, not NOT-NULL, is the
> integrity control.

### `post_grad_surveys`
```sql
CREATE TABLE post_grad_surveys (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cohort_year     SMALLINT NOT NULL,
  title           VARCHAR(300) NOT NULL,
  survey_month    SMALLINT NOT NULL,     -- months after graduation (e.g. 3, 6, 12)
  status          VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'active' | 'closed'
  opens_at        TIMESTAMPTZ,
  closes_at       TIMESTAMPTZ,
  questions       JSONB NOT NULL DEFAULT '[]',
  created_by      UUID NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE survey_responses (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  survey_id       UUID NOT NULL REFERENCES post_grad_surveys(id),
  respondent_id   UUID NOT NULL REFERENCES users(id),
  answers         JSONB NOT NULL DEFAULT '{}',
  completed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(survey_id, respondent_id)
);
```

---

## 28. Mentorship

### `mentor_profiles`
```sql
CREATE TABLE mentor_profiles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
  headline        VARCHAR(300),
  bio             TEXT,
  expertise_tags  VARCHAR[] NOT NULL DEFAULT '{}',
  industries      VARCHAR[] NOT NULL DEFAULT '{}',
  max_mentees     SMALLINT NOT NULL DEFAULT 3,
  session_duration_minutes SMALLINT NOT NULL DEFAULT 30,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  is_verified     BOOLEAN NOT NULL DEFAULT FALSE,  -- university-verified alumni/expert
  linkedin_url    VARCHAR(500),
  total_sessions  INT NOT NULL DEFAULT 0,
  avg_rating      NUMERIC(3,2),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mentor_profiles_active ON mentor_profiles(is_active, is_verified);
```

### `mentorship_requests`
```sql
CREATE TABLE mentorship_requests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mentee_id       UUID NOT NULL REFERENCES users(id),
  mentor_id       UUID NOT NULL REFERENCES users(id),
  message         TEXT NOT NULL,
  goals           TEXT,
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'accepted' | 'declined' | 'expired'
  responded_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mentorship_requests_mentor ON mentorship_requests(mentor_id, status);
CREATE INDEX idx_mentorship_requests_mentee ON mentorship_requests(mentee_id, status);
```

### `mentorship_sessions`
```sql
CREATE TABLE mentorship_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id      UUID NOT NULL REFERENCES mentorship_requests(id),
  mentor_id       UUID NOT NULL REFERENCES users(id),
  mentee_id       UUID NOT NULL REFERENCES users(id),
  scheduled_at    TIMESTAMPTZ NOT NULL,
  duration_minutes SMALLINT NOT NULL DEFAULT 30,
  meeting_url     VARCHAR(1000),         -- encrypted at rest
  status          VARCHAR(20) NOT NULL DEFAULT 'scheduled',
  -- 'scheduled' | 'completed' | 'cancelled' | 'no_show'
  mentor_notes    TEXT,                  -- private to mentor
  mentee_rating   SMALLINT CHECK (mentee_rating BETWEEN 1 AND 5),
  mentee_feedback TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ
);
```

---

## 29. Alumni Network

### `alumni_profiles`
```sql
CREATE TABLE alumni_profiles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
  graduation_year SMALLINT NOT NULL,
  major           VARCHAR(200),
  current_company VARCHAR(300),
  current_title   VARCHAR(300),
  current_city    VARCHAR(100),
  linkedin_url    VARCHAR(500),
  is_open_to_mentor BOOLEAN NOT NULL DEFAULT FALSE,
  is_open_to_connect BOOLEAN NOT NULL DEFAULT TRUE,
  skills          VARCHAR[] NOT NULL DEFAULT '{}',
  industries      VARCHAR[] NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_alumni_grad_year ON alumni_profiles(graduation_year, is_open_to_connect);
```

### `alumni_connections`
```sql
CREATE TABLE alumni_connections (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  requester_id    UUID NOT NULL REFERENCES users(id),
  recipient_id    UUID NOT NULL REFERENCES users(id),
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'connected' | 'declined'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  responded_at    TIMESTAMPTZ,
  UNIQUE(requester_id, recipient_id),
  CHECK (requester_id <> recipient_id)
);
```

---

## 30. Visual Workflow Engine

### `workflow_flows`
```sql
CREATE TABLE workflow_flows (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            VARCHAR(300) NOT NULL,
  description     TEXT,
  trigger_type    VARCHAR(100) NOT NULL,
  -- 'system.student_registered' | 'system.application_submitted' | 'scheduler.cron' | etc.
  graph           JSONB NOT NULL,         -- React Flow node/edge serialization
  status          VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'active' | 'paused' | 'archived'
  version         INT NOT NULL DEFAULT 1,
  created_by      UUID NOT NULL REFERENCES users(id),
  activated_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_workflow_flows_status ON workflow_flows(status, trigger_type);
```

### `workflow_executions`
```sql
CREATE TABLE workflow_executions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  flow_id         UUID NOT NULL REFERENCES workflow_flows(id),
  trigger_event   JSONB NOT NULL,         -- original trigger payload
  status          VARCHAR(20) NOT NULL DEFAULT 'running',
  -- 'running' | 'completed' | 'failed' | 'cancelled'
  node_logs       JSONB NOT NULL DEFAULT '[]',
  -- [{node_id, entered_at, exited_at, decision, error}]
  started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at     TIMESTAMPTZ,
  idempotency_key VARCHAR(200),           -- trigger_event_id + flow_id
  UNIQUE(idempotency_key)
);
CREATE INDEX idx_workflow_executions_flow ON workflow_executions(flow_id, started_at DESC);
CREATE INDEX idx_workflow_executions_status ON workflow_executions(status) WHERE status = 'running';
```

---

## 31. QA Bank (Interview Question Community)

### `qa_bank_questions`
```sql
CREATE TABLE qa_bank_questions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  posted_by       UUID REFERENCES users(id),     -- NULL = anonymous
  org_id          UUID REFERENCES organizations(id), -- company context if known
  job_category    VARCHAR(100),
  title           VARCHAR(500) NOT NULL,
  body            TEXT,
  tags            VARCHAR[] NOT NULL DEFAULT '{}',
  difficulty      VARCHAR(10),                   -- 'easy' | 'medium' | 'hard'
  question_type   VARCHAR(30),                   -- 'behavioral' | 'technical' | 'case_study'
  upvote_count    INT NOT NULL DEFAULT 0,
  answer_count    INT NOT NULL DEFAULT 0,
  status          VARCHAR(20) NOT NULL DEFAULT 'published',
  -- 'published' | 'flagged' | 'removed'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_qa_questions_category ON qa_bank_questions(job_category, upvote_count DESC)
  WHERE status = 'published';

CREATE TABLE qa_bank_answers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_id     UUID NOT NULL REFERENCES qa_bank_questions(id) ON DELETE CASCADE,
  author_id       UUID REFERENCES users(id),
  body            TEXT NOT NULL,
  is_accepted     BOOLEAN NOT NULL DEFAULT FALSE,
  upvote_count    INT NOT NULL DEFAULT 0,
  status          VARCHAR(20) NOT NULL DEFAULT 'published',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_qa_answers_question ON qa_bank_answers(question_id, upvote_count DESC)
  WHERE status = 'published';

CREATE TABLE qa_bank_votes (
  user_id         UUID NOT NULL REFERENCES users(id),
  target_type     VARCHAR(10) NOT NULL,  -- 'question' | 'answer'
  target_id       UUID NOT NULL,
  vote_type       VARCHAR(4) NOT NULL,   -- 'up' | 'down'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, target_type, target_id)
);
```

---

## 32. Application Timeline Events

```sql
CREATE TABLE application_timeline_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  event_type      VARCHAR(100) NOT NULL,
  -- 'submitted' | 'shortlisted' | 'interview_scheduled' | 'offer_extended' | 'rejected' | etc.
  label_vi        VARCHAR(200) NOT NULL,  -- friendly Vietnamese label (never raw enum)
  label_en        VARCHAR(200) NOT NULL,
  actor_id        UUID REFERENCES users(id),
  metadata        JSONB NOT NULL DEFAULT '{}',
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_app_timeline ON application_timeline_events(application_id, occurred_at ASC);
```

---

## 33. Account Preferences, Devices, And Security Events

### `user_preferences`
```sql
CREATE TABLE user_preferences (
  user_id         UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  locale          VARCHAR(5) NOT NULL DEFAULT 'vi',
  timezone        VARCHAR(100) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
  theme           VARCHAR(20) NOT NULL DEFAULT 'system',
  quiet_hours     JSONB NOT NULL DEFAULT '{}',
  notification_settings JSONB NOT NULL DEFAULT '{}',
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `security_events`
```sql
CREATE TABLE security_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type      VARCHAR(100) NOT NULL,
  -- 'login_success' | 'login_failed' | 'password_changed' | 'totp_enabled' | 'session_revoked'
  session_id      UUID REFERENCES sessions(id),
  device_hint     VARCHAR(200),
  ip_hash         VARCHAR(128),
  city_level_location VARCHAR(200),
  metadata        JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_security_events_user ON security_events(user_id, created_at DESC);
```

Session table rules:

- `sessions.device_hint` is a safe summary, not full raw user-agent.
- `sessions.ip_hash` may be added when needed; raw IP is not stored.
- Remote logout sets `revoked_at` and creates a security event.

---

## 34. Notification Preferences And Templates

### `notification_preferences`
```sql
CREATE TABLE notification_preferences (
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category        VARCHAR(100) NOT NULL,
  in_app_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
  email_setting   VARCHAR(20) NOT NULL DEFAULT 'immediate',
  -- 'off' | 'immediate' | 'daily' | 'weekly' | 'mandatory'
  push_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, category)
);
```

### `notification_templates`
```sql
CREATE TABLE notification_templates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_scope     VARCHAR(20) NOT NULL,  -- 'university' | 'partner'
  owner_org_id    UUID REFERENCES organizations(id),
  key             VARCHAR(150) NOT NULL,
  channel         VARCHAR(20) NOT NULL,  -- 'email' | 'in_app' | 'push'
  locale          VARCHAR(5) NOT NULL,   -- 'vi' | 'en'
  version         INT NOT NULL DEFAULT 1,
  status          VARCHAR(20) NOT NULL DEFAULT 'draft',
  -- 'draft' | 'active' | 'archived'
  subject         VARCHAR(500),
  title           VARCHAR(500),
  body            TEXT NOT NULL,
  variables_schema JSONB NOT NULL DEFAULT '{}',
  created_by      UUID NOT NULL REFERENCES users(id),
  activated_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(owner_scope, owner_org_id, key, channel, locale, version)
);
CREATE INDEX idx_notification_templates_active
  ON notification_templates(key, channel, locale)
  WHERE status = 'active';
```

### `notification_deliveries`
```sql
CREATE TABLE notification_deliveries (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
  channel         VARCHAR(20) NOT NULL,
  template_id     UUID REFERENCES notification_templates(id),
  status          VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'sent' | 'failed' | 'skipped'
  provider_message_id VARCHAR(300),
  error_code      VARCHAR(100),
  attempted_at    TIMESTAMPTZ,
  delivered_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(notification_id, channel)
);
```

---

## 35. Platform Trust — Consents, Privacy Requests, Content Reports (ADR-0014, E36)

Three new tables. `consents`/`privacy_requests` live in the new `compliance`
module; `content_reports` lives in `moderation` beside `human_review_queue`.
None use `BaseEntity` (no partner/university org-scoped soft-delete/version
semantics apply — these are append/current-state student- or
platform-integrity rows); each declares only the columns it needs, matching
the house pattern already used by `NotificationOutbox` / `HumanReviewItem` /
`ReviewReport` (plain PK + explicit `created_at`, no blanket `BaseEntity`).

### `consents`

Current-state row per `(user_id, consent_type)` — not an event log. Two fixed
consent types are enforced in code (`app.modules.compliance.domain.models`),
not DB-configurable in V1: `interview_recording`,
`career_outcomes_data_sharing`.

```sql
CREATE TABLE consents (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  consent_type VARCHAR(50) NOT NULL,       -- code-enforced vocabulary, not a DB enum
  granted      BOOLEAN NOT NULL DEFAULT FALSE,
  granted_at   TIMESTAMPTZ,
  revoked_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, consent_type)
);
CREATE INDEX idx_consents_user ON consents(user_id);
```

Every grant/revoke also writes an `audit_logs` row
(`action="compliance.consent_updated"`, `resource_type="consent"`,
`before_snapshot={"granted": ...}`, `after_snapshot={"granted": ...}`) — the
`consents` row itself is current-state only; the audit trail is the history.

### `privacy_requests`

Student-facing submit (`requested_by` = the subject in V1 self-service);
staff-facing list/fulfill gated by `privacy:process`. Admin fulfillment is
manual (queries existing tables) — no orchestrated auto-purge engine in V1.

```sql
CREATE TABLE privacy_requests (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_type   VARCHAR(20) NOT NULL,      -- 'export' | 'deletion'
  status         VARCHAR(20) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'processing' | 'fulfilled' | 'rejected'
  requested_by   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  processed_by   UUID REFERENCES users(id) ON DELETE SET NULL,
  note           TEXT,
  fulfilled_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_privacy_requests_requested_by ON privacy_requests(requested_by);
CREATE INDEX idx_privacy_requests_status ON privacy_requests(status, created_at DESC);
```

One open (`pending`/`processing`) request per `(requested_by, request_type)`
is enforced at the service layer (idempotent "already pending" response, not
a DB constraint — mirrors `review_service`'s duplicate-report handling)
because a student could legitimately file a new request after a prior one is
`fulfilled`/`rejected`.

### Retention Constants (not a table)

Hardcoded institutional constants documented in code
(`app.modules.compliance.domain.retention`) and surfaced as read-only text on
`/account/privacy`. V1 does **not** ship a DB-configurable
`retention_policies` table. Enforcement is a scheduled job (ADR-0003 pattern,
registered in `automation/scheduler/jobs.py`) that soft-deletes/anonymizes
`application_cv_snapshots` rows past the constant via the `documents` module's
snapshot facade — no direct cross-module ORM writes.

### `content_reports`

Generalizes `review_reports`' shape (§21) to any reportable entity. V1 scope
is `entity_type ∈ {company, job, message}` only — application and
ad-creative report buttons are deferred follow-ups (documented, not built).

```sql
CREATE TABLE content_reports (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type      VARCHAR(20) NOT NULL,   -- 'company' | 'job' | 'message' (V1)
  entity_id        UUID NOT NULL,          -- polymorphic; no FK (cross-module)
  reporter_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reporter_org_id  UUID,                   -- nullable; reporter's org context if acting as partner/university staff
  reason_code      VARCHAR(30) NOT NULL,
  note             TEXT,
  status           VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  -- 'PENDING' | 'TRIAGED' | 'DISMISSED' (pre-escalation triage state,
  -- distinct from human_review_queue.status on the escalated row)
  review_item_id   UUID REFERENCES human_review_queue(id) ON DELETE SET NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (reporter_id, entity_type, entity_id)
);
CREATE INDEX idx_content_reports_entity ON content_reports(entity_type, entity_id);
CREATE INDEX idx_content_reports_status ON content_reports(status, created_at DESC);
```

`UNIQUE (reporter_id, entity_type, entity_id)` makes a duplicate report from
the same reporter on the same entity an idempotent no-op
(`{"status": "already_reported"}`, mirroring `review_service.py`'s existing
`already_reported` pattern) rather than a second row — this is the primary
anti-spam control. In addition, `report_service.submit` must apply a
service-layer rate limit on **distinct-entity** report volume per reporter
per time window (e.g. max N reports across any entities per hour) so the
unique constraint alone cannot be defeated by reporting many different
entities in a burst.

### `human_review_queue.source` vocabulary extension

No migration. `source` is `String(32)` with no DB enum/CHECK constraint
(migration `0052_human_review_queue.py`). Two new code-level constants are
added to `app.modules.moderation.domain.models`:

```python
SOURCE_SUPPORT_CASE = "support_case"
SOURCE_USER_REPORT = "user_report"
```

`review_queue_service.list_items(source=...)` and the
`/moderation/review-queue?source=` filter already accept arbitrary strings —
no code change required there beyond exporting the two new constants in
`__all__` for other modules to import (mirrors `SOURCE_FRAUD` etc.).
`resource_type` for a `support_case` row is the entity the support agent is
acting on (`"user"` | `"organization"` | `"job"` ...); for a `user_report` row
it matches `content_reports.entity_type`.
```
