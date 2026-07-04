# Claude Multi-Agent Task Commands — VinUni Career Platform

> Last updated: 2026-07-04
> Purpose: copy these commands into separate terminals to run focused Claude
> agents/workstreams in parallel. Each prompt forces the agent to read the
> product reality docs and produce implementation evidence instead of demo UI.

Run from repository root:

```bash
cd /Users/anhtuan/Desktop/Vinuni/Build/C2-App-037
```

## 0. Release Blocker Stabilization First

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Run the post-Claude release blocker stabilization pass before any broad new feature work. Read CLAUDE.md, docs/IMPLEMENTATION_STATUS.md Post-Claude review checkpoint, docs/AGENT_PARALLEL_EXECUTION_PLAN.md Workstream 0, docs/SYSTEM_ACCEPTANCE_BAR.md, docs/API_CONTRACTS.md Auth/Jobs/Workflow/CV sections, docs/DATA_MODEL.md, docs/CV_STUDIO_SPEC.md, docs/PARTNER_RBAC_ANALYTICS_SPEC.md, docs/AI_PRODUCT_SPEC.md, .claude/rules/backend.md, .claude/rules/frontend.md, .claude/rules/testing.md, and inspect current backend/frontend code with rg. Fix the current blockers, not just symptoms: backend ruff/mypy failures; undefined SPONSORED_SURFACES in competition intelligence; onboarding doc-verification/session-factory and nullable principal issues; salary/experience presenter/service typing and legacy-data handling; frontend jobs/notifications hook dependency warnings; auth register contract email/password-only with name moved to onboarding/profile; verify/reset screens fully i18n-backed and no name-dependent email copy; workflow builder canvas state sync/persist, name/trigger config, selectors instead of raw IDs, validation/dry-run/history; CV Studio template-version/assets/render-PDF-preview-unification blockers at least contracted and implemented where local scope allows. Run backend ruff, mypy, targeted pytest, frontend typecheck/build, and any focused tests added. Update docs/IMPLEMENTATION_STATUS.md with exact commands and pass/fail evidence, and update BACKLOG only for remaining blockers with owner/date.
PROMPT
)"
```

## 1. Product Reality Audit And Execution Map

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Run /product-reality-audit for the entire VinUni Career Platform before any broad implementation. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md, docs/PRODUCT_REQUIREMENTS.md, docs/API_CONTRACTS.md, docs/DATA_MODEL.md, docs/AI_PRODUCT_SPEC.md, docs/CV_STUDIO_SPEC.md, docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md, docs/PARTNER_RBAC_ANALYTICS_SPEC.md, docs/SYSTEM_ACCEPTANCE_BAR.md, docs/TASK_ROUTING.md, docs/AGENT_PARALLEL_EXECUTION_PLAN.md, docs/BACKLOG.md, docs/IMPLEMENTATION_STATUS.md, and relevant .claude/rules/*.md. Inspect backend/ and frontend/ with rg before writing. Do not implement app code unless a docs contract is clearly stale and must be patched first. Produce a severity-ordered gap map across auth/onboarding, CV Studio, jobs/JD, applications, student intelligence, partner ATS/RBAC/workflow, university governance, public discovery/ads/events, messaging/notifications, billing/quota, support/compliance/abuse, read models/analytics, seed/crawl quality, and frontend UI reality. Update docs/IMPLEMENTATION_STATUS.md and docs/BACKLOG.md only if the audit finds missing acceptance criteria. End with exact owner routing and blockers.
PROMPT
)"
```

