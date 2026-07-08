# API Contracts — VinUni Career Platform

> Phiên bản: 1.0 | Cập nhật: 26/06/2026  
> Source of truth for greenfield HTTP, SSE, error, auth, pagination, and event contracts.

## Base Rules

- Base path: `/api/v1`.
- JSON request/response by default.
- Broad APIs must satisfy `docs/PRODUCT_REALITY_REBUILD_SPEC.md`: define the
  real workflow, adjacent data/auth/notification/audit/AI/analytics contracts,
  and failure states before exposing a user-visible endpoint.
- Vietnamese primary user-facing labels, English secondary through i18n.
- End users receive friendly statuses, not raw enum codes.
- API schemas must not expose AI provider/model/token internals except
  superadmin-only AI operations/settings registry APIs. Ordinary university
  staff, partners, students, guests, exports, and notifications receive masked
  alias/status/budget fields only.
- Public API paths use plural nouns: `/organizations`, `/jobs`, `/events`, `/applications`.

## Auth And Identity

- Access token: short-lived JWT.
- Refresh token: secure rotation and revocation.
- Browser clients receive refresh tokens only through `HttpOnly`, `Secure`
  where HTTPS, `SameSite=Lax` cookies. Refresh tokens must not be returned in
  JSON bodies or stored in frontend localStorage/sessionStorage.
- Active identity is explicit for multi-identity users.
- Protected service methods enforce permissions at service layer.
- Unauthenticated: `401`.
- Authenticated but missing permission: `403`.
- Unauthorized resource discovery risk: return `404` for hidden job/event details when enumeration prevention is required.

### MFA / TOTP Login Contract

If a user has TOTP enabled or the active identity requires TOTP, login returns a
short-lived MFA challenge instead of a full session:

```json
{
  "data": {
    "totp_required": true,
    "challenge_token": "signed-short-lived-token"
  }
}
```

`POST /api/v1/auth/login/totp`

```json
{ "challenge_token": "...", "code": "123456" }
```

On success, the backend sets the refresh cookie and returns the access-token
envelope. TOTP secrets are encrypted at rest. If TOTP is not enforced end to
end, the UI must not present it as active account protection.

### Password Reset & Verification Resend

All endpoints below are **unauthenticated** and **anti-enumerating**: the
response is identical whether or not the email maps to an account, so they never
reveal account existence or verification state. Errors use the standard envelope
(`docs/API_CONTRACTS.md` error families); machine hints go in `details.reason`.

Reset tokens are single-use, hashed at rest, and expire after
`PASSWORD_RESET_TTL_MINUTES` (default 60). A successful reset revokes **all** of
the user's sessions and refresh tokens and records a `password_reset` security
event + audit entry. Emails are dispatched only via the notification outbox
(`account.password_reset`, `account.password_changed`, `account.email_verification`)
with links to the **frontend** app, locale-scoped, e.g.
`http://localhost:3000/{locale}/auth/reset-password?token=...`.

Both password reset and email verification support two completion modes, sent
in the same email: a magic **link** (`token`) and a 6-digit **OTP** code, sharing
one underlying `email_verifications` record per issuance:

- `POST /auth/reset-password/otp` — `{ "email": "...", "otp_code": "123456", "password": "NewSecret123!" }` → same
  `200`/error shape as `POST /auth/reset-password`, plus `otp_max_attempts` (default 3)
  wrong-code lockout forcing a fresh resend; reason `otp_wrong:{remaining}` while
  attempts remain, `otp_max_attempts` once exhausted.
- `POST /auth/verify-email/otp` — `{ "email": "...", "otp_code": "123456", "purpose": "register" | "student_email" }` →
  `200 { "data": { "email": "...", "email_verified": true } }`; same OTP attempt-lockout
  behavior as above (`otp_expired`, `otp_invalid`, `otp_max_attempts`, `otp_wrong:{remaining}`).
- `POST /auth/activate` — `{ "token": "...", "password": "NewSecret123!" }`. Passwordless-account
  activation (e.g. an approved partner-admin invite): sets the first password and verifies the
  email in one step. Only valid while the account has no password set yet.

**Resend cooldown and rate limiting.** `POST /auth/forgot-password`,
`POST /auth/verify-email/resend`, and a duplicate `POST /auth/register` against a
pending (unverified) email (see below) are throttled **by the normalized email
address itself**, independent of whether an account exists for it — this keeps
the 429 behavior identical for known and unknown emails, preserving
anti-enumeration. Two limits apply per `(scope, email)`:

- **Cooldown**: `AUTH_RESEND_COOLDOWN_SECONDS` (default 60) minimum gap between
  two triggers.
- **Rolling hourly cap**: `AUTH_EMAIL_REQUEST_RATE_LIMIT_PER_HOUR` (default 5).

Either limit hit → `429 RATE_LIMITED`:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "...",
    "details": { "reason": "resend_cooldown", "retry_after_seconds": 42 },
    "request_id": "req_..."
  }
}
```

`details.reason` is `resend_cooldown` (too soon since the last request) or
`rate_limited` (hourly cap reached); both carry `retry_after_seconds`.

**Pending-verification resume.** `POST /auth/register` with an email that
already exists but is **not yet verified** (an abandoned/retried signup) does
NOT return `409 CONFLICT`. It resumes the pending account: the submitted
password overwrites the unverified account's password, prior outstanding
verification tokens are invalidated, and a fresh verification email is enqueued
(subject to the resend cooldown/rate limit above — if throttled, the same
generic `202 { "status": "verification_sent" }` response is still returned, no
new email is sent, and no error is surfaced, so retry-spam stays invisible to
the caller). A **verified** existing email still returns
`409 CONFLICT { "reason": "email_already_registered" }` unchanged.

Registration collects only identity credentials: `email`, `password`, and
client-side `confirm_password` (not persisted). `full_name`, phone, avatar,
education, student/employer profile details, and CV facts are collected later
through onboarding/profile/CV flows or confirmed extraction. Notification
templates for verification/reset must therefore not require a user name.

#### `POST /auth/forgot-password`

Request:

```json
{ "email": "student@vinuni.edu.vn" }
```

Response `200` (always, regardless of account existence):

```json
{ "data": { "status": "reset_email_sent", "email": "student@vinuni.edu.vn" } }
```

If the email maps to a real active account, prior outstanding reset tokens are
invalidated, a new single-use reset token is issued, and an
`account.password_reset` email is enqueued. Otherwise nothing is sent.

#### `POST /auth/reset-password`

Request:

```json
{ "token": "<opaque-reset-token>", "password": "NewSecret123!" }
```

Response `200`:

```json
{ "data": { "status": "password_reset" } }
```

Invalid / expired / already-used token → `400` `VALIDATION_FAILED` with
`details.reason` in `{ reset_invalid, reset_expired, reset_used }`:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Liên kết không hợp lệ hoặc đã hết hạn. Vui lòng yêu cầu lại.",
    "details": { "reason": "reset_used" },
    "request_id": "req_..."
  }
}
```

On success: new Argon2 password is set, the token is marked used, every session +
refresh token is revoked (old refresh tokens then return `401`), a `password_reset`
security event + audit are written, and an `account.password_changed` confirmation
email is enqueued.

#### `POST /auth/verify-email/resend`

Request:

```json
{ "email": "student@vinuni.edu.vn" }
```

Response `200` (always):

```json
{ "data": { "status": "verification_sent", "email": "student@vinuni.edu.vn" } }
```

If an **unverified** account exists, prior outstanding verification tokens are
invalidated and a fresh `account.email_verification` email is enqueued. For
unknown or already-verified emails nothing is sent (no behavioural oracle).

### OAuth Account Linking (Google, Facebook)

`oidc_accounts` (`docs/DATA_MODEL.md` §4) links a `user` to a third-party
identity provider. Flow is redirect-based; the frontend never handles a
provider access/id token directly.

1. `GET /auth/oauth/{provider}/start?mode=login|register&return_to=...` —
   `provider` is `google` or `facebook`. `302` redirect to the provider's
   consent screen; sets a short-lived httpOnly nonce cookie for CSRF
   double-submit. `400 VALIDATION_FAILED { "reason": "oauth_not_configured" }`
   if the provider's client id/secret are not configured.
2. `GET /auth/oauth/{provider}/callback?code=...&state=...` — provider
   redirect target. Never returns JSON to the browser; always `302`s to a
   **frontend** page:
   - Success (existing linked account, or a new/auto-linkable account) →
     `{frontend_url}/{locale}/auth/oauth/callback?ticket=<one-time-ticket>`.
   - Conflict (the OAuth email matches an existing account that already has a
     password set, with no link yet for this provider) →
     `{frontend_url}/{locale}/auth/oauth/link-conflict?ticket=<link-ticket>&email=...`.
     No `oidc_accounts` row is created until the user confirms with their
     password; an `account.oauth_conflict` email is sent to the account owner
     regardless, so an unattempted hijack attempt is still visible to them.
   - Hard failure → `{frontend_url}/{locale}/auth/login?error=oauth_failed`
     (no provider/internal error detail in the URL).
   A verified-by-provider email with no existing account creates a new user
   (`email_verified_at` set immediately) and identity. An existing account with
   **no password set** (SSO-only/invited) auto-links without a confirmation
   step and sends `account.oauth_linked`. An email the provider does not report
   as verified is rejected (`400 VALIDATION_FAILED { "reason": "oauth_email_unverified" }`),
   never creating or linking an account.
3. `POST /auth/oauth/exchange` — `{ "ticket": "..." }` → same success envelope
   as `POST /auth/login` (refresh cookie set, access-token payload + user).
   Tickets are short-lived (~2 minutes) and single-use.
4. `POST /auth/oauth/link-confirm` — `{ "ticket": "...", "password": "..." }` →
   same success envelope as above on a correct password; `401 AUTH_REQUIRED`
   (uniform, no enumeration signal) on a wrong password or expired ticket.
   Only on success is the `oidc_accounts` row created.

## Standard Response Shapes

```json
{
  "data": {},
  "meta": {}
}
```

For lists:

```json
{
  "data": [],
  "page": {
    "next_cursor": null,
    "limit": 20
  }
}
```

For errors:

```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Bạn không có quyền thực hiện thao tác này.",
    "details": {},
    "request_id": "req_..."
  }
}
```

## Error Code Families

- `AUTH_REQUIRED`
- `PERMISSION_DENIED`
- `RESOURCE_NOT_FOUND`
- `VALIDATION_FAILED`
- `CONFLICT`
- `RATE_LIMITED`
- `QUOTA_EXCEEDED`
- `PAYMENT_REQUIRED`
- `AI_UNAVAILABLE`
- `INTERNAL_ERROR`

## Pagination And Filtering

- Cursor pagination for mutable lists.
- Offset pagination only for small admin/static lookup lists.
- Filters must be explicit and RBAC-aware.
- Job/event search counts reflect only visible records.

## Idempotency

Required for:

- application submit
- withdrawal
- payment/manual payment confirmation
- event registration
- seat lock/confirm
- AI write tool execution
- webhooks

Use `Idempotency-Key` or server-generated operation IDs where appropriate.

## API Path Defaults

