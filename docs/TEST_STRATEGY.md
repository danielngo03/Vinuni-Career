# Test Strategy — VinUni Career Platform

> Phiên bản: 1.0 | Cập nhật: 26/06/2026  
> Source of truth for greenfield quality gates and test ownership.

## Test Pyramid

- Unit: domain rules, validators, pure functions.
- Integration: DB repositories, services, permissions, outbox, workers.
- API/E2E: persona workflows through HTTP.
- Frontend: critical components, forms, auth gates, confirmation flows.
- AI eval: prompt/tool behavior, safety, fallback.

## Environment And Order Isolation

- Backend test commands must pin relevant local flags instead of relying on the
  developer's current `.env`.
- AI/OCR/CV ingestion tests must explicitly set or fixture
  `CV_LLM_STRUCTURING_ENABLED`, `CV_INGESTION_ASYNC`, `CV_OCR_ENGINE`, and
  `AI_REAL_CALLS_ENABLED`.
- Modules that publish runtime singletons or mutate process env must reset them
  after each test.
- If a test file passes alone but fails when run after another module, treat it
  as a test-isolation blocker. Do not claim checkpoint green until the combined
  order passes or the blocker is recorded with exact commands.

## Required Test Areas

### Product Reality Regression

- Broad feature slices satisfy `docs/PRODUCT_REALITY_REBUILD_SPEC.md` and prove
  adjacent backend/data/AI/frontend paths, not just the visible screen.
- Duplicate/resume flows: duplicate registration, pending verification,
  duplicate CV upload, duplicate application, repeated idempotency key, repeated
  resend/reset requests.
- Snapshot immutability: application CV, screening answers, offer submit,
  workflow active version, notification template version, and published CV
  template version remain historically stable after later edits.
- Read-model truth: dashboard counts, recommendation rails, job analytics,
  competition intelligence, and ad attribution reconcile with source events or
  show honest stale/empty states.
- Privacy/compliance: no raw CV text, prompts, provider payloads, secrets,
  exact rankings, other-candidate data, or hidden partner notes leak to the
  wrong persona.
- Support/admin actions are scoped, audited, and do not expose secrets or
  unnecessary PII.

### Authentication And RBAC

- Email/password registration, verification, login, refresh, logout.
- VinUni SSO happy path and fallback.
- Active identity switching.
- Missing permission returns `403`.
- Hidden resources return `404` where enumeration prevention applies.
- Cross-organization access is blocked.
- RBAC changes are audited.

### Student Core Loop

- Student preferences/profile settings do not block CV creation.
- CV upload and parse lifecycle.
- CV upload edge cases: unsupported file, too large, infected/scan failure, password-protected PDF, corrupt file, blank PDF, non-CV PDF, duplicate upload, low-quality scan, unsupported-language review.
- CV Studio creation modes: blank template, confirmed facts import, uploaded CV import, duplicate existing CV, AI draft from sources.
- CV active quota: default 5 active CV library items, quota reached recovery, archived CVs excluded from active count.
- CV section editor autosave, version restore, template switch, and PDF export.
- CV-to-job fit: recommends best CV, returns 0-100 score, explains categories/gaps, handles stale CV/no eligible CV/AI unavailable.
- Application CV snapshot remains immutable after later CV edits.
- Job discovery visibility rules.
- Apply with selected CV.
- Duplicate application prevention.
- Withdrawal with reason and audit.
- Application timeline uses friendly labels.

### Partner Hiring

- Partner first registrant becomes admin.
- Role/department/member management.
- Job submit/moderation/live flow.
- Pipeline stage transition invariants.
- Scorecard required-action enforcement.
- Rollback reason minimum and audit.
- Bulk action limits.

### University Governance

- Moderation queue SLA.
- Approve/reject with mandatory reason.
- Partner suspension.
- AI suggestion audited with human final decision.
- Sponsored labels enforced.