## 2. Auth, Identity, Recovery, And Onboarding Hardening

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Implement the production-shaped auth/onboarding slice for E36 B-542 and B-543. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md, docs/API_CONTRACTS.md Auth/Identity sections, docs/DATA_MODEL.md, docs/SECURITY_PRIVACY.md, docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md, docs/SYSTEM_ACCEPTANCE_BAR.md, docs/TEST_STRATEGY.md, .claude/rules/backend.md, .claude/rules/frontend.md, and current backend/frontend auth code. Requirements: canonical unique email identity; duplicate verified email blocked; pending verification safely resumed; OAuth account linking/conflict states; email verification and password reset support OTP entry and link flow where configured; expiry, resend cooldown, rate limiting, too-many-attempt handling, anti-enumeration responses; email templates never assume name exists; reset revokes sessions; onboarding state machine draft/resume/completed without deleting audit/support history; frontend login/register/verify/forgot/reset screens have practical top-left back navigation, preserve safe fields like email, no decorative-only icons, no unsupported attempt-count copy, clean input focus/error UI. Add migrations/services/API tests/frontend tests where needed. Run relevant backend pytest/ruff/mypy and frontend type/build checks if feasible. Update docs/IMPLEMENTATION_STATUS.md with exact verification.
PROMPT
)"
```

## 3. Visual CV Studio, Template Governance, And AI Editing

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Build the CV Studio slice as a visual canvas product, not a form-first profile editor. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md, docs/CV_STUDIO_SPEC.md, docs/CV_INGESTION_EXTRACTION_SPEC.md, docs/AI_PRODUCT_SPEC.md, docs/API_CONTRACTS.md CV sections, docs/DATA_MODEL.md CV/template sections, docs/DESIGN.md, docs/UI_QUALITY_BAR.md, docs/SYSTEM_ACCEPTANCE_BAR.md, .claude/rules/frontend.md, .claude/rules/backend.md, .claude/rules/ai.md, and current backend/frontend CV code. Implement or harden upload existing CV, choose official/university templates, duplicate CV, import reviewed extraction, visual A4 canvas inline editing, selectable blocks, drag/drop reorder, photo replace/crop, page-break warnings, undo/redo, autosave, version restore, export preview/PDF consistency, template versioning/publish/archive/admin upload, active CV quota/archive, immutable originals and application snapshots. AI command-to-patch must produce structured pending diffs only, never silently mutate or invent facts; student confirms before applying. Add backend migrations/services/API tests, AI eval fixtures/fallback, frontend browser-responsive states, and update docs/status.
PROMPT
)"
```

## 4. Structured Jobs, JD Requirements, Salary/Experience, Filters, And Public Jobs UI

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Implement the structured job and public jobs discovery slice for E36 B-544/B-545 and the current /{locale}/jobs UX. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md Jobs/Discovery sections, docs/API_CONTRACTS.md Public discovery query contract, docs/DATA_MODEL.md, docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md, docs/DESIGN.md, docs/UI_QUALITY_BAR.md, docs/TEST_STRATEGY.md, and current backend/frontend jobs code. Backend: support structured salary modes negotiable/hidden/fixed/range/from/to with currency/period/gross-net where available; structured experience modes no requirement/fresher/range/min/max; level, education, languages, skills, work authorization, nationality, gender, age range, marital status, multiple canonical locations, screening questions, deadline, seats. Filters must use canonical category/location IDs and deepest selected taxonomy scope, not display strings or broad OR parents. Frontend /jobs: toolbar order category -> search -> location -> advanced; advanced menu/popover near toolbar, not side drawer unless deep config; sort dropdown fixed, list/grid toggle aligned, grid typography compact, preview sticky only as a real detail pane, pagination, sponsored/organic disclosure, accurate salary display such as '30 - 60 triệu', 'Tới 50 triệu', 'Thỏa thuận'. Add tests for filter semantics, salary/experience formatting, multiple locations, and browser screenshots.
PROMPT
)"
```

## 5. Student Job Intelligence, Matching, Competition, And Learning Guidance

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Implement the logged-in student job intelligence slice E35 B-535 through B-540. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md Matching/Competition sections, docs/AI_PRODUCT_SPEC.md, docs/API_CONTRACTS.md student-intelligence contract, docs/DATA_MODEL.md, docs/SECURITY_PRIVACY.md, docs/SYSTEM_ACCEPTANCE_BAR.md, docs/TEST_STRATEGY.md, and current job/CV/application code. Build GET /api/v1/jobs/{job_id}/student-intelligence with best eligible CV recommendation, CV-JD fit score as a product score, evidence gaps, truthful CV improvement actions, apply readiness, learning gap recommendations, and privacy-safe competition intelligence only for logged-in students. Competition must use aggregate/bucketed signals: seats, application volume, applicant quality bucket, student fit bucket, deadline freshness, source mix, recent activity, and low-signal fallback. Never expose exact rank, other candidates, raw CV text, raw model confidence, provider/model/prompt/token internals, or hiring guarantees. Frontend job detail should show fit/competition only after login with clear next actions: select best CV, improve CV, apply, save, compare adjacent roles. Add eval fixtures and API/UI tests.
PROMPT
)"
```

