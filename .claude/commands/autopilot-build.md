---
description: Run an overnight VinUni build loop with phase checkpoints, verification, and status updates
argument-hint: [optional focus, e.g. Phase 2 CV Studio + apply flow]
allowed-tools: Read, Edit, MultiEdit, Write, Bash, Glob, Grep, TodoWrite, Task
---

# VinUni Autopilot Build

Focus:

`$ARGUMENTS`

Run as the main orchestrator for a long autonomous build session. Keep working through the current roadmap until the requested focus is complete, all gates pass, or a true blocker requires human input.

## Operating Mode

- Default to **Fast Slice Mode** unless the user explicitly asks for a long
  exploratory build. A slice should target one vertical outcome, usually
  60-90 minutes of work: one API contract + one implementation surface + focused
  tests, not the whole platform.
- If the user asks for faster throughput, "build more before testing", or an
  overnight run with fewer interruptions, switch to **Build Burst Mode**:
  implement 2-4 related slices as one coherent batch, run cheap/targeted checks
  during the burst, and defer full suites/browser/E2E to the checkpoint. Never
  mark a slice `browser verified` or `E2E verified` until the deferred gates
  actually run.
- If the requested focus is broad ("make the project better", "build everything",
  "large recruiting platform"), first run a slicing review and return 2-4 small
  build prompts. Prefer `/product-reality-audit` when the risk is product,
  business logic, AI usefulness, or persona UX. Do not start a multi-hour
  implementation from a vague scope.
- Treat absent `backend/` and `frontend/` as intentional clean-slate state; scaffold them from docs. If they exist, treat them as the current implementation.
- If `backend/` or `frontend/` contain only `.env` / `.env.example`, treat them as env seeds and scaffold code around them without deleting local env files.
- Use root `CLAUDE.md` as the canonical operating guide.
- Follow the project lifecycle loop in `docs/AGENT_WORKFLOW.md`: discover,
  challenge, contract, build, verify, then status/retro.
- If `docs/IMPLEMENTATION_STATUS.md` contains a human review checkpoint,
  suspected product/UI drift, or over-claimed completion, stop normal build
  flow and run `/review-snapshot` first. Continue implementation only after the
  review produces a prioritized fix plan.
- If the focus mentions Visual/Product Rescue, pause new phase expansion until
  the public marketplace and persona dashboards satisfy `docs/DESIGN.md`
  §6.3, `docs/UI_QUALITY_BAR.md`, `docs/SCREEN_SPECS.md`, and
  `docs/DESIGN_EXAMPLE.png` structural comparison.
- Read only the docs needed for the current batch, but always start with:
  - `docs/IMPLEMENTATION_STATUS.md`
  - `docs/IMPLEMENTATION_PLAN.md`
  - `docs/ROADMAP.md`
  - `docs/BACKLOG.md`
  - `docs/TASK_ROUTING.md`
  - `docs/SYSTEM_ACCEPTANCE_BAR.md`
  - `docs/LOCAL_DEV_STACK.md`
  - `docs/ENVIRONMENT.md`
  - `docs/EDGE_CASES_FAILURE_MODES.md`
- Do not repeatedly reread unrelated long docs in the same slice. Read
  feature-specific sections with search/anchors, then cache the local decisions
  in the TodoWrite plan and handoff notes.
- For long sessions, maintain `.claude/run-state.md` as a short working cache:
  docs/sections read, decisions made, files touched, checks run, and deferred
  gates. Check it before rereading long docs. Reread a full doc only when the
  section was not summarized, the file changed, or the decision is high risk.
- Prefer main-conversation work when latency matters and context is shared.
  Subagents are useful for independent reviews, but they start with isolated
  context and may need to gather files again.
- For frontend/UI work, also read:
  - `docs/DESIGN.md`
  - `docs/DESIGN_EXAMPLE.png` when touching public marketplace/header/homepage
    or judging whether the public surface looks like a real recruiting product
  - `docs/UI_QUALITY_BAR.md`
  - `docs/SCREEN_SPECS.md`
- For CV, AI, security, data, API, or test work, read the matching source-of-truth docs before editing.
- For notification, email, account settings, device/session, or template work, read `docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`.
- Scaffold local-first app run commands; Docker is optional infrastructure only unless explicitly requested.
- Keep root `.env` for AI hook logging only; put backend env in `backend/.env` and frontend env in `frontend/.env`.
- Every completed feature must include invalid input, empty state, duplicate/idempotent retry, permission, concurrency, async failure, and AI/provider failure handling where relevant.
- Every frontend slice must name the persona surface it improves and satisfy the
  relevant public/student/partner/university experience contract before coding.
