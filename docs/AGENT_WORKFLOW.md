# Agent Workflow — VinUni Career Platform

> Phiên bản: 5.0 | Cập nhật: 26/06/2026  
> Canonical routing details live in `docs/TASK_ROUTING.md`.

---

## 1. Default Workflow

```text
Explore docs/code references
  -> Plan and resolve scope/contracts
  -> Implement within owned files
  -> Test and verify
  -> Summarize with handoff packet
```

For large features, Claude Code should explicitly plan before implementation. If `backend/` and `frontend/` are absent, scaffold them from docs; if present, treat them as the current implementation. Ignore pre-reset history unless the user explicitly asks.

---

## 2. Team Behavior And Challenge Protocol

Subagents should behave like a real product/engineering team, not like passive
task executors.

- If a request is unclear, weak, risky, or conflicts with product/security/data
  integrity, the responsible agent must say so and propose a better path.
- `product-owner-system-planner` owns value, scope, priority, and acceptance
  criteria; it may reject or reframe feature ideas that do not fit the platform.
- `system-architect` owns boundaries, data/API contracts, scalability, and ADRs;
  it may block implementation until contracts are stable.
- Domain agents own persona realism and edge cases; they may reject generic
  dashboards or flows that do not match real student/partner/university work.
- Implementation agents own quality and maintainability; they may make low-risk
  cleanup or robustness improvements when they stay in scope.
- `tester-qa` owns release gates and may refuse completion even when code is
  green if product, security, AI, data, or UX acceptance is incomplete.

Use `docs/SYSTEM_ACCEPTANCE_BAR.md` as the shared definition of done.

---

## 3. Project Lifecycle Loop

For long autonomous builds, every meaningful slice should pass this loop:

1. Discover
   - Read the minimum source docs for the slice.
   - Inspect current code/status instead of trusting prior claims.
   - Identify persona, job-to-be-done, and current blocker.

2. Challenge
   - Reject or reframe weak, unsafe, generic, or product-incoherent requests.
   - Surface missing features, edge cases, admin settings, notification needs,
     audit needs, and AI risks that the user may not have named.

3. Contract
   - Define API/data/event/read-model/UI/permission/test contracts before large
     implementation.
   - Update docs/ADR when contracts materially change.

4. Build
   - Implement in small vertical slices.
   - Allow low-risk improvements that clearly improve product quality,
     maintainability, security, or UX within the current phase.

5. Verify
   - Run code, tests, and browser checks appropriate to the slice.
   - Use `docs/SYSTEM_ACCEPTANCE_BAR.md`, not only compiler/test success.

6. Status And Retro
   - Update `docs/IMPLEMENTATION_STATUS.md` with verified facts only.
   - Record important gaps, follow-up slices, and any product/architecture
     correction discovered while building.

### 3.1 Build Burst Variant

Use when the user explicitly wants faster throughput or an overnight batch.
Build Burst is faster, not less accountable:

- Plan 2-4 related slices as one coherent batch.
- Maintain `.claude/run-state.md` with docs read, decisions, files touched,
  cheap checks, and deferred gates.
- Prefer the main conversation for implementation because it preserves shared
  context and reduces repeated file reads.
- Use subagents only for independent review/spec risks.
- Run cheap/targeted checks after each slice.
- Defer full suites/browser/E2E to a checkpoint.
- Do not update status to `complete`, `browser verified`, or `E2E verified`
  until checkpoint gates actually run.

---

## 4. New Feature Workflow

1. `product-owner-system-planner`
   - Confirm backlog/phase/success criteria.
   - Define in-scope and out-of-scope.

2. Domain agent
   - Student, employer, or university agent reviews journey, policy, and edge cases.

3. `system-architect`
   - Define module boundaries, API/data/event contracts, invariants, and ADR if needed.

4. Implementation agents
   - `backend-developer` implements backend after contracts are stable.
   - `frontend-developer` implements frontend after API/data states are stable.
   - `ai-engineer` owns prompt/tool/eval/safety when AI is involved.
   - `data-engineer` owns projections/events/exports when reporting is involved.

5. `tester-qa`
   - Validates acceptance criteria, security/RBAC, regression risk, and release gate.

6. Main Claude session
   - Synthesizes results and reports final state to user.

---

## 5. AI Feature Workflow

1. `product-owner-system-planner`: scope and user value.
2. `ai-engineer`: task matrix, tool permission class, prompt, eval, fallback, rollback.
3. Relevant domain agent: UX and policy review.
4. `system-architect`: session, streaming, tool execution, data access boundaries.
5. `backend-developer`: `ai_assistant` API/tool execution/audit.
6. `frontend-developer`: chat/tool cards/confirmation UX.
7. `ai-engineer`: final AI safety review.
8. `tester-qa`: leakage, adversarial, confirmation, fallback tests.

---

## 6. Bug Fix Workflow

1. Responsible implementation agent reproduces and identifies root cause.
2. Fix is scoped to the smallest safe file set.
3. `tester-qa` adds or reviews regression coverage.
4. Main session reports commands run and residual risk.

---

## 7. Review Workflow

For review requests, lead with findings:

1. Severity-ordered issues with file/line references where applicable.
2. Missing tests or quality gates.
3. Open questions/assumptions.
4. Brief summary.

Use specialist reviewers in parallel only when review lenses are independent.

## 7.1 Paused Build / Review Snapshot Workflow

Use this when the user stops Claude because the implementation feels wrong,
`IMPLEMENTATION_STATUS.md` may be over-claiming completion, or UI/product intent
has drifted.

1. Main orchestrator runs `/review-snapshot`.
2. `product-owner-system-planner` checks product fit, phase scope, and missing
   workflows.
3. Relevant domain agents review the student/employer/university journey.
4. `system-architect` checks module boundaries, data/API contracts, and whether
   backend/frontend can continue safely.
5. `frontend-developer` + `tester-qa` review UI/UX against `DESIGN.md`,
   `UI_QUALITY_BAR.md`, `SCREEN_SPECS.md`, and browser evidence.
6. `ai-engineer` reviews AI workflows, confirmations, eval/fallback, and
   provider secrecy where AI is involved.
7. Main orchestrator updates status/docs if stale and produces the exact next
   build prompt.

No app code should be changed during this workflow unless the user explicitly
switches from review to implementation.

---

## 8. Agent Teams Optional Mode

Default subagents report to the main session only. Use Agent Teams only when explicitly enabled and useful for independent teammates that must coordinate.

Good Agent Team use cases:

- Parallel review: security, performance, test coverage.
- Cross-layer feature with disjoint owned files.
- Competing root-cause investigations.

Bad Agent Team use cases:

- Small bug fixes.
- Same-file edits.
- Unresolved architecture or product scope.

---

## 9. Required Handoff Packet

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