## 6. Application Journey And Student Application Workspace

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Implement E36 B-551: application lifecycle hardening and the student application workspace. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md Applications section, docs/API_CONTRACTS.md Application CV Selection/Pipeline/Interview/Offer sections, docs/DATA_MODEL.md, docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md, docs/SYSTEM_ACCEPTANCE_BAR.md, docs/TEST_STRATEGY.md, .claude/rules/backend.md, and .claude/rules/frontend.md. Backend: immutable snapshots for submitted CV/version/upload, screening answers, cover letter, consent, public job/company fields, and structured job requirements; duplicate applications blocked or draft resumed with clear 409 reasons; idempotency safe retries; withdrawal/archive policy; canonical status timeline events; interview/offer milestones; student-safe status projections that never expose partner internal notes. Frontend: student application workspace with draft/submitted/viewed/in review/interview/offer/rejected/withdrawn/hired/archived states, next action, messages/interviews/offers/documents, truthful copy, empty/error/permission states. Add tests for duplicate apply, stale/closed job, missing CV, snapshot immutability, withdrawal, interview reschedule, offer expiry, and notification events.
PROMPT
)"
```

## 7. Partner ATS, RBAC, Workflow Builder, Analytics, And Employer CRM

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Implement the partner operating-system slice for E33 plus E36 B-552/B-553. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md Partner sections, docs/PARTNER_RBAC_ANALYTICS_SPEC.md, docs/API_CONTRACTS.md partner/dashboard/pipeline/workflow/billing/reveal sections, docs/DATA_MODEL.md, docs/DESIGN.md, docs/SYSTEM_ACCEPTANCE_BAR.md, .claude/rules/backend.md, .claude/rules/frontend.md, and current partner dashboard/sidebar/settings/jobs code. Requirements: Partner Admin has full org control by default, but all capabilities are grantable by user/role/department/scope; member invite, roles, departments, permission preview, revoke, inactive, ownership transfer, audit; job creation workflow with structured JD capture, JD quality checks, preview as guest/student, quota/plan gate, moderation submit, approval/rejection, clone-from-performing-job, publication amendment policy; visual recruiting workflow builder with node palette, canvas, inspector, validation, dry run, immutable active versions, execution logs, failed-node recovery tasks; ATS pipeline with concurrency, scorecards, interviews, offers, rejections, withdrawals, bulk actions, SLA reminders; job analytics read models for impressions/views/saves/apply-starts/applications/source mix/conversion/sponsored attribution/quality buckets; employer CRM profile quality, verification, recruiter seats, campus relationship owner, event/campaign history, outcomes, risk/trust. Add tests and browser checks.
PROMPT
)"
```

