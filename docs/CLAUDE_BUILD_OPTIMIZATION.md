# Claude Build Optimization — VinUni Career Platform

> Purpose: make Claude Code faster without turning the project into unverified
> code. Use with `.claude/commands/build-burst.md`,
> `.claude/commands/autopilot-build.md`, and `docs/TEST_STRATEGY.md`.

## 1. Why Claude Code Can Feel Slow

- It runs real shell commands, tests, builds, browser checks, and subagents.
- Subagents are useful reviewers, but each invocation starts with isolated
  context and may reread files unless the main orchestrator passes a precise
  handoff.
- Long docs are context-expensive. Keep `CLAUDE.md` concise and put detailed
  rules in path-scoped `.claude/rules/`, skills, and focused docs.
- Full test suites and browser screenshot matrices are expensive; running them
  after every small edit wastes time.

## 2. Recommended Build Modes

### Tiny Patch Mode

Use when the change is small and localized: copy tweak, icon swap, small layout
fix, one component bug, one helper bug, or a known-file patch.

Command:

```text
/tiny-patch <exact small change>
```

Rules:

- 1-3 files only by default.
- No subagents.
- No `frontend-design`.
- No product/architecture contract.
- No long docs unless the user explicitly asks for one exact section.
- No status/run-state updates.
- Cheapest relevant check only, usually `pnpm --dir frontend run typecheck` for
  frontend changes.

Use Tiny Patch instead of `/feature-vinuni` for small UI fixes. This avoids
pulling PRD/BACKLOG/ROADMAP/design/status context into trivial work.

### Review Mode

Use when product direction is unclear or implementation feels wrong.

Command:

```text
/product-reality-audit <focus>
```

No app code. Produces findings and fast-slice prompts.

### Fast Slice Mode

Use for normal feature work.

Command:

```text
/autopilot-build <one vertical slice>
```

One outcome, targeted checks, then status update.

### Build Burst Mode

Use when you want faster overnight progress.

Command:

```text
/build-burst <2-4 related slices>
```

Builds a coherent batch. Runs cheap checks during the batch and defers full
backend suite, full frontend build, browser matrix, and E2E until the checkpoint.

Do not claim `browser verified`, `E2E verified`, or phase complete until the
checkpoint gates actually run.

### Overnight Burst Loop

Use when you want Claude to continue through multiple bursts unattended.

Command:

```text
/overnight-burst-loop <focus>
```

This repeats: choose batch -> build burst -> checkpoint gates -> fix failures ->
status update -> next batch. It still stops for true blockers, missing secrets,
destructive actions, or source-of-truth conflicts.

When several next modules are valid, Claude should choose automatically instead
of asking for steering. Default order after explicit user focus:

1. Verification debt for already-built core flows.
2. Recruitment pipeline/interviews/scorecards/offers.
3. Events.
4. Advertising/sponsored discovery.
5. AI cost infra/real-provider enablement only when env keys are present or the
   user explicitly asks to spend credits.
6. RAG/semantic features only after pgvector or a local fallback is available.

Do not open a steering prompt for ordinary next-batch choice. If the highest
priority batch is blocked by a non-critical external resource, record the
blocked verification debt and continue to the next unblocked batch. For browser
verification, try Chrome DevTools MCP, installed Chrome/Chromium, or existing
Playwright cache first; if a new browser download needs approval, defer that
matrix and keep building.

A clean checkpoint is not a stop condition. After a green checkpoint, Claude
should update `IMPLEMENTATION_STATUS.md` and `.claude/run-state.md`, choose the
next batch, and continue. If context is deep, summarize into `.claude/run-state.md`
and proceed with targeted reads instead of pausing to "start fresh".

### Release Gate Mode

Use after a burst or before marking a phase complete.

Command:

```text
/autopilot-build Verification checkpoint only for <batch>
```

Runs full gates and fixes failures.

## 3. Context And Memory Strategy

Use `.claude/run-state.md` as an ephemeral working cache during long sessions.

The file should contain:

- current batch goal;
- docs and exact sections already read;
- product/API/data decisions already made;
- owned files touched;
- cheap checks already run;
- full gates deferred;
- next checkpoint.

Rules:

- Before rereading a long doc, check `.claude/run-state.md`.
- Use `Grep`/section reads instead of full-file reads when possible.
- Reread the full doc only if it changed, the run-state is missing the relevant
  section, or the decision affects security/data/contracts.
- Keep `.claude/run-state.md` short. It is a cache, not another PRD.

## 4. Subagent Strategy

Use the main conversation when:

- latency matters;
- implementation and test fixes share the same context;
- the change is small or medium;
- multiple phases reuse the same docs/files.

Use subagents when:

- review lenses are independent;
- output can be summarized;
- the agent has tool restrictions that improve safety;
- the task is self-contained.

For ordinary build slices, use at most one owner and one reviewer. Save full
PO/architect/domain/AI/QA routing for cross-domain, AI, security, data-model, or
Visual/Product Rescue work.

## 5. Test Cadence

During implementation:

- Run cheap checks close to edits.
- Run focused tests for changed modules.
- Run type/lint/build only when the edited layer needs it or at checkpoints.
- Run browser matrix only for real UI checkpoint, not every component tweak.

At checkpoint:

- backend tests/lint/type/migrations as relevant;
- frontend typecheck/lint/build;
- browser screenshots for major surfaces;
- E2E for critical persona loops;
- update `docs/IMPLEMENTATION_STATUS.md` with verified facts only.

## 6. Fast Overnight Prompt Pattern

Fast overnight is for speed with checkpoint safety. It should not behave like a
fresh product-planning session after every slice.

Required constraints:

- Prefer the main conversation. Use subagents only for independent security,
  data, architecture, AI, or product-risk review.
- Do not reread long docs. Check `.claude/run-state.md` first, then use targeted
  `Grep`/section reads.
- Keep `.claude/run-state.md` under 250 lines. Keep only current batch, decisions,
  files touched, checks, blockers, and next action.
- Build 3-6 related slices per checkpoint when they belong to one area.
- Run cheap checks per slice.
- Run full backend suite, full frontend build, browser matrix, and E2E only at
  checkpoints or before claiming verified completion.
- Do not update `docs/IMPLEMENTATION_STATUS.md` after every tiny slice; update it
  once per checkpoint with verified facts only.
- Do not invoke `frontend-design` unless the current batch is explicitly a major
  visual redesign or `globals.css` theme work.
- If visual QA is not the batch goal, skip browser screenshots and record the
  verification debt.

```text
/build-burst Overnight Build Burst: <focus>. Build 2-4 related slices before
full gates. Maintain .claude/run-state.md. Use main conversation unless a
reviewer is clearly needed. Run cheap targeted checks after each slice. Defer
full backend suite, frontend build, browser matrix, and E2E to the checkpoint.
Do not mark browser/E2E/phase complete until checkpoint gates run.
```

For unattended work:

```text
/overnight-burst-loop <focus>. Maintain .claude/run-state.md, reuse summarized
context, build 2-4 related slices per batch, run checkpoint gates after each
batch, fix failures, update IMPLEMENTATION_STATUS, then continue to the next
highest-priority batch until blocked or the roadmap focus is complete.
```