| Domain | Paths |
|---|---|
| Auth | `/auth/register`, `/auth/verify-email`, `/auth/verify-email/otp`, `/auth/verify-email/resend`, `/auth/activate`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/reset-password/otp`, `/auth/login`, `/auth/login/totp`, `/auth/refresh`, `/auth/logout`, `/auth/me`, `/auth/identity`, `/auth/oauth/{provider}/start`, `/auth/oauth/{provider}/callback`, `/auth/oauth/exchange`, `/auth/oauth/link-confirm` |
| Account settings | `/account/preferences`, `/account/security-events`, `/account/sessions` |
| Organizations | `/organizations`, `/organizations/roles`, `/organizations/departments`, `/organizations/members` |
| Jobs | `/jobs`, `/jobs/{job_id}`, `/jobs/{job_id}/applications`, `/jobs/{job_id}/pipeline` |
| Applications | `/applications`, `/applications/{application_id}`, `/applications/{application_id}/withdraw` |
| Candidate pipeline | `/applications/{application_id}/advance`, `/applications/{application_id}/rollback`, `/applications/{application_id}/reject` |
| Scorecards | `/applications/{application_id}/scorecards` (POST/GET), `/applications/{application_id}/scorecards/{scorecard_id}/withdraw` |
| Interviews | `/applications/{application_id}/interviews` (POST/GET), `/applications/{application_id}/interviews/{interview_id}` (PATCH), `/applications/{application_id}/interviews/{interview_id}/assignees` (PUT), `/applications/{application_id}/interviews/{interview_id}/cancel` (POST), `/applications/{application_id}/interviews/{interview_id}/complete` (POST) |
| Offers | `/applications/{application_id}/offers` (POST/GET), `/applications/{application_id}/offers/{offer_id}` (PATCH), `/offers/{offer_id}/submit` (POST), `/offers/{offer_id}/approve` (POST), `/offers/{offer_id}/send` (POST), `/offers/{offer_id}/rescind` (POST), `/offers` (GET, student), `/offers/{offer_id}` (GET, student), `/offers/{offer_id}/respond` (POST, student) |
| CVs | `/cvs`, `/cvs/job-fit`, `/cvs/{cv_id}`, `/cvs/{cv_id}/canvas`, `/cvs/{cv_id}/ai-edit-command`, `/cvs/{cv_id}/duplicate`, `/cvs/{cv_id}/sections`, `/cvs/{cv_id}/sections/{section_id}`, `/cvs/{cv_id}/versions`, `/cvs/{cv_id}/versions/{version_id}/restore`, `/cvs/{cv_id}/parse`, `/cvs/{cv_id}/signed-url`, `/cv-templates`, `/admin/cv-templates`, `/cv-exports/{export_id}` |
| Events | `/events`, `/events/{event_id}`, `/events/{event_id}/register`, `/events/{event_id}/online-link` |
| AI assistant | `/ai-assistant/sessions`, `/ai-assistant/sessions/{session_id}/messages`, `/ai-assistant/stream` |
| AI settings | **(V1 — IMPLEMENTED, ADR-0011)** `/admin/ai-settings` (GET/PATCH), `/admin/ai-settings/disable-ai` (POST). The `/ai-settings/providers`, `/ai-settings/task-models`, `/ai-settings/health` split is the deferred multi-row end-state. |
| Reporting/export | `/exports`, `/exports/{export_id}`, `/dashboards/{persona}` |
| Notifications | `/notifications`, `/notification-preferences`, `/notification-templates` |

## Jobs (Opportunities) Contracts

Phase 1c. Implemented by the `opportunities` module. RBAC + tenant isolation are
enforced at the service layer; routers are HTTP-only. Enum codes are always paired
with a localized `*_label`; public responses never leak moderation notes,
moderation status, the poster, or internal lifecycle fields.

### Job lifecycle (state machine)

`status`: `draft → pending_review → active → closed` with `rejected` and
`expired` branches. Legal transitions only (illegal → `409 CONFLICT`,
`details.reason = illegal_transition`):

- `submit`: `draft | rejected → pending_review` (re-enters moderation fresh)
- `approve` (university): `pending_review → active` (publishes)
- `reject` (university): `pending_review → rejected`
- `close` (partner): `active → closed`
- `reopen` (partner): `closed → active` (only if still moderation-approved and
  deadline not passed)

`moderation_status`: `pending | approved | rejected | flagged`. A job is publicly
visible only when `status = active`, `moderation_status = approved`,
`published_at` set, deadline not passed, and its `visibility` tier matches the
caller. Soft delete allowed in `draft|rejected|closed|expired`.

**Post-publication amendment policy (B-552):** editing is allowed in
`draft`/`rejected` (any field) **and** in `active` under a field-bucket policy —
other statuses (`pending_review`/`closed`/`expired`) remain fully locked (`409`,
`details.reason = not_editable`). For an `active` job:

- **Free-amend fields** (`application_deadline`, `headcount`, `visibility`,
  `benefits`) apply immediately; the job stays `active`/published.
- **Re-moderation fields** (`title`, `description`, `requirements`,
  `employment_type`, `location_*`, `required/preferred_skills`,
  `experience_*`, `industry_id`, `degree_required`, `seniority_level`,
  `candidate_requirements`, `salary_*`) push the job back to `pending_review`
  (unpublished pending re-approval).
- **Locked field**: `screening_questions` cannot be edited once a job is
  `active` (`409`, `details.reason = screening_locked_after_publish`) —
  protects existing `applications.screening_answers` from drifting out of
  sync with answered questions.

Every amendment writes an audit row with an old/new value diff;
re-moderation amendments additionally note
`reason = content_amendment_requires_remoderation`.

**JD quality gate:** `submit` runs a deterministic, rule-based quality check
(`GET /jobs/{job_id}/quality-check` exposes the same rubric as a preview) and
blocks on any `blocking`-severity issue (`422`, `details.issues`); `advisory`
issues are reported but do not block submission.

**Preview:** `GET /jobs/{job_id}/preview?as=guest|student` (`jobs:read`, owner
only) renders the exact guest/student projection of a job pre- or
post-publish without actually publishing it, reusing the public job detail
serialization.

### Visibility matrix enforcement

`visibility` ∈ `public | authenticated | students_only | vinuni_only |
invitation_only` (`docs/BUSINESS_LOGIC.md` §5). Discovery is filtered at the DB
query layer by the caller's persona tier; `invitation_only` requires a per-job
allow-list (later phase) and is never returned by the generic public filter.

### Public discovery query contract

`GET /jobs` filters use canonical IDs and structured modes, never display-only
labels. Category filters accept one deepest selected scope at a time
(`industry_group_id`, `industry_id`, or `specialization_id`). A parent scope
matches descendants; a child/specialization narrows to that exact subtree and
must not be OR-expanded with its parent. Location filters accept canonical
province/district/ward IDs and may be multi-select. Salary and experience
filters use structured modes from `docs/DATA_MODEL.md` rather than parsing
localized strings such as `30 - 60 triệu` or `Không yêu cầu`.

Implemented param names (B-544/B-545): `industry_group_id` (level-0, matches
descendants), `industry_id` (level-1, matches its level-2 children only),
`specialization_id` (level-2, exact match, no expansion) — mutually exclusive,
`422` if more than one is given or the id/level don't match the slot. The
deprecated free-text `industry_terms` still works when none of the three are
given. `salary_mode` (`negotiable | hidden | fixed | range | from | to`) and
`experience_mode` (`no_requirement | fresher | range | min | max`) are the job
create/update body fields backing the salary/experience filters and the
`salary_display`/`experience_display` response projections.

### Endpoints

| Path | Method | Auth | Notes |
|---|---|---|---|
| `/jobs` | GET | Guest or any | **Public discovery.** RBAC-aware; returns only visible/published jobs. Cursor pagination; `page.total` reflects visible-only count. |
| `/jobs/mine` | GET | `jobs:read` | **Partner-scoped** list of the caller org's own jobs (all statuses); `?status=` filter; cursor pagination. |
| `/jobs/{job_id}` | GET | Guest or any | Owner (same org + `jobs:read`) → full detail incl. moderation/screening; otherwise public detail iff visible, else `404` (enumeration hiding). |
| `/jobs` | POST | `jobs:create` | Create a `draft` (org-scoped). |
| `/jobs/{job_id}` | PATCH | `jobs:update` | Edit `draft`/`rejected` (any field) or `active` (amendment-policy field buckets, see above); optimistic `version`. |
| `/jobs/{job_id}/quality-check` | GET | `jobs:read` | JD quality-rubric preview (`passed`, `issues[]`). |
| `/jobs/{job_id}/preview` | GET | `jobs:read` | `?as=guest\|student` pre-publish/post-publish preview projection. |
| `/jobs/{job_id}/submit` | POST | `jobs:submit` | `draft|rejected → pending_review`; blocks on JD quality-gate `blocking` issues. |
| `/jobs/{job_id}/close` | POST | `jobs:publish` | `active → closed`. |
| `/jobs/{job_id}/reopen` | POST | `jobs:publish` | `closed → active`. |
| `/jobs/{job_id}` | DELETE | `jobs:delete` | Soft delete/archive. |
| `/admin/jobs` | GET | `jobs:moderate` + **university org / superadmin** | Moderation queue (default `pending_review`); `?status=`. |
| `/admin/jobs/{job_id}/approve` | POST | `jobs:moderate` + university/superadmin | Approve + publish; notifies partner via outbox. Idempotent. |
| `/admin/jobs/{job_id}/reject` | POST | `jobs:moderate` + university/superadmin | `{ "reason": "..." }` → `rejected`; notifies partner via outbox. |

**Moderation gate:** mirrors partner approval (ADR-0002 §4.1/§5.2). A partner
Admin holds `*:*` which would match `jobs:moderate`, so the org-type gate keeps
moderation **university-only** (`403`, `details.reason = university_only`); a
partner can never moderate its own jobs.

**Design note (deviation):** `docs/API_CONTRACTS.md` listed `/jobs` once. To avoid
overloading one route by principal, public discovery is `GET /jobs` and the
partner management list is `GET /jobs/mine` — the cleaner unambiguous design.

**Data-model additions (`docs/DATA_MODEL.md` §8):** added `jobs.visibility`
(first-class column for the §5 matrix) and `jobs.submitted_at`; rejection reason is
stored in the canonical `moderation_note`. Notification templates added:
`job.approved`, `job.rejected` (vi + en).

**Public job projection requirement:** public list/detail responses must include
a safe organization display projection (`organization.id`, `organization.slug`,
`organization.display_name`, `organization.logo_url`, `organization.is_verified`,
`organization.trust_level`) or equivalent `org_name` fallback. Do not expose
private partner notes, registration documents, billing state, internal contacts,
or moderation fields. Public discovery must hide jobs whose organization is
suspended, deleted, or not approved.

### Events, Registration & Check-in Contracts (ADR-0008, V1 free-admission)

Events live in the `opportunities` module alongside jobs (separate `events` table
+ lifecycle). V1 is **free single-admission**: capacity is one nullable number on
the event (`null` = unlimited); ticketing/seats/QR/payment/online-link reveal are
deferred. All routes are under `/api/v1`.

**Event lifecycle (`events.status`):** `draft → pending_review → published`,
`published → cancelled`, `published → completed` (scheduler when `ends_at` passes),
`pending_review → rejected → (resubmit) → pending_review`. Raw codes never reach
users — every code has a vi+en label (`status_label`/`event_type_label`/
`format_label`/`registration_state_label`). `event_type ∈ {career_fair, workshop,
info_session, networking, webinar}`; `format ∈ {onsite, online, hybrid}`.

| Route | Method | Auth / Permission | Notes |
| --- | --- | --- | --- |
| `/events` | GET | public (RBAC-aware) | Discovery; cursor-paginated, `?q=&event_type=&format=`. Visible = `published` + `approved` + `ends_at > now` + tier. Ordered soonest-first. `page.total` = visible-only. |
| `/events/{id}` | GET | public (RBAC-aware) | Owner/moderator → full detail; else public detail iff visible, else `404`. Public detail strips moderation/internal fields; exposes `cover_image_url` only (never a raw path). |
| `/events/mine` | GET | `events:read` (org member) | Caller-org events, any status; `?status=`. |
| `/events` | POST | `events:create` (owning org) | Create `draft`. |
| `/events/{id}` | PATCH | `events:update` | Edit `draft`/`rejected` only; optimistic `version` → `409 version_conflict`; other states → `409 not_editable`. |
| `/events/{id}/submit` | POST | `events:submit` | `draft/rejected → pending_review` (**partner**) or `→ published` (**university auto-approve**, PRD §14.9). |
| `/events/{id}/cancel` | POST | `events:manage` | `published → cancelled`; fans out a neutral cancellation notice to confirmed + waitlisted registrants. |
| `/events/{id}` | DELETE | `events:manage` | Soft-delete `draft/rejected/cancelled/completed` (a `published` event must be cancelled first). |
| `/events/{id}/register` | POST | `events:register` (auth) | → `confirmed` \| `waitlisted`. Guest → `401`; past deadline → `409 registration_closed`; not yet open → `409 registration_not_open`; cancelled/completed → `409 event_not_open`; not visible → `404`. Idempotent for an existing active registration. |
| `/events/{id}/register` | DELETE | `events:register` | Cancel my registration; inline-promotes the FIFO waitlist head. No active registration → `409 not_registered`. |
| `/events/registrations/mine` | GET | `events:register` | "My Events": active registrations + state + `waitlist_position`. |
| `/events/{id}/registrations` | GET | organizer (`events:manage`, owning org) **or** university (`events:moderate`) | Attendee list. **Email only in the owning-organizer view**; university sees the list without email. Cross-org → `404`. |
| `/events/{id}/registrations/{rid}/check-in` | POST | organizer / university (as above) | `confirmed → attended`; idempotent. Non-staff / cross-org → `404`. |
| `/admin/events` | GET | `events:moderate` + **university org / superadmin** | Moderation queue (default `pending_review`); `?status=`. |
| `/admin/events/{id}/approve` | POST | `events:moderate` + university/superadmin | `pending_review → published`; notifies organizer (outbox + feed). Idempotent. |
| `/admin/events/{id}/reject` | POST | `events:moderate` + university/superadmin | `{ "reason": "..." }` → `rejected` (`422` if blank); notifies organizer. Idempotent. |

**Capacity / waitlist / concurrency.** Registration runs the live
`COUNT(status='confirmed')` check + insert under an event-row `SELECT … FOR UPDATE`
(Postgres; dialect-guarded — SQLite tests rely on the single-writer service guard).
A partial unique index `uq_event_reg_active (event_id, user_id) WHERE status <>
'cancelled'` is the duplicate safety net and lets a *cancelled* user re-register.
A full event waitlists FIFO; on cancel of a `confirmed` seat the FIFO head is
promoted **inline** in the same transaction, with a scheduler `events.waitlist_backfill`
safety net. `registration_count` is a denormalized display mirror; the
authoritative capacity check is the locked live count.

**Attendee-list PII guarantee (ADR-0008 §3, SECURITY_PRIVACY).** Attendee email is
shown **only** to the owning organizer (for legitimate event comms), never to
university staff, other registrants, or guests, and **never** appears in logs or
audit snapshots — registration audit `after` snapshots carry only `event_id` +
`user_id` + `registration_id` + `status`. The recruitment anonymity/reveal
handshake does **not** apply to events.

**Moderation gate.** Same org-type gate as jobs: a partner Admin's `*:*` cannot
self-approve (`403`, `details.reason = university_only`); university-created events
auto-publish on submit.

**Notifications (category `event`, vi+en, allowlisted variables only).** In-app +
outbox: `event.registration_confirmed`, `event.registration_waitlisted`,
`event.waitlist_promoted`, `event.reminder` (T-24h sweep, deduped
`event.reminder:{event_id}:{user_id}`), `event.cancelled`; organizer-facing
`event.approved` / `event.rejected`. Online/hybrid reminders carry an in-app
access **pointer**, never a raw link.

**Scheduler jobs (ADR-0003).** `events.reminder_sweep` (~300s, T-24h),
`events.waitlist_backfill` (~300s), `events.auto_complete` (~600s, `ends_at < now`),
`events.no_show_sweep` (~600s, ended + grace → `no_show`). All idempotent.

**Marketplace overview.** `GET /marketplace/overview` adds `upcoming_events`,
`sponsored_events`, `featured_events`, sourced **only** through the events
public-read facade (no cross-module ORM). Each array is empty (section hides) when
nothing qualifies; sponsored/featured come from the real `is_sponsored`/
`is_featured` flags, never fabricated.

### Application Decision Status (partner) — Phase 1.5 subset

The full configurable multi-round pipeline (stages, scorecards, score thresholds,
auto-advance; `BUSINESS_LOGIC.md` §3) and its `/applications/{id}/advance` /
`/rollback` endpoints remain **Phase 2** (stage engine). The Phase-1.5 subset
below ships the minimal real decision loop a recruiter needs and closes the
student's outcome notification gap, reusing the existing `applications` columns
(`status`, `rejection_reason`, `rejection_note`, `last_status_at`, `version`) —
no migration.

Application `status` (decision subset): `submitted → under_review → rejected`,
plus the student-driven `withdrawn`. `under_review` is still an ACTIVE status
(occupies the single active slot); `rejected`/`withdrawn` are terminal/inactive.

| Path | Method | Auth | Notes |
|---|---|---|---|
| `/applications/{id}/review` | POST | partner member of the job's org (same authz as reveal) + optimistic `version?` | `submitted → under_review`. Idempotent (already under_review → 200 no-op). Illegal from `rejected`/`withdrawn` → `409`. Cross-org → `404`. Audited (`application.reviewed`). Notifies the student (`recruitment.application_under_review`). |
| `/applications/{id}/reject` | POST | partner member of the job's org + `version?` | Body `{ "reason": <code>, "note"?: <text> }`. `{submitted,under_review} → rejected`; sets `rejection_reason`+`rejection_note`+`last_status_at`. `reason` REQUIRED (coded enum `not_qualified|experience_mismatch|position_filled|incomplete|other`; missing → `422`). Idempotent if already rejected. Illegal from `withdrawn` → `409`. Cross-org → `404`. Audited (`application.rejected`, reason in audit metadata). Notifies the student (`recruitment.application_rejected`). |

**Student-facing copy is neutral.** The status-change notification and the
student application detail expose only the localized status label (e.g. "Đang
xem xét" / "Không phù hợp") — never the internal `rejection_reason` code or the
partner's `rejection_note` (those stay org-internal until/unless a "share
feedback" feature is designed). Partner/owner application projections DO expose
`rejection_reason`/`rejection_note`/`last_status_at`. Anonymity is preserved: a
status change never reveals the student's identity to the partner, and the
student notification reveals only the company/job they already applied to.

New notification types (catalog, vi+en): `recruitment.application_under_review`,
`recruitment.application_rejected` (category `application_status`).

### Pipeline Stage Engine (partner) — ADR-0004 first slice

The configurable stage engine ships its foundational layer (ADR-0004 §6):
`pipeline_templates` / `pipeline_stages` (one immutable system-default 3-stage
ladder Screening → Interview → Offer seeded per org) + `candidate_stages` (the
append-only stage history, one `ACTIVE` row per application). The fine pipeline
position lives in `candidate_stages`; `applications.status` stays the coarse
outcome (`under_review` ≡ "active in the pipeline") and is **unchanged**. The
template-builder UI, scorecard/score-threshold `required_action` gating, interviews,
offers, auto-advance, and bulk moves are deferred to later ADRs.

| Path | Method | Auth | Notes |
|---|---|---|---|
| `/applications/{id}/advance` | POST | partner member of the job's org (same authz as review/reject) + optimistic `version?` + optional `Idempotency-Key` header | Moves the active `candidate_stages` row to the next stage by `sort_order` (current row → `PASSED`; new `ACTIVE` row at N+1). Requires `applications.status = under_review` (else `409`); advance past the last stage → `409`. **Scorecard gate (ADR-0005 + ADR-0006):** when the current stage's `required_action = scorecard`, advance is blocked until the gate's submitted-count is met → `409 { reason: "scorecard_required", submitted, required }`. `required` is **assignee-derived** (ADR-0006): the count of assigned interviewers on the stage's open interview when one exists (**all assigned interviewers must submit**), else the fallback `1`; only **assignee** scorecards count toward `submitted`. **`score_threshold` gate (ADR-0006):** the same assignee-count gate first, THEN the average gate — once all assignees have submitted, if `mean(overall_score) < stage.score_threshold` → `409 { reason: "score_below_threshold", avg_overall, threshold }`. A `manual` stage is the trivial allow (unchanged); an unknown action stays fail-closed (`409 illegal_transition`). Bumps `applications.version`. Cross-org → `404`. Audited (`application.stage_advanced`). Notifies the student (`recruitment.application_stage_advanced`) only when the target stage is `candidate_visible` — neutral copy. `Idempotency-Key` dedupes a true retry. |
| `/applications/{id}/rollback` | POST | partner member of the job's org + `version?` + optional `Idempotency-Key` header | Body `{ "target_stage_id": <uuid>, "reason": <text ≥ 20>, "version"?: <int> }`. Moves the active row back to a STRICTLY prior stage of the SAME template (current row → `ROLLED_BACK`; new `ACTIVE` row at the target). `reason` REQUIRED, min 20 chars (`422`), partner-internal — **never sent to the student**. Target not a prior stage of the same template → `409`. Max 3 rollbacks per application; the 4th → `409` (`reason: "rollback_limit"`, university-admin approval deferred). Bumps `version`. Cross-org → `404`. Audited (`application.stage_rolled_back`, reason in metadata only). Notifies the student (`recruitment.application_under_rereview`, neutral). |

The partner application projection (detail + advance/rollback responses) carries a
`pipeline` block: `{ template_id, current_stage{ id,name,stage_type,sort_order,
is_terminal,candidate_visible,required_action }, position, total_stages,
rollback_count, evaluation, interview, stages[] }`. The partner-only `evaluation`
summary (ADR-0005 + ADR-0006, current stage): `{ submitted_count, required,
gate_met, avg_overall, threshold, recommendation_summary }` (`required`
assignee-derived). The partner-only `interview` block (ADR-0006, current stage —
`null` when no open interview): `{ id, mode, scheduled_at, status, assignee_count }`
— **no `meeting_link`** (attendee-only). **Anonymity is non-negotiable:** a stage move never
reveals the student — the reveal handshake stays the only identity path; the
`pipeline` block (including `evaluation`) is partner-internal and **never** appears
in the student application projection, a student notification, or any email body.
New notification types (catalog, vi+en, category `application_status`):
`recruitment.application_stage_advanced`, `recruitment.application_under_rereview`.

#### Scorecards (partner-internal evaluation; ADR-0005)

A scorecard is ONE partner reviewer's evaluation of ONE candidate at ONE pipeline
stage: a fixed V1 criteria set `{ technical, communication, culture_fit, motivation }`
each scored `1..5`, a derived `overall_score` (mean), a required 4-value
`recommendation ∈ { strong_no, no, yes, strong_yes }`, and an optional
partner-internal `comment`. Scorecards are the same privacy class as
`rejection_reason`: **partner-internal, never surfaced to the student** (existence,
scores, recommendation, comment, aggregate). A scorecard carries **no
student-identity field**; the reveal handshake stays the only identity path.

| Path | Method | Auth | Notes |
|---|---|---|---|
| `/applications/{id}/scorecards` | POST | partner member of the job's org (`recruitment:submit_scorecard`) | Body `{ "recommendation": <code>, "scores": [{ "criterion_key", "score": 1..5 }], "comment"?: <text>, "version"?: <int> }`. Submit / **upsert** the caller's scorecard for the candidate's CURRENT ACTIVE stage (one ACTIVE per `(application, stage, reviewer)`). `recommendation` REQUIRED + every `DEFAULT_CRITERIA` key present with `score ∈ 1..5`, else `422`. App not `under_review` / no ACTIVE stage → `409 illegal_transition`. Re-submit edits in place, bumps the per-scorecard `version` (stale `version` → `409`), recomputes `overall_score`. Cross-org → `404`. Audited (`application.scorecard_submitted` / `…_updated`). Returns the anchoring-safe stage payload (below). |
| `/applications/{id}/scorecards` | GET | partner member (`recruitment:read_scorecard`); optional `?stage_id=` (default: current stage) | Returns `{ stage_id, mine, scorecards[], aggregate, criteria[] }`. **Anchoring (BUSINESS_LOGIC §3.4):** `mine` always; OTHER reviewers' scorecards (`scorecards[]`) and the score-derived aggregate fields (`avg_overall`, `recommendation_summary`, `by_criterion`) appear **only after the caller has submitted their own** for that stage — before then only `{ submitted_count, required, gate_met }` is exposed. Cross-org → `404`. |
| `/applications/{id}/scorecards/{scorecard_id}/withdraw` | POST | **author only** (else `404`) | `status → withdrawn` (soft; row retained for audit, excluded from the gate + every aggregate). Audited (`application.scorecard_withdrawn`). Returns the stage payload. |

`aggregate`: `{ submitted_count, required, gate_met, avg_overall,
recommendation_summary{ strong_no,no,yes,strong_yes }, by_criterion{ <key>: <avg> } }`.
A scorecard item: `{ id, stage_id, reviewer_id (partner member, not the student),
is_mine, recommendation, recommendation_label, overall_score, scores[], comment,
status, version, submitted_at, updated_at }`.

`review` and `reject` integrate with the engine: `review` (`submitted →
under_review`) now also lazily materializes the stage-1 `candidate_stages` row;
`reject` additionally closes the open stage row (`status = REJECTED`). Both shipped
contracts are otherwise unchanged.

#### Interviews (partner-internal; ADR-0006)

An interview is ONE editable-in-place scheduled round for an application at its
CURRENT ACTIVE pipeline stage (the round IS the stage; the interview carries only a
delivery `mode ∈ { onsite, online, phone }`), with an explicit list of assigned
interviewers (PERSON mode, `threshold_pct = 1.0` — **all assigned interviewers must
submit a scorecard**, the upgraded advance gate's `required`). At most ONE OPEN
(`scheduled`) interview per `(application, stage)`.

**Reveal precondition (NON-NEGOTIABLE):** scheduling an interview on an **anonymous**
application whose reveal has **not** been accepted → `409 { reason: "reveal_required" }`.
The reveal handshake stays the only identity path; the student's consent is never
silently bypassed. Non-anonymous (or anonymous + accepted reveal) schedules freely.

**`meeting_link` is Fernet-encrypted at rest and decrypted ONLY for attendees** (the
candidate + assigned interviewers). It is **absent** from the board glance and every
non-attendee/student surface; a non-attendee partner member's interview view carries
`meeting_link: null`.

| Path | Method | Auth | Notes |
|---|---|---|---|
| `/applications/{id}/interviews` | POST | partner member (`recruitment:schedule_interview`) | Body `{ mode, scheduled_at, duration_minutes?, location?, meeting_link?, assignee_ids:[uuid], title?, notes? }`. Schedule the candidate's CURRENT-stage interview. **Anonymous + no accepted reveal → `409 reveal_required`.** App not `under_review` / no ACTIVE stage → `409 illegal_transition`. A second open interview for the stage → `409 { reason:"interview_exists" }`. `assignee_ids` must be ACTIVE members of the job's org (else `422`); `online` requires `meeting_link`, `onsite` requires `location` (else `422`). Encrypts `meeting_link`. Cross-org → `404`. Audited (`application.interview_scheduled`). Notifies the candidate (`recruitment.interview_scheduled`) + assigned interviewers (`recruitment.interview_assigned`). |
| `/applications/{id}/interviews` | GET | partner member (`recruitment:manage_interview`) | `{ application_id, interviews:[ <interview view> ] }` (partner-internal). `meeting_link` is decrypted only when the caller is an attendee of that interview. Cross-org → `404`. |
| `/applications/{id}/interviews/{interview_id}` | PATCH | partner member (`recruitment:manage_interview`) + `version?` | Reschedule / edit (`scheduled_at`, `mode`, `location`, `meeting_link`, `title`, `notes`); omitted fields unchanged. Optimistic `version` (stale → `409`). Audited (`application.interview_rescheduled`). Re-notifies candidate + assignees. |
| `/applications/{id}/interviews/{interview_id}/assignees` | PUT | partner member (`recruitment:manage_interview`) | Body `{ assignee_ids:[uuid] }` — replaces the set (members of the org, else `422`). **Changes the gate `required`.** Audited (`application.interview_assignees_changed`). Notifies newly-assigned interviewers. |
| `/applications/{id}/interviews/{interview_id}/cancel` | POST | partner member (`recruitment:manage_interview`) + `version?` | `status → cancelled` (frees the open slot). Audited (`application.interview_cancelled`). Notifies the candidate (`recruitment.interview_cancelled`). |
| `/applications/{id}/interviews/{interview_id}/complete` | POST | partner member (`recruitment:manage_interview`) + `version?` | Body `{ outcome: "completed"｜"no_show" }`. `status → completed`/`no_show`. Audited (`application.interview_completed` / `…_no_show`). Partner-internal (no candidate notice). |

Partner **interview view**: `{ id, application_id, stage_id, title, mode, mode_label,
scheduled_at, duration_minutes, location, meeting_link (attendee-only — else null),
status, notes, assignees:[{ user_id, name }] (partner members, never the student),
evaluation:{ submitted_count, required, gate_met, avg_overall, threshold,
recommendation_summary }, version, created_at, updated_at }`.

**Student application detail** surfaces only the candidate's OWN upcoming interview
(`upcoming_interview`): `{ id, scheduled_at, mode, mode_label, duration_minutes,
location_or_link, status }` — `location_or_link` is the address (onsite), their own
meeting link (online), or `null` (phone). It **never** carries assignee identities,
scorecards, the gate, or any other candidate's data.

**Reminders:** the ADR-0003 scheduler job `interview.reminder_sweep` (every 5 min)
enqueues T-24h (candidate + assignees) and T-1h (candidate) reminders for due
`scheduled` interviews; idempotent via a per-`(interview, window[, user])` outbox
`dedupe_key` (`interview.reminder:{id}:{window}`). schedule/reschedule/cancel enqueue
their notices inline within the write transaction (no synchronous SMTP).

New notification types (catalog, vi+en, category `interview`):
`recruitment.interview_scheduled`, `recruitment.interview_rescheduled`,
`recruitment.interview_cancelled`, `recruitment.interview_reminder` (candidate);
`recruitment.interview_assigned`, `recruitment.interview_reminder_assignee`
(assigned interviewers). Email templates: `application.interview_scheduled`,
`…_rescheduled`, `…_cancelled`, `…_reminder`, `…_assigned`.

#### Offers (approval, send, accept/decline; ADR-0007)

An **offer** is the terminal POSITIVE outcome of the pipeline — the only path to
`applications.status='hired'`. **One LIVE offer per application** (LIVE = `draft |
pending_approval | approved | sent`). An 8-state machine: `draft ──submit──▶
pending_approval ──approve──▶ approved ──send──▶ sent ──accept/decline/expire──▶
accepted | declined | expired`; `rescind` (partner) from any LIVE state →
`rescinded`. Terminal = `accepted | declined | expired | rescinded`. Content is
mutable in place **only while `draft`** (frozen at submit). Four permission codes:
`recruitment:create_offer`, `recruitment:approve_offer`, `recruitment:send_offer`,
`recruitment:withdraw_offer` (partner `*:*` covers them); V1 does **not** enforce
separation-of-duties but records both `created_by` + `approved_by`.

**Salary (`salary_amount`) is Fernet-encrypted at rest** ("recruiter + student
only", DATA_MODEL §17): decrypted only for the partner detail view and the **owning
student's** own offer view — **never** in a notification/email body, the board
glance, or the `offer.accepted` event payload. **Reveal precondition:** SENDING an
anonymous application's offer requires an already-accepted reveal (else `409
reveal_required`) — the handshake stays the only identity path.

| Path | Method | Auth | Notes |
|---|---|---|---|
| `/applications/{id}/offers` | POST | partner member (`recruitment:create_offer`) | Body `{ position_title, department?, start_date?, salary_amount?, salary_currency?, salary_period?, benefits_summary?, terms_notes?, expiry_date }`. Creates the `draft` offer at the candidate's CURRENT ACTIVE stage. App not `under_review` / no ACTIVE stage → `409 illegal_transition`. A second LIVE offer → `409 { reason:"offer_exists" }`. Encrypts `salary_amount`. Cross-org → `404`. Audited (`application.offer_created`). Returns the partner offer view. |
| `/applications/{id}/offers` | GET | partner member (`recruitment:create_offer`) | `{ application_id, offers:[ <partner offer view> ] }` (full comp decrypted for the partner). Cross-org → `404`. |
| `/applications/{id}/offers/{offer_id}` | PATCH | partner member (`recruitment:create_offer`) + `version?` | Edit comp/terms/expiry **only while `draft`** (else `409 { reason:"offer_not_editable" }`). Optimistic `version` (stale → `409`). Audited (`application.offer_updated`). |
| `/offers/{offer_id}/submit` | POST | partner member (`recruitment:create_offer`) + `version?` | `draft → pending_approval` (freezes content). Audited (`application.offer_submitted`). |
| `/offers/{offer_id}/approve` | POST | partner member (`recruitment:approve_offer`) + `version?` | Body `{ decision: "approve"｜"reject" }`. `pending_approval → approved` (sets `approved_by`/`approved_at`) or `→ draft` (reject-back). Audited (`application.offer_approved` / `…_rejected_back`). |
| `/offers/{offer_id}/send` | POST | partner member (`recruitment:send_offer`) + `version?` | `approved → sent` (`sent_at`). **`409 { reason:"offer_not_approved" }`** if not `approved` (the structural approval gate). **`409 reveal_required`** for an anonymous app with no accepted reveal. Audited (`application.offer_sent`). Notifies the candidate (`recruitment.offer_received`, NO salary). |
| `/offers/{offer_id}/rescind` | POST | partner member (`recruitment:withdraw_offer`) + `version?` | `{draft,pending_approval,approved,sent} → rescinded`. Notifies the candidate (`recruitment.offer_rescinded`) only if it had been `sent`. Audited (`application.offer_rescinded`). |
| `/offers` | GET | the applicant (student) | `{ offers:[ <student offer view> ] }` — the student's OWN offers; only `sent`+terminal states are visible (`draft`/`pending_approval`/`approved` are partner-internal). |
| `/offers/{id}` | GET | the applicant (owner) | The student's OWN offer detail — full comp (decrypted; they are the owner). Non-owner / not student-visible → `404`. |
| `/offers/{id}/respond` | POST | the applicant (owner) | Body `{ decision: "accepted"｜"declined", notes?, idempotency_key }`. Only a `sent` (non-expired) offer (lazy-expire checked first; expired/terminal → `409 { reason:"offer_not_actionable" }`). Non-owner → `404`. Idempotent (re-responding the same decision is a no-op). **Accept →** offer `accepted` + `applications.status='hired'` + closes the Offer-stage `candidate_stages` row `PASSED`/`exit_kind='hired'` + emits the **non-blocking `offer.accepted` outbox event** (career-outcome seam, trust_level=4, **NO salary**) + audit `application.hired`. **Decline →** offer `declined` (stores `decline_reason` from `notes`, partner-internal); the application **stays `under_review`** (no auto-reject). |

**Partner offer view**: `{ id, application_id, stage_id, status, status_label,
position_title, department, start_date, salary_amount, salary_currency,
salary_period, comp_summary, benefits_summary, terms_notes, expiry_date, created_by,
approved_by, approved_at, sent_at, student_response_at, decline_reason, version,
created_at, updated_at }` (full comp; approval trail + `decline_reason` are
partner-internal). **Student offer view** (`GET /offers/{id}`): the same comp fields
**minus** `created_by`/`approved_by`/`approved_at`/`decline_reason`.

**Partner pipeline block** gains an `offer` glance (current stage; `null` when none):
`{ id, status, status_label, expiry_date, sent_at }` — **no salary** on the board
glance (open the offer detail to see comp). **Student application detail** gains an
`offer` card (only for a `sent`+terminal offer; `null` otherwise): `{ id, status,
status_label, position_title, department, start_date, expiry_date, comp_summary }` —
their own comp, never partner internals.

**Expiry:** the ADR-0003 scheduler job `offer.expire_sweep` (every 5 min) flips
past-deadline `sent` offers to `expired` (notifying candidate + partner) and enqueues
the T-24h `offer_expiring` reminder; idempotent (status-gated flip + per-offer outbox
`dedupe_key`). A read/respond lazy-expires a stale `sent` offer first.

New notification types (catalog, vi+en, category `application_status`):
`recruitment.offer_received`, `recruitment.offer_expiring`,
`recruitment.offer_expired`, `recruitment.offer_rescinded` (candidate);
`recruitment.offer_accepted`, `recruitment.offer_declined` (partner feed). **No
salary figure in any body.** Candidate email templates: `application.offer_received`,
`…_expiring`, `…_expired`, `…_rescinded`. New domain event: `offer.accepted`
(`outbox_events`, payload `{ application_id, offer_id, org_id, employer_org_id,
position_title, start_date }` — NO salary).

**Career-outcomes materializer (ADR-0007 deferred consumer; module
`career_outcomes`).** The `offer.accepted` event is consumed by the FIRST drainer
of the generic `outbox_events` table: `career_outcomes.materialize_sweep` (ADR-0003
scheduler job, ~300s). `materialize_career_outcomes(session, now)` claims
unprocessed `offer.accepted` events (`published_at IS NULL`; `FOR UPDATE SKIP
LOCKED` on Postgres, inert on SQLite), writes one `career_outcome_record` per event
at `trust_level=4` / `source='system_estimate'` / `outcome_type='hired'`, and stamps
the event's `published_at` to mark it processed. **Idempotent two ways:** the
`published_at` processed marker (a processed event is never re-claimed) AND the
UNIQUE `career_outcome_records.source_event_id` (an at-least-once redelivery cannot
duplicate). The consumer reads ONLY the event payload (no recruitment ORM import,
no student PII, no salary). A future university read surface (`GET
/career-outcomes/records` / `/kpi`) reads this table with trust-level/consent
filters; that read API is a later slice.

#### Pipeline Board (kanban read model)

| Path | Method | Auth | Notes |
|---|---|---|---|
| `/jobs/{job_id}/pipeline` | GET | partner member of the job's org (same authz as `/jobs/{job_id}/applications`) | The whole kanban board for one job in a bounded number of queries (no per-application N+1). Cross-org / non-partner → `404` (indistinguishable from missing). Anonymity-safe: pre-reveal a card carries only the `UV-xxxx` handle. |

Response `data`:

```jsonc
{
  "job": { "id": "<uuid>", "title": "Backend Intern" },
  "template_id": "<uuid>",                  // the org's default pipeline template
  "stages": [                               // ordered columns metadata
    { "id": "<uuid>", "name": "Sàng lọc hồ sơ", "stage_type": "screening",
      "sort_order": 1, "is_terminal": false, "candidate_visible": true,
      "required_action": "manual" }         // "scorecard" → card is scorecard-gated
    // … interview (2), offer (3)
  ],
  "columns": [
    { "key": "new", "stage_id": null, "name": "Hồ sơ mới", "sort_order": 0,
      "candidate_visible": true, "count": 3, "candidates": [ /* cards */ ] },
    { "key": "stage:<uuid>", "stage_id": "<uuid>", "name": "Sàng lọc hồ sơ",
      "stage_type": "screening", "sort_order": 1, "candidate_visible": true,
      "is_terminal": false, "count": 5, "candidates": [ /* cards */ ] }
    // … one column per template stage
  ],
  "summary": { "new": 3, "by_stage": { "<stage_id>": 5, "…": 2 },
               "active_total": 10, "rejected": 4, "withdrawn": 1 },
  "truncated": false,        // true if active card count exceeded the cap
  "candidate_cap": 300       // max CARDS rendered across the board; counts stay exact
}
```

Each candidate **card** (anonymity-minimal — never CV text, cover letter,
screening answers, scores, or the internal rejection reason):

```jsonc
{
  "application_id": "<uuid>",
  "is_anonymous": true,
  "applicant": {                      // pre-reveal: handle only
    "is_anonymous": true, "revealed": false,
    "anonymous_id": "UV-AB12CD34", "display_name": "Ứng viên ẩn danh"
    // post-accept reveal: { revealed:true, user_id, display_name, email }
  },
  "status": "under_review", "status_label": "Đang xem xét",
  "reveal_status": "none", "reveal_status_label": null,
  "cv_download_available": false,     // true only after an anonymous reveal is accepted
  "stage_id": "<uuid|null>",          // null in the "new" bucket
  "position": 1,                       // current stage sort_order (null in "new")
  "entered_at": "<iso8601|null>",      // when the card entered its current stage
  "rollback_count": 0,
  "evaluation": {                      // partner-only scorecard glance (current stage);
    "submitted_count": 0, "required": 1, "gate_met": false,  // null when pre-pipeline
    "avg_overall": null, "threshold": null,  // `required` assignee-derived; threshold set on score_threshold stages
    "recommendation_summary": { "strong_no": 0, "no": 0, "yes": 0, "strong_yes": 0 }
  },                                   // NEVER present on any student projection
  "applied_at": "<iso8601>", "last_status_at": "<iso8601>"
}
```

Bucketing rules:

- **`new` (pre-pipeline) bucket** — applications still `submitted` (not yet
  reviewed → no `candidate_stages` row), so they are never lost off the board. A
  legacy `under_review` with no ACTIVE stage row also falls here.
- **stage columns** — one per ordered template stage; a card sits in the column of
  its current ACTIVE `candidate_stages` row.
- **terminal outcomes** (`rejected` / `withdrawn`) do **not** render as cards — a
  kanban board shows only candidates currently in the pipeline — but their counts
  remain in `summary.rejected` / `summary.withdrawn`.
- Column **`count`** values are authoritative (derived from `candidate_stages`
  ACTIVE rows, exact even when the rendered `candidates` are capped at
  `candidate_cap`). When more than `candidate_cap` active cards exist, `truncated`
  is `true` and the newest applications by `applied_at` are kept.

### Organization Media And Logo Delivery

Use this contract for the Visual/Product Rescue logo pipeline. It is a required
future implementation contract, not proof that the current backend already does
it.

System/default media:

- Static VinUni-owned public visuals live in `frontend/public/brand/*` and
  `frontend/public/images/*`.
- These assets may be used by the public gateway, default banners, default event
  cards, and empty states without a backend media row.
- They are not a substitute for employer-uploaded company logos.

Organization media:

- `organizations.logo_path` is an internal storage key only. It is never returned
  by public APIs, frontend API clients, logs, analytics, or error details.
- Public organization/job/company projections expose only `logo_url`, never
  `logo_path`.
- `logo_url` must be a stable safe delivery URL or `null`. It may be public only
  for `active` partner organizations that are not deleted/suspended.
- Partner admins may upload/update their own company logo through an authenticated
  org-profile endpoint gated by `organizations:update`.
- University admins may remove, replace, or moderate uploaded logos/media when
  the media violates brand, safety, or authenticity policy.
- Partner registration may optionally attach a pending logo upload, but approval
  must copy/promote it into the created organization only after validation.
- Valid logo files: PNG, JPEG, WebP; max 3 MB by default; verify MIME and magic
  bytes; strip metadata where practical.
- Invalid, blank, corrupt, oversize, unsupported, or suspicious files return a
  user-safe `VALIDATION_FAILED` reason.
- Logo delivery must not depend on a signed CV/document token that reveals raw
  storage semantics. Use a dedicated org-media resolver or public asset endpoint.

Implemented endpoints (org logo media pipeline):

- `POST /api/v1/organizations/{org_id}/logo` — multipart (`file`, optional
  `version` form field). Auth required; gated by `organizations:update` at the
  service layer. Tenant-scoped: a cross-org `org_id` returns `404` (never 403).
  Validation is magic-byte first — only PNG/JPEG/WebP, max 3 MB (`ORG_LOGO_MAX_MB`),
  empty/oversize/non-image/declared-type-not-allowlisted return `422
  VALIDATION_FAILED` with a `details.reason` of `empty_file` / `file_too_large` /
  `unsupported_image_type`. On success the logo replaces any previous one (old
  object deleted), bumps `version`, writes an `organization.logo_updated` audit
  row, and returns the org detail (`data.logo_url`, never `logo_path`). If
  `version` is supplied and stale, returns `409 CONFLICT`.
- `DELETE /api/v1/organizations/{org_id}/logo` — same auth/RBAC/tenant rules.
  Idempotent; clears `logo_path`, bumps `version` (when a logo existed), writes an
  `organization.logo_removed` audit row, returns org detail with `logo_url: null`.
- `GET /api/v1/companies/{slug}/logo` — public, unauthenticated. Streams the
  active partner org's logo bytes with the correct image `Content-Type` and
  `Cache-Control: public, max-age=3600`. Returns `404` when the org is not
  publicly listable (university/pending/suspended/deleted/missing) or has no logo,
  so a stale URL for a now-hidden org never leaks bytes.
- `logo_url` behavior: `public_logo_url(org)` resolves to
  `{app_url}/api/v1/companies/{slug}/logo?v={version}` when `logo_path` is set,
  else `null`. This single resolver populates `logo_url` on the companies
  directory, company detail, marketplace spotlight, embedded job `company` blocks,
  and the authenticated org-profile detail. The raw `logo_path` is never returned
  on any surface; the org-profile `PATCH` no longer accepts `logo_path` (it was a
  validation bypass) — the logo is mutated only through the endpoints above.
- University moderation of partner logos (remove/replace/queue) is a separate
  later slice and is not part of this pipeline.

Required tests before marking logo pipeline complete:

- Partner can upload/update own logo.
- Wrong org/persona is denied.
- University admin can remove/moderate uploaded media.
- Public `logo_url` is present only for active partner orgs with a validated
  logo.
- Raw `logo_path` never appears in public company/job/dashboard API responses.
- Jobs, companies, homepage spotlight, mega-menu, and partner dashboard all use
  the same safe `logo_url` projection with initials fallback.

## Public Marketplace Overview

`GET /api/v1/marketplace/overview` — public, unauthenticated. Read-only aggregate
for the homepage gateway (`docs/DESIGN.md` §metric strip, `docs/SCREEN_SPECS.md`
§1.1). It owns no models and runs every read through the public-tier visibility
predicate, so it can never surface a job a guest list would not show.

```json
{
  "metrics": {
    "active_jobs": 128,
    "companies": 24,
    "open_for_applications": 128
  },
  "jobs_trend": {
    "new_jobs_30d": 17,
    "series": [
      { "date": "2026-05-29", "count": 0 },
      { "date": "2026-05-30", "count": 2 }
      // ... exactly 30 trailing UTC days, oldest first, zero-filled
    ],
    "delta_pct": 41.7
  },
  "sponsored_jobs": [],
  "featured_jobs": [],
  "recent_jobs": [],
  "spotlight_companies": [],

  "hero_campaign": null,
  "recommended_jobs": { "source": "recent", "personalized": false, "items": [] },
  "recommended_events": [],
  "sponsored_banner": null,
  "employer_spotlight": [],
  "popular_roles": [],
  "trust_modules": [ { "key": "verified_by_vinuni" }, { "key": "career_support" } ]
}
```

**Recommendation / sponsored / curated rails (spec §6/§8, slice 2).** Optional-auth:
the route resolves the `vinuni_discovery` cookie + any bearer token so the
recommended rail can personalize honestly; a guest still gets the full homepage.

- `hero_campaign` — the homepage hero banner for slot `homepage_hero`. When a REAL
  live sponsored placement fills it: `{ placement_id, slot, source:"partner",
  target_type:"job", job:<summary>, creative, disclosure, sponsored_disclosure }`,
  where `creative` is the placement's `approved` `homepage_hero` creative
  (`{ image_url, alt, focal_point, click_target }`) or `null` if none uploaded yet,
  `disclosure` is keyed by the placement's `disclosure_class` (polished label +
  `is_paid`/`is_removable`), and `sponsored_disclosure` is kept for backward
  compatibility. A placement whose target job is now hidden is dropped (never a
  broken banner). When NO partner placement fills the slot, a **VinUni-curated
  fallback** is used: `{ placement_id:null, slot, source:"vinuni_curated", creative,
  disclosure }` labelled `university_curated` (NEVER paid) — only when a fallback
  asset is configured (`MARKETPLACE_HERO_FALLBACK_IMAGE`, a `frontend/public`
  path); otherwise `null` (hide-if-empty, no fabricated banner).
- `sponsored_banner` — the right-rail banner for slot `right_rail` = the *next* live
  placement after the hero (no duplication), same shape, else the
  `right_rail` curated fallback (`MARKETPLACE_RAIL_FALLBACK_IMAGE`) or `null`.
  `image_url` on any creative is the public serve route, never a storage key.
- `recommended_jobs` — `{ source, personalized, items[] }` from the ranking layer
  (see *Recommendation & Ranking Layer* below). Guest → session signals or honest
  `recent`/`popular` fallback. Sponsored inventory is delivered in the hero/banner
  rails ONLY (`with_sponsored=false` here) so it never reorders this organic rail.
- `recommended_events` — upcoming events carrying `source` + `reason_codes`
  (V1 = `source:"recent"`; session-based event personalization is a follow-up).
- `employer_spotlight` — verified-first public company directory summaries.
- `popular_roles` — REAL aggregate `{ role_family, job_count, application_count }`
  from eligible jobs by deterministic role family; `[]` (hide) when no data. No
  fabricated metrics.
- `trust_modules` — static, metric-free honest trust content (`{ key }` only; the
  frontend localizes). Never fake numbers.

Metric strip semantics (4 metrics: the 3 scalars + `jobs_trend.new_jobs_30d`):

- `metrics` — live counts of currently guest-visible jobs / public partner
  companies / jobs still open for applications. The whole object is `null` (not
  faked) if any of its queries raise; the frontend then hides the 3 scalar tiles.
- `jobs_trend.new_jobs_30d` — the 4th metric: count of currently guest-visible
  jobs that **became published** (`published_at`) within the trailing 30 UTC days
  (today inclusive). It is derived from the **same** visibility predicate as
  `active_jobs`, so the two can never drift (a job published 40 days ago counts in
  `active_jobs` but not here; a job published yesterday then closed counts in
  neither).
- `jobs_trend.series` — exactly 30 buckets `{ date: "YYYY-MM-DD", count }`,
  oldest first, one per trailing UTC day, zero-filled. Suitable for a sparkline.
  `sum(series.count) == new_jobs_30d`.
- `jobs_trend.delta_pct` — percent change of `new_jobs_30d` vs the prior
  equivalent 30-day period (days 30–59 ago), rounded to 1 decimal. It is `null`
  (never `0` or a fabricated `+100%`) when the prior period has no jobs — i.e.
  insufficient history. The frontend then hides the trend arrow but still renders
  the sparkline.
- `jobs_trend` is `null` (not faked) if its single grouped aggregate query raises;
  the 3 scalar `metrics` still return and the endpoint never 500s on a trend
  failure. The query is bounded to the trailing 60 days and grouped in SQL (one
  query, no per-row scan).

Honesty rule: every trend field is real-or-omitted. No field is ever invented to
fill the design; insufficient data yields `null`/empty, never a placeholder
number.

## CV Studio Contracts

Use with `docs/CV_STUDIO_SPEC.md`.

### CV Template

```json
{
  "id": "uuid",
  "key": "classic_one_page",
  "name": "Classic One Page",
  "category": "classic",
  "is_premium": false,
  "preview_url": "signed-url-or-null"
}
```

### CV Profile

`GET /api/v1/cvs/{cv_id}` (owner only; cross-owner → `404`).

```json
{
  "id": "uuid",
  "title": "Backend Internship CV",
  "source_type": "builder",
  "source_label": "Tự tạo",
  "template_id": "uuid",
  "language": "vi",
  "status": "draft",
  "status_label": "Bản nháp",
  "is_primary": false,
  "version": 7,
  "last_edited_at": "iso-datetime",
  "created_at": "iso-datetime",
  "current_version_id": "uuid",
  "versions": [
    {
      "id": "uuid",
      "version": 7,
      "change_source": "manual",
      "change_summary": "add section awards",
      "is_current": true,
      "created_at": "iso-datetime"
    }
  ],
  "sections": []
}
```

- `version` is the optimistic-concurrency token (an integer; used as
  `expected_version` on section writes).
- `current_version_id` is the `cv_versions` UUID of the latest accepted snapshot.
  It is the value clients pass to `POST /cvs/{cv_id}/export` (`version_id`) and to
  the application apply flow (`cv_selection.cv_version_id`). It is always non-null
  for a builder CV (the first snapshot is created at CV creation).
- `versions` is the version history, newest-first; the head is the current
  snapshot. The immutable `snapshot_json` is never returned in this list.

Friendly labels must be returned through i18n metadata or frontend mapping; raw statuses are not displayed directly.

### CV Library And Quota

`GET /api/v1/cvs` returns the student's active CV library, upload/import
sources, and tier quota state.

```json
{
  "data": [
    {
      "id": "uuid",
      "title": "Backend Internship CV",
      "source_type": "builder",
      "status": "ready",
      "in_library": true,
      "finalized_at": "iso-datetime",
      "language": "vi",
      "template_id": "uuid",
      "last_edited_at": "iso-datetime"
    }
  ],
  "meta": {
    "active_cv_limit": 5,
    "active_cv_used": 3,
    "can_create": true,
    "quota_reset_at": null,
    "quota_source": "student_tier"
  }
}
```

Default active CV limit is 5 per student tier unless overridden. `quota_source`
is `"student_tier"` for the platform default and **`"subscription"`** when an
active paid plan overrides the cap (ADR-0010: `student_pro` → `cv_active_quota`
10, resolved through `billing.limit_facade`).

**CV library lifecycle (design spec 2026-07-05, owner-approved).** A CV has two
tiers via `status`:

- `draft` — an unlimited scratch CV. The student designs/edits freely on the
  canvas; it does **not** count against the 5-cap and is **not** usable for apply
  or job-fit. Creating (`POST /cvs`, every `creation_mode`) and duplicating
  (`POST /cvs/{id}/duplicate`) produce drafts and are **not** quota-gated.
- `ready` — a committed **library** CV (analyzed, matching-ready). It counts
  against the 5-cap and is usable for apply + job-fit. Each summary/detail carries
  `in_library` (bool) and `finalized_at` (iso-datetime | null).

A CV enters the library one of two ways: the student finalizes a template draft
(`POST /cvs/{id}/finalize`), or an uploaded CV is imported (already extracted, so
it lands `ready`). Archived CVs, drafts, and immutable application snapshots do
not count; `active_cv_used` = the owner's `ready` (non-deleted) CVs. Archiving or
deleting a `ready` CV frees a slot immediately. The 5-cap is enforced server-side
only where a CV is committed — **finalize** and **upload import** — returning
`409 QUOTA_EXCEEDED` with actions such as `archive_existing`, `delete_draft`,
`request_more_quota`, or `upgrade`.

### Finalize CV (commit a draft into the library)

`POST /api/v1/cvs/{cv_id}/finalize` (owner only; cross-owner → `404`). No request
body.

Promotes a `draft` CV to `ready` (`status='ready'`, `finalized_at=now()`), writes
an immutable `cv_versions` snapshot (`change_source='finalize'`) + a `cv.finalized`
audit row, and returns the full CV detail (same shape as `GET /cvs/{cv_id}`).

- **Idempotent:** an already-`ready` CV returns its current detail unchanged (no
  new version, no re-count, no duplicate audit).
- **Empty CV → `422 VALIDATION_FAILED`** with `details.reason = "cv_empty"` when
  the CV has no header `name` and no visible section carrying real content
  (`entries` / `items` / `text`). Nothing is mutated.
- **Library full → `409 QUOTA_EXCEEDED`** with the `cv_quota_reached` payload +
  recovery `actions` below. Nothing is mutated.

### CV Version History

`GET /api/v1/cvs/{cv_id}/versions` (owner only; cross-owner → `404`).

Returns the CV's immutable version history, newest-first. The head entry has
`is_current: true` and its `id` equals the profile's `current_version_id`.

```json
{
  "data": [
    {
      "id": "uuid",
      "version": 8,
      "change_source": "restore",
      "change_summary": "restored v6",
      "is_current": true,
      "created_at": "iso-datetime"
    },
    {
      "id": "uuid",
      "version": 7,
      "change_source": "manual",
      "change_summary": "add section awards",
      "is_current": false,
      "created_at": "iso-datetime"
    }
  ]
}
```

`change_source` ∈ `manual | import | restore` (AI-accept sources land in a later
slice). Storage keys, raw snapshot JSON, and provider internals are never exposed.

### Create CV

`POST /api/v1/cvs`

```json
{
  "title": "Backend Internship CV",
  "template_id": "uuid",
  "creation_mode": "blank_template",
  "language": "vi",
  "source": {
    "import_confirmed_profile_facts": false,
    "uploaded_document_id": "uuid-or-null",
    "cv_parse_run_id": "uuid-or-null",
    "source_cv_id": "uuid-or-null",
    "source_cv_version_id": "uuid-or-null",
    "raw_notes": "optional user-provided notes"
  }
}
```

Allowed `creation_mode` values:

- `blank_template`
- `confirmed_facts_import` (alias accepted: `profile_import`)
- `notes_import`
- `uploaded_import`
- `duplicate_existing`
- `ai_assisted_draft`

`blank_template`, `confirmed_facts_import`, `notes_import`, `uploaded_import`, and
`duplicate_existing` are normal application writes. `ai_assisted_draft` creates
a pending AI suggestion/draft and must follow AI confirmation/audit rules.

`notes_import` is the deterministic CV-first "create from raw notes" path: it
seeds the CV section skeleton **directly from the student's pasted text** in
`source.raw_notes` with **no AI/model call**. Notes are split into lines and
routed into `summary` / `experience` / `skills`; lines before any recognized
header (`Summary:` / `Experience:` / `Skills:`, vi + en) default to `summary`,
and a `Skills:` header splits inline comma/slash items into individual skill
entries. Nothing is invented — every seeded item is a verbatim slice of the
user's input, so this path works for a brand-new student with zero structured
profile rows. `source.raw_notes` is required for this mode; an empty/whitespace
value returns `422 VALIDATION_FAILED` with `details.reason = "source_required"`
and `details.field = "raw_notes"`. The resulting CV has `source_type =
"notes_import"` and is created as a `draft` (it counts against the 5-cap only once
the student finalizes it into the library — see *CV library lifecycle* above).

`confirmed_facts_import` may use only student-confirmed facts/preferences. It
must not force the student to complete a long profile form before CV creation.
If legacy UI/API names still say `profile_import`, treat them as an alias for
confirmed facts only and migrate naming in the next touched slice.

#### CV active-CV quota (`QUOTA_EXCEEDED`)

The active-CV library limit is enforced **server-side** where a CV is committed to
the library — `POST /api/v1/cvs/{cv_id}/finalize` (template drafts) and CV upload
import — **not** on `POST /api/v1/cvs` or `POST /api/v1/cvs/{cv_id}/duplicate`
(those produce unlimited scratch drafts). "In library" = `status='ready'` and not
soft-deleted; drafts, archived CVs, and immutable application snapshots do not
count, so archiving/deleting a `ready` CV frees a slot. To save extraction tokens,
CV upload import is also quota pre-checked at **upload start** so a full library
rejects the upload before the extraction cascade runs. Default limit is 5 per
student tier (`STUDENT_ACTIVE_CV_QUOTA`, tier-overridable). An idempotent duplicate
replay returns the existing copy and is never quota-blocked; an idempotent
finalize of an already-`ready` CV is never re-counted.

At/over the limit, finalize / upload import returns `409 QUOTA_EXCEEDED`:

```json
{
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "Bạn đã đạt giới hạn số CV đang hoạt động. Hãy lưu trữ hoặc xóa bớt một CV trước khi tạo CV mới.",
    "details": {
      "reason": "cv_quota_reached",
      "current": 5,
      "limit": 5,
      "actions": ["archive_existing", "delete_draft", "request_more_quota", "upgrade"]
    },
    "request_id": "req_..."
  }
}
```

The live counter for the UI comes from the `GET /api/v1/cvs` `meta` block
(`active_cv_limit`, `active_cv_used`, `can_create`). The UI must offer the
`details.actions` recovery paths and must not silently fail.

### Upload CV Document

`POST /api/v1/cvs/upload`

Multipart form:

- `file`: PDF/DOCX/TXT/image where enabled.
- `idempotency_key`: client-generated key.

Response:

```json
{
  "data": {
    "document_id": "uuid",
    "parse_run_id": "uuid",
    "status": "virus_scanning",
    "next_action": "wait"
  }
}
```

### CV Parse Status

`GET /api/v1/cvs/parse-runs/{parse_run_id}`

```json
{
  "data": {
    "id": "uuid",
    "document_id": "uuid",
    "status": "review_required",
    "quality_code": "REVIEW_REQUIRED",
    "user_message": "Chúng tôi đã trích xuất được một số thông tin nhưng cần bạn kiểm tra trước khi nhập vào CV.",
    "next_actions": ["review_fields", "upload_another", "create_from_template"],
    "review_fields": [
      { "path": "education[0].school", "value": "VinUni", "needs_review": false },
      { "path": "experience[0].dates", "value": "2024 - ?", "needs_review": true }
    ]
  }
}
```

Failure `quality_code` values:

- `UNSUPPORTED_FILE_TYPE`
- `FILE_TOO_LARGE`
- `FILE_REJECTED_SECURITY`
- `PASSWORD_PROTECTED_FILE`
- `CORRUPT_FILE`
- `DUPLICATE_FILE`
- `BLANK_DOCUMENT`
- `LOW_QUALITY_SCAN`
- `NOT_A_CV`
- `INSUFFICIENT_CV_CONTENT`
- `LANGUAGE_REVIEW_REQUIRED`
- `REVIEW_REQUIRED`

Responses return friendly messages and next actions only. Internal parser errors, OCR details, provider aliases, confidence, storage paths, and raw extracted text are never exposed unless the endpoint is an owner-only review endpoint explicitly designed to show extracted fields.

### CV Ingestion (preview-first, adapter cascade)

> **UPDATE 2026-07-05 (owner decision — supersedes the review-screen parts of this
> contract):** The uploaded-CV flow is **upload → confirm file → name the CV →
> done**. Backend extraction is authoritative and creates the versioned draft
> directly; there is NO manual field-review step. The `needs_review` status, the
> "Check this" review screen, and the import `overrides[]` corrections described
> below are historical — the student no longer reviews or edits extracted fields.
> The cascade also gains a cheap **vision-LLM** tier that MAY receive DOWNSCALED
> document images for images and styled/scanned PDFs; the text-LLM structuring
> tier still receives text only. Non-CV/blank/corrupt uploads are rejected, never
> fabricated.

The explicit ingestion API (`docs/CV_INGESTION_EXTRACTION_SPEC.md` §3/§5) runs
alongside the legacy `POST /api/v1/cvs/upload` (kept for back-compat). It is
preview-first: store the original, ingest asynchronously through an
availability-gated adapter cascade (native text → layout → OCR → vision-LLM →
classifier → deterministic structuring → optional text-LLM structuring), then name
and import. All endpoints are owner-scoped; cross-owner access → `404`.
Engine/model/provider names, prompts, token counts, raw confidence, storage keys,
text length, and stack traces never appear in any response.

#### Upload original (preview metadata)

`POST /api/v1/cv-uploads` — multipart form: `file`, optional `idempotency_key`.

Stores the original file and returns preview/upload metadata only (not builder
content). Cheap pre-storage gates (size/type/security); password/corrupt detection
and classification happen at ingest. Repeated `idempotency_key` replays the same
document.

```json
{
  "data": {
    "document_id": "uuid",
    "filename": "cv.pdf",
    "content_type": "application/pdf",
    "size": 48213,
    "page_count": null,
    "preview_url": "https://.../api/v1/cv-files/<signed-token>"
  }
}
```

`preview_url` is a short-lived signed `GET /api/v1/cv-files/{token}` capability
(`kind=document`, owner-scoped); it streams the original bytes, never a storage
path. Oversized/unsupported/security-rejected uploads → `422 VALIDATION_FAILED`
with a friendly message + `details.quality_code` + recovery `details.actions`.

#### Start / resume ingestion

`POST /api/v1/cv-uploads/{document_id}/ingest` — body: optional
`{ "idempotency_key": "..." }`.

Starts (or resumes) ingestion. Runs through the background queue when
`CV_INGESTION_ASYNC=true` (idempotent + resumable; re-ingest is safe); the inline
local queue executes synchronously. Returns the ingestion status (same shape as
the GET below).

#### Ingestion status

`GET /api/v1/cv-ingestions/{ingestion_id}` (owner only; cross-owner → `404`).

```json
{
  "data": {
    "id": "uuid",
    "ingestion_id": "uuid",
    "document_id": "uuid",
    "status": "needs_review",
    "status_label": "Cần bạn kiểm tra",
    "quality_code": "REVIEW_REQUIRED",
    "quality_message": "Chúng tôi đã trích xuất được một số thông tin nhưng cần bạn kiểm tra trước khi nhập.",
    "detected_language": "vi",
    "mixed_language": true,
    "review_fields": [
      { "path": "contact.email", "value": "an@example.com", "needs_review": false },
      { "path": "experience[0].text", "value": "Intern 2024 - ?", "needs_review": true }
    ],
    "next_actions": ["review_fields", "import_to_cv", "keep_original"],
    "imported_cv_id": null
  }
}
```

Friendly `status` vocabulary (the only states the UI renders):

- `queued` — accepted, not started.
- `checking` — security/file gates ("Checking file").
- `reading` — native text extraction ("Reading document").
- `improving_layout` — layout pass ("Improving layout").
- `reading_scanned` — OCR pass ("Reading scanned pages"), only when OCR is needed.
- `preparing_review` — structuring ("Preparing review").
- `needs_review` — terminal: extracted, has fields to confirm ("Needs your review").
- `ready` — terminal: clean, ready to import ("Ready to import").
- `failed` — terminal recoverable problem; `quality_code` + `quality_message` +
  `next_actions` describe the fix (blank/not-CV/password/corrupt/duplicate/
  low-quality). Never says an engine is missing.

`review_fields` carry field-level needs-review markers (the "Check this" UX), NOT
numeric confidence. Each item is `{ path, value, needs_review, source_span?, page? }`.

#### Import a reviewed ingestion

`POST /api/v1/cv-ingestions/{ingestion_id}/import` — body:

```json
{
  "title": "Backend Internship CV",
  "template_id": "uuid-or-null",
  "target_cv_id": "uuid-or-null",
  "fact_confirmation": true,
  "overrides": [
    { "path": "contact.email", "value": "jane.engineer@example.com" },
    { "path": "skills[0].text", "value": "Go, Rust, Kubernetes, Terraform" }
  ],
  "idempotency_key": "client-generated-key"
}
```

Requires the ingestion to be `ready` or `needs_review`. Creates a NEW versioned
draft CV (`source_type=uploaded_import`, first `cv_versions` snapshot) and links it
to the ingestion (re-import is idempotent → returns the same draft). When
`target_cv_id` is supplied it must reference a DRAFT owned by the caller — an
accepted/`ready` CV is never silently overwritten (`422` `target_not_draft`).
Respects the active-CV quota → `409 QUOTA_EXCEEDED` with recovery actions. Returns
the full CV detail (same shape as `GET /api/v1/cvs/{cv_id}`).

`overrides` (optional) carries the student's reviewed corrections from the
"Check this" review screen (`docs/CV_INGESTION_EXTRACTION_SPEC.md` §2:
"Low-confidence fields are editable before import"). Each entry is
`{ "path", "value" }`:

- `path` MUST be one the ingestion itself emitted in `review_fields`
  (`contact.<name|email|phone>` or `<section_type>[<idx>].text`). Any path
  outside that allowlist — or a malformed/out-of-range path — is ignored, so an
  override can only edit an existing extracted field and can never inject a new
  section or value.
- `value` is a plain string (the user's typed correction); it is sanitised the
  same way extracted text is (control/binary bytes stripped, whitespace trimmed,
  capped). Max 200 overrides per request, max 5000 chars per value.

Overrides are applied to a COPY of the server-side extracted data BEFORE the
draft is structured, so the edited value lands in the new draft's
sections/version. The stored ingestion row's `extracted_data`/`review_fields`
are never mutated, and overrides do not bypass the quota or no-overwrite rules.

### Duplicate CV

`POST /api/v1/cvs/{cv_id}/duplicate`

```json
{
  "title": "Backend Internship CV - Shopee",
  "template_id": "uuid-or-null",
  "target_job_id": "uuid-or-null",
  "idempotency_key": "client-generated-key"
}
```

Duplicating creates a new `cv_profiles` record and first `cv_versions` snapshot. It never mutates the source CV.

### Add Section

`POST /api/v1/cvs/{cv_id}/sections` (owner only; cross-owner → `404`).

Appends a new section to a CV. Same body shape as the section upsert; `sort_order`
is optional (when omitted the new section is placed after the current last
section). `section_type` is optional and defaults to `custom`; an unknown type →
`400 VALIDATION_FAILED` (`details.reason = invalid_field`). The write bumps the CV
`version`, creates a new `cv_versions` snapshot, and writes an audit record
(`cv.section.created`).

```json
{
  "section_type": "awards",
  "title": "Awards",
  "sort_order": 70,
  "is_visible": true,
  "content": { "items": [{ "text": "Dean's List 2025" }] },
  "expected_version": 7
}
```

Response `201`:

```json
{
  "data": {
    "section": {
      "id": "uuid",
      "section_type": "awards",
      "title": "Awards",
      "sort_order": 70,
      "content": { "items": [{ "text": "Dean's List 2025" }] },
      "is_visible": true
    },
    "cv_version": 8
  }
}
```

A stale `expected_version` → `409 CONFLICT` (`details.current_version`), identical
to the section upsert conflict shape below.

### Section Upsert

`PATCH /api/v1/cvs/{cv_id}/sections/{section_id}`

```json
{
  "title": "Experience",
  "sort_order": 20,
  "is_visible": true,
  "content": {
    "items": []
  },
  "expected_version": 7
}
```

Conflict response:

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "CV này đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi lưu.",
    "details": { "current_version": 8 },
    "request_id": "req_..."
  }
}
```

### Restore Version

`POST /api/v1/cvs/{cv_id}/versions/{version_id}/restore` (owner only; cross-owner
or unknown `version_id` → `404`).

Restores a CV to a prior immutable snapshot. Restoration is **non-destructive to
history**: the live sections are rebuilt from the target snapshot and the result
is recorded as a NEW `cv_versions` row (`change_source = restore`); prior versions
remain intact. The response is the full CV detail (same shape as `GET
/cvs/{cv_id}`) with the new restore snapshot as `current_version_id`.

```json
{
  "expected_version": 8
}
```

Body is optional; when `expected_version` is supplied a stale token → `409
CONFLICT` (`details.current_version`). Writes an audit record
(`cv.version.restored`).

### CV Template Administration

University-only unless a future policy grants template ownership to another
organization type. Template administration is versioned and audited.

`POST /api/v1/admin/cv-templates`

```json
{
  "name_vi": "CV kỹ thuật một trang",
  "name_en": "One-page technical CV",
  "category": "technical",
  "target_role_families": ["software_engineering"],
  "layout_schema": {},
  "content_binding_schema": {},
  "is_premium": false,
  "idempotency_key": "client-generated-key"
}
```

`PATCH /api/v1/admin/cv-templates/{template_id}` updates draft metadata,
layout schema, binding schema, and assets. Published versions are immutable; an
edit creates or updates a draft version.

`POST /api/v1/admin/cv-templates/{template_id}/preview` validates the current
draft and returns a render preview plus validation warnings.

`POST /api/v1/admin/cv-templates/{template_id}/publish` validates required
bindings, overflow/page rules, localization, and preview/export rendering before
publishing a new immutable version.

`POST /api/v1/admin/cv-templates/{template_id}/archive` hides the template from
new selection while preserving existing student CVs that reference it.

Responses must not expose raw storage keys. Use safe media/render URLs where
the caller is authorized.

### AI Suggestion Request

`POST /api/v1/cvs/{cv_id}/ai-suggestions`

```json
{
  "task_type": "rewrite_cv_section",
  "target_section_id": "uuid",
  "job_id": "uuid-or-null",
  "instruction": "Rewrite this section in concise English for backend internship roles.",
  "raw_notes": "optional user-provided notes",
  "source_ids": {
    "profile": true,
    "uploaded_document_id": "uuid-or-null",
    "cv_parse_run_id": "uuid-or-null",
    "source_cv_id": "uuid-or-null"
  },
  "idempotency_key": "client-generated-key"
}
```

Allowed CV AI `task_type` values:

- `draft_cv_from_sources`
- `fill_cv_template_from_sources`
- `generate_cv_bullets`
- `rewrite_cv_section`
- `natural_language_cv_canvas_edit`
- `optimize_cv_for_job`
- `recommend_cv_for_job`
- `ats_keyword_suggestions`
- `cv_fabrication_check`

Response:

```json
{
  "data": {
    "suggestion_id": "uuid",
    "status": "pending",
    "credits_charged": 2,
    "diff": {
      "summary": "3 bullets rewritten",
      "before": {},
      "after": {},
      "requires_fact_confirmation": true
    }
  }
}
```

### Accept AI Suggestion

`POST /api/v1/cvs/{cv_id}/ai-suggestions/{suggestion_id}/accept`

```json
{
  "accepted_diff": {},
  "fact_confirmation": true,
  "idempotency_key": "client-generated-key"
}
```

Accepting a suggestion creates a new `cv_versions` row and emits an audit event.

### CV-To-Job Fit

`GET /api/v1/cvs/job-fit?job_id={uuid}`

Implemented contract (supersedes the earlier `POST /jobs/{job_id}/cv-fit`
sketch). Owner-only (`cv:read`): scores the **caller's own active CVs** (not
soft-deleted, not archived) against a target job and recommends the best one to
apply with. Read-only — no audit write, no CV mutation. Declared before the
dynamic `/cvs/{cv_id}` route so the static path is not captured.

Response:

```json
{
  "data": {
    "job": {
      "id": "uuid",
      "title": "Backend Intern",
      "company": { "display_name": "Acme Co." }
    },
    "recommended_cv_id": "uuid-or-null",
    "results": [
      {
        "cv_id": "uuid",
        "title": "My Backend CV",
        "score": 86,
        "bands": {
          "skills": 88,
          "experience": 82,
          "logistics": 95,
          "quality": 80
        },
        "matched_skills": ["Python", "FastAPI"],
        "gaps": ["Docker"],
        "stale": false,
        "last_updated_days": 12,
        "explanation": "short user-facing string or null"
      }
    ],
    "signal": "ok",
    "ai_explanation_available": true
  }
}
```

Scoring (deterministic, reproducible — same inputs always yield the same
integer score):

```text
score = round(0.50*skills + 0.25*experience + 0.10*logistics + 0.15*quality)
```

- `skills` — JD required (0.8 weight) + preferred (0.2 weight) skill coverage in
  the CV text (reuses the grounding keyword-coverage primitive). With no
  structured JD skills, falls back to top JD-text keywords.
- `experience` — evidence in experience/project sections, base credit + JD-skill
  relevance.
- `logistics` — work-mode/location fit where the job exposes data (remote → full;
  city/country match → high; data present but no match → low; no data → neutral).
  Language fit is not scored (jobs carry no structured language requirement).
- `quality` — core-section completeness + recency (decays past the stale window).

Band names are a 4-band grouping of the six `docs/BUSINESS_LOGIC.md` §4B.3B
categories: required + nice-to-have skills → `skills`; experience/project
evidence → `experience`; language/location/work-mode → `logistics`; CV
quality/staleness → `quality`. A dedicated `education/eligibility` band is
deferred (degree data is read but not yet scored as its own band).

Rules:

- `score` and `bands` are user-facing **product** scores, not raw model
  confidence/similarity. Never expose provider, model, prompt, token, latency,
  embedding, or raw confidence internals.
- Deterministic scoring runs first and always. The AI `explanation` is OPTIONAL
  enrichment for the recommended CV only (one model call, output-guarded). When
  no real provider is active (default offline) or the call fails: `explanation`
  is `null` and `ai_explanation_available` is `false`, but full deterministic
  results are still returned.
- `signal` is `"low_signal"` when the JD yields fewer than 2 parseable
  requirements; the endpoint still scores on what is available.
- `stale: true` when the CV's latest content update is older than the configured
  window (`cv_stale_after_days`, default 60).
- `recommended_cv_id` is the highest-scoring CV (tie-break: freshest, then id);
  `null` when there are no eligible CVs.
- Missing skills are surfaced in `gaps` and framed "if true, add evidence" by the
  client — the scorer never fabricates a skill the CV lacks.

Edge states:

- Student has 0 active CVs → `200` with `results: []`, `recommended_cv_id: null`
  (client shows "create a CV"). Never `404`.
- Job not found / not visible / closed / unpublished / past deadline → `404`
  (non-enumerable, same visibility predicate as the public job read).

### Natural-Language CV Canvas Edit

`POST /api/v1/cvs/{cv_id}/ai-edit-command`

Owner-only. Converts a student instruction into a pending canvas/content patch.
It does not mutate the CV until the student accepts the suggestion.

```json
{
  "instruction": "0324xx0898 is my phone number",
  "selected_element_id": "optional-canvas-element-id",
  "selected_section_id": "optional-section-id",
  "source_policy": {
    "allow_uploaded_cv_extraction": true,
    "allow_confirmed_profile_facts": true,
    "allow_raw_notes": true
  },
  "idempotency_key": "client-generated-key"
}
```

Response:

```json
{
  "data": {
    "suggestion_id": "uuid",
    "status": "pending",
    "preview_patch": {
      "target": "contact.phone",
      "summary": "Update phone number",
      "before": "",
      "after": "0324xx0898",
      "requires_fact_confirmation": true
    },
    "canvas_preview": {
      "affected_element_ids": ["element-phone"],
      "render_version": 12
    }
  }
}
```

Rules:

- AI-generated patches are stored as `cv_ai_suggestions` until accepted.
- Accepting the patch uses `POST /api/v1/cvs/{cv_id}/ai-suggestions/{suggestion_id}/accept`.
- The response must not expose prompt text, provider/model names, token counts,
  raw confidence, or unredacted source documents.
- Invalid/ambiguous instructions return user-safe guidance and no mutation.
- Uploaded CVs are read-only (owner decision 2026-07-05; enforced service-side
  2026-07-08, B-589): any edit/AI-mutation path on a `source_type == "uploaded_import"`
  CV — section upsert, `PATCH /cvs/{cv_id}/canvas`, `ai-edit-command`,
  `ai-suggestions`, version restore — returns `409 { reason: "uploaded_cv_read_only",
  actions: ["duplicate"] }`. Reading, exporting, and duplicating (into an editable
  builder copy) remain allowed.

### Student Job Intelligence

`GET /api/v1/jobs/{job_id}/student-intelligence?cv_id={optional_uuid}`

Authenticated-student only. Returns the practical job-detail intelligence used
by the signed-in student job page. Guests must use public job detail and must not
receive personalized fit/competition data.

```json
{
  "data": {
    "job_id": "uuid",
    "selected_cv_id": "uuid-or-null",
    "best_cv_id": "uuid-or-null",
    "fit": {
      "score": 86,
      "label": "strong_fit",
      "bands": {
        "skills": 88,
        "experience": 82,
        "logistics": 95,
        "quality": 80
      },
      "matched_evidence": [],
      "gaps": [],
      "improvement_actions": []
    },
    "competition": {
      "score": 64,
      "label": "moderate",
      "signal": "ok",
      "seats_bucket": "small_batch",
      "application_volume_bucket": "medium",
      "applicant_quality_bucket": "mixed",
      "student_standing_bucket": "middle_of_pack",
      "student_fit_bucket": "above_average",
      "source_mix": {
        "organic": 0.58,
        "recommendation": 0.31,
        "sponsored": 0.11
      },
      "guidance": [
        "Apply after strengthening backend project evidence."
      ]
    },
    "learning_gaps": [
      {
        "skill": "Docker",
        "suggestion": "Build a small portfolio project that demonstrates Docker...",
        "resource_type": "practice_project",
        "cv_edit": {
          "action": "cv_edit_command",
          "method": "POST",
          "endpoint": "/api/v1/cvs/{cv_id}/ai-edit-command",
          "cv_id": "uuid",
          "skill": "Docker",
          "rationale": "Build a small portfolio project that demonstrates Docker...",
          "request": { "instruction": "Add concrete evidence for the \"Docker\" skill..." },
          "requires_confirmation": true
        }
      }
    ],
    "apply_readiness": {
      "ready": true,
      "blocked_reason": null,
      "already_applied": false,
      "deadline_passed": false,
      "has_active_cv": true
    },
    "next_actions": [
      {"action": "select_best_cv", "cv_id": "uuid", "label": "..."},
      {"action": "improve_cv", "cv_id": "uuid", "label": "..."},
      {"action": "apply", "label": "...", "ready": true, "blocked_reason": null},
      {"action": "save_job", "label": "..."},
      {"action": "compare_adjacent_roles", "label": "..."}
    ]
  }
}
```

Rules:

- `competition.signal = "low_signal"` when sample size or job data is too weak
  (fewer than 3 active applications); the frontend hides precise `score`/`label`
  (both `null`) and shows the softer `guidance` list instead.
- Competition outputs are aggregate/bucketed only. Never expose other applicants,
  exact rank, raw CV text, raw model confidence, provider/model names, prompts,
  token counts, or internal cost.
- `competition.applicant_quality_bucket` (`strong`/`mixed`/`developing`) and
  `competition.student_standing_bucket` (`ahead_of_most`/`middle_of_pack`/`behind_most`)
  are derived (B-587, 2026-07-08) from the persisted `cv_job_fit_scores` read model:
  the aggregate quality is the pool's fit-score distribution (MAX score per distinct
  OTHER user; the requesting student is excluded) and the standing is the student's
  coarse position within it. Both are `"unknown"` below the sample threshold (fewer
  than 5 scored applicants). The "pool" is distinct other users with a persisted fit
  score for the job (a scored-interest proxy), computed independently of the
  application-volume `signal` — so a job can be `low_signal` yet still surface a
  quality bucket. Aggregate buckets only: never expose per-applicant identity, exact
  score, rank, or percentile.
- `fit.status = "no_active_cv"` when the caller has no eligible CV; every scored
  field is `null` and `improvement_actions` carries a single "create a CV" hint.
- `selected_cv_id` reflects the `cv_id` query param only when it belongs to the
  caller's active CV library; otherwise it is `null` and `fit`/`competition`
  score the recommended (`best_cv_id`) CV instead.
- `apply_readiness.blocked_reason` priority: `already_applied` >
  `deadline_passed` > `no_active_cv` > `null` (ready).
- The endpoint internally reuses `/cvs/job-fit` (`documents.job_fit_service`)
  for the deterministic fit score; the frontend should prefer this combined
  endpoint over calling `/cvs/job-fit` and `/jobs/{job_id}/competition-signal`
  separately for signed-in job detail.
- **Authoritative fit contract (WS-3 consolidation, 2026-07-08).** This is the
  ONE endpoint the signed-in job-detail page calls on load for deterministic fit +
  bands + matched/gaps + competition + next actions. It NEVER invokes the model
  (score/bands are deterministic), so default page load has no model cost. The AI
  narrative + structured matching detail is a clearly-separated on-demand sub-call
  (`GET /jobs/{job_id}/fit-explanation`, below). `GET /cvs/job-fit` remains for the
  CV-Studio fit rail / other consumers but should NOT be fired on the job-detail
  page. Do not re-introduce a third overlapping fetch on this surface.
- `learning_gaps[].cv_edit` is a confirmation-gated CV-Studio hand-off (or `null`
  when there is no target CV): a ready-to-send `POST /cvs/{cv_id}/ai-edit-command`
  body that drafts an improvement for the gap. It NEVER auto-applies — the
  edit-command returns a PENDING diff the student must accept (which creates a new
  version and charges `cv_edit_command` energy). The instruction is advisory
  ("only if you genuinely have experience") and never asserts the student has the
  skill.

### CV-JD Fit Analysis (On-Demand AI Narrative + Structured Suggestions)

`GET /api/v1/jobs/{job_id}/fit-explanation?cv_id={optional_uuid}`

Authenticated-student only. The clearly-separated, on-demand half of the fit
contract: the deterministic score/bands return instantly from
`/jobs/{job_id}/student-intelligence`; the frontend fires THIS on the "Analyze CV"
action to fill in the AI narrative + structured matching detail. The model is
invoked only here (energy-metered via `cv_fit_explanation`, once per content
version, cached + reused across reloads and cross-CV). Default page load never
reaches it.

```json
{
  "data": {
    "cv_id": "uuid-or-null",
    "explanation": "short user-facing summary or null",
    "analysis": {
      "overall_suggestion": "Highlight cloud/infra impact to close the platform gap.",
      "matched_evidence": [
        {
          "requirement": "Python",
          "cv_evidence": "Built REST APIs with Python and FastAPI",
          "evidence_strength": "strong",
          "reasoning": "Hands-on backend delivery at a startup."
        }
      ],
      "gaps": [
        {
          "requirement": "Kubernetes",
          "cv_evidence": null,
          "severity": "hard",
          "reasoning": "No container-orchestration evidence in the CV.",
          "suggestion": "Add a project deploying a service to Kubernetes, if you have genuine experience with it."
        }
      ]
    },
    "improvements": [
      {
        "action": "cv_edit_command",
        "method": "POST",
        "endpoint": "/api/v1/cvs/{cv_id}/ai-edit-command",
        "cv_id": "uuid",
        "skill": "Kubernetes",
        "rationale": null,
        "request": { "instruction": "Add concrete evidence for the \"Kubernetes\" skill..." },
        "requires_confirmation": true
      }
    ],
    "ai_explanation_available": true
  }
}
```

Rules:

- `explanation` is the free-text HR-evaluator summary (backward-compatible field).
- `analysis` is the STRUCTURED matching detail (previously computed then discarded):
  per-requirement `matched_evidence` with an `evidence_strength` label
  (`strong`/`moderate`/`weak`), confirmed `gaps` with a `severity`
  (`hard`/`soft`) and a per-requirement advisory `suggestion`, plus an
  `overall_suggestion`. `null` when the AI narrative is unavailable (gate off /
  provider failure / a cross-CV summary-reuse that carried no CV-specific detail).
  It never contains the model's numeric score, provider/model/token/prompt, or any
  raw confidence — the authoritative 0-100 product score lives in the deterministic
  fit contract only.
- `improvements` is one confirmation-gated CV-Studio hand-off per deterministic fit
  gap (same shape as `learning_gaps[].cv_edit`). It is DETERMINISTIC and present
  even when the AI narrative is unavailable, so the "apply this improvement" loop
  always works. Never auto-applies.
- `cv_id` (optional query) explains that CV when it belongs to the caller and is
  scored; otherwise the recommended CV (a foreign/unknown `cv_id` degrades to the
  recommendation, never `404`). Hidden/closed/missing jobs -> `404`. No active CVs
  -> `{ cv_id: null, explanation: null, analysis: null, improvements: [],
  ai_explanation_available: false }`.

### CV Export

`POST /api/v1/cvs/{cv_id}/export`

`version_id` is a `cv_versions` UUID. Clients obtain it from the CV detail
(`current_version_id`) or the version history (`GET /cvs/{cv_id}/versions`); it
must belong to `{cv_id}` (else `404`).

```json
{
  "version_id": "uuid",
  "format": "pdf",
  "idempotency_key": "client-generated-key"
}
```

Response can be immediate or queued:

```json
{
  "data": {
    "export_id": "uuid",
    "status": "queued",
    "download_url": null
  }
}
```

`GET /api/v1/cv-exports/{export_id}` returns status and signed download URL when ready.

## Application CV Selection Contract

`POST /api/v1/applications`

```json
{
  "job_id": "uuid",
  "cv_selection": {
    "type": "builder_cv",
    "cv_profile_id": "uuid-or-null",
    "cv_version_id": "uuid-or-null",
    "uploaded_document_id": "uuid-or-null"
  },
  "cover_letter": "optional text",
  "screening_answers": {},
  "is_anonymous": false,
  "idempotency_key": "client-generated-key"
}
```

Allowed `cv_selection.type` values:

- `builder_cv`
- `uploaded_document`

Submitting an application creates immutable application snapshot rows for the
selected CV/version or uploaded document, screening answers, cover letter,
student consent, public job/company display fields, and structured job
requirements used for fit/eligibility at submission time. Later edits to the CV,
uploaded document metadata, JD, company profile, or screening questions do not
change the submitted application history.

Duplicate application behavior is explicit: `(student_id, job_id)` allows at
most one non-archived application. If a draft exists, the API returns
`409 { reason: "application_draft_exists", application_id, resume_url }`; if a
submitted/active application exists, it returns
`409 { reason: "application_exists", application_id, status }`. A true retry
with the same `idempotency_key` returns the existing result.

Student application workspace endpoints must expose the canonical status
timeline, next action, snapshot summary, messages/interviews/offers pointers,
withdrawal availability, and localized status copy without exposing partner
internal notes or other candidates.

## AI Usage & Quota

Two read endpoints power the caller's own AI-usage surfaces. Both are
request-count only and **never** expose provider/model names, model aliases,
token counts, cost, or latency (`docs/AI_PRODUCT_SPEC.md` §15). Counts come from
real `ai_usage_log` rows for the authenticated caller.

- `GET /api/v1/ai/usage/me` — the sidebar meter. Returns
  `{ day, week, warning, blocked, blocked_scope }` where each window is
  `{ used, limit, pct }`. `blocked_scope` is `"day" | "week" | null` and the
  weekly window dominates (an exhausted week blocks even with daily room). This
  is the same gate the gateway enforces with `409 QUOTA_EXCEEDED`.
- `GET /api/v1/ai/usage/summary` — the billing/usage panel. Extends `/me` with:
  - `day_reset`, `week_reset` — ISO-8601 UTC instants the windows reset;
  - `window_days` (default `30`) and `total` — total requests in the window
    (includes system tasks not shown per-feature);
  - `by_feature: [{ feature, count }]` — sorted desc. `feature` is a stable
    **product code** the client localizes (`assistant`, `cover_letter`,
    `cv_edit`, `cv_import`, `interview`, `scorecard`, `screening`, `jd_draft`,
    `jd_import`, `market_intel`, `other`). Internal `task_type` labels are mapped
    server-side; system/internal tasks (embeddings, rerank, translation, eval
    judge) are excluded from the breakdown but still count toward `total`;
  - `recent: [{ feature, ok, at }]` — most-recent-first activity, `at` an ISO-8601
    UTC instant, `ok` the success flag. No other fields.

Both require authentication (guest → `401`). The summary reflects request-count
usage; per-feature credit charges depend on the billable-ledger call-site
closure (backlog B-580) and are additive to this contract when landed.

## SSE Contract

Use for AI streaming and long-running operation updates.

**Reconciled 2026-07-02 (ai-engineer):** this section previously documented an
aspirational event shape (`message.delta`/`tool.started`/`tool.confirmation_required`)
that was never implemented and never adopted by the frontend. The contract
below is what `ai_assistant`'s `GET /api/v1/ai/sessions/{session_id}/stream`
actually emits today and what `frontend/src/components/ai-assistant/ai-chat-window.tsx`
actually consumes — this is the real, shipped, integrated contract; treat it
as authoritative. `docs/AI_PRODUCT_SPEC.md` §5.3 has been updated to match.

Events (`event: <type>` is implicit — the client dispatches on `data.type`, a
single generic SSE `message` event, not distinct named SSE event types):

```json
{"type": "status", "code": "received|retrieving_context|thinking|synthesizing|using_tool|confirming_action|responding"}
{"type": "tool_call", "name": "search_jobs"}
{"type": "tool_result", "name": "search_jobs", "ok": true}
{"type": "token", "text": "word "}
{"type": "done", "message": { /* full persisted ChatMessage, incl. requires_confirmation for a pending tool call */ }}
{"type": "error", "code": "auth_required|session_not_found|invalid_message"}
```

- A pending `confirmation_required` tool call is delivered via a `done` event
  whose `message.requires_confirmation` is `true` — there is no separate
  `tool_confirmation_required` event type.
- `token` is word-level text, no `index` field.
- SSE payloads must not include provider or model internals (name, alias,
  token counts, latency).

## Audit Event Contract

Every write action emits audit data:

```json
{
  "actor_id": "uuid",
  "active_identity_id": "uuid",
  "action": "application.submitted",
  "target_type": "application",
  "target_id": "uuid",
  "org_id": "uuid-or-null",
  "metadata": {},
  "occurred_at": "iso-datetime",
  "request_id": "req_..."
}
```

## Partner & Student Registration Contracts

### Partner Registration

`POST /api/v1/partner-registration`

```json
{
  "company_name": "Acme Corp",
  "tax_code": "0123456789",
  "company_website": "https://acme.com",
  "company_size": "50-200",
  "industry": "technology",
  "contact_name": "Nguyen Van A",
  "contact_title": "HR Manager",
  "email": "hr@acme.com",
  "phone": "+84912345678",
  "description": "...",
  "logo_upload_id": "uuid-or-null"
}
```

Response: `{ "data": { "registration_id": "uuid", "status": "pending_review" } }`

First registrant automatically receives admin role after approval.

### Partner Approval (University Admin)

`POST /api/v1/admin/partners/{partner_id}/approve`

```json
{ "package_id": "uuid", "trust_level": "standard", "note": "optional" }
```

`POST /api/v1/admin/partners/{partner_id}/reject`

```json
{ "reason": "required text" }
```

---

## Subscriptions & Manual Billing (V1, ADR-0010 — IMPLEMENTED)

V1 ships a **manual-billed subscription** core (ADR-0010): a student or partner
**requests a paid plan**, a university/admin records a **bank transfer** to
activate it for a **fixed window**, the plan's **`limits` map overrides the
defaults** (the CV active-library cap is the first real consumer — see *CV Library
And Quota*). A single **audience-typed `subscription_plans`** reference table (4
seeded plans: `student_free`, `student_pro`, `partner_basic`, `partner_pro`) serves
both audiences, with limits as a structured JSON map; a single polymorphic
`subscriptions` table keys to a **user** (student) or **org** (partner) principal.
Free/default tier == **no subscription row**. Mirrors the ADR-0009 advertising
manual-billing pattern (frozen price, manual `mark_paid`, university-only gate,
ADR-0003 scheduler sweeps, revenue roll-up, optimistic `version`, per-write audit,
`404` cross-principal masking). **Plans are auth-gated, scoped by audience** —
public sees nothing (reconciles the older `/packages/partner | Public` row).

**Lifecycle (`subscriptions.status`):** `pending` (requested, awaiting manual
bank-transfer confirmation) → `active` (admin `mark_paid`; window
`[start_at, end_at]` = `now .. now+plan.duration_days`; plan limits apply) →
`expired` (scheduler, window closed; reverts to default) | `cancelled` (requester
or admin; reverts to default). `mark_paid` is the single activation gate (no
separate `approved` state). Renewal = a fresh request once the prior row is
terminal. One in-flight (`pending`/`active`) subscription per principal.

| Path | Method | Actor | Notes |
|---|---|---|---|
| `/billing/plans?audience=student\|partner` | GET | Authenticated (`billing:view`) | Visible plans for an audience (name, price, period, `limits` summary). Auth-gated. |
| `/billing/subscription` | GET | Subscriber (`billing:view`) | My current subscription (`active`/`pending`) + effective `limits` + audience `default_plan`; null-safe when none. |
| `/billing/subscription` | POST | Student / Partner Admin (`billing:subscribe`) | Request a paid plan → `pending`; freezes `price_amount`/`billing_period`; returns `payment_instructions` (bank-transfer details). `409 subscription_exists` if a pending/active row exists; `422 plan_audience_mismatch` if `plan.audience` ≠ principal kind. |
| `/billing/subscription/cancel` | POST | Subscriber (`billing:subscribe`) | Cancel my `pending`/`active` subscription (reverts to default). Optimistic `version`. |
| `/admin/billing/subscriptions` | GET | University (`billing:moderate`) | ALL subscriptions (filter `status`/`audience`/`principal_id`) + `meta.revenue` roll-up `{ active_revenue_amount, currency, active_count, pending_count }`. |
| `/admin/billing/subscriptions/{id}/mark-paid` | POST | University/admin (`billing:moderate`) | Records manual/bank-transfer `payment_reference` (sets `paid_at`/`paid_by`/window) → `active`. `422 reference_required`. |
| `/admin/billing/subscriptions/{id}/cancel` | POST | University (`billing:moderate`) | Admin revoke/reject (coded reason) → `cancelled`. |

The `/admin/billing/*` university gate mirrors the advertising gate (superadmin OR
member of a `university`-type org holding `billing:moderate`; a partner Admin's
`*:*` cannot self-confirm payment). **Billing data is PII-sensitive:** the revenue
roll-up + `payment_reference` appear **only** in admin responses + audit `after`,
**never** in notification bodies, non-admin responses, or logs. Presenters emit
vi+en labels (`status_label`, `audience_label`, `billing_period_label`) + the
frozen price; never raw enum codes or another principal's data.

### Limit-resolution facade (the integration seam)

`billing/application/limit_facade.py` is the **only** way another module reads tier
limits — `resolve_limit(session, principal, *, key, default)` /
`resolve_limits(session, principal)` return the principal's **active** paid
subscription's `plan.limits` map (org-sub when `principal.org_id` set, else
user-sub; only `status='active' AND end_at > now`), else the caller's default. The
dependency is one-way (`documents → billing`, lazy import; billing never imports
documents). **First consumer:** `cv_service._active_cv_limit` resolves
`cv_active_quota` through the facade (default `student_active_cv_quota` = 5);
`student_pro` overrides it to 10 and flips the CV-quota `quota_source` to
`"subscription"`. V1 *resolves+displays* all limit keys but only **enforces**
`cv_active_quota` (a standing cap, no period reset); the other keys
(`job_post_quota`, `pdf_exports_per_month`, …) plug into the same facade in later
slices.

### Scheduler jobs (ADR-0003 registry)

| Job | Cadence | Action |
|---|---|---|
| `billing.expiry_sweep` | ~600s | `status='active' AND end_at ≤ now` → `expired` (reverts limits to default), notify owner. Status/time-gated + idempotent. |
| `billing.expiring_notice` | nightly | `status='active' AND end_at ≤ now+7d AND expiring_notified_at IS NULL` → enqueue "expiring soon" + set dedupe stamp. |

### Create subscription

`POST /api/v1/billing/subscription`

```json
{ "plan_id": "uuid" }
```

Response is the `pending` subscription + a `payment_instructions` object (bank
name / account / note hint) for the manual transfer. `price_amount` is frozen from
the plan at request.

> **Deferred end-state (NOT built in V1; later ADRs).** The per-persona
> `/subscriptions/partner` + `/subscriptions/student` + `/packages/{student,partner}`
> split, a multi-payment `/billing/payment-records` ledger, AI `/credits/balance`,
> upgrade proration / scheduled downgrade / refund window / grace+dunning /
> auto-renew, and metered-quota *enforcement* + `quota_usage` period-reset are the
> DATA_MODEL §19 / BUSINESS_LOGIC §1.2–§1.6 reference end-state — superseded for V1
> by the unified `subscription_plans`/`subscriptions` per ADR-0010.

---

## Admin AI Settings (V1 — IMPLEMENTED, ADR-0011)

Admin governance of masked AI settings, feature flags, per-day budget, and the
kill switch. Real provider/model registry management is superadmin-only. Module
`backend/app/modules/ai_settings/`; entity `ai_settings` — a
**single platform-scoped row** (migration `0022`). **SECRECY (non-negotiable):** the
table and every response store/expose **alias names + toggles + budget + derived
status only** — never the raw API key, base URL, concrete provider/model id, prompt,
latency, or token counts (the table has no key column to leak; keys live solely in
`backend/.env`).

**RBAC:**

- Masked AI settings/status: superadmin OR a member of a `university`-type org
  holding `ai_settings:read` (GET) / `ai_settings:manage` (masked PATCH + kill
  switch). End users and partners → `403` (the surface is invisible to them).
- Real provider/model registry CRUD, concrete model ids, provider routing
  chains, price rows, and provider health probes: **superadmin only**. Ordinary
  university staff never receive provider/model names or concrete ids, even with
  `ai_settings:read`/`manage`.

**Endpoints:**

| Path | Method | Actor | Notes |
|---|---|---|---|
| `/admin/ai-settings` | GET | University (`ai_settings:read`) / superadmin | Masked effective settings (lazily seeds the singleton). |
| `/admin/ai-settings` | PATCH | University (`ai_settings:manage`) / superadmin | Partial update of aliases (allowlist-validated), feature flags, `daily_budget_usd`, `real_calls_enabled`, `rollout_state`, `notes`. Audited before/after diff; republishes the runtime snapshot. |
| `/admin/ai-settings/disable-ai` | POST | University (`ai_settings:manage`) / superadmin | Kill switch: forces `real_calls_enabled=false` + `rollout_state='offline'`, audited, republished. |

**Response shape (masked):**

```json
{
  "data": {
    "scope": "platform",
    "models": { "chat": "chat_cheap", "reasoning": "reasoning_cheap",
                "embedding": "embedding_cheap", "eval": "eval_cheap" },
    "allowed_aliases": { "chat": ["chat_cheap"], "reasoning": ["reasoning_cheap"],
                          "embedding": ["embedding_cheap"], "eval": ["eval_cheap"] },
    "feature_flags": { "cv_llm_structuring_enabled": false,
                        "job_fit_ai_explanation_enabled": true },
    "daily_budget_usd": "1.00",
    "rollout_state": "enabled",
    "real_calls_enabled": false,
    "key_configured": false,
    "real_calls": "offline",
    "version": 1,
    "updated_at": "2026-06-28T..."
  }
}
```

**Derived status (the only window into provider state — no secret revealed):**

- `key_configured: bool` — whether a non-placeholder key is present in env (never the key).
- `real_calls: "offline" | "available" | "enabled"`:
  - `offline` — env gate (`AI_REAL_CALLS_ENABLED`) off **or** no key (env-blocked; an admin cannot override).
  - `available` — env+key OK but the DB toggle/rollout keeps real calls off.
  - `enabled` — real calls fully active (post-precedence).

**Precedence (env+key is the HARD CEILING; the DB can only restrict/select within it):**

```
real_calls_active = AI_REAL_CALLS_ENABLED(env)
                    AND key_present(env)
                    AND (row.real_calls_enabled AND row.rollout_state == 'enabled')
```

With **no key**, persisting `real_calls_enabled=true` is allowed but **inert** — the
response stays `real_calls: "offline"` so the admin sees the env block. An admin can
DISABLE AI or SELECT aliases/flags/budget within the permitted envelope, but can
**never** enable real calls beyond what env+key permit.

**Validation:** alias fields accept only allowlisted names (`422 VALIDATION_FAILED`
on a raw `vendor/model-path`); `rollout_state ∈ {enabled, paused, offline}`;
`daily_budget_usd ∈ [0, 10000]`.

**Budget:** `daily_budget_usd` is a stored field + a `budget_guard.check` seam
(no-op accumulator in V1, never trips offline). The metered `ai_usage_log` ledger +
`402 BUDGET_EXCEEDED` enforcement are the named deferred integration point.

### ADR-0011 Amendment (ADR-0011.2 — superadmin-only provider/model identity)

**Status:** Accepted (product owner decision, 2026-07-08), superseding
ADR-0011.1's grantable provider-identity exception.

**Context:** the system must not reveal which providers or concrete models are
used to students, partners, guests, or ordinary university staff. The platform
belongs to the university, but provider/model choice is a superadmin operations
concern, not a normal staff configuration detail.

**Decision:**

- Any endpoint returning `provider_internal`, concrete `model_id`, provider
  routing chains, provider health identity, provider/model price rows, or model
  registry CRUD is **superadmin-only** (`principal.is_superadmin`), enforced in
  service/application layer as well as router dependencies.
- `ai_settings:view_provider_identity` is no longer sufficient to reveal raw
  provider/model identity. If the permission remains in the catalog for
  backwards compatibility, it is ignored for identity disclosure unless the
  principal is also superadmin.
- University staff with `ai_settings:read`/`manage` may operate only masked
  settings: aliases/slot handles, feature flags, rollout state, budget/limit
  state, kill switch, and user-safe health labels. They never receive concrete
  provider/model strings.
- Students, partners, guests, public pages, exports, notifications, logs
  visible to non-superadmins, and org-scoped dashboards must never include
  provider/model names, concrete ids, token counts, latency, prompt text, API
  keys, base URLs, or routing internals.
- Superadmin provider/model reads and all provider/model writes are audited:
  `ai_settings.provider_identity_viewed`,
  `ai_settings.provider_created`, `ai_settings.provider_updated`,
  `ai_settings.provider_deleted`, `ai_settings.model_created`,
  `ai_settings.model_updated`, `ai_settings.model_deleted`,
  `ai_settings.provider_price_updated`, `ai_settings.routing_chain_updated`,
  and kill-switch/key-rotation events where applicable.

**Response examples:**

```json
// Non-superadmin university staff: masked only
{
  "alias": "chat_default",
  "status": "enabled",
  "health": "available",
  "budget_state": "ok"
}
```

```json
// Superadmin only
{
  "alias": "chat_default",
  "provider_internal": "openai_compatible",
  "model_id": "internal-model-id",
  "status": "enabled",
  "price_configured": true
}
```

**Consequences:** the routing canvas can still exist for university operators,
but it must be masked unless the viewer is a platform superadmin. Provider/model
CRUD belongs in the superadmin operations console, not ordinary university
workspace screens.

---

## Quota

| Path | Method | Description |
|---|---|---|
| `/quota/partner` | GET | **(Deferred — DATA_MODEL §19 end-state.)** Per-period partner quota usage. V1 *resolves+displays* these limit keys through the ADR-0010 `limit_facade` but only **enforces** the CV active-library cap (see *Subscriptions & Manual Billing* + *CV Library And Quota*); `quota_usage` period-reset/carryover is not built yet. |

```json
{
  "data": {
    "job_post": { "used": 3, "limit": 10, "resets_at": "2026-07-01" },
    "passive_search": { "used": 12, "limit": 50, "resets_at": "2026-07-01" },
    "email_blast": { "used": 1, "limit": 5, "resets_at": "2026-07-01" },
    "spotlight_slots": { "used": 1, "limit": 2, "permanent": true }
  }
}
```

---

## Discovery & Guest Personalization (V1 — IMPLEMENTED, first slice)

First slice of the Discovery/Recommendation/Ads rescue
(`docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md` §3/§8): the privacy-safe guest session
+ the analytics event sink that ad-funded surfaces and recommendation rails call.
Ranking/recommendation rails and the public delivery rails (S2) build on this.
Module `backend/app/modules/discovery/`; entities `discovery_sessions` +
`discovery_events` (migration `0020`).

**Endpoints (implemented):**

| Path | Method | Actor | Notes |
|---|---|---|---|
| `/discovery/events` | POST | Public (optional-auth) | Record one privacy-safe analytics event (`impression\|click\|view\|apply_start\|save_intent\|event_register_intent`). Sets/refreshes the httpOnly `vinuni_discovery` cookie. Returns only `{recorded: true}` — never the session id, scope, or tags. |
| `/discovery/session/reset` | POST | Public (optional-auth) | Clear stored coarse signals; `opt_out:true` opts the session out of personalization and drops the cookie. Honors the privacy reset preference. |

`POST /discovery/events` body:

```json
{
  "event_type": "impression",
  "source_surface": "homepage_recommended",
  "target_type": "job",
  "target_id": "<uuid>",
  "placement_id": "<uuid|null>",
  "idempotency_key": "<8-120 chars, unique>",
  "locale": "vi",
  "signal_tags": { "categories": ["data analyst"], "work_mode": "remote" }
}
```

- The schema is `extra="forbid"` — a stray PII-looking field is `422 VALIDATION_FAILED`,
  never stored. An unknown `event_type` / `source_surface` / `target_type` is also `422`.
- **Idempotent** on `idempotency_key` (same key → exactly one `discovery_events` row).
- `scope` (`anonymous|session|user`) is derived **server-side** from the principal +
  discovery cookie; it is never accepted from the client.
- `placement_id` is retained **only** for sponsored surfaces (`homepage_sponsored`,
  `search_sponsored`, `right_rail_banner`, `email_sponsored`, or a `banner` target);
  on any organic/recommended/curated surface a supplied `placement_id` is dropped —
  organic, recommended, sponsored, and university-curated inventory stay separate.
- `signal_tags` is optional and re-sanitized against the allowlist before any
  storage (only allowlisted keys survive — see below).

**Cookie behavior.** First-party `vinuni_discovery` cookie carries ONLY a random
session uuid (no PII). `httpOnly`, `SameSite=lax`, `Secure` derived from env (off on
`local`), `path=/api/v1/discovery`, `max_age = DISCOVERY_SESSION_TTL_DAYS` (30d).
Set/refreshed on every `events` call unless the session opted out; cleared on
`reset` with `opt_out:true`.

**Privacy allowlist (NON-NEGOTIABLE, enforced in the service layer).** Guest
discovery sessions store ONLY privacy-safe coarse signals
(`docs/SECURITY_PRIVACY.md`, `.claude/rules/backend.md`). The allowlist is
default-deny — anything not listed is stripped and never persisted:

- **Allowed `coarse_tags` keys** (clamped/de-duped, lists capped ≤20, terms ≤64–80
  chars): `categories`, `industries`, `role_families`, `company_ids` (uuids),
  `event_ids` (uuids), `search_terms`, `work_mode` (`onsite|remote|hybrid`), `city`
  (a coarse FILTER selection, not GPS), `device_type` (`desktop|mobile|tablet`).
  Plus the `locale` column.
- **Forbidden / stripped** (never stored, never audited): name, email, phone,
  username; raw IP, GPS, latitude/longitude, exact location, address; raw CV /
  resume / document text; sensitive categories (health, ethnicity/national origin,
  gender/sexual orientation, religion, politics, disability, pregnancy, financial
  status); cross-site / third-party ad ids (`gaid`, `idfa`, `fbclid`, `gclid`,
  `ad_id`, `advertising_id`, `third_party_id`, `device_id`, fingerprints).

**Audit/privacy.** `discovery_events` is itself the append-only analytics ledger for
discovery interactions, so the high-volume event/session-create path is not
separately audited. The control-plane privacy action `discovery.session_reset`
writes a metadata-only audit row (`{opt_out, signals_cleared}`) with NO coarse tags
or PII; IP/UA are salted-hashed via `app/shared/hashing.py`.

**Scheduler job** (ADR-0003 registry; time-gated + idempotent):

| Job | Cadence | Action |
|---|---|---|
| `discovery.session_cleanup` | nightly | prune sessions past `expires_at` (short TTL) + events older than `DISCOVERY_EVENT_RETENTION_DAYS` (90d). Re-tick is a no-op. |

---

## Recommendation & Ranking Layer (V1 — IMPLEMENTED, slice 2)

Second slice of the Discovery/Recommendation/Ads rescue
(`docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md` §5/§8): the deterministic
organic-relevance ranker + sponsored-slot separation that powers the public
recommendation rails. Policy lives in `backend/app/modules/discovery/` (domain
`ranking.py`/`taxonomy.py`, application `ranking_service.py`/`health_service.py`);
it owns NO ORM and reaches data only through read facades
(`opportunities.ranking_read`, `advertising.inventory_facade`,
`documents.cv_ranking_facade`, `student_profiles.preferences_facade`) — all using
the SAME public-visibility predicate as `GET /jobs`.

**Endpoints:**

| Path | Method | Actor | Notes |
|---|---|---|---|
| `/jobs/recommendations` | GET | Public (optional-auth) | Personalized jobs. `?q=`, `?limit=` (1–30, default 12). Authenticated student → CV-fit + preference reasons + `recommended_cv_id`; guest → `discovery_session` coarse-tag reasons OR honest `recent`/`popular` fallback. Returns `{ source, personalized, items[] }`. Registered **before** `/jobs/{job_id}` so the static path is never captured. |
| `/jobs/{id}/similar` | GET | Public (optional-auth) | Deterministic similar public jobs by skill/role-family overlap. `?limit=` (1–20, default 6). Eligibility-filtered; hidden/closed seed → `404` (enumeration-safe). `{ job_id, items[] }`; `items: []` when nothing genuinely similar (hide-if-empty). |
| `/admin/discovery/health` | GET | University / superadmin (`jobs:moderate` + university org) | Privacy-safe inventory + delivery health: empty rails, active sponsored count, missing/broken sponsored logos, CTR/impression outliers, policy flags. Aggregates only — no user/session id or PII. Partner Admin (`*:*`) is blocked by the org-type gate. |

**Recommendation item shape:**

```json
{
  "id": "<job uuid>", "title": "...", "company": { "...": "..." },
  "score": 82,
  "source": "recommended",
  "reason_codes": [ { "code": "cv_fit", "score": 82, "cv_id": "<uuid>", "cv_title": "Backend CV" } ],
  "recommended_cv_id": "<uuid|null>",
  "sponsored_disclosure": null,
  "placement_id": null
}
```

**`source` values** (the inventory class of a list / item):

- `recommended` — a genuine personalization signal exists (query / session tags /
  confirmed preferences / CV). Only then may a list call itself "recommended".
- `recent` — honest fallback: newest eligible inventory (no signal).
- `popular` — honest fallback: most-applied/-viewed eligible inventory.
- `sponsored` — paid inventory filling a **defined slot** (carries a non-removable
  `sponsored_disclosure` + `placement_id`).
- `curated` — university-curated inventory (reserved; spotlight/curated rails).

**`reason_codes` vocabulary** (user-safe codes; the frontend localizes — never raw
enums, never provider/model/confidence). Each entry is `{ "code", ...params }`:

| Code | Params | Meaning |
|---|---|---|
| `cv_fit` | `score`, `cv_id`, `cv_title` | Best CV's 0-100 product fit for this job. |
| `preferred_job_type` | `value` | Matches a confirmed open-to-work type. |
| `preferred_location` | `value` | Matches the confirmed preferred city. |
| `preferred_field` | `value` | Matches the confirmed major/field. |
| `matches_search` | `term` | "Because you searched X" (query or session term). |
| `similar_industry` | `value` | Matches a viewed industry/category. |
| `similar_role` | — | Matches a viewed role family. |
| `skill_match` | `skills[]` | Shared skill tokens (similar-jobs). |
| `verified_employer` | — | Employer verified by VinUni. |
| `deadline_soon` | `days` | Apply window closing within 7 days. |
| `popular` | — | Trending / most-applied. |
| `recent` | — | Newly posted (fallback). |

**Ranking policy (spec §5, deterministic — no AI dependency).**

1. **Eligibility** — the single `opportunities.visibility` predicate at the
   caller's persona tier (no hidden/unmoderated/expired/closed leak).
2. **Organic relevance** — a 0-100 **product score** (renormalized weighted blend
   of query match, CV-fit, preference match, session-tag match, recency, employer
   quality, popularity). It is a product score, **not** a model confidence; no
   provider/model/token/embedding internal is ever exposed.
3. **Sponsored slot selection** — live placements (via `advertising.inventory_facade`)
   fill the defined `SPONSORED_SLOTS` (positions `0, 4`) ONLY. Sponsored items are
   deduped out of the organic stream and **never reorder organic relevance**: the
   organic subsequence of the response is exactly the organic ranking, untouched.
4. **Diversity & freshness** — avoid the same company back-to-back when avoidable.
5. **Explanation** — every recommended item carries ≥1 user-safe reason code.

A list with no signal honestly falls back to `recent`/`popular` — it is never
silently mislabelled "recommended". `recommended_cv_id` is the best CV for that
specific job (authenticated student only); `null` otherwise.

The student dashboard `recommended_jobs` rail uses this same ranker and now
carries `{ source, personalized, items[] }` — a CV-/preference-less student gets
`source: "recent"`/`"popular"`, not a mislabelled "recommended" list.

---

## Advertising — Sponsored / Featured Placements (V1, ADR-0009 — IMPLEMENTED)

V1 ships a **manual-billed sponsored-placement** core (ADR-0009): a partner
requests to sponsor/feature **one of their own jobs or events** for a paid,
date-windowed, university-approved period. There is **no bidding, no budget pacing,
no audience targeting, no banner/video/email creatives, and no payment gateway** in
V1 — those are the deferred `ad_campaigns` end-state documented under *Advertising
Campaigns* below (NOT yet built). Entities: `ad_packages` (seeded fixed-price tiers)
+ `sponsored_placements` (migration `0017`).

**Endpoints (implemented):**

| Path | Method | Actor | Notes |
|---|---|---|---|
| `/advertising/packages` | GET | Partner / any | Pricing tiers (name, price, duration, grants_sponsored/featured). No campaign internals. |
| `/advertising/placements` | GET | Partner | My org's placements, any status (advertiser surface). |
| `/advertising/placements` | POST | Partner (`advertising:create`) | Create draft (`target_type`,`target_id`,`placement_type`,`package_id`,`start_at`,`disclosure_confirmed`). Cross-org/unknown target → `404`. |
| `/advertising/placements/{id}` | GET | Partner owner | Owner detail, else `404`. |
| `/advertising/placements/{id}` | PATCH | Partner (`advertising:edit`) | Edit draft/rejected (optimistic `version`). |
| `/advertising/placements/{id}/submit` | POST | Partner (`advertising:submit`) | draft\|rejected → `pending_approval`. `422 disclosure_required` if not confirmed; `409 active_placement_limit`; `409 placement_exists`. Freezes `price_amount`. |
| `/advertising/placements/{id}/cancel` | POST | Partner | Own placement pre-completed → `cancelled` (flags OFF if active). |
| `/advertising/placements/{id}` | DELETE | Partner | Soft-delete draft/rejected. |
| `/admin/advertising/placements` | GET | University (`advertising:moderate`) | ALL placements (filter `status`/`org_id`) + spend roll-up in `meta.spend`. |
| `/admin/advertising/placements/{id}/approve` | POST | University | `pending_approval` → `approved` (inline-activates if paid + window open). |
| `/admin/advertising/placements/{id}/reject` | POST | University | `pending_approval` → `rejected` (coded reason; `422` if blank). |
| `/admin/advertising/placements/{id}/mark-paid` | POST | University/admin | Records manual/bank-transfer `payment_reference` (sets `paid_at`/`paid_by`); inline-activates if approved + window open. |
| `/admin/advertising/placements/{id}/cancel` | POST | University | Disable any placement immediately (flags OFF) — PRD §13.6. |
| `/admin/advertising/placements/{id}/disclosure-class` | POST | University | Relabel the public inventory class (`disclosure_class`). PAID inventory (placement with `paid_at`) → `409 paid_disclosure_immutable` if relabelled to a non-paid class. |
| `/admin/advertising/creatives/{id}/review` | POST | University | Approve/reject an uploaded creative (`decision`=`approve`\|`reject`; reject needs a note). Only an `approved` creative on an `active` placement serves publicly. |

### Campaign creatives (banner assets) + inventory-class disclosure taxonomy (Visual-Realism §4/§5/§6 — V1: hero + right-rail)

**Inventory classes** (`docs/PRODUCT_INTERACTION_VISUAL_REALISM_SPEC.md` §4):
`organic`, `recommended`, `university_curated`, `strategic_partner`,
`paid_sponsored`, `featured`. A placement carries a **`disclosure_class`** ∈
{`paid_sponsored`, `university_curated`, `strategic_partner`, `featured`} (default
`paid_sponsored` for partner placements; the university may relabel a NON-paid
placement). **Only `paid_sponsored` is PAID** → its disclosure is non-removable;
the others are truthful editorial/partnership labels and are NEVER presented as
paid. Polished bilingual labels (the only thing the public sees):

| `disclosure_class` | vi | en | paid? |
|---|---|---|---|
| `paid_sponsored` | Đối tác tài trợ | Partner-sponsored | yes (non-removable) |
| `university_curated` | VinUni tuyển chọn | Curated by VinUni | no |
| `strategic_partner` | Đối tác chiến lược | Strategic partner | no |
| `featured` | Nổi bật | Featured | no |

A placement projection now carries `disclosure_class`, `disclosure`
(`{class,label,is_paid,is_removable,is_sponsored}`), `creatives[]`,
`missing_primary_slots[]`, and `has_approved_creative`.

**Creative endpoints** (slots `homepage_hero`|`right_rail`|`inline_card`|`event_banner`; V1 wires hero + right-rail to public reads):

| Endpoint | Method | Auth | Notes |
|---|---|---|---|
| `/advertising/placements/{id}/creatives` | GET | Partner owner | List the placement's creatives (owner / `404`). |
| `/advertising/placements/{id}/creatives` | POST | Partner (`advertising:edit` OR `organizations:update`) | Multipart upload: `file`, `slot`, `alt_vi`/`alt_en`, `focal_x`/`focal_y` (0–1), `click_target`, `analytics_source_surface`. Magic-byte image allowlist (PNG/JPEG/WebP) + size cap (`CAMPAIGN_CREATIVE_MAX_MB`, default 5). New creative is `pending` review. Cross-org → `404`; bad slot/focal → `422`. |
| `/advertising/creatives/{id}` | DELETE | Partner owner | Soft-delete (owner / `404`). |
| `/advertising/creatives/{id}/image` | GET | Public | Stable serve route; returns bytes **only** for an `approved` creative on an `active`, in-window placement (else `404`). `Cache-Control: public, max-age=3600`. |

Creative projection: `{ id, placement_id, slot, slot_label, asset_requirements,
image_url, media_type, alt, alt_vi, alt_en, focal_point:{x,y}, click_target,
moderation_status(+label), moderation_note, start_at, end_at,
analytics_source_surface, version }`. The internal `image_path` storage key is
**never** returned; `image_url` is the resolved public serve route with a `?v=`
cache key (mirrors `public_logo_url`).

The `/admin/advertising/*` university gate mirrors the jobs moderation gate
(superadmin OR member of a `university` org holding `advertising:moderate`); a
partner Admin's `*:*` cannot self-approve. Routers are HTTP-only; RBAC + audit +
tenant isolation live in the services. Cross-org → `404`; optimistic `version`
mismatch → `409`; illegal transition → `409`.

**Lifecycle** (`sponsored_placements.status`):

```
draft → pending_approval → approved → active → completed
                    │            │
                    ├─→ rejected (resubmittable)
                    └─→ cancelled (partner pre-completed OR university anytime)
```

`activate` requires `status=approved AND paid_at IS NOT NULL AND start_at ≤ now <
end_at` (approval = university disclosure+spend oversight; payment = admin manual
`mark_paid`; both are preconditions). Presenters emit vi+en labels + the frozen
price + target title — never raw enum codes; the `payment_reference` is admin-only.

**Flag source-of-truth (the load-bearing piece).** `sponsored_placements` is the
SOURCE OF TRUTH for sponsorship; `jobs/events.is_sponsored`/`is_featured` are a
RENDERED PROJECTION recomputed from **active** placements:

```
desired_is_sponsored(target) = EXISTS active placement on target with placement_type IN (sponsored, both)
desired_is_featured(target)  = EXISTS active placement on target with placement_type IN (featured, both)
```

The **only** production writer of the flags is the one-way
`opportunities.application.sponsorship_facade.set_target_flags(...)` setter
(`advertising → opportunities`, never the reverse): it loads the job/event row
`FOR UPDATE`, sets the two booleans, bumps `version`, and writes a
`job.sponsorship_changed` / `event.sponsorship_changed` audit row. Overlapping
placements are correct by construction — a flag stays ON while any active placement
still covers the target. The public **marketplace overview contract is UNCHANGED**:
it still reads the real `is_sponsored`/`is_featured` flags (now placement-driven) via
the existing facades and learns nothing about campaigns; the only thing the public
ever sees is the non-removable `Được tài trợ` / `Nổi bật` label.

**Scheduler jobs** (ADR-0003 registry; status/time-gated + idempotent):

| Job | Cadence | Action |
|---|---|---|
| `advertising.activation_sweep` | ~5 min | approved+paid+window-open → `active`, recompute flags ON |
| `advertising.completion_sweep` | ~5 min | active/approved with `end_at ≤ now` → `completed`, recompute flags (OFF unless another active placement covers target); + T-24h `advertising.ending` notice |
| `advertising.flag_reconcile` | nightly | recompute flags for every target with ≥1 placement (self-healing drift guard) |

Activation also fires **inline** from `approve`/`mark_paid` when the window is
already open; `cancel` of an active placement recomputes flags inline.

**Notifications** (category `advertising`, outbox + in-app feed, vi+en): partner —
`advertising.approved`, `advertising.rejected` (reason), `advertising.payment_recorded`,
`advertising.live`, `advertising.ending`; no spend/PII in non-admin bodies.

---

## Advertising Campaigns (DEFERRED end-state — NOT built in V1)

> Deferred per ADR-0009 (CLAUDE.md manual-billing precedence): CPM/CPC bidding,
> budget pacing, audience targeting, banner/video/email creatives, impression/click
> analytics, and the public placement-delivery / event-tracking endpoints below are
> the future `ad_campaigns` system and are **not implemented**. V1 ships the
> sponsored-placement core documented above.

| Path | Method | Actor |
|---|---|---|
| `/advertising/campaigns` | GET | Partner |
| `/advertising/campaigns` | POST | Partner |
| `/advertising/campaigns/{id}` | GET | Partner |
| `/advertising/campaigns/{id}` | PATCH | Partner (draft only) |
| `/advertising/campaigns/{id}/submit` | POST | Partner |
| `/advertising/campaigns/{id}/pause` | POST | Partner |
| `/admin/advertising/campaigns` | GET | University Admin |
| `/admin/advertising/campaigns/{id}/approve` | POST | University Admin |
| `/admin/advertising/campaigns/{id}/reject` | POST | University Admin |
| `/advertising/placements/{placement}` | GET | Guest or any |
| `/advertising/events` | POST | Guest or any |

### Create Campaign

`POST /api/v1/advertising/campaigns`

```json
{
  "name": "Summer Hiring 2026",
  "campaign_type": "CPM",
  "ad_placement": "job_feed",
  "headline": "Join our team",
  "description": "...",
  "cta_url": "https://...",
  "total_budget": 5000000,
  "daily_budget": 500000,
  "bid_amount": 12000,
  "starts_at": "2026-07-01T00:00:00+07:00",
  "ends_at": "2026-07-31T23:59:59+07:00",
  "targeting": [
    { "dimension": "user_tier", "values": ["vinuni_student", "alumni"] },
    { "dimension": "industry_interest", "values": ["technology"] }
  ],
  "sponsored_label_confirmed": true
}
```

Targeting validator rejects forbidden dimensions (`gender`, `health`, `religion`, etc.) with `VALIDATION_FAILED`.

### Public Placement Delivery

`GET /api/v1/advertising/placements/{placement}`

Allowed placements:

- `public_home_hero`
- `public_home_employer_spotlight`
- `public_home_event_sponsor`
- `job_feed`
- `event_detail`
- `email_digest`

Response returns only approved, active, budget-valid campaigns and must include
the localized disclosure label.

```json
{
  "data": [
    {
      "id": "uuid",
      "placement": "public_home_hero",
      "headline": "Summer internships are open",
      "description": "Apply to verified VinUni partner roles.",
      "creative_url": "signed-or-public-asset-url",
      "cta_label": "Explore roles",
      "cta_url": "/jobs?campaign=uuid",
      "sponsor": {
        "organization_id": "uuid",
        "display_name": "Partner name",
        "logo_url": "signed-or-public-asset-url",
        "is_verified": true
      },
      "disclosure_label": "Được tài trợ"
    }
  ],
  "meta": { "placement": "public_home_hero" }
}
```

`POST /api/v1/advertising/events`

Tracks `impression`, `click`, and `apply_start` with idempotency. Do not store
raw GPS or sensitive attributes; anonymous guests use a privacy-safe session id.

---

## Dashboard Read Models

Dashboards are persona operating surfaces, not generic KPI pages. They read from
projection/read-model tables per `docs/DATA_MODEL.md`; do not build them through
heavy live joins across domains.

| Path | Method | Actor |
|---|---|---|
| `/dashboards/student` | GET | Student/Alumni |
| `/dashboards/partner` | GET | Partner member |
| `/dashboards/university` | GET | University staff |

Common response fields:

```json
{
  "data": {
    "generated_at": "2026-06-27T10:00:00+07:00",
    "stale": false,
    "summary": {},
    "primary_queue": [],
    "next_actions": [],
    "alerts": [],
    "deep_links": []
  }
}
```

Student dashboard minimum:

- profile/CV readiness;
- active applications, upcoming interviews, pending offers, deadlines;
- recommended jobs or search prompts;
- CV next actions;
- unread notifications and event reminders.

Partner dashboard minimum:

- active jobs, pending moderation, new applications, interviews today, offers
  pending, package/quota/ad status;
- jobs/candidates needing action;
- recent applications with job/stage/freshness/owner;
- pipeline overview by job.

University dashboard minimum:

- moderation queue counts for partners/jobs/events/ads/content;
- SLA breaches and operational alerts;
- partner health and career-outcome summaries;
- notification/template delivery issues;
- AI/cost/provider health for admins only.

Empty dashboards must return actionable onboarding/setup items, not blank KPI
cards.

### Market Intelligence (V1 — IMPLEMENTED, 2026-07-02)

| Path | Method | Actor |
|---|---|---|
| `/dashboards/university/market-intelligence` | GET | University staff / superadmin |

Aggregate-only hiring stats (`AI_PRODUCT_SPEC.md` §3 `market_intelligence`):

```json
{
  "data": {
    "active_jobs": 42,
    "jobs_last_30d": 12,
    "jobs_prev_30d": 7,
    "trend": "up",
    "employment_types": [{"type": "full_time", "count": 30}],
    "top_skills": [{"skill": "python", "count": 18}],
    "salary_disclosure_rate": 55,
    "low_signal": false,
    "ai_narrative": "…3-5 sentence aggregate-grounded briefing…",
    "ai_narrative_available": true
  }
}
```

- `ai_narrative` is optional enrichment: gateway failure or `low_signal: true`
  (< 5 active jobs) degrades to aggregates with `ai_narrative_available: false`
  — never an error.
- No per-student, per-application, or partner-name data; counts only. No
  provider/model/token internals.

---

## AI Moderation & Human Review Queue (V1 — IMPLEMENTED, 2026-07-02)

`AI_PRODUCT_SPEC.md` §9.3: AI findings are advisory; a university human makes
every final call. All routes require university staff (`jobs:moderate` +
university org) or superadmin.

| Path | Method | Actor | Notes |
|---|---|---|---|
| `/moderation/review-queue` | GET | University staff | Filters: `status` (PENDING/RESOLVED/DISMISSED), `source`, `limit` |
| `/moderation/review-queue/{id}/resolve` | POST | University staff | Body `{ "note"?: string }` — confirms the finding; 409 if already reviewed |
| `/moderation/review-queue/{id}/dismiss` | POST | University staff | Marks a false positive (feeds human-override-rate SLO §10.4) |
| `/moderation/fraud-scan/jobs/{job_id}` | POST | University staff | Deterministic fraud-signal scan; escalates to queue at §9.3 threshold |

Review item shape:

```json
{
  "id": "…", "source": "content_moderation", "resource_type": "job",
  "resource_id": "…", "severity": "high", "status": "PENDING",
  "findings": {"content_check": {"flagged": true, "policy_violation": true, "findings": []}},
  "resolution_note": null, "created_at": "…", "reviewed_at": null
}
```

Fraud scan response exposes `risk_level` wording + reason codes only — the raw
internal `risk_score` never appears in API responses.

Producers writing to the queue today: JD-draft bias/content escalation
(`jd_ai_service`) and the on-demand fraud scan. JD draft responses now include
both advisory fields: `bias_check` and `content_check`.

---

## Company Reviews

**IMPLEMENTED — Module 13 / E19 slice-1 (ADR-0013), migration `0025`.** Endpoints
as built (university moderation gate = superadmin OR `jobs:moderate` +
org_type=university; a dedicated `reviews:moderate` grant is a later refinement).
The public payload never includes `reviewer_id` and masks the author when
`is_anonymous`; trust/status arrive as friendly localized labels (no raw enums).

| Path | Method | Actor | Notes |
|---|---|---|---|
| `/companies/{slug}/reviews` | GET | Guest/any | Public PUBLISHED+FLAGGED list (flagged stays visible). `?limit`, `?locale`. Non-listable slug → 404. |
| `/companies/{slug}/reviews` | POST | Eligible student | Interaction-gated (`system_verified_interview\|offer`); ineligible → `403 {reason:not_eligible}`; dup → `409 {reason:review_exists}`; body<50 → `422`. Stored `pending`. |
| `/companies/{slug}/reviews/mine` | GET | Student | Caller's own review (any status) or 404. |
| `/reviews/{id}` | PATCH | Author + `version` | Edit own (30-day window); re-enters `pending`, re-moderates; stale version → `409 {reason:state_conflict}`; non-author → 404. |
| `/reviews/{id}` | DELETE | Author | Soft-delete; recomputes aggregate. 204. |
| `/reviews/{id}/report` | POST | Authenticated | `{reason_code}`; idempotent per reporter; first report → `flagged` (stays published). |
| `/admin/reviews` | GET | University | Moderation queue. `?status=pending\|flagged\|published\|removed`, `?limit`. Returns `counts{pending,flagged}` + author identity (accountability). |
| `/admin/reviews/{id}/publish` | POST | University | `pending\|flagged → published`; recompute. Idempotent. |
| `/admin/reviews/{id}/remove` | POST | University | `{reason}` POLICY-GATED to allowed grounds (pii/harassment/discrimination/spam/off_topic/false_claim) — a genuine negative opinion → `422 {reason:removal_reason_invalid}`. Drops from aggregate. |
| `/admin/reviews/{id}/restore` | POST | University | `removed\|flagged → published`; recompute. |

The public **company profile** (`GET /companies/{slug}`) embeds a `rating` block
(`review_count`, Bayesian `overall_avg`, per-category averages, `distribution`) via
the reviews facade, or `null` when there are no published reviews.

### Legacy draft (superseded by the table above)

| Path | Method | Actor |
|---|---|---|
| `/companies/{slug}/reviews` | GET | Authenticated |
| `/companies/{slug}/reviews` | POST | Eligible student/alumni |
| `/reviews/{id}` | PATCH | Original author (pending only) |
| `/reviews/{id}/report` | POST | Authenticated |
| `/admin/reviews/{id}/remove` | POST | University Admin |

### Create Review

`POST /api/v1/companies/{slug}/reviews`

```json
{
  "title": "Môi trường làm việc tốt",
  "body": "...",
  "pros": "...",
  "cons": "...",
  "is_anonymous": false,
  "application_id": "uuid-or-null",
  "ratings": {
    "overall": 4,
    "work_life_balance": 4,
    "culture_values": 5,
    "compensation": 3,
    "career_growth": 4,
    "interview_experience": 4
  }
}
```

Response: `{ "data": { "review_id": "uuid", "status": "pending_auto_review", "publishes_after": "iso-datetime" } }`

---

## Passive Search & Talent Pool

| Path | Method | Actor |
|---|---|---|
| `/passive-search/profiles` | GET | Partner (with quota) |
| `/passive-search/profiles/{id}/contact` | POST | Partner |
| `/talent-pool` | GET | Partner |
| `/talent-pool` | POST | Partner |
| `/talent-pool/{entry_id}` | DELETE | Partner |
| `/applications/{id}/reveal` | POST | Partner (anonymous apply) |
| `/applications/{id}/reveal/respond` | POST | Student |
| `/saved-jobs` | GET | Student |
| `/saved-jobs` | POST | Student |
| `/saved-jobs/{job_id}` | DELETE | Student |

### Passive Search Query

`GET /api/v1/passive-search/profiles?skills=python,fastapi&graduation_year=2025&page_cursor=xxx`

Returns anonymized profiles. Reveals full profile only when a `contact_reveal_request` is accepted.

### Anonymous Reveal Request

`POST /api/v1/applications/{id}/reveal`

```json
{ "reason": "Chúng tôi muốn tìm hiểu thêm về kinh nghiệm của bạn (min 20 chars)" }
```

Student responds via:

`POST /api/v1/applications/{id}/reveal/respond`

```json
{ "decision": "accepted" }
```

---

## Messaging

V1 is implemented per **ADR-0012 (Messaging — Institutional In-App Threads)**:
module `messaging`, public paths under `/api/v1/messaging/threads`, tables
`message_threads` / `messages` / `message_thread_participants`. Delivery is
**REST + client polling** (mirroring the notification-bell unread poll); WebSocket
`/ws/` + Redis fan-out + presence + the segmented broadcast builder + attachments +
reactions/pin/search are an explicitly **deferred** follow-up (contract
pre-committed in ADR-0012 §3). The legacy `/conversations*`, `message_reads`,
`/admin/broadcast`, and `message_type/attachments` names above are **superseded** by
the shapes below.

### Entities

- **`message_threads`** — `id`, `kind` (`direct` | `announcement`), `context_type`
  (`application` | `support` | `team` | null), `context_id` (FK-by-convention to
  `applications.id` for application threads; not a hard cross-module FK), `org_id`
  (tenant-isolation scope), `subject`, `is_anonymous` (denormalized from the bound
  application at create), `created_by`, `last_message_at`, `status`
  (`active`|`archived`|`closed`), soft-delete `deleted_at`, optimistic `version`.
- **`message_thread_participants`** — PK `(thread_id, user_id)`; `role_in_thread`,
  `can_reply` (false for announcement recipients), `last_read_at` (unread basis),
  `muted`, `joined_at`, `removed_at`.
- **`messages`** — `id`, `thread_id`, `sender_id` (null = system, undeletable),
  `body` (markdown-lite, sanitized on render), `is_system`, `reply_to_id`,
  `client_dedupe_key` (idempotent send; unique per `(thread_id, sender_id, key)`),
  `created_at`, `deleted_at` (soft-delete → "Tin nhắn đã bị xóa").

### Endpoints

| Path | Method | Actor |
|---|---|---|
| `/messaging/threads` | GET | Participant (mine, masked, cursor, `last_message_at DESC`) |
| `/messaging/threads` | POST | Within permission matrix (partner↔student REQUIRES `context_type=application`+`context_id`; for that path `recipient_ids` is OPTIONAL — the service resolves the masked applicant from the application) |
| `/messaging/threads/{id}` | GET | Participant / university moderator (else 404) |
| `/messaging/threads/{id}/messages` | GET | Participant / moderator; cursor `?after=` |
| `/messaging/threads/{id}/messages` | POST | Participant (re-check permission + rate limit; idempotent) |
| `/messaging/threads/{id}/read` | POST | Participant (set `last_read_at = now`) |
| `/messaging/threads/{id}/mute` | POST | Participant (mute/unmute; suppresses notifications) |
| `/messaging/threads/{id}/messages/{mid}` | DELETE | Own ≤10min / university any / system never / partner-to-student never |
| `/messaging/threads/{id}/report` | POST | Participant (audit + notify university) |
| `/messaging/unread-count` | GET | Authenticated (badge sum across my non-muted threads; polling) |

### Permission matrix (enforced at THREE service-layer checkpoints — create, every send, read)

| Sender | Recipient | Allowed? | Condition |
|---|---|---|---|
| `university_staff` | anyone | ✓ | direct; may initiate; only announcement author |
| `partner_member` | `student`/`alumni` | ✓ | ONLY if an `applications` row exists where `org_id==sender.org_id` AND `applicant_id==recipient`; thread bound to that `application_id`; partner initiates; anonymity-masked until reveal. **Recipient resolution**: a partner opening an `application`-context thread MAY omit `recipient_ids` — the service resolves the recipient = `application.applicant_id` server-side (the partner never possesses the masked student's user id). An application owned by another org (or unknown) → **404**. When `recipient_ids` is also supplied it is IGNORED in favor of the context-resolved applicant, so this path can only reach the bound applicant |
| `partner_member` | `partner_member` same org | ✓ | team (`context_type=team`) |
| `partner_member` | `partner_member` other org | ✗ | cross-org blocked → **404** (enumeration-masked) |
| `student`/`alumni` | `university_staff` | ✓ | support; may initiate |
| `student`/`alumni` | `partner_member` | ✓ reply-only | may reply into an existing partner thread; **cannot initiate** → 403 |
| `student`/`alumni` | `student`/`alumni` | ✗ NEVER | hard FIRST check, at BOTH create and send → `400 STUDENT_TO_STUDENT_BLOCKED` |
| `system` (announcement) | many | ✓ | one-way; author `university_staff`; recipients `can_reply=false` |

A user's *effective* persona for the matrix is institutional-first (a
university/partner member who also holds the baseline `student` identity is treated
institutionally; the student↔student block targets users who are ONLY student-side).

### Send Message

`POST /api/v1/messaging/threads/{id}/messages` → body `{ "body": "...",
"reply_to_id": "uuid-or-null", "client_dedupe_key": "string-or-null" }`. The send
runs in ONE transaction: re-check permission (§ matrix) → rate limit → **persist the
message** → bump thread → PII-safe audit → notify each other non-muted participant
(in-app feed + preference-gated email outbox) → commit. **Persist-before-deliver**:
no delivery path exists before commit; the poll/feed read only committed rows.
Idempotent on `client_dedupe_key` (same key → the original message, no duplicate /
re-notify).

### Anonymity + PII rules

- Identity is a **projection-time** decision (single source: `thread_view`). A
  partner viewing the applicant of an anonymous, not-yet-revealed `application`
  thread sees a stable handle `Ứng viên ẩn danh #<short-app-code>` — never name,
  email, or CV. On `applications.reveal_approved_at` (the shipped recruitment reveal
  handshake — the ONLY identity path) the same projection flips to the real name.
- A student always sees the partner's **org display name** (org identity is not
  protected). University moderators see real identities.
- The **`message.received` notification** (in-app + email, category `message`,
  optional/default-on) carries a **masked** sender label + a neutral "Bạn có tin
  nhắn mới" + the thread deep link — **never the message body**, never the anonymous
  student's identity. The partner's notification about an anonymous reply stays
  anonymous; the student's names the org. `message.flagged` notifies university
  staff on report.
- Audit (`messaging.thread.create` / `messaging.message.send` / `.delete` /
  `messaging.report`) snapshots are PII-safe: ids + status only, never body / name /
  email. Reads are not audited.

### Coded errors

`400 STUDENT_TO_STUDENT_BLOCKED` ("Không thể nhắn tin trực tiếp giữa sinh viên"),
`403 PERMISSION_DENIED` (refused initiation / reply-not-allowed / delete-not-allowed),
`404 RESOURCE_NOT_FOUND` (non-participant / cross-tenant / no bound application —
enumeration-masked), `409 THREAD_CLOSED`, `422 VALIDATION_FAILED` (blank body /
missing `context_id` for partner↔student), `429 RATE_LIMITED`
(`details.reason=message_rate_limited`, `details.scope`, `details.reset_at`; global
per-sender/day ceiling + the inactive-application 3/day taper).

---

## Knowledge Base

| Path | Method | Actor |
|---|---|---|
| `/knowledge-bases` | GET | Admin / Partner Admin |
| `/knowledge-bases` | POST | Admin / Partner Admin |
| `/knowledge-bases/{id}` | GET | Permitted |
| `/knowledge-bases/{id}/documents` | GET | Permitted |
| `/knowledge-bases/{id}/documents` | POST | Admin / Partner Admin |
| `/knowledge-bases/{id}/documents/{doc_id}` | DELETE | Admin / Partner Admin |
| `/knowledge-bases/{id}/documents/{doc_id}/retry` | POST | Admin / Partner Admin |
| `/knowledge-bases/{id}/query` | POST | Admin (test panel only) |

Test query response must never include chunk IDs, storage keys, similarity scores, or provider names.

---

## Bulk Apply Cart

| Path | Method | Actor |
|---|---|---|
| `/applications/cart` | GET | Student |
| `/applications/cart` | POST | Student (add job) |
| `/applications/cart/{job_id}` | DELETE | Student |
| `/applications/cart/{job_id}/cover-letter` | POST | Student (AI draft) |
| `/applications/cart/{job_id}/cover-letter` | PUT | Student (edit) |
| `/applications/bulk-apply` | POST | Student |

### Bulk Apply

`POST /api/v1/applications/bulk-apply`

```json
{
  "cart_job_ids": ["uuid1", "uuid2"],
  "idempotency_key": "client-generated-key"
}
```

Response includes per-job result:

```json
{
  "data": {
    "succeeded": [{ "job_id": "uuid1", "application_id": "uuid2" }],
    "failed": [{ "job_id": "uuid3", "reason": "QUOTA_EXCEEDED" }]
  }
}
```

---

## Career Outcomes

| Path | Method | Actor |
|---|---|---|
| `/career-outcomes/records` | GET | University Admin / Staff |
| `/career-outcomes/records` | POST | Partner (confirm hire) / Student (self-report) |
| `/career-outcomes/kpi` | GET | University Admin |
| `/surveys` | GET | University Admin / Student (own) |
| `/surveys` | POST | University Admin |
| `/surveys/{id}` | GET | Participant |
| `/surveys/{id}/respond` | POST | Student |
| `/surveys/{id}/stats` | GET | University Admin |

---

## Mentorship

| Path | Method | Actor |
|---|---|---|
| `/mentorship/mentors` | GET | Student / Alumni |
| `/mentorship/mentors/{id}` | GET | Authenticated |
| `/mentorship/requests` | POST | Student |
| `/mentorship/requests/{id}/respond` | POST | Mentor |
| `/mentorship/sessions` | GET | Mentor / Mentee |
| `/mentorship/sessions/{id}` | GET | Participant |
| `/mentorship/sessions/{id}/complete` | POST | Mentor |
| `/mentorship/sessions/{id}/rate` | POST | Mentee |

---

## Offers

| Path | Method | Actor |
|---|---|---|
| `/offers` | GET | Student / Partner |
| `/offers/{id}` | GET | Student / Partner |
| `/offers/{id}/respond` | POST | Student |

### Respond to Offer

`POST /api/v1/offers/{id}/respond`

```json
{
  "decision": "accepted",
  "notes": "optional",
  "idempotency_key": "client-generated-key"
}
```

Accepted decisions trigger career outcome record creation at `trust_level = 4` (estimated).

---

## Workflows (University Admin)

| Path | Method | Actor |
|---|---|---|
| `/workflows` | GET | University Admin |
| `/workflows` | POST | University Admin |
| `/workflows/{id}` | GET | University Admin |
| `/workflows/{id}` | PATCH | University Admin (draft only) |
| `/workflows/{id}/activate` | POST | University Admin |
| `/workflows/{id}/deactivate` | POST | University Admin |
| `/workflows/{id}/executions` | GET | University Admin |
| `/workflows/{id}/test` | POST | University Admin (dry run) |

Active workflow versions are immutable — must deactivate before editing.

---

## Notifications

| Path | Method | Actor |
|---|---|---|
| `/notifications` | GET | Authenticated |
| `/notifications/unread-count` | GET | Authenticated |
| `/notifications/{id}/read` | POST | Recipient |
| `/notifications/read-all` | POST | Recipient |
| `/notification-preferences` | GET | Authenticated |
| `/notification-preferences` | PATCH | Authenticated |
| `/notification-templates` | GET | University Admin / allowed Partner Admin |
| `/notification-templates` | POST | University Admin / allowed Partner Admin |
| `/notification-templates/{id}` | PATCH | Template owner |
| `/notification-templates/{id}/preview` | POST | Template owner |
| `/notification-templates/{id}/activate` | POST | University Admin |
| `/notifications/push-subscription` | POST | Authenticated |
| `/notifications/push-subscription/{id}` | DELETE | Authenticated |

```json
{
  "data": [{
    "id": "uuid",
    "notif_type": "application.status_changed",
    "title": "Đơn ứng tuyển đã được xem xét",
    "body": "Vingroup đã chuyển đơn bạn sang vòng phỏng vấn.",
    "action_url": "/student/applications/uuid",
    "is_read": false,
    "created_at": "iso-datetime"
  }],
  "page": { "next_cursor": null, "limit": 20 },
  "meta": { "unread_count": 7 }
}
```

`GET /api/v1/notifications/unread-count` returns:

```json
{ "data": { "unread_count": 7 } }
```

### Notification Preference Update

```json
{
  "locale": "vi",
  "timezone": "Asia/Ho_Chi_Minh",
  "quiet_hours": { "enabled": true, "start": "22:00", "end": "07:00" },
  "categories": {
    "application.status_changed": { "in_app": true, "email": true, "push": false },
    "job.digest": { "in_app": true, "email": "weekly", "push": false }
  }
}
```

Mandatory security/compliance categories may be returned as locked and cannot be disabled.

### Template Preview

`POST /api/v1/notification-templates/{id}/preview`

```json
{
  "locale": "vi",
  "sample_variables": {
    "name": "An",
    "job_title": "Software Engineer Intern",
    "company_name": "VinBigdata",
    "action_url": "/student/applications/app_123"
  }
}
```

Preview validates unknown/missing variables and returns rendered subject/body without sending email.

---

## Account Settings And Devices

| Path | Method | Actor |
|---|---|---|
| `/account/preferences` | GET | Authenticated |
| `/account/preferences` | PATCH | Authenticated |
| `/account/sessions` | GET | Authenticated |
| `/account/sessions/{id}/revoke` | POST | Owner |
| `/account/security-events` | GET | Authenticated |
| `/account/password` | PATCH | Authenticated |
| `/account/totp/setup` | POST | Authenticated |
| `/account/totp/verify` | POST | Authenticated |
| `/account/totp/disable` | POST | Authenticated |

Device/session APIs return device hints and city-level location only; never raw IP, exact location, refresh token, or full user-agent.

---

## System Configuration (University Admin)

| Path | Method | Actor |
|---|---|---|
| `/admin/settings` | GET | University Super Admin |
| `/admin/settings` | PATCH | University Super Admin |
| `/admin/feature-flags` | GET | University Super Admin |
| `/admin/feature-flags/{key}` | PATCH | University Super Admin |
| `/admin/tiers` | GET | University Admin |
| `/admin/tiers` | POST | University Admin |
| `/admin/tiers/{id}` | PATCH | University Admin |

---

## QA Bank

| Path | Method | Actor |
|---|---|---|
| `/qa-bank/questions` | GET | Authenticated |
| `/qa-bank/questions` | POST | Authenticated |
| `/qa-bank/questions/{id}` | GET | Authenticated |
| `/qa-bank/questions/{id}/answers` | GET | Authenticated |
| `/qa-bank/questions/{id}/answers` | POST | Authenticated |
| `/qa-bank/answers/{id}/vote` | POST | Authenticated |
| `/qa-bank/questions/{id}/vote` | POST | Authenticated |

---

## Platform Trust — Support, Privacy, Abuse (ADR-0014, E36)

New RBAC nouns added to `PERMISSION_CATALOG`
(`organization/domain/catalog.py`), grantable on any university-org role like
`jobs:moderate` (no new hardcoded role; `principal.is_superadmin` bypasses):
`support: {read, act, escalate}`, `privacy: {read, process}`,
`abuse: {read, triage, escalate, override}`. Every gate below also requires
`org_reporting_facade.is_university_org(principal.org_id)` — mirrors
`review_queue_service._require_university` — so a misconfigured partner role
can never hold these nouns even if granted by mistake.

### Support Console (`platform_support` module)

No new tables. Reads compose `org_reporting_facade` +
`admin_users_service.list_platform_users` + `notification_outbox` +
`human_review_queue`; writes append to `audit_logs`
(`resource_type` prefixed `support_*`).

| Path | Method | Permission | Notes |
|---|---|---|---|
| `/platform-support/lookup` | GET | `support:read` | Query params `q`, `type=user\|organization`. Wraps `admin_users_service.list_platform_users` + an org search; response includes verification/suspension/package state, never raw PII beyond what `list_platform_users` already exposes. |
| `/platform-support/outbox-health` | GET | `support:read` | Read-only counts over `notification_outbox`: `{pending, sent, failed, dead, skipped}` counts + `oldest_pending_age_seconds`. "processing" in the product packet maps to `pending` rows whose `next_attempt_at` is in the future (backoff-scheduled) — surfaced as a `retry_scheduled` sub-count, not a distinct DB status (none exists). |
| `/platform-support/outbox/{outbox_id}/requeue` | POST | `support:act` | Only legal on `status="dead"` rows (409 `not_dead_lettered` otherwise); resets `status="pending"`, `attempts=0`, `next_attempt_at=NULL` via the existing `dispatch_service` retry path. Audited: `action="support.outbox_requeued"`, `resource_type="support_notification_outbox"`, `after={"outbox_id":..., "template_key":...}`. |
| `/platform-support/users/{user_id}/package-override` | POST | `support:act` | Body `{ "plan_id": "...", "reason": "..." }`. Delegates to the existing `billing` package-assignment service; support call site is audited (`action="support.package_overridden"`, `resource_type="support_billing"`) in addition to whatever audit `billing` already writes. |
| `/platform-support/reveal/{resource_type}/{resource_id}` | POST | `support:act` | Body `{ "reason": string }`. Masked PII (raw CV text, contact info) is masked by default in every support view; this endpoint mirrors the existing `documents` reveal_service pattern — the reveal itself is the audited action (`action="support.pii_revealed"`, `resource_type="support_reveal"`, `after={"target_type":..., "target_id":..., "reason":...}` — never the revealed value itself in the audit row). |
| `/platform-support/cases` | GET | `support:read` | Thin filter over `/moderation/review-queue?source=support_case` — no duplicate UI/table; link-out per product decision. |
| `/platform-support/cases/{item_id}/resolve` | POST | `support:act` | Body `{ "note"?: string }`. Delegates to `review_queue_service.resolve_item` with `source="support_case"` validated; audited as `action="support.case_resolved"` in addition to the existing `moderation.review_item_resolved` audit row `review_queue_service` already writes. |

### Privacy & Compliance (`compliance` module)

New tables `consents`, `privacy_requests` (see `docs/DATA_MODEL.md` §35).

| Path | Method | Permission | Notes |
|---|---|---|---|
| `/account/privacy/consents` | GET | Authenticated (own) | Returns current-state rows for the two fixed types: `{ "interview_recording": {"granted": bool, "granted_at": ..., "revoked_at": ...}, "career_outcomes_data_sharing": {...} }`. |
| `/account/privacy/consents/{consent_type}` | PUT | Authenticated (own) | Body `{ "granted": bool }`. `consent_type` validated against the two code-fixed values only (400 otherwise). Writes/updates the `consents` row + an `audit_logs` entry (`action="compliance.consent_updated"`). |
| `/account/privacy/retention` | GET | Authenticated (own) | Read-only text: hardcoded retention constants (not DB rows), localized. |
| `/account/privacy/requests` | POST | Authenticated (own) | Body `{ "request_type": "export"\|"deletion", "note"?: string }`. `requested_by = principal.user_id`. 409 `request_already_pending` if an open (`pending`/`processing`) request of the same `request_type` exists for this user. |
| `/account/privacy/requests` | GET | Authenticated (own) | List the caller's own requests, cursor-paginated. |
| `/admin/privacy-requests` | GET | `privacy:read` | Staff list, filterable by `status`/`request_type`, cursor-paginated. |
| `/admin/privacy-requests/{id}/fulfill` | POST | `privacy:process` | Body `{ "status": "fulfilled"\|"rejected", "note"?: string }`. Manual fulfillment (staff has already performed the export/deletion by querying existing tables) — no orchestrated auto-purge engine in V1. Sets `processed_by`, `fulfilled_at`; audited (`action="compliance.privacy_request_fulfilled"`, before/after `status`). |

### Abuse & Content Reports (`moderation` module extension)

New table `content_reports` (see `docs/DATA_MODEL.md` §35); triage merges it
with `human_review_queue`.

| Path | Method | Permission | Notes |
|---|---|---|---|
| `/content-reports` | POST | Authenticated | Body `{ "entity_type": "company"\|"job"\|"message", "entity_id": "...", "reason_code": "...", "note"?: string }`. V1 entity types only; application/ad-creative report buttons are deferred (409/400 `unsupported_entity_type` otherwise). Duplicate `(reporter_id, entity_type, entity_id)` returns `{"status": "already_reported"}` idempotently (unique constraint). Service-layer rate limit on distinct-entity report volume per reporter per window returns `429 RATE_LIMITED` beyond that. |
| `/moderation/triage` | GET | `abuse:read` | Merged prioritized list: `content_reports` (status `PENDING`/`TRIAGED`) + `human_review_queue` (all sources), filterable by `?source=user_report\|fraud_detection\|content_moderation\|bias_detection\|support_case\|agent_loop`. Read-only aggregation query, not a new projection table at V1 volume. |
| `/content-reports/{id}/escalate` | POST | `abuse:triage` | Promotes a `content_reports` row into a `human_review_queue` action: creates/refreshes a `HumanReviewItem` with `source="user_report"`, sets `content_reports.review_item_id` + `status="TRIAGED"`. Severity is set heuristically (single report → `low`; N reports on the same entity within a window → `medium`; corroborates an existing pending `fraud_detection` item on the same `resource_id` → `high`) — see ADR-0014 "Risk Flagged To Product". |
| `/moderation/actions/{review_item_id}/override` | POST | `abuse:override` | Body `{ "note": string }`. Reverses a prior moderation action (unsuspend/republish/unflag) on the resource the review item targeted. Audited via `audit_logs` with an explicit before/after snapshot of the resource's public state (`action="abuse.action_overridden"`, `resource_type="support_abuse_override"`, `before={"status": ...}`, `after={"status": ...}`) — this is the one write path in this ADR that must carry a real before/after diff, not just a marker. |
| (reported-party notification) | — | — | Not a separate endpoint: on escalation/override, reuse existing notification templates to send a generic reason-category-only notice (no reporter identity, no raw report text) to the reported party. |
| (appeal) | — | — | Not a separate endpoint: reported party appeals via the existing partner support/messaging surface, referencing the moderation action ID in the message body — no new appeal table/route in V1. |

---

## Versioning

- Do not break `/api/v1` response fields without explicit migration plan.
- Additive changes are preferred.
- Deprecate fields before removal.