- Claude may propose and implement low-risk improvements that clearly strengthen
  product quality, clean code, UX, security, or maintainability and stay within
  the documented scope. Route bigger product changes through
  `product-owner-system-planner`; route architecture/data changes through
  `system-architect`.
- When a missing feature or weak business flow appears during implementation,
  run the Product Gap Review path in `docs/TASK_ROUTING.md` before expanding
  scope.
- For student/CV work, enforce the CV-first rule from `docs/CV_STUDIO_SPEC.md`:
  upload/template/raw-notes/AI/duplicate/job-fit flows must work without a
  mandatory profile form; active CV quota and CV-to-job recommendation are part
  of the product contract.
- If the user's requested approach is weak, unsafe, inconsistent, or likely to
  hurt product quality, challenge it with a short reason and safer alternative
  instead of blindly implementing.

## Loop

Repeat this loop until done:

1. Inspect verified status and identify the highest-priority incomplete slice.
2. If the status/user notes indicate implementation drift, run a review snapshot
   and update the fix plan before editing code.
3. Route through `docs/TASK_ROUTING.md`.
4. Use project skills when relevant. Keep subagent fan-out proportional to risk:
   one owner + one reviewer for ordinary slices; full PO/architect/domain/QA
   routing only for cross-domain, AI, security, data-model, or Visual/Product
   Rescue work.
   - `vinuni-feature` for feature work.
   - `vinuni-ui-polish` for UI quality.
   - `vinuni-ai-product` for AI workflows.
   - `vinuni-security-review` for RBAC/privacy/safety.
   - `vinuni-test-gate` for test coverage and release gates.
   - `vinuni-status` after verification.
5. Create or update a TodoWrite plan for the current slice and `.claude/run-state.md`
   for long/burst sessions.
6. Implement backend, frontend, tests, and docs needed for that slice.
7. Run targeted verification first. In Build Burst Mode, run cheap checks per
   slice and full suites/builds/browser checks at the batch checkpoint. Outside
   burst mode, run full gates when shared contracts, migrations, auth/RBAC, or
   major UI flows changed.
8. Fix failures before moving on.
9. Update `docs/IMPLEMENTATION_STATUS.md` with verified facts only.
10. Continue to the next highest-priority slice.

## Quality Gates

Before marking any slice complete:

- Backend gates should include focused tests for touched modules first; add
  migration check, lint, type checks, and wider tests when shared code/contracts
  changed.
- Frontend gates should include targeted type/lint/build checks for touched
  surfaces; add responsive/browser QA for non-trivial UI, and no fake placeholder
  dashboards.
- Frontend gates must include persona workflow review: public marketplace,
  student command center, partner recruiting ops, or university operations
  center. Passing typecheck/build is not enough.
- Visual/Product Rescue gates must include screenshots or browser inspection of
  `/vi`, `/vi/jobs`, `/vi/companies`, `/vi/student/dashboard`,
  `/vi/partner/dashboard`, and `/vi/university/dashboard` at 375, 768, 1024,
  and 1440 px after a fresh backend/frontend restart. If screenshots cannot be
  captured, status must say "not browser verified".
- AI gates should include provider/model secrecy, confirmation for write actions, fallback behavior, and eval notes.
- Real AI calls should use low-cost/free aliases first and only after offline/unit checks pass.
- Security gates should include RBAC at service layer, PII-safe logs, signed file access where relevant, and audit events for sensitive writes.
- System gates must pass `docs/SYSTEM_ACCEPTANCE_BAR.md`; do not mark locally
  green code complete if product, data, AI, security, or UX gates are still open.
- Status must distinguish `implemented`, `API wired`, `browser verified`, and `E2E verified`.

## Fast Slice Output

At the end of each slice, report:

- Slice goal completed or blocked.
- Files changed.
- Targeted checks run and result.
- Full gates intentionally skipped, with reason.
- Product/AI/business gaps discovered but deferred.
- Exact next slice prompt.

## Stop Rules

Do not stop for routine choices. Make a reasonable implementation decision using the docs and record it in the status notes.

Stop only when:

- A required external secret/account/credential is missing.
- A production deploy, production data mutation, or force-push would be required.
- A destructive action is required and blocked by project deny rules.
- Source-of-truth docs conflict in a way that would materially change product scope or security posture.

When stopping, write a concise blocker report with:

- Current slice.
- Work completed.
- Commands run.
- Exact blocker.
- Safest next command or user decision needed.
