# Agent Parallel Execution Plan — VinUni Career Platform

> Last updated: 2026-07-04
> Purpose: divide the next rebuild pass into parallel agent workstreams with
> clear ownership, source docs, contracts, and acceptance gates.
> Copy-ready CLI prompts live in `docs/CLAUDE_MULTI_AGENT_TASKS.md`.

## Shared Principles For Every Agent

- Build from docs and current code only. Do not assume old implementation
  behavior is correct.
- For any broad slice, apply `docs/PRODUCT_REALITY_REBUILD_SPEC.md` before
  implementation. Agents must inspect adjacent flows and missing backend/data/
  AI/frontend contracts, not only the visible UI the user mentioned.
- Product must feel like a real recruiting platform, not a demo board.
- Use real APIs/read models or honest loading/empty/permission states. Never
  fake metrics, recommendations, AI scores, or dashboards.
- Follow v9 Monochrome design: premium black/white/gray hierarchy, restrained
  semantic color, no decorative gradients/orbs, no emoji icons.
- AI is advisory by default. Mutating AI actions require explicit confirmation,
  versioning/audit, and safe rollback/failure states.
- Service-layer RBAC owns authorization. Frontend visibility is not security.
- Sponsored/advertising inventory must remain disclosed and separated from
  organic/recommended inventory.
- All deliverables must include tests or an explicit test gap with next action.

## Workstream 0 — Release Blocker Stabilization

Owner agents: `backend-developer`, `frontend-developer`, `ai-engineer`,
`tester-qa`, with `system-architect` for contract conflicts.

Scope:

- Restore current backend quality gates before broad product expansion:
  `ruff`, `mypy`, targeted tests, and migration sanity where relevant.
- Fix the current competition-intelligence blocker
  (`SPONSORED_SURFACES` undefined) and verify source-mix/sponsored attribution
  remains privacy-safe and truthful.
- Resolve onboarding/document-verification import/type issues and nullable
  authenticated principal handling.
- Make salary/experience presenters and services defensive for all current and
  legacy modes.
- Fix frontend build warnings in jobs/notifications hook dependencies and add
  regression tests for public jobs filter/sort/grid/preview behavior.
- Align auth/register contract: email/password only; name is onboarding/profile
  data; OTP/link verify/reset flows are i18n-backed and do not assume a user
  name exists.
- Make workflow builder canvas state, node/edge changes, validation, dry run,
  trigger/name configuration, execution history, and operator selectors real
  enough for partner/university operators.
- Close CV Studio's product gaps that block "large-system" credibility:
  template versions/assets, render/PDF/preview unification, browser QA, and
  accessibility.

Acceptance:

- `backend` ruff and mypy are green or remaining failures are explicitly
  documented as unrelated legacy debt with owners and dates.
- `frontend` typecheck/build are green without new hook dependency warnings on
  core surfaces.
- Status docs record exact pass/fail commands and verification tiers.
- No slice is marked complete based only on a screenshot or partial test subset.

## Workstream 1 — Product And Architecture Reality Audit

Owner agents: `product-owner-system-planner`, `system-architect`

Scope:

- Reconcile current code with `CLAUDE.md`, PRD,
  `docs/PRODUCT_REALITY_REBUILD_SPEC.md`, API/data docs, and backlog.
- Mark which features are production-shaped, functional-only, or misleading.
- Resolve contract conflicts before implementation agents start.
- Produce a cross-domain execution map for CV Studio, job intelligence,
  partner/university workflow, auth recovery, discovery/personalization, and
  notifications.
- Audit adjacent flows across auth, onboarding, notifications, billing/quota,
  seed/data quality, analytics, support, AI, and admin governance so agents do
  not build isolated demo screens.

Acceptance:

- Updated docs/status identify exact gaps and owners.
- No broad implementation begins until API/data contracts are stable enough.

## Workstream 2 — Visual CV Studio Backend