## 8. University Governance, Career Services, Templates, Events, And Moderation

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Implement the university operations slice for E36 B-554 and related governance backlog. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md University sections, docs/API_CONTRACTS.md admin/moderation/events/templates/AI settings sections, docs/DATA_MODEL.md, docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md, docs/CV_STUDIO_SPEC.md, docs/DESIGN.md, docs/SYSTEM_ACCEPTANCE_BAR.md, .claude/agents/university-domain-agent.agent.md, .claude/rules/backend.md, and .claude/rules/frontend.md. Build or harden partner approval/trust level, job/event/ad moderation queues with status/SLA/assignee/reason/escalation/bulk action/audit, official CV template governance with publish/archive/version/review, notification template governance with variable validation and localized preview, student tier/eligibility policy, AI provider/policy visibility for admins only, reporting exports, audit review, incident/support view, career outcomes tracking. Add career-services workflows: counselor cohorts, at-risk students, CV review queue, appointment scheduling, employer relationship notes, intervention history, and outcome reporting. Service-layer RBAC must enforce university roles; do not hardcode staff role names. Add backend/frontend tests and browser verification.
PROMPT
)"
```

## 9. Discovery, Recommendations, Ads, Events, Seed/Crawl Data, And Read Models

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Implement E36 B-546/B-548/B-558 and public/student discovery quality. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md Discovery/Data sections, docs/DISCOVERY_RECOMMENDATION_ADS_SPEC.md, docs/API_CONTRACTS.md marketplace/recommendation/advertising/events sections, docs/DATA_MODEL.md, docs/BACKLOG.md, docs/SYSTEM_ACCEPTANCE_BAR.md, .claude/rules/backend.md, .claude/rules/frontend.md, and current backend scripts/seeds plus public frontend mega menu/jobs/events/company code. Requirements: separate organic/recommended/sponsored/university-curated inventory with mandatory sponsored labels; recommendation reason codes/source type/score bucket/fallback/session-vs-user signal boundary; privacy-safe guest personalization and logged-in personalization from saved jobs/CV fit/searches/apps/preferences; ads with placement/creative approval/targeting/impression/click/apply-start tracking/frequency caps/disclosure; events with capacity/waitlist/registration/check-in/reminders/follow-up; seed/crawl pipeline in backend/scripts/seeds with verified company profiles, accurate logos/media, cleaned jobs/events, linked taxonomy/location/salary/experience, sponsored/banner inventory, varied edge cases; read models with source events, refresh strategy, stale flags, fallback UI, reconciliation checks. Add tests and browser checks.
PROMPT
)"
```

## 10. Platform Support, Privacy/Compliance, Abuse Controls, QA, And Release Evidence

```bash
./.claude/bin/claude-code -p "$(cat <<'PROMPT'
Implement E36 B-555/B-556/B-557/B-550 as the final platform hardening and release-evidence slice. Read CLAUDE.md, docs/PRODUCT_REALITY_REBUILD_SPEC.md Platform Admin/Support/Compliance/Data/Frontend sections, docs/SECURITY_PRIVACY.md, docs/API_CONTRACTS.md support/admin/security/device/session sections, docs/DATA_MODEL.md, docs/TEST_STRATEGY.md, docs/SYSTEM_ACCEPTANCE_BAR.md, docs/IMPLEMENTATION_STATUS.md, .claude/rules/backend.md, .claude/rules/frontend.md, .claude/rules/testing.md, and current backend/frontend/admin/support/security code. Implement or harden platform support console: tenant/account lookup, verification state, outbox health, failed async recovery, moderation escalation, package override, safe support view, audited support actions; privacy/compliance: consent capture, data export, retention/deletion policy, CV/application snapshot retention, notification preferences, student-visible security history; abuse/fraud: suspicious company/job/application/message/ad creative reports, fraud-signal queues, manual escalation, safe appeal/override. Then run the release gate: backend pytest/ruff/mypy/migrations as available, frontend typecheck/build/lint, Playwright/browser screenshots for critical public/student/partner/university/auth flows, accessibility/focus checks, privacy boundary tests, AI eval smoke. Update docs/IMPLEMENTATION_STATUS.md with exact commands, pass/fail, verification tier, known gaps, and next owners.
PROMPT
)"
```
