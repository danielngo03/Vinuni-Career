---
description: Build a larger VinUni batch faster by deferring expensive gates to checkpoints while keeping cheap safety checks
argument-hint: [focused batch, e.g. CV-first student flow + job-fit + apply polish]
allowed-tools: Read, Edit, MultiEdit, Write, Bash, Glob, Grep, TodoWrite, Task
---

# VinUni Build Burst

Focus:

`$ARGUMENTS`

Use this when the user wants faster implementation than `/autopilot-build` and
accepts checkpoint testing instead of full tests after every small edit.

## Operating Mode

- Build one coherent product batch, usually 2-4 related vertical slices.
- Do not expand into the whole platform. If the focus is vague, first produce a
  2-4 item burst plan and start only the first coherent batch.
- Prefer the main conversation for latency-sensitive work. Use subagents only
  for review/spec of independent risks, because subagents start fresh and may
  need to reread context.
- Keep a run-state note in `.claude/run-state.md` during the session:
  - current batch goal;
  - docs/sections already read;
  - contracts decided;
  - files touched;
  - cheap checks already run;
  - deferred full gates;
  - next checkpoint.
- Keep `.claude/run-state.md` under 250 lines. It is a working cache, not a full
  status log.
- Before rereading a long doc, check `.claude/run-state.md` and use `Grep` for
  the exact section needed. Reread the whole file only if the run-state is stale,
  the file changed, or the task depends on details not summarized there.
- Prefer main conversation. Use subagents only for independent review/spec risks.
- Do not update `docs/IMPLEMENTATION_STATUS.md` after each slice; update it once
  at the checkpoint with verified facts only.

## Test Cadence

During the burst:

- Run cheap checks close to edits:
  - type/lint for touched package when fast enough;
  - focused backend tests for changed services;
  - targeted component/page build checks;
  - simple smoke commands after API/schema boundaries.
- Defer expensive gates until checkpoint:
  - full backend suite;
  - full frontend build if many UI files are still moving;
  - full browser screenshot matrix;
  - full E2E.
- If a slice shrinks to 1-3 localized files, switch to Tiny Patch behavior for
  that slice: no broad docs, no subagents, cheapest check only.
- Do not mark any slice `complete`, `browser verified`, or `E2E verified` until
  the checkpoint gates actually run.
- If a cheap check fails, fix immediately before piling more code on top.

## Loop

1. Read `CLAUDE.md`, `.claude/run-state.md` if present, and the minimum docs for
   the current batch.
2. Produce a burst plan with 2-4 slices, owned files, cheap checks, and final
   checkpoint gates.
3. Implement slice 1.
4. Run cheap checks for slice 1.
5. Update `.claude/run-state.md`.
6. Repeat for the next slice in the batch.
7. Run checkpoint gates.
8. Update `docs/IMPLEMENTATION_STATUS.md` with verified facts only.

## Stop Rules

Stop the burst and report when:

- A contract conflict would cause rework across backend/frontend/data.
- A cheap check fails repeatedly and blocks safe continuation.
- A secret/account/external service is required.
- A destructive action, deploy, force push, or production mutation would be
  required.

## Output

At the end, report:

- Batch completed or blocked.
- Files changed.
- Cheap checks run during the burst.
- Checkpoint gates run or deferred.
- Known risk from deferred tests.
- Next exact command.