Owner agents: `backend-developer`, `ai-engineer` for AI surfaces

Scope:

- Implement or harden `cv_templates`, `cv_template_versions`,
  `cv_template_assets`, `cv_profiles`, `cv_sections`, `cv_versions`,
  `cv_ai_suggestions`, exports, and uploaded-CV import contracts.
- Add template ownership/version/status fields and publish/archive audit.
- Add canvas patch endpoint and AI edit-command endpoint.
- Keep uploaded originals immutable and application snapshots immutable.

Acceptance:

- Migrations, repositories, services, API contracts, permission checks, quota
  checks, and tests exist.
- AI edit command stores pending diffs only; accept creates a new CV version and
  audit event.

## Workstream 3 — Visual CV Studio Frontend

Owner agents: `frontend-developer`, `student-domain-agent`, `tester-qa`

Scope:

- Replace form-first CV editing with template marketplace + visual A4 canvas.
- Support upload, choose template, duplicate, inline edit, block selection,
  drag/drop reorder, photo replace/crop, inspector, autosave, undo/redo,
  version restore, export preview, mobile review mode, and AI diff review.

Acceptance:

- No student is forced to fill a long profile form before creating a CV.
- Browser verified at 375/768/1024/1440 in light/dark.
- Keyboard and screen-reader flows work for template choice, block selection,
  diff review, and export.

## Workstream 4 — Student Job Fit And Competition Intelligence

Owner agents: `backend-developer`, `ai-engineer`, `frontend-developer`,
`student-domain-agent`

Scope:

- Build `GET /api/v1/jobs/{job_id}/student-intelligence`.
- Combine best CV, CV-JD fit, evidence gaps, truthful improvement actions,
  learning gaps, apply readiness, and competition guidance.
- Competition uses real aggregate/bucketed signals: seats/hiring intent,
  application volume, applicant quality buckets, student fit bucket, deadline,
  source mix, and low-signal handling.

Acceptance:

- Guests never see personalized fit/competition.
- No other candidate PII, exact rank, raw CV text, raw model confidence,
  provider/model, prompt, token, or cost leaks.
- UI presents guidance, not hiring probability guarantees.

## Workstream 5 — Partner And University Visual Workflow/RBAC

Owner agents: `system-architect`, `backend-developer`,
`frontend-developer`, `employer-domain-agent`, `university-domain-agent`

Scope:

- Turn workflow configuration into a real visual builder with node palette,
  canvas, inspector, validation, dry run, immutable active versions, execution
  logs, permission blockers, and audit.
- Support partner recruiting flows and university moderation/approval flows.
- Keep Partner Admin wildcard by default but all capabilities grantable by
  user/role/department scope.

Acceptance:

- Activation validates every action against RBAC.
- Failed nodes create recoverable tasks.
- Sensitive actions such as CV access, reveal, rejection, offer send, billing,
  and AI actions are audited and permission-gated.

## Workstream 6 — Auth, Recovery, Onboarding, And Notifications

Owner agents: `backend-developer`, `frontend-developer`, `tester-qa`

Scope:

- Registration must reject duplicate verified email and handle pending
  verification safely.
- Email verification and password reset support OTP entry and link flow where
  configured.
- Recovery screens must have practical back navigation, resend/rate-limit/expiry
  states, non-enumerating copy, and no reliance on user name before onboarding.
- Onboarding records should preserve progress until completion; completion
  should mark state cleanly without losing audit/history needed for support.

Acceptance:

- Tests cover duplicate email, pending verification, expired OTP/link, wrong OTP,
  too many attempts, resend cooldown, already verified, reset for nonexistent
  email, and onboarding interruption/resume.

## Workstream 7 — Public/Student Discovery, Filters, Ads, And Data Quality

Owner agents: `frontend-developer`, `backend-developer`,
`data-engineer`, `student-domain-agent`

Scope:

- Public jobs/events/companies mega menus and list pages use realistic
  personalization, session signals, categories, location filters, salary and
  experience formatting, pagination/sorting, sponsored banners, and clean
  empty states.
- Backend exposes real categories/industries/locations and normalized salary,
  experience, job-level, education, language, eligibility, and location data.

Acceptance:

- Organic, recommended, sponsored, and curated sources are separated.
- Filters are usable, accessible, and backed by real API params.
- Salary/experience/location display handles negotiated, from/to ranges,
  multiple locations, no requirement, and post-2025 Vietnam location data.

## Workstream 8 — QA, Security, Evals, And Release Gates

Owner agents: `tester-qa`, `security-guidance`/security reviewer if available,
`ai-engineer`

Scope:

- Build high-value tests and evals across auth, CV Studio, CV ingestion,
  job intelligence, competition privacy, RBAC, workflow activation, and
  discovery/ads disclosure.
- Verify frontend build, type checks, backend tests, migration checks, and
  browser/a11y smoke passes.

Acceptance:

- Privacy boundary failures block release.
- Status docs distinguish `API wired`, `browser verified`, and `E2E verified`.
- Known gaps are documented with owners, not hidden behind "done".

## Workstream 9 — Application Journey And Student Workspace

Owner agents: `backend-developer`, `frontend-developer`,
`student-domain-agent`, `tester-qa`

Scope:

- Harden the full student application lifecycle: draft apply, submitted,
  viewed, in review, interview, offer, rejected, withdrawn, hired, and archived.
- Store immutable application snapshots of submitted CV, screening answers, JD
  requirements, consent, and public company/job fields.
- Prevent duplicate applications or resume the existing draft/submission with a
  clear next action.
- Build the student application workspace with status timeline, next action,
  messages, interviews, documents, withdrawal policy, and truthful copy.

Acceptance:

- Student and partner status views agree on canonical backend events.
- No UI claim such as "viewed" or "shortlisted" appears without a backing
  event/status transition.
- Tests cover duplicate apply, stale job, closed job, missing CV, withdrawn
  application, interview reschedule, offer expiry, and snapshot immutability.

## Workstream 10 — Platform Support, Compliance, And Abuse Controls

Owner agents: `system-architect`, `backend-developer`,
`university-domain-agent`, `tester-qa`

Scope:

- Add or harden platform support/admin surfaces for tenant/account lookup,
  verification state, outbox health, failed async jobs, moderation escalations,
  safe support views, and audited package overrides.
- Define and implement privacy/compliance controls: consent capture, data
  export, retention/deletion policy, CV/application snapshot retention,
  notification preferences, and student-visible security history.
- Add abuse/fraud queues for suspicious companies/jobs, spam applications,
  abusive messages, risky ad creatives, and manual escalation/appeal.

Acceptance:

- Support actions are scoped, audited, and never expose secrets, raw refresh
  tokens, raw provider payloads, hidden CV contents, or unnecessary PII.
- Privacy/security docs, API contracts, and tests cover consent, retention,
  export/delete, notification preferences, and abuse escalation paths.

## Workstream 11 — Read Models, Analytics, And Data Quality

Owner agents: `data-engineer`, `backend-developer`, `ai-engineer`,
`tester-qa`

Scope:

- Define source events, refresh strategy, stale-data behavior, and fallback UI
  for dashboards, recommendations, job analytics, competition intelligence,
  ads attribution, and university outcome reporting.
- Make seed/crawl pipelines repeatable, idempotent where possible, and linked to
  canonical organization, taxonomy, location, salary, experience, event, ad,
  and template entities.
- Add reconciliation checks so dashboards and recommendations do not drift from
  source tables.

Acceptance:

- No dashboard or recommendation rail is powered by fake constants.
- Demo data represents realistic edge cases and has accurate logos/media,
  structured salary/experience/location, verification state, sponsored labels,
  and moderated statuses.
