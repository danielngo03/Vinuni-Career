---
name: vinuni-feature
description: Use for end-to-end VinUni feature work from scope resolution through implementation, tests, and handoff.
---

# VinUni Feature Workflow

Use this skill when the user asks to design, build, modify, or review a product feature in the greenfield VinUni Career Platform.

## Tiny Patch Bypass

If the request is a small localized change, do **not** run the full feature
workflow. Switch to Tiny Patch behavior from `.claude/commands/tiny-patch.md`.

Signals:

- user says tiny, micro, small, quick, localized, only this file, or 1-3 files;
- exact files are named;
- no new API/data/security/product scope is needed;
- change is a copy/icon/layout/helper tweak.

Tiny Patch means: no subagents, no PRD/BACKLOG/ROADMAP read, no status/run-state
update, no frontend-design, smallest safe edit, cheapest relevant check only.

## Required Inputs

- User feature request.
- Relevant backlog/story ID if provided.
- Current constraints from `CLAUDE.md`.

## Workflow

1. Scope
   - Read `CLAUDE.md`.
   - Read only relevant sections of `docs/PRODUCT_REQUIREMENTS.md`,
     `docs/PRODUCT_REALITY_REBUILD_SPEC.md`, feature-specific docs such as
     `docs/CV_STUDIO_SPEC.md`, `docs/BACKLOG.md`, and `docs/ROADMAP.md`.
   - If the feature is not in the product docs, stop and ask whether to add/clarify docs first.

2. Routing
   - Use `docs/TASK_ROUTING.md`.
   - Main session orchestrates; subagents report back with handoff packets.
   - Do not assume subagents talk directly unless Agent Teams are explicitly enabled.

3. Contracts
   - Backend/API: read `docs/API_CONTRACTS.md`, `docs/DATA_MODEL.md`, `docs/SECURITY_PRIVACY.md`, `.claude/rules/backend.md`.
   - Frontend/UI: read `docs/DESIGN.md`, `docs/SCREEN_SPECS.md`, `docs/API_CONTRACTS.md`, `.claude/rules/frontend.md`.
   - AI: read `docs/AI_PRODUCT_SPEC.md`, `.claude/rules/ai.md`.
   - Local/env/runtime: read `docs/ENVIRONMENT.md` and `docs/LOCAL_DEV_STACK.md`.
   - Notifications/account/email templates: read `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`.
   - Edge/failure modes: read `docs/EDGE_CASES_FAILURE_MODES.md`.
   - Testing: read `docs/TEST_STRATEGY.md`, `.claude/rules/testing.md`.
   - System acceptance: read `docs/SYSTEM_ACCEPTANCE_BAR.md` before finalizing
     scope, especially for multi-surface or AI/data/security features.
   - Experience contract: define the persona, primary job-to-be-done, first
     screenful, primary queue/list/editor/pipeline, next actions, empty/error
     states, and browser verification required before implementation.

4. Plan
   - For non-trivial work, produce a concrete plan before implementation.
   - Define owned files/modules, API/data contracts, permissions, tests, and open questions.
   - Define UI/UX acceptance criteria for every touched persona surface. Backend
     correctness is not enough for feature completion.
   - Check adjacent flows from `docs/PRODUCT_REALITY_REBUILD_SPEC.md` before
     coding. If a requested UI change also requires auth, onboarding, backend,
     AI, seed data, notification, quota, or analytics changes to be real, add
     those contracts or route to product/architecture first.
   - Challenge weak, unsafe, or inconsistent requirements and propose a safer
     alternative before coding.
   - Parallelize only after API/data contracts are stable and file ownership is disjoint.

5. Implement
   - Follow greenfield naming from `CLAUDE.md`.
   - If `backend/` or `frontend/` are absent, scaffold them from docs. If they exist, build on the current implementation only.
   - Do not use pre-reset code, old git history, or remembered implementation status as foundation unless the user explicitly asks to inspect it.
   - Low-risk improvements to clean code, UX clarity, edge handling, or tests are
     allowed when they stay in scope and are reported in the handoff.
   - Every write path needs RBAC, audit, tenant isolation, and error handling.
   - Sponsored labels and AI confirmation rules are non-negotiable.

6. Verify
   - Run the narrowest meaningful tests/checks available.
   - Report commands run, failures, unrun checks, residual risks, and next agent if needed.

## Output Contract

```markdown
## Handoff
**Goal:** ...
**Source docs read:** ...
**Decisions:** ...
**Contracts:** ...
**Owned files/modules:** ...
**Tests:** ...
**Risks:** ...
**Open questions:** ...
**Next agent:** ...
```
