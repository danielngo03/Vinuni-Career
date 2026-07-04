# System Acceptance Bar — VinUni Career Platform

> Cross-functional release bar for a large, realistic product. Use with
> `PRODUCT_REQUIREMENTS.md`, `PRODUCT_REALITY_REBUILD_SPEC.md`,
> `ARCHITECTURE.md`, `API_CONTRACTS.md`, `DATA_MODEL.md`,
> `AI_PRODUCT_SPEC.md`, `DESIGN.md`, `UI_QUALITY_BAR.md`, and
> `TEST_STRATEGY.md`.

## 1. Purpose

A slice is not complete just because code compiles or an endpoint exists. It is
complete only when product value, business rules, backend correctness, data
integrity, AI safety, frontend experience, security, and verification all pass.

This file is the final cross-functional gate before updating
`docs/IMPLEMENTATION_STATUS.md`.

## 2. Required Slice Contract

Before implementation, define:

- Persona and real job-to-be-done.
- Business outcome and acceptance criteria.
- In-scope and out-of-scope behavior.
- API/data/event contracts.
- Permission/RBAC and tenant boundaries.
- UI surface and first-screen experience.
- AI permission class, eval, fallback, and rollback when AI is involved.
- Data model/read-model/projection ownership.
- Edge cases from `EDGE_CASES_FAILURE_MODES.md`.
- Test and browser verification plan.
- Adjacent-flow impact from `PRODUCT_REALITY_REBUILD_SPEC.md`: auth,
  onboarding, notifications, audit, billing/quota, seed/data quality, AI,
  analytics, support, compliance/privacy, abuse/fraud, read models, application
  snapshots, and admin governance where relevant.

If this contract cannot be defined, route to `product-owner-system-planner` and
`system-architect` before coding.

## 3. Product And Business Gate

- Solves a real VinUni student, partner, university, or public workflow.
- Does not create generic SaaS filler or dead-end navigation.
- Has clear next actions, recovery paths, and business logic for real-world
  cases.
- Passes the cross-system realism checklist in
  `docs/PRODUCT_REALITY_REBUILD_SPEC.md`; an isolated UI or API endpoint is not
  complete when required adjacent flows are missing.
- Features that change student submissions, partner decisions, university
  moderation, recommendations, analytics, or AI outputs must define snapshot,
  audit, privacy, stale-data, and rollback behavior.
- Student CV workflows are CV-first: upload, template library, duplicate, raw
  notes, AI draft/fill, OCR/review, active CV quota, and CV-to-job recommendation
  must work without forcing a long profile form first.
- Honors package/quota, moderation, payments, ads, events, notifications, and
  tier rules where relevant.
- Adds new features only when they fit the PRD/roadmap or are explicitly
  proposed and accepted by the product-owner agent.

Before coding a non-trivial slice, run a short product gap review:

- What is the user's next action, and what happens after success/failure?
- What data is missing, stale, pending approval, or blocked by permission?
- What notifications, settings, audit records, admin configuration, or template
  content must exist for this to work in a real school environment?
- What should be self-serve, what needs staff approval, and what needs human
  override?
- Where can AI reduce work, and where would AI add risk or unnecessary cost?
- What low-risk improvement can be included now without expanding the phase?

## 4. Backend And Architecture Gate

- Module boundaries match `ARCHITECTURE.md`.
- Business logic lives in services/domain, not routers.
- RBAC, tenant isolation, audit, idempotency, optimistic concurrency, and
  user-safe errors are implemented for writes.
- Migrations have upgrade and downgrade.
- Cross-module reads use APIs, interfaces, events, or read models, not ad hoc
  deep imports.
- Dashboards and high-volume lists use projections/read models, not heavy live
  multi-domain joins.

## 5. Data Gate

- Canonical entities, ownership, soft delete, audit fields, and projections are
  clear.
- Public projections hide private/internal fields.
- Partner/university/student data never crosses tenant/persona boundaries.
- Analytics and logs are metadata-only; no raw CV, prompt, PII, or secret data.
- Read models have refresh strategy, staleness expectation, and failure behavior.