### AI

- Provider/model names never appear in end-user response.
- Mutating tools cannot execute without confirmation.
- Prompt injection attempts do not reveal prompts or bypass tool permissions.
- AI CV template fill returns pending diff/draft, not direct overwrite.
- AI CV generation/rewrite/tailor does not invent education, employer, GPA, dates, awards, certifications, or quantified outcomes.
- AI CV recommendation does not expose raw confidence, embedding similarity,
  provider/model names, prompts, or token counts.
- CV fabrication check flags unsupported claims without exposing internal confidence or provider details.
- AI unavailable fallback works.
- AI/LLM is not called for blank, corrupt, infected, or not-CV uploads.
- Evaluation set documented for each shipped AI task.

### Events

- Public/authorized visibility.
- Registration eligibility.
- Seat lock conflict and expiry.
- Online link visibility only for confirmed registrants.
- QR check-in idempotency.
- Waitlist promotion.
- V1 manual payment confirmation.

### Exports

- Field-level RBAC (exports omit fields outside the actor's role/department scope).
- Sync export under threshold.
- Async export above threshold.
- Expiring download link.

## Phase Gates

### Phase 0 — Foundation

- Health endpoint.
- DB migration up/down.
- Lint/type checks configured.
- Base app renders shell.
- CI runs backend and frontend checks.
- Tests run without real AI keys.
- Lightweight parser fixtures cover Vietnamese and English CV text.
- Parser negative fixtures cover blank, not-CV, corrupt, password-protected, duplicate, and low-quality scan outcomes.
- Local email/template renderer works without sending real email.
- Test commands validate environment sanity. Inherited env vars such as
  `DEBUG=release` must be overridden to a boolean (`DEBUG=false`) before backend
  settings load.

### Phase 1 — Core Loops

- Student can register, create/upload/manage CVs without completing a mandatory profile form, and apply.
- Student can create a CV from template, import confirmed facts/uploaded CV data, export PDF, get CV-to-job recommendation, and apply with immutable snapshot.
- Partner can register, pass approval, post job, view applications.
- University can moderate partner/job.
- Notifications basic path works.
- Account settings: device list and remote logout.
- Notification preferences: disabled optional category does not send email/push.
- Locale detection and user language override work.

### Phase 2 — Advanced Hiring

- Pipeline transitions and invariants.
- Talent-pool AI semantic search: consent/opt-out indexing, RBAC-gated CV access,
  external-JD search, and deterministic keyword+filter fallback.
- Company reviews moderation.
- Excel export.

### Phase 3 — AI Intelligence

- AI assistant streaming and tool registry.
- Tool confirmation.
- Provider leakage tests.
- CV Studio AI fill/rewrite/tailor eval and no-fabrication tests.
- Interview simulator eval.
- AI settings governance.
- Real model smoke tests are opt-in and capped by `AI_MAX_REAL_CALLS_PER_TEST_RUN`.
- Real model smoke tests run only after offline evals are green, use cheap
  internal aliases, and report alias/cost bucket without exposing provider,
  model, key, raw prompt, or PII-bearing response.

### Phase 4 — Events And Monetization

- Event registration, ticketing, seat locks, QR.
- Manual payment default and future gateway adapter boundaries.
- Sponsored labels and ad targeting validation.
- Package/quota enforcement.

### Phase 5 — University Intelligence

- Career outcomes trust levels.
- Post-grad survey cadence.
- Accreditation reports.
- SIS sync failure handling.
- Faculty aggregate-only access.

## Agent Responsibilities

- `tester-qa`: owns test plan, acceptance criteria, QA gates, test files.
- `backend-developer`: writes backend unit/integration/API tests with implementation.
- `frontend-developer`: writes UI/component/e2e tests with implementation.
- `ai-engineer`: owns eval datasets, adversarial tests, provider leakage tests.
- Domain agents: review scenarios and edge cases, not application code.