## 6. Frontend And UX Gate

- UI surface is persona-specific:
  - Public marketplace.
  - Student signed-in marketplace / career command center.
  - Partner recruiting operations.
  - University operations center.
- Shell/navigation matches persona: public and student use marketplace top-nav
  patterns; partner/university use ops sidebar + topbar when dense workflows
  require it.
- First screenful shows real work: queues, next actions, filters, lists,
  editors, pipelines, alerts, or review tasks.
- Student CV surfaces show a CV library/template marketplace, active CV quota,
  upload/import states, and job-fit actions; profile forms are secondary settings
  surfaces, not the primary CV onboarding path.
- Loading, empty, error, permission, offline, conflict, and success states exist.
- No fake stats, fake logos, generic dashboard cards, or placeholder routes
  marked complete.
- Responsive/browser reviewed at 375, 768, 1024, and 1440 px for major surfaces.
- vi/en copy is i18n-backed and does not hardcode user-facing text.
- Public marketplace, header/mega-menu, hero, and persona dashboards are
  compared against `docs/DESIGN_EXAMPLE.png` (structural composition) and
  `docs/SCREEN_SPECS.md`. Real organization logos/media and `frontend/public`
  imagery are wired (via the `logo_url`/media-URL contract) — initials-only
  avatars and flat placeholder bands are an empty/loading state, not the
  primary presentation a surface ships with.

## 7. AI Gate

- AI solves workflow pain, not decoration.
- Every AI task has permission class, tool registry entry, prompt version, eval
  dataset, fallback, rollback, and cost estimate.
- Mutating tools require explicit confirmation and normal service/RBAC path.
- Provider/model/token/prompt/latency/confidence internals never reach end users.
- AI never invents CV facts or finalizes moderation/fraud/approval decisions.
- CV/job matching explains a user-facing 0-100 product score with evidence and
  gaps, while hiding raw confidence, embedding, provider, prompt, and token
  internals.
- Real model calls are opt-in, capped, and low-cost/free aliases first.

## 8. Security And Privacy Gate

- Refresh/session handling uses secure httpOnly cookie strategy where applicable;
  secrets are never stored in frontend localStorage.
- TOTP/2FA is either fully enforced and encrypted at rest or not advertised as
  active protection.
- PII, CV text, raw prompts, storage paths, and internal parser/provider errors
  are not logged or exposed.
- Sponsored/ad content always has non-removable disclosure.
- File downloads use signed URLs; partner CV downloads are watermarked and
  audited.

## 9. Verification Gate

Minimum before status update:

- Backend tests/lint/type checks and migration checks where relevant.
- Frontend typecheck/lint/build and browser verification for non-trivial UI.
- E2E for core persona workflows before claiming E2E verified.
- AI eval/adversarial/provider-leakage tests for AI features.
- Security/RBAC/cross-tenant/audit tests for sensitive features.
- For public marketplace / persona dashboard redesigns, the browser pass records
  whether it is **functional-only** (renders, flows work, console clean) or
  **visual-design verified** (composition compared against
  `docs/DESIGN_EXAMPLE.png`, real logos/media present) — `browser verified`
  alone never implies design-matched.
- `IMPLEMENTATION_STATUS.md` distinguishes `implemented`, `API wired`,
  `browser verified` (and, for visual surfaces, `visual-design verified`), and
  `E2E verified`.

## 10. Autonomous Improvement Protocol

Claude and subagents should not blindly implement weak or risky requests.

- If a user request conflicts with product, security, architecture, or data
  integrity, stop and explain the conflict.
- If a better low-risk implementation is obvious, propose it and proceed when it
  stays within scope.
- If a useful new feature emerges during implementation, route it to
  `product-owner-system-planner` for scope and priority before building.
- If architecture/data/API shape changes, route to `system-architect` and update
  docs/ADR before coding.
- If UI/product experience feels weak, route through `vinuni-ui-polish`, the
  relevant domain agent, and `tester-qa`.
